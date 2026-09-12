import os
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
SCHEDULE_URL = os.getenv("SCHEDULE_URL", "https://raw.githubusercontent.com/username/repo/main/schedule.json")

EKAT_TZ = timezone(timedelta(hours=5))
notified_events_today = set()
last_reset_day = None

# Веб-сервер для Render (обязательно слушает порт из переменной окружения PORT)
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running and healthy!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    print(f"Веб-сервер запущен на порту {port}")
    server.serve_forever()

def get_schedule():
    try:
        url = f"{SCHEDULE_URL}?t={int(time.time())}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Ошибка получения JSON: {e}")
    return []

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

def check_lessons():
    global last_reset_day, notified_events_today

    now_ekat = datetime.now(EKAT_TZ)
    current_day_idx = now_ekat.weekday()

    if last_reset_day != current_day_idx:
        notified_events_today.clear()
        last_reset_day = current_day_idx

    events = get_schedule()
    if not events:
        return

    cur_mins = now_ekat.hour * 60 + now_ekat.minute

    for ev in events:
        if ev.get('weekOffset', 0) != 0 or ev.get('day') != current_day_idx or ev.get('isDone', False):
            continue

        time_str = ev.get('timeStr', '')
        if not time_str or "Асинхронно" in time_str:
            continue

        try:
            start_part = time_str.split('-')[0].split('–')[0].strip()
            start_h, start_m = map(int, start_part.split(':'))
            start_mins = start_h * 60 + start_m
        except Exception:
            continue

        diff = start_mins - cur_mins
        event_id = ev.get('id')

        # Уведомление за 10 минут
        if 0 < diff <= 10 and event_id not in notified_events_today:
            notified_events_today.add(event_id)

            msg = f"🔔 <b>Скоро пара (через {diff} мин)!</b>\n\n"
            msg += f"📚 <b>{ev.get('subject', 'Занятие')}</b>\n"
            msg += f"⏰ Время: {time_str}\n"
            if ev.get('location'): msg += f"📍 Ауд.: {ev['location']}\n"
            if ev.get('teacher'): msg += f"👤 Преп.: {ev['teacher']}\n"
            if ev.get('homework'): msg += f"📝 ДЗ: {ev['homework']}\n"
            if ev.get('link'): msg += f"\n🔗 <a href=\"{ev['link']}\">Ссылка на занятие</a>"

            send_telegram(msg)

def loop_checker():
    send_telegram("🚀 <b>Бот успешно запущен!</b>")
    while True:
        try:
            check_lessons()
        except Exception as e:
            print(f"Ошибка в цикле проверки: {e}")
        time.sleep(30)

if __name__ == "__main__":
    # Запускаем проверку расписания в отдельном фоне
    checker_thread = threading.Thread(target=loop_checker, daemon=True)
    checker_thread.start()
    
    # Запускаем веб-сервер в основном потоке ( Render увидит открытый порт )
    run_web_server()

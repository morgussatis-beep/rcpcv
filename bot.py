import os
import re
import time
import html
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

class SimpleHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running and healthy!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

def get_schedule():
    try:
        url = f"{SCHEDULE_URL}?t={int(time.time())}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"[ERROR] Не удалось скачать schedule.json: статус {res.status_code}")
    except Exception as e:
        print(f"[ERROR] Сетевая ошибка при скачивании расписания: {e}")
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
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"[ERROR] Ошибка отправки в TG: {resp.status_code} {resp.text}")
        else:
            print("[SUCCESS] Сообщение успешно доставлено в Telegram!")
    except Exception as e:
        print(f"[ERROR] Ошибка подключения к Telegram: {e}")

def check_lessons():
    global last_reset_day, notified_events_today

    now_ekat = datetime.now(EKAT_TZ)
    current_day_idx = now_ekat.weekday()  # 0 = Пн, 6 = Вс

    # Сброс отправленных напоминаний в полночь
    if last_reset_day != current_day_idx:
        notified_events_today.clear()
        last_reset_day = current_day_idx

    events = get_schedule()
    if not events:
        return

    cur_mins = now_ekat.hour * 60 + now_ekat.minute

    for ev in events:
        # 1. Проверяем день недели (0 - Пн ... 6 - Вс)
        ev_day = ev.get('day')
        if ev_day is None or int(ev_day) != current_day_idx:
            continue

        # 2. Не учитываем уже завершенные
        if ev.get('isDone') is True:
            continue

        # 3. Проверка времени через регулярку
        time_str = ev.get('timeStr', '')
        if not time_str or "Асинхронно" in time_str or "Онлайн" in time_str:
            continue

        match = re.search(r'(\d{1,2}):(\d{2})', time_str)
        if not match:
            continue

        start_h = int(match.group(1))
        start_m = int(match.group(2))
        start_mins = start_h * 60 + start_m

        diff = start_mins - cur_mins
        event_id = ev.get('id', f"{ev_day}_{time_str}_{ev.get('subject')}")

        # Логируем потенциальные пары дня для контроля
        if -60 <= diff <= 30:
            print(f"[DEBUG] Найдена пара '{ev.get('subject')}': начало в {start_h}:{start_m:02d}, до нее {diff} мин.")

        # Уведомление за 10 минут (интервал от 0 до 10 минут включительно)
        if 0 < diff <= 10 and event_id not in notified_events_today:
            notified_events_today.add(event_id)

            subj = html.escape(ev.get('subject') or 'Занятие')
            location = html.escape(ev.get('location') or '')
            teacher = html.escape(ev.get('teacher') or '')
            homework = html.escape(ev.get('homework') or '')
            link = ev.get('link') or ''

            msg = f"🔔 <b>Скоро пара (через {diff} мин)!</b>\n\n"
            msg += f"📚 <b>{subj}</b>\n"
            msg += f"⏰ Время: {time_str}\n"
            if location:
                msg += f"📍 Ауд.: {location}\n"
            if teacher:
                msg += f"👤 Преп.: {teacher}\n"
            if homework:
                msg += f"📝 ДЗ: {homework}\n"
            if link:
                msg += f"\n🔗 <a href=\"{link}\">Ссылка на занятие</a>"

            send_telegram(msg)

def loop_checker():
    send_telegram("🚀 <b>Бот обновлен и активен!</b>")
    while True:
        try:
            check_lessons()
        except Exception as e:
            print(f"[CRITICAL ERROR] Сбой в цикле проверки: {e}")
        time.sleep(30)

if __name__ == "__main__":
    checker_thread = threading.Thread(target=loop_checker, daemon=True)
    checker_thread.start()
    run_web_server()

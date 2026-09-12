import os
import re
import time
import html
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SCHEDULE_URL = os.getenv("SCHEDULE_URL", "")

EKAT_TZ = timezone(timedelta(hours=5))
notified_events_today = set()
last_reset_day = None
last_check_status = "Бот еще не проверял расписание"

class SimpleHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        # Страница диагностики
        content = f"""
        <html><body>
            <h1>Статус бота: Работает</h1>
            <p><b>Последняя проверка:</b> {last_check_status}</p>
            <p><b>URL расписания:</b> {SCHEDULE_URL}</p>
            <p><b>ID чата:</b> {TELEGRAM_CHAT_ID}</p>
            <hr>
            <p>Если в списке 0 пар, проверьте ссылку на JSON в настройках Render!</p>
        </body></html>
        """
        self.wfile.write(content.encode('utf-8'))

def get_schedule():
    global last_check_status
    try:
        # Добавляем случайное число к ссылке, чтобы GitHub не выдавал старую версию файла
        url = f"{SCHEDULE_URL}&t={int(time.time())}" if "?" in SCHEDULE_URL else f"{SCHEDULE_URL}?t={int(time.time())}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            last_check_status = f"Успешно загружено пар: {len(data)} (Время: {datetime.now(EKAT_TZ).strftime('%H:%M:%S')})"
            return data
        else:
            last_check_status = f"Ошибка GitHub: {res.status_code}"
    except Exception as e:
        last_check_status = f"Ошибка сети: {str(e)}"
    return []

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def check_lessons():
    global last_reset_day, notified_events_today
    now_ekat = datetime.now(EKAT_TZ)
    current_day_idx = now_ekat.weekday()

    if last_reset_day != current_day_idx:
        notified_events_today.clear()
        last_reset_day = current_day_idx

    events = get_schedule()
    cur_mins = now_ekat.hour * 60 + now_ekat.minute

    for ev in events:
        # Проверяем день (0-Пн, 6-Вс)
        ev_day = ev.get('day')
        if ev_day is None or int(ev_day) != current_day_idx:
            continue
        
        # Если пара отмечена как выполненная в планировщике - пропускаем
        if ev.get('isDone'):
            continue

        time_str = ev.get('timeStr', '')
        match = re.search(r'(\d{1,2}):(\d{2})', time_str)
        if not match:
            continue

        start_mins = int(match.group(1)) * 60 + int(match.group(2))
        diff = start_mins - cur_mins
        event_id = str(ev.get('id', f"{time_str}_{ev.get('subject')}"))

        # Интервал уведомления: от 1 до 11 минут до начала
        if 0 < diff <= 11 and event_id not in notified_events_today:
            notified_events_today.add(event_id)
            
            subj = html.escape(ev.get('subject', 'Пара'))
            msg = f"🔔 <b>Через {diff} мин: {subj}</b>\n⏰ Время: {time_str}"
            if ev.get('location'): msg += f"\n📍 Ауд: {html.escape(ev['location'])}"
            if ev.get('link'): msg += f"\n🔗 <a href='{ev['link']}'>Войти</a>"
            
            send_telegram(msg)
            print(f">>> Отправлено уведомление для: {subj}")

def loop_checker():
    # Ждем пару секунд перед первым запуском для прогрева сервера
    time.sleep(5)
    send_telegram("🚀 <b>Бот-планировщик запущен и готов к работе!</b>")
    while True:
        check_lessons()
        time.sleep(40) # Проверка каждые 40 секунд

if __name__ == "__main__":
    threading.Thread(target=loop_checker, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), SimpleHandler).serve_forever()

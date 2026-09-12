import os
import time
import requests
from datetime import datetime, timezone, timedelta

# --- НАСТРОЙКИ (берутся из переменных окружения или указываются вручную) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ОТ_BOTFATHER")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
# Ссылка на RAW-версию вашего schedule.json в GitHub:
# Формат: https://raw.githubusercontent.com/<логин>/<репозиторий>/<ветка>/schedule.json
SCHEDULE_URL = os.getenv("SCHEDULE_URL", "https://raw.githubusercontent.com/username/repo/main/schedule.json")

# Часовой пояс Екатеринбурга (UTC+5)
EKAT_TZ = timezone(timedelta(hours=5))

notified_events_today = set()
last_reset_day = None

def get_schedule():
    """Загрузка расписания с GitHub без кэширования"""
    try:
        url = f"{SCHEDULE_URL}?t={int(time.time())}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка получения JSON: Status {response.status_code}")
    except Exception as e:
        print(f"Ошибка сети: {e}")
    return []

def send_telegram(text):
    """Отправка сообщения в Telegram"""
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
        print(f"Ошибка отправки в Telegram: {e}")

def check_lessons():
    """Проверка пар на скорое начало"""
    global last_reset_day, notified_events_today

    now_ekat = datetime.now(EKAT_TZ)
    current_day_idx = now_ekat.weekday()  # 0 = Понедельник, 6 = Воскресенье

    # Очистка истории отправленных уведомлений в midnight
    if last_reset_day != current_day_idx:
        notified_events_today.clear()
        last_reset_day = current_day_idx

    events = get_schedule()
    if not events:
        return

    cur_mins = now_ekat.hour * 60 + now_ekat.minute

    for ev in events:
        # Проверяем только пары текущей недели, текущего дня и не отметченные как выполненные
        if ev.get('weekOffset', 0) != 0:
            continue
        if ev.get('day') != current_day_idx:
            continue
        if ev.get('isDone', False):
            continue

        time_str = ev.get('timeStr', '')
        if not time_str or "Асинхронно" in time_str:
            continue

        # Парсим время начала (например из "10:15 – 11:45")
        try:
            start_part = time_str.split('-')[0].split('–')[0].strip()
            start_h, start_m = map(int, start_part.split(':'))
            start_mins = start_h * 60 + start_m
        except Exception:
            continue

        diff = start_mins - cur_mins
        event_id = ev.get('id')

        # Уведомляем за 10 минут до начала (интервал 0...10 минут)
        if 0 < diff <= 10 and event_id not in notified_events_today:
            notified_events_today.add(event_id)

            msg = f"🔔 <b>Скоро пара (через {diff} мин)!</b>\n\n"
            msg += f"📚 <b>{ev.get('subject', 'Занятие')}</b>\n"
            msg += f"⏰ Время: {time_str}\n"
            if ev.get('location'):
                msg += f"📍 Аудитория: {ev['location']}\n"
            if ev.get('teacher'):
                msg += f"👤 Преподаватель: {ev['teacher']}\n"
            if ev.get('homework'):
                msg += f"📝 ДЗ: {ev['homework']}\n"
            if ev.get('link'):
                msg += f"\n🔗 <a href=\"{ev['link']}\">Ссылка на онлайн-занятие</a>"

            send_telegram(msg)
            print(f"[{now_ekat.strftime('%H:%M:%S')}] Уведомление отправлено: {ev.get('subject')}")

def main():
    print("Бот запущена и отслеживает расписание...")
    send_telegram("🚀 <b>Бот уведомлений о парах успешно запущен!</b>")
    while True:
        check_lessons()
        time.sleep(30)  # Проверка каждые 30 секунд

if __name__ == "__main__":
    main()

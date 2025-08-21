import json
import os
from datetime import datetime
import pytz
from telegram import Bot
import logging
import asyncio

# Настройка
BOT_TOKEN = "ТВОЙ_ТОКЕН"
SETTINGS_FILE = "group_settings.json"
KYRGYZSTAN_TZ = pytz.timezone("Asia/Bishkek")

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка настроек
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}

# Сохранение настроек
def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

# Основная логика
async def send_reminders():
    now = datetime.now(KYRGYZSTAN_TZ)
    hour = now.hour
    minute = now.minute
    today = now.strftime("%Y-%m-%d")

    group_settings = load_settings()
    bot = Bot(token=BOT_TOKEN)

    for chat_id_str, config in group_settings.items():
        chat_id = int(chat_id_str)
        if (
            config.get("subscribed")
            and config.get("hour") == hour
            and config.get("minute") == minute
            and config.get("last_sent_date") != today
        ):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="💬 Напоминание!\nПожалуйста, отправьте свои результаты по Duolingo и Polyglot 📚\nНе забудьте конспекты, если были!"
                )
                config["last_sent_date"] = today
                logger.info(f"✔️ Напоминание отправлено в {chat_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка в {chat_id}: {e}")

    save_settings(group_settings)

# Запуск
if __name__ == "__main__":
    asyncio.run(send_reminders())

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7384921058:AAEcDrQbW0kcQwceYDH4inZGq15Wtu-c9hE"
KYRGYZSTAN_TZ = pytz.timezone("Asia/Bishkek")

group_settings = {}
waiting_for_time = set()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Добавьте меня в группу и используйте /start")
        return

    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ Только администратор может подписывать группу.")
        return

    group_settings[chat_id] = {
        "subscribed": True,
        "hour": 21,
        "minute": 0,
        "last_sent_date": None
    }
    await update.message.reply_text(
        "✅ Группа подписана на напоминания!\n"
        "⏰ Время по умолчанию: 21:00\n"
        "📋 Команды:\n"
        "⏰ /time - установить время отправки\n"
        "🛑 /stop - отписать группу\n"
        "❓ /help - показать справку"
    )

# /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ Только администратор может отписать группу.")
        return

    group_settings[chat_id]["subscribed"] = False
    waiting_for_time.discard(chat_id)
    await update.message.reply_text("❌ Группа отписана от напоминаний.")

# /time
async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id not in group_settings:
        await update.message.reply_text("Сначала подпишите группу с помощью /start")
        return

    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ Только администратор может изменить время.")
        return

    waiting_for_time.add(chat_id)
    now = datetime.now(KYRGYZSTAN_TZ)
    current = group_settings[chat_id]
    await update.message.reply_text(
        f"⏰ Текущее время отправки: {current['hour']:02d}:{current['minute']:02d}\n"
        f"🕐 Сейчас: {now.strftime('%H:%M')}\n"
        f"📝 Введите новое время в формате ЧЧ:ММ (например: 06:30)"
    )

# Проверка времени
def validate_time_input(time_str):
    pattern = r'^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$'
    match = re.match(pattern, time_str)
    if not match:
        return False, None, None, "Неправильный формат времени"
    return True, int(match.group(1)), int(match.group(2)), "OK"

# Обработка времени
async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text.strip()

    if message_text.startswith("/") or chat_id not in waiting_for_time:
        return

    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        return

    is_valid, hour, minute, error_msg = validate_time_input(message_text)

    if is_valid:
        group_settings[chat_id]["hour"] = hour
        group_settings[chat_id]["minute"] = minute
        waiting_for_time.discard(chat_id)

        now = datetime.now(KYRGYZSTAN_TZ)
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)
        delta = target_time - now

        await update.message.reply_text(
            f"✅ Отлично! Время напоминания установлено на {hour:02d}:{minute:02d} ⏰\n\n"
            f"⏳ До следующего сообщения осталось примерно {delta.seconds // 3600} ч. {(delta.seconds % 3600) // 60} мин.\n\n"
            f"💬 Я пришлю напоминание точно в это время каждый день!"
        )
    else:
        await update.message.reply_text(
            f"❌ Ошибка: {error_msg}\n"
            "Формат: ЧЧ:ММ (например: 08:00, 21:45)"
        )

# Ежедневное сообщение
async def send_daily_message(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYRGYZSTAN_TZ)
    today_str = now.strftime("%Y-%m-%d")
    hour, minute = now.hour, now.minute

    for chat_id, settings in list(group_settings.items()):
        if (settings["subscribed"]
            and settings["hour"] == hour
            and settings["minute"] == minute
            and settings.get("last_sent_date") != today_str):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Всем здравствуйте! 🌟\n"
                        f"Напоминаю, что нужно:\n"
                        f"✅ отправить свои результаты по Duolingo и Polyglot\n"
                        f"✅ прикрепить конспекты, если они были.\n"
                        f"Спасибо за вашу ответственность! Жду ваши отчёты. 😊\n"
                    )
                )
                group_settings[chat_id]["last_sent_date"] = today_str
            except Exception as e:
                logger.error(f"Ошибка отправки в {chat_id}: {e}")
                if "bot was kicked" in str(e).lower():
                    del group_settings[chat_id]

# /status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now(KYRGYZSTAN_TZ)
    total = len([s for s in group_settings.values() if s["subscribed"]])
    msg = f"📊 Подписанных групп: {total}\n🕒 Сейчас: {now.strftime('%H:%M:%S')}"
    if chat_id in group_settings:
        s = group_settings[chat_id]
        msg += f"\n⏰ Время: {s['hour']:02d}:{s['minute']:02d}"
    await update.message.reply_text(msg)

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n"
        "/start — подписать группу\n"
        "/time — установить время\n"
        "/stop — отписаться\n"
        "/status — статус\n"
        "/help — помощь"
    )

# Запуск
from telegram.ext import Application, ApplicationBuilder, JobQueue

async def setup_jobqueue(app):
    job_queue = app.job_queue
    job_queue.run_repeating(send_daily_message, interval=30, first=0)

def main():
    application = Application.builder().token(BOT_TOKEN).post_init(setup_jobqueue).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("time", time_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT, handle_time_input))

    print("✅ Бот готов и слушает все текстовые сообщения")
    application.run_polling()

if __name__ == "__main__":
    main()

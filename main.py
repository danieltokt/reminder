import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import mention_html
import re
import pytz
import os
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "7384921058:AAEcDrQbW0kcQwceYDH4inZGq15Wtu-c9hE")
KYRGYZSTAN_TZ = pytz.timezone("Asia/Bishkek")

group_settings = {}
group_users = {}  # chat_id: set(user_ids)
waiting_for_time = set()

# Health check endpoint
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Отключаем логи HTTP сервера

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# Keep alive функция
async def keep_alive():
    """Функция для предотвращения засыпания на Render"""
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        return
        
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(f"{render_url}/health")
            logger.info("Keep alive ping sent")
        except Exception as e:
            logger.error(f"Keep alive error: {e}")
        
        await asyncio.sleep(840)  # каждые 14 минут

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
    group_users[chat_id] = set()
    await update.message.reply_text(
        "💜 Здравствуйте!\n"
        "Я — 🤖 бот Envio — ваш личный напоминатель от курсов английского языка Envio.\n"
        "📌 Моя задача: напоминать вам о выполнении домашнего задания, чтобы ваш английский становился всё лучше с каждым днём!\n"
        "Нажмите /join чтобы подписаться\n"
    )

# /join
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in group_settings or not group_settings[chat_id]["subscribed"]:
        await update.message.reply_text("❗Группа не подписана. Сначала используйте /start")
        return

    if chat_id not in group_users:
        group_users[chat_id] = set()

    group_users[chat_id].add(user.id)
    logger.info(f"👤 Добавлен: {user.full_name} (ID: {user.id}, @username: {user.username}) в чат {chat_id}")
    await update.message.reply_text(
        f"👋 {user.full_name}, вы подписались на напоминания!\n"
        f"✅ Ваш username: @{user.username}" if user.username else "❗ У вас не задан username!"
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
                mentions = []
                logger.info(f"🔍 Подписанные в чате {chat_id}: {group_users.get(chat_id)}")

                for user_id in group_users.get(chat_id, []):
                    try:
                        member = await context.bot.get_chat_member(chat_id, user_id)
                        user = member.user
                        if user.username:
                            mentions.append(f"@{user.username}")
                        else:
                            mentions.append(mention_html(user.id, user.full_name))
                    except Exception as e:
                        logger.error(f"Ошибка при получении {user_id}: {e}")

                mention_text = " ".join(mentions)
                logger.info(f"📣 Упоминания: {mention_text}")

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"{mention_text}\n\n"
                        f"Всем здравствуйте! 🌟\n"
                        f"Напоминаю, что нужно:\n"
                        f"✅ отправить свои результаты по Duolingo и Polyglot\n"
                        f"✅ прикрепить конспекты, если они были.\n"
                        f"Спасибо за вашу ответственность! Жду ваши отчёты. 😊"
                    ),
                    parse_mode=ParseMode.HTML
                )

                group_settings[chat_id]["last_sent_date"] = today_str

            except Exception as e:
                logger.error(f"Ошибка отправки в {chat_id}: {e}")
                if "bot was kicked" in str(e).lower():
                    del group_settings[chat_id]

# Обёртка для асинхронной функции keep_alive в JobQueue
async def keep_alive_wrapper(context: ContextTypes.DEFAULT_TYPE):
    """Обёртка для запуска keep_alive в JobQueue"""
    await keep_alive()

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
        "/join — подписаться на упоминания\n"
        "/time — установить время\n"
        "/stop — отписаться\n"
        "/status — статус\n"
        "/help — помощь"
    )

def main():
    # Запуск health server в отдельном потоке для Render
    if os.environ.get("RENDER_EXTERNAL_URL"):
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
        logger.info("Health server started")
    
    try:
        # Создание приложения с правильной инициализацией
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Проверяем наличие JobQueue
        if application.job_queue is None:
            logger.error("JobQueue не инициализирован! Проверьте установку python-telegram-bot[job-queue]")
            return
        
        logger.info("JobQueue успешно инициализирован")
        
        # Настройка job queue
        job_queue = application.job_queue
        job_queue.run_repeating(send_daily_message, interval=60, first=10)
        logger.info("Задача send_daily_message добавлена в очередь")
        
        # Keep alive только для Render
        if os.environ.get("RENDER_EXTERNAL_URL"):
            # Исправлено: используем правильную обёртку
            job_queue.run_repeating(keep_alive_wrapper, interval=840, first=60)
            logger.info("Задача keep_alive добавлена в очередь")
        
    except Exception as e:
        logger.error(f"Ошибка создания приложения: {e}")
        return

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("time", time_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT, handle_time_input))

    logger.info("✅ Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
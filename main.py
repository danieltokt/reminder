import asyncio
import logging
import sys
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import mention_html
from telegram.error import NetworkError, TelegramError
import re
import pytz
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Проверка наличия токена
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)

KYRGYZSTAN_TZ = pytz.timezone("Asia/Bishkek")

group_settings = {}
group_users = {}  # chat_id: set(user_ids)
waiting_for_time = set()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Добавьте меня в группу и используйте /start")
        return

    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Только администратор может подписывать группу.")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        await update.message.reply_text("❌ Ошибка проверки прав.")
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
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Только администратор может отписать группу.")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return

    if chat_id in group_settings:
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

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Только администратор может изменить время.")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
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
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
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
                logger.info(f"✅ Сообщение отправлено в чат {chat_id}")

            except Exception as e:
                logger.error(f"Ошибка отправки в {chat_id}: {e}")
                if "bot was kicked" in str(e).lower() or "chat not found" in str(e).lower():
                    logger.info(f"Удаляем чат {chat_id} из настроек")
                    if chat_id in group_settings:
                        del group_settings[chat_id]
                    if chat_id in group_users:
                        del group_users[chat_id]

# /status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now(KYRGYZSTAN_TZ)
    total = len([s for s in group_settings.values() if s["subscribed"]])
    msg = f"📊 Подписанных групп: {total}\n🕒 Сейчас: {now.strftime('%H:%M:%S')}"
    if chat_id in group_settings:
        s = group_settings[chat_id]
        msg += f"\n⏰ Время: {s['hour']:02d}:{s['minute']:02d}"
        msg += f"\n👥 Подписанных: {len(group_users.get(chat_id, []))}"
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

# Обработка ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")

def main():
    logger.info("🚀 Запуск бота...")
    
    try:
        # Создание приложения
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Проверяем наличие JobQueue
        if application.job_queue is None:
            logger.error("❌ JobQueue не инициализирован!")
            sys.exit(1)
        
        logger.info("✅ JobQueue успешно инициализирован")
        
        # Настройка job queue
        job_queue = application.job_queue
        job_queue.run_repeating(send_daily_message, interval=60, first=10)
        logger.info("✅ Задача send_daily_message добавлена в очередь")
        
        # Добавление обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("join", join))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("time", time_command))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT, handle_time_input))
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("✅ Все обработчики добавлены")
        logger.info("🤖 Бот запущен и готов к работе!")
        
        # Запуск polling с обработкой ошибок
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
    except NetworkError as e:
        logger.error(f"🌐 Сетевая ошибка: {e}")
        sys.exit(1)
    except TelegramError as e:
        logger.error(f"📱 Ошибка Telegram API: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
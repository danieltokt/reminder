import logging
import sys
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import mention_html
import re
import pytz
import os
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7384921058:AAEcDrQbW0kcQwceYDH4inZGq15Wtu-c9hE")
KYRGYZSTAN_TZ = pytz.timezone("Asia/Bishkek")

# Глобальные переменные
group_settings = {}
group_users = {}
waiting_for_time = set()

# Команды бота
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
        logger.error(f"Ошибка проверки прав: {e}")
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
        "Нажмите /join чтобы подписаться"
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in group_settings or not group_settings[chat_id]["subscribed"]:
        await update.message.reply_text("❗Группа не подписана. Сначала используйте /start")
        return

    if chat_id not in group_users:
        group_users[chat_id] = set()

    group_users[chat_id].add(user.id)
    logger.info(f"Добавлен пользователь {user.full_name} в чат {chat_id}")
    
    username_text = f"✅ Ваш username: @{user.username}" if user.username else "❗ У вас не задан username!"
    await update.message.reply_text(f"👋 {user.full_name}, вы подписались на напоминания!\n{username_text}")

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in group_settings:
        await update.message.reply_text("Сначала подпишите группу с помощью /start")
        return

    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Только администратор может изменить время.")
            return
    except Exception:
        return

    waiting_for_time.add(chat_id)
    now = datetime.now(KYRGYZSTAN_TZ)
    current = group_settings[chat_id]
    await update.message.reply_text(
        f"⏰ Текущее время отправки: {current['hour']:02d}:{current['minute']:02d}\n"
        f"🕐 Сейчас: {now.strftime('%H:%M')}\n"
        f"📝 Введите новое время в формате ЧЧ:ММ (например: 06:30)"
    )

async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text.strip()

    if message_text.startswith("/") or chat_id not in waiting_for_time:
        return

    # Проверка формата времени
    pattern = r'^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$'
    match = re.match(pattern, message_text)
    
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        group_settings[chat_id]["hour"] = hour
        group_settings[chat_id]["minute"] = minute
        waiting_for_time.discard(chat_id)
        
        await update.message.reply_text(
            f"✅ Время установлено на {hour:02d}:{minute:02d}!"
        )
    else:
        await update.message.reply_text(
            "❌ Неправильный формат времени. Используйте ЧЧ:ММ (например: 08:00)"
        )

async def send_daily_message(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYRGYZSTAN_TZ)
    today_str = now.strftime("%Y-%m-%d")
    hour, minute = now.hour, now.minute

    for chat_id, settings in list(group_settings.items()):
        if (settings["subscribed"] and 
            settings["hour"] == hour and 
            settings["minute"] == minute and
            settings.get("last_sent_date") != today_str):
            
            try:
                mentions = []
                for user_id in group_users.get(chat_id, []):
                    try:
                        member = await context.bot.get_chat_member(chat_id, user_id)
                        user = member.user
                        if user.username:
                            mentions.append(f"@{user.username}")
                        else:
                            mentions.append(mention_html(user.id, user.full_name))
                    except Exception:
                        continue

                mention_text = " ".join(mentions)
                message = (
                    f"{mention_text}\n\n"
                    f"Всем здравствуйте! 🌟\n"
                    f"Напоминаю, что нужно:\n"
                    f"✅ отправить свои результаты по Duolingo и Polyglot\n"
                    f"✅ прикрепить конспекты, если они были.\n"
                    f"Спасибо за вашу ответственность! Жду ваши отчёты. 😊"
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML
                )

                group_settings[chat_id]["last_sent_date"] = today_str
                logger.info(f"Сообщение отправлено в чат {chat_id}")

            except Exception as e:
                logger.error(f"Ошибка отправки в чат {chat_id}: {e}")

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n"
        "/start — подписать группу\n"
        "/join — подписаться на напоминания\n"
        "/time — установить время\n"
        "/status — статус\n"
        "/help — помощь"
    )

def main():
    logger.info("🚀 Запуск бота...")
    
    try:
        # Простое создание приложения
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("join", join))
        app.add_handler(CommandHandler("time", time_command))
        app.add_handler(CommandHandler("status", status))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(MessageHandler(filters.TEXT, handle_time_input))
        
        # Добавляем задачу проверки времени
        if app.job_queue:
            app.job_queue.run_repeating(send_daily_message, interval=60, first=10)
            logger.info("✅ Задача напоминаний добавлена")
        
        logger.info("🤖 Бот готов к работе!")
        
        # Запуск
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        return

if __name__ == "__main__":
    main()
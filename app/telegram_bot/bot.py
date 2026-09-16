import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from app.database.db import SessionLocal
from app.database import crud
from app.assistant.assistant import ask_assistant
from app.parser.scraper import parse_and_save
from app.config import ADMIN_TELEGRAM_IDS

MAX_MESSAGE_LEN = 4096


def is_admin(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в списке администраторов из .env."""
    return user_id in ADMIN_TELEGRAM_IDS


async def reply_in_chunks(message, text: str):
    for i in range(0, len(text), MAX_MESSAGE_LEN):
        await message.reply_text(text[i:i + MAX_MESSAGE_LEN])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        crud.get_or_create_user(db, telegram_id=user.id, username=user.username,
                                first_name=user.first_name, last_name=user.last_name)
    finally:
        db.close()
    await update.message.reply_text(
        "Привет! 👋 Я — бот-консультант по API Bitrix24.\n"
        "Задайте вопрос по документации — я отвечу и приложу ссылку на источник.\n\n"
        "Команды:\n/help — справка\n/history — последние вопросы\n"
        "/update_docs — обновить документацию (только для администраторов)"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я отвечаю на вопросы разработчиков по документации API Bitrix24.\n"
        "Напишите вопрос обычным текстом — я найду ответ в базе знаний "
        "и приложу ссылку на фрагмент документации."
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        db_user = crud.get_or_create_user(db, telegram_id=user.id)
        records = crud.get_user_history(db, user_id=db_user.id, limit=5)
    finally:
        db.close()

    if not records:
        await update.message.reply_text("История пока пуста. Задайте первый вопрос!")
        return

    lines = ["📜 Ваши последние вопросы:"]
    for i, rec in enumerate(records, 1):
        lines.append(f"{i}. {rec.question}")
    await update.message.reply_text("\n".join(lines))


async def update_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновляет документацию парсером Selenium. Доступно только администраторам из .env."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ Доступ запрещён: команда обновления документации доступна "
            "только администраторам проекта."
        )
        return

    status_msg = await update.message.reply_text(
        "🔄 Обновляю документацию Bitrix24... Это может занять несколько минут."
    )
    try:
        parsed_count = await asyncio.to_thread(parse_and_save)
        await status_msg.edit_text(
            f"✅ Документация обновлена: перезагружено страниц — {parsed_count}."
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при обновлении документации: {e}")


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    question = update.message.text.strip()

    db = SessionLocal()
    try:
        db_user = crud.get_or_create_user(db, telegram_id=user.id, username=user.username,
                                          first_name=user.first_name, last_name=user.last_name)
        await update.message.reply_text("🤔 Ищу ответ в документации Bitrix24...")
        answer = await asyncio.to_thread(ask_assistant, question)
        crud.save_message(db, user_id=db_user.id, question=question, answer=answer)
    finally:
        db.close()

    await reply_in_chunks(update.message, answer)

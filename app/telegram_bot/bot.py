import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from app.database.db import SessionLocal
from app.database import crud
from app.assistant.assistant import ask_assistant

# Telegram не принимает сообщения длиннее 4096 символов
MAX_MESSAGE_LEN = 4096

async def reply_in_chunks(message, text: str):
    """Отправляет длинный ответ частями, чтобы не превысить лимит Telegram."""
    for i in range(0, len(text), MAX_MESSAGE_LEN):
        await message.reply_text(text[i:i + MAX_MESSAGE_LEN])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start: приветствие и регистрация пользователя в БД."""
    user = update.effective_user
    db = SessionLocal()
    try:
        crud.get_or_create_user(
            db,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    finally:
        db.close()
    await update.message.reply_text(
        "Привет! 👋 Я — бот-консультант по API Bitrix24.\n"
        "Задайте мне вопрос по документации (например: "
        "«Как создать сделку через REST API?»), и я отвечу на основе базы знаний.\n\n"
        "Команды:\n/help — справка\n/history — последние вопросы"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я отвечаю на вопросы разработчиков по документации API Bitrix24.\n"
        "Просто напишите вопрос обычным текстом — я найду ответ в базе знаний."
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /history: последние 5 вопросов пользователя из БД."""
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

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик: вопрос -> ассистент -> ответ + сохранение в БД."""
    user = update.effective_user
    question = update.message.text.strip()

    db = SessionLocal()
    try:
        db_user = crud.get_or_create_user(
            db,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await update.message.reply_text("🤔 Ищу ответ в документации Bitrix24...")

        # ask_assistant — синхронная и долгая (нейросеть), поэтому запускаем
        # её в отдельном потоке, чтобы не блокировать event loop бота
        answer = await asyncio.to_thread(ask_assistant, question)

        # Сохраняем пару "вопрос-ответ" в историю
        crud.save_message(db, user_id=db_user.id, question=question, answer=answer)
    finally:
        db.close()

    await reply_in_chunks(update.message, answer)
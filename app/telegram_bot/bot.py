import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from app.database.db import SessionLocal
from app.database import crud
from app.assistant.assistant import ask_assistant
from app.parser.scraper import parse_and_save
from app.config import ADMIN_TELEGRAM_IDS

from app.assistant.search_index import index

_update_lock = asyncio.Lock()

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
    """Обновление документации. Замечание №6: взаимная блокировка запусков."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ Доступ запрещён: команда доступна только администраторам проекта."
        )
        return

    # Если обновление уже идёт — сразу отвечаем и выходим
    if _update_lock.locked():
        await update.message.reply_text(
            "⏳ Обновление документации уже выполняется другим администратором. "
            "Дождитесь завершения."
        )
        return

    async with _update_lock:
        status_msg = await update.message.reply_text(
            "🔄 Обновляю документацию Bitrix24... Это может занять несколько минут."
        )
        try:
            parsed_count = await asyncio.to_thread(parse_and_save)
            await status_msg.edit_text("📚 Документация собрана. Перестраиваю поисковый индекс...")
            chunks_count = await asyncio.to_thread(index.build)
            await status_msg.edit_text(
                f"✅ Готово: страниц — {parsed_count}, чанков в индексе — {chunks_count}."
            )
        except Exception as exc:
            logger.error("Ошибка обновления документации: %s", exc, exc_info=True)
            await status_msg.edit_text(f"❌ Ошибка при обновлении: {exc}")


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

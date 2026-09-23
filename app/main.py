from app.logger import logger
from telegram.ext import Application, CommandHandler, MessageHandler, filters


from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_PROXY
from app.telegram_bot import bot

#logging.basicConfig(
    #format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
   # level=logging.INFO,
#)

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Ошибка: не задан TELEGRAM_BOT_TOKEN в файле .env")

    # Замечание №4: индекс базы знаний строится ОДИН РАЗ при старте бота
    from app.assistant.search_index import index
    logger.info("Построение поискового индекса...")
    chunks_count = index.build()
    logger.info("Индекс готов (%d чанков). Запуск бота...", chunks_count)

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True)

    if TELEGRAM_PROXY:
        from telegram.request import HTTPXRequest
        request = HTTPXRequest(proxy=TELEGRAM_PROXY)
        get_updates_request = HTTPXRequest(proxy=TELEGRAM_PROXY)
        builder = builder.request(request).get_updates_request(get_updates_request)
        logger.info("Используем прокси: %s", TELEGRAM_PROXY)

    application = builder.build()

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("history", bot.history_command))
    application.add_handler(CommandHandler("update_docs", bot.update_docs))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_question))

    logger.info("🚀 Бот запущен и ожидает сообщения...")
    application.run_polling()

if __name__ == "__main__":
    main()

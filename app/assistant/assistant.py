"""
RAG-модуль: генерация ответа по вопросу с опорой на базу знаний Bitrix24.

Гибридный поиск (BM25 + эмбеддинги + RRF) предоставляет релевантные фрагменты,
YandexGPT формирует развёрнутый структурированный ответ со ссылками на источники.
"""
from yandex_ai_studio_sdk import AIStudio
from yandex_ai_studio_sdk.auth import APIKeyAuth

from app.config import YC_API_KEY, YC_FOLDER_ID
from app.logger import logger

sdk = AIStudio(folder_id=YC_FOLDER_ID, auth=APIKeyAuth(YC_API_KEY))


def ask_assistant(question: str) -> str:
    """RAG: гибридный поиск -> YandexGPT -> развёрнутый ответ со ссылками на источники."""
    try:
        from app.assistant.search_index import index

        if not index.chunks:
            return (
                "База знаний пуста. Попросите администратора обновить "
                "документацию командой /update_docs."
            )

        logger.info("Поиск по индексу: %s", question)
        # 7 фрагментов в контексте: модели хватает материала для полного ответа
        chunks = index.search(question, top_k=7)

        if not chunks or chunks[0].score == 0:
            return (
                "Не нашёл ответа в документации Bitrix24. "
                "Попробуйте переформулировать вопрос или обновите базу знаний "
                "командой /update_docs."
            )

        context = "\n\n".join(
            f"[Источник: {c.url or c.filename}]\n{c.text}" for c in chunks
        )

        system_prompt = f"""Ты — опытный технический консультант по API Bitrix24 для разработчиков.
Опираясь ТОЛЬКО на фрагменты документации ниже, дай развёрнутый практический ответ.

Структура ответа:
1. Коротко: какой метод или подход решает задачу.
2. Как вызвать: HTTP-метод, адрес, обязательные и важные параметры (списком или таблицей).
3. Пошаговый порядок действий и пример запроса/кода, если они есть во фрагментах.
4. Важные ограничения и примечания из документации.

Правила:
- Пиши подробно и конкретно: ответ должен содержать всё необходимое для реализации.
- Не выдумывай параметры и методы: если чего-то нет во фрагментах — скажи об этом прямо.
- Если ответа во фрагментах нет совсем — честно скажи, что информации недостаточно.

=== ФРАГМЕНТЫ ДОКУМЕНТАЦИИ ===
{context}
=== КОНЕЦ ФРАГМЕНТОВ ==="""

        logger.info("Отправка запроса в YandexGPT...")
        model = sdk.models.completions('yandexgpt')
        model = model.configure(temperature=0.3, max_tokens=3000)

        full_prompt = f"{system_prompt}\n\nВопрос: {question}"
        result = model.run(full_prompt)

        answer = None
        for alternative in result:
            answer = getattr(alternative, "text", None) or str(alternative)
            break
        if not answer:
            return "Не удалось получить ответ от модели."

        # Ссылки на источники: без дубликатов и не больше пяти
        sources = []
        for c in chunks:
            link = c.url or c.filename
            if link and link not in sources:
                sources.append(link)
        sources = sources[:5]

        answer += "\n\n📚 Источники:\n" + "\n".join(f"• {s}" for s in sources)
        return answer

    except Exception as exc:
        logger.error("Ошибка при обращении к YandexGPT: %s", exc, exc_info=True)
        return f"Ошибка при генерации ответа: {exc}"


if __name__ == "__main__":
    logger.info("%s", ask_assistant("Как создать сделку в CRM Bitrix24?"))
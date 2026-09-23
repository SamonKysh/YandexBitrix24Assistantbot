import os
import re
from collections import Counter
from app.logger import logger
from yandex_ai_studio_sdk import AIStudio
from yandex_ai_studio_sdk.auth import APIKeyAuth

from app.config import YC_API_KEY, YC_FOLDER_ID

DOCS_DIR = "data/docs"

sdk = AIStudio(folder_id=YC_FOLDER_ID, auth=APIKeyAuth(YC_API_KEY))


def load_documents():
    """Читает .txt файлы и извлекает ссылку-источник из первой строки."""
    documents = []
    if not os.path.exists(DOCS_DIR):
        return documents
    for filename in os.listdir(DOCS_DIR):
        if not filename.endswith(".txt"):
            continue
        with open(os.path.join(DOCS_DIR, filename), "r", encoding="utf-8") as f:
            content = f.read()
        url = ""
        lines = content.splitlines()
        if lines and lines[0].startswith("Source:"):
            url = lines[0].replace("Source:", "").strip()
            content = "\n".join(lines[1:]).strip()
        documents.append({"filename": filename, "url": url, "text": content})
    return documents


def chunk_text(text, chunk_size=1200, overlap=200):
    """Разбивает текст документа на перекрывающиеся фрагменты."""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def tokenize(text):
    return re.findall(r"[a-zа-яё0-9_.]+", text.lower())


def retrieve(question, documents, top_k=3):
    """Простой лексический поиск: возвращает самые релевантные фрагменты с источниками."""
    question_tokens = set(tokenize(question))
    scored = []
    for doc in documents:
        for chunk in chunk_text(doc["text"]):
            chunk_tokens = Counter(tokenize(chunk))
            score = sum(chunk_tokens[t] for t in question_tokens)
            if score > 0:
                scored.append((score, chunk, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"text": chunk, "url": doc["url"], "filename": doc["filename"]}
        for _, chunk, doc in scored[:top_k]
    ]


def ask_assistant(question: str) -> str:
    """RAG с использованием поискового индекса (BM25). Ссылки на источники в конце."""
    try:
        from app.assistant.search_index import index

        if not index.chunks:
            return (
                "База знаний пуста. Попросите администратора обновить "
                "документацию командой /update_docs."
            )

        logger.info("Поиск по индексу: %s", question)
        chunks = index.search(question, top_k=3)

        if not chunks or chunks[0].score == 0:
            return (
                "Не нашёл ответа в документации Bitrix24. "
                "Попробуйте переформулировать вопрос или обновите базу знаний "
                "командой /update_docs."
            )

        context = "\n\n".join(
            f"[Источник: {c.url or c.filename}]\n{c.text}" for c in chunks
        )

        system_prompt = f"""Ты — опытный технический консультант по API Bitrix24.
Отвечай кратко и по существу, опираясь ТОЛЬКО на фрагменты документации ниже.
Если во фрагментах нет ответа — честно скажи об этом.

=== ФРАГМЕНТЫ ДОКУМЕНТАЦИИ ===
{context}
=== КОНЕЦ ФРАГМЕНТОВ ==="""

        logger.info("Отправка запроса в YandexGPT...")
        model = sdk.models.completions('yandexgpt')
        model = model.configure(temperature=0.3, max_tokens=2000)

        full_prompt = f"{system_prompt}\n\nВопрос: {question}"
        result = model.run(full_prompt)

        answer = None
        for alternative in result:
            answer = getattr(alternative, "text", None) or str(alternative)
            break
        if not answer:
            return "Не удалось получить ответ от модели."

        # Ссылки на источники (замечание руководителя)
        sources = []
        for c in chunks:
            link = c.url or c.filename
            if link and link not in sources:
                sources.append(link)
        answer += "\n\n📚 Источники:\n" + "\n".join(f"• {s}" for s in sources)
        return answer

    except Exception as exc:
        logger.error("Ошибка при обращении к YandexGPT: %s", exc, exc_info=True)
        return f"Ошибка при генерации ответа: {exc}"

if __name__ == "__main__":
    logger.info("🤖 Тестируем RAG с источниками...")
    q = "Как добавить новую сделку в CRM через REST API?"
    logger.info(f"Вопрос: {q}\n")
    logger.info(f"Ответ ассистента:\n{ask_assistant(q)}")

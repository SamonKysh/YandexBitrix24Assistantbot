import os
import re
from collections import Counter

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
    """RAG: поиск фрагментов -> генерация ответа YandexGPT -> ссылки на источники."""
    try:
        print("📖 Подбор релевантных фрагментов документации...")
        documents = load_documents()
        chunks = retrieve(question, documents)

        if not chunks:
            return ("Не нашёл ответа в документации Bitrix24 по этому вопросу. "
                    "Попробуйте переформулировать его или попросите администратора "
                    "обновить базу знаний командой /update_docs.")

        context = "\n\n".join(
            f"[Источник фрагмента: {c['url'] or c['filename']}]\n{c['text']}" for c in chunks
        )

        system_prompt = f"""Ты — опытный технический консультант по API Bitrix24.
Отвечай на вопрос разработчика кратко и по существу, опираясь ТОЛЬКО на фрагменты документации ниже.
Если во фрагментах нет ответа — честно скажи об этом. Приводи примеры кода, если они есть в тексте.

=== ФРАГМЕНТЫ ДОКУМЕНТАЦИИ ===
{context}
=== КОНЕЦ ФРАГМЕНТОВ ==="""

        print("🤖 Отправка запроса в YandexGPT...")
        model = sdk.models.completions('yandexgpt')
        model = model.configure(temperature=0.3, max_tokens=2000)

        full_prompt = f"{system_prompt}\n\nВопрос разработчика: {question}"
        result = model.run(full_prompt)

        answer = None
        for alternative in result:
            answer = getattr(alternative, "text", None) or str(alternative)
            break
        if not answer:
            return "Не удалось получить ответ от модели."

        # Требование руководителя: ссылки на фрагменты документации в конце ответа
        sources = []
        for c in chunks:
            link = c["url"] or c["filename"]
            if link not in sources:
                sources.append(link)
        answer += "\n\n📚 Источник(и) в документации:\n" + "\n".join(f"• {s}" for s in sources)
        return answer

    except Exception as e:
        return f"Ошибка при обращении к YandexGPT: {e}"


if __name__ == "__main__":
    print("🤖 Тестируем RAG с источниками...")
    q = "Как добавить новую сделку в CRM через REST API?"
    print(f"Вопрос: {q}\n")
    print(f"Ответ ассистента:\n{ask_assistant(q)}")

import os
from yandex_ai_studio_sdk import AIStudio
from yandex_ai_studio_sdk.auth import APIKeyAuth
from app.config import YC_API_KEY, YC_FOLDER_ID

# Папка, где лежат спарсенные .txt файлы с документацией
DOCS_DIR = "data/docs"

# Инициализируем SDK: folder_id и auth передаются ОДИН РАЗ здесь
sdk = AIStudio(folder_id=YC_FOLDER_ID, auth=APIKeyAuth(YC_API_KEY))

def load_docs_context() -> str:
    """Загружает текст из всех .txt файлов в папке data/docs/ и объединяет их."""
    context = []
    if not os.path.exists(DOCS_DIR):
        return "Документация не найдена."
        
    for filename in os.listdir(DOCS_DIR):
        if filename.endswith(".txt"):
            filepath = os.path.join(DOCS_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                # Берем первые 3000 символов из каждого файла, чтобы не превысить лимит токенов
                content = f.read()[:3000]
                context.append(f"--- Файл: {filename} ---\n{content}")
                
    return "\n\n".join(context)

def ask_assistant(question: str) -> str:
    """Отправляет вопрос YandexGPT с контекстом из документации."""
    try:
        print("📖 Загрузка контекста из документации...")
        docs_context = load_docs_context()
        
        system_prompt = f"""Ты — опытный технический консультант по API Bitrix24. 
Отвечай на вопросы разработчиков кратко, по существу и только на основе предоставленной ниже документации. 
Если в документации нет ответа, честно скажи об этом. Приводи примеры кода, если они есть в тексте.

=== КОНТЕКСТ ИЗ ДОКУМЕНТАЦИИ ===
{docs_context}
=== КОНЕЦ КОНТЕКСТА ==="""

        print("🤖 Отправка запроса в YandexGPT...")
        # ВАЖНО: folder_id сюда НЕ передаём — он уже задан в конструкторе AIStudio
        model = sdk.models.completions('yandexgpt')
        model = model.configure(temperature=0.3, max_tokens=2000)
        
        # Объединяем инструкцию, контекст и вопрос в один промпт
        full_prompt = f"{system_prompt}\n\nВопрос разработчика: {question}"
        result = model.run(full_prompt)
        
        # result — набор альтернатив ответа; берём текст первой непустой
        for alternative in result:
            text = getattr(alternative, "text", None) or str(alternative)
            if text:
                return text
        return "Не удалось получить ответ от модели."
        
    except Exception as e:
        return f"Ошибка при обращении к YandexGPT: {e}"

if __name__ == "__main__":
    print("🤖 Тестируем локальный RAG...")
    test_question = "Как добавить новую сделку в CRM через REST API?"
    print(f"Вопрос: {test_question}\n")
    
    answer = ask_assistant(test_question)
    print(f"\nОтвет ассистента:\n{answer}")
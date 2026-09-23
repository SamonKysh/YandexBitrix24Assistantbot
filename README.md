# Telegram RAG Bot для API Bitrix24

Telegram-бот, отвечающий на вопросы разработчиков по API Bitrix24 на основе официальной документации.
Реализовано: парсинг всей документации (Selenium + sitemap.xml), гибридный поиск
(BM25 + эмбеддинги YandexGPT + RRF), генерация ответов YandexGPT с обязательными
ссылками на источники, PostgreSQL для хранения пользователей и истории диалогов.

## Архитектура проекта

- `app/main.py` — точка входа: однократное построение поискового индекса при старте, запуск polling;
- `app/telegram_bot/bot.py` — обработчики `/start`, `/help`, `/history`, `/update_docs`;
- `app/assistant/assistant.py` — RAG: поиск по индексу → YandexGPT → ответ с источниками;
- `app/assistant/search_index.py` — гибридный индекс: BM25 + эмбеддинги (косинус) + фьюжн RRF; дисковый кэш векторов;
- `app/parser/scraper.py` — Selenium-парсер всей документации через sitemap.xml, удаляет устаревшие страницы;
- `app/database/` — модели SQLAlchemy (`users`, `chat_history`, `telegram_id BigInteger`) и CRUD;
- `app/logger.py` — единое логирование с анонимизацией секретов;
- `app/config.py` — конфигурация из переменных окружения (`.env`).

## Описание переменных окружения (.env)

Все секреты и настройки хранятся в файле `.env` и загружаются через `python-dotenv`.


| Переменная | Описание | Пример |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather | `123456789:AAF...` |
| `TELEGRAM_PROXY` | Прокси для Telegram API (пусто — если не нужен) | `socks5://127.0.0.1:1080` |
| `ADMIN_TELEGRAM_IDS` | ID администраторов через запятую; только им доступен `/update_docs` | `123456789,987654321` |
| `DB_HOST` | Хост PostgreSQL | `localhost` |
| `DB_PORT` | Порт PostgreSQL | `5432` |
| `DB_NAME` | Имя базы данных | `bitrix_bot_db` |
| `DB_USER` | Пользователь БД | `octagon` |
| `DB_PASSWORD` | Пароль БД | `secret` |
| `YC_API_KEY` | API-ключ Yandex Cloud | `AQVN...` |
| `YC_FOLDER_ID` | ID каталога Yandex Cloud | `b1g...` |
| `YC_AGENT_ID` | ID агента (необязательно, справочно) | `btq...` |
| `YC_KB_ID` | ID базы знаний (необязательно, справочно) | `btg...` |
| `PARSE_MAX_PAGES` | Лимит страниц парсера (5000 = полный прогон) | `5000` |
| `PARSE_DELAY_SECONDS` | Задержка между запросами (вежливость к сайту) | `0.8` |
| `USE_SEMANTIC_SEARCH` | Включить семантический поиск (`true`/`false`) | `true` |
| `EMBEDDING_DOC_MODEL` | Модель эмбеддингов документов | `text-search-doc` |
| `EMBEDDING_QUERY_MODEL` | Модель эмбеддингов запросов | `text-search-query` |
| `EMBEDDING_BATCH_SIZE` | Размер батча при вычислении эмбеддингов | `16` |
| `EMBEDDING_CACHE_PATH` | Путь к кэшу векторов | `data/embeddings_cache.npz` |
| `DATABASE_URL` | Переопределение строки подключения ТОЛЬКО для локальной разработки (например, `sqlite:///bot.db`)

## Инструкция по запуску

> **Важная архитектурная особенность:** В связи с сетевыми ограничениями (блокировка `api.telegram.org` в WSL), Telegram-бот запускается в среде **Windows**, а база данных **PostgreSQL** работает внутри **WSL (Ubuntu)**. WSL2 автоматически пробрасывает порты, поэтому бот из Windows успешно подключается к БД по `localhost`.

## Команды бота
- `/start` — регистрация и приветствие;
- `/help` — справка;
- `/history` — последние 5 вопросов пользователя;
- `/update_docs` — актуализация базы знаний (парсинг apidocs.bitrix24.ru через Selenium). **Доступна только администраторам**, перечисленным в `ADMIN_TELEGRAM_IDS`.

Каждый ответ бота завершается блоком «📚 Источник(и) в документации» со ссылками на фрагменты, на основе которых построен ответ.

## Гибридный поиск (RAG)
1. Лексический: BM25 по чанкам документации (2000 символов, перекрытие 400).
2. Семантический: эмбеддинги YandexGPT (text-search-doc для чанков,
text-search-query для запросов), косинусное сходство по векторной матрице.
Векторы кэшируются в data/embeddings_cache.npz и не пересчитываются при перезапуске;
устаревшие векторы удаляются вместе с устаревшими чанками.
3. Объединение: Reciprocal Rank Fusion (RRF, k=60): score(d) = Σ 1/(k + rank(d)).
О векторном хранилище: в рекомендациях упоминался pgvector; поскольку официальных сборок
pgvector под Windows-PostgreSQL не существует, векторное хранилище реализовано как
дисковый кэш + numpy-матрица в памяти. Путь миграции в продакшене: таблица
chunk_embeddings с типом vector и косинусным оператором <=>.

### 1. Подготовка WSL (База данных и Парсер)
1. Запустите PostgreSQL внутри WSL:
    sudo service postgresql start
2. Создайте базу данных и примените миграции:
    python3 -m app.init_db
3. (Опционально) Соберите свежую документацию с сайта Bitrix24:
    python3 -m app.parser.scraper
### 2. Запуск бота в Windows
1. Скопируйте файлы .env и папку data/docs из WSL в папку проекта в Windows.
2. В .env укажите DB_HOST=localhost и оставьте TELEGRAM_PROXY= пустым.
3. Откройте cmd в папке проекта, создайте и активируйте виртуальное окружение:
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
4. Если у вас установлен системный прокси (например, TG WS Proxy), отключите его для текущей сессии, чтобы Python шел в интернет напрямую:
   set HTTP_PROXY=
   set HTTPS_PROXY=
   set ALL_PROXY=
   set NO_PROXY=*
5. Запустите бота:
   python -m app.main

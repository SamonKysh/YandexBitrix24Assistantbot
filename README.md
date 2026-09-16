# Telegram RAG Bot для API Bitrix24

Интеллектуальный Telegram-бот, который отвечает на вопросы разработчиков по документации API Bitrix24. 
Бот использует **YandexGPT** для генерации ответов и технологию **RAG** (Retrieval-Augmented Generation): перед ответом нейросеть ищет релевантную информацию в локальной базе знаний, собранной из официальной документации Bitrix24.

## Архитектура проекта

Проект реализован с использованием модульной архитектуры:
- `app/telegram_bot/` — модуль интеграции с Telegram (обработка сообщений).
- `app/database/` — модуль работы с PostgreSQL через SQLAlchemy (пользователи и история чата).
- `app/parser/` — модуль парсинга документации Bitrix24 с помощью Selenium.
- `app/assistant/` — модуль интеграции с Yandex Cloud (YandexGPT) и локальный поиск по базе знаний.
- `app/main.py` — общий модуль, связывающий всё воедино.

## Описание переменных окружения (.env)

Все секреты и настройки хранятся в файле `.env` и загружаются через `python-dotenv`.

| Переменная | Описание | Пример заполнения |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота, полученный от @BotFather | `123456789:AAF...` |
| `TELEGRAM_PROXY` | SOCKS/HTTP прокси для обхода блокировок (если не нужен — оставить пустым) | `socks5://127.0.0.1:1080` |
| `ADMIN_TELEGRAM_IDS` | Telegram ID администраторов проекта (через запятую). Только им доступна команда `/update_docs` | `123456789,987654321` |
| `DB_HOST` | Хост базы данных PostgreSQL | `localhost` |
| `DB_PORT` | Порт PostgreSQL | `5432` |
| `DB_NAME` | Имя базы данных | `bitrix_bot_db` |
| `DB_USER` | Имя пользователя БД | `octagon` |
| `DB_PASSWORD` | Пароль от БД | `12345` |
| `YC_API_KEY` | API-ключ Yandex Cloud (AI Studio) | `y0_AgAAAA...` |
| `YC_FOLDER_ID` | ID каталога (папки) в Yandex Cloud | `b1g8xxxxxxxx` |
| `YC_AGENT_ID` | ID текстового агента (опционально для справки) | `btqxxxxxxxx` |
| `YC_KB_ID` | ID поискового индекса / базы знаний | `btgxxxxxxxx` |

## Инструкция по запуску

> **Важная архитектурная особенность:** В связи с сетевыми ограничениями (блокировка `api.telegram.org` в WSL), Telegram-бот запускается в среде **Windows**, а база данных **PostgreSQL** работает внутри **WSL (Ubuntu)**. WSL2 автоматически пробрасывает порты, поэтому бот из Windows успешно подключается к БД по `localhost`.

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

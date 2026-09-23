import os
from dotenv import load_dotenv

# Загружаем переменные из .env-файла
load_dotenv()

# === Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "")

# Список ID администраторов проекта (через запятую)
ADMIN_TELEGRAM_IDS = [int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]

# === PostgreSQL ===
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

#DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# === Yandex Cloud ===
YC_API_KEY = os.getenv("YC_API_KEY")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID")
YC_AGENT_ID = os.getenv("YC_AGENT_ID")
YC_KB_ID = os.getenv("YC_KB_ID")

# === Парсер документации ===
PARSE_MAX_PAGES = int(os.getenv("PARSE_MAX_PAGES", "5000"))   # лимит страниц (защита от бесконечного обхода)
PARSE_DELAY_SECONDS = float(os.getenv("PARSE_DELAY_SECONDS", "1.5"))  # вежливая задержка между запросами

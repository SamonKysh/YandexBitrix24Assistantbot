from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

# Создаём движок базы данных
engine = create_engine(DATABASE_URL)

# Создаём фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для всех моделей
Base = declarative_base()

# Функция для получения сессии (используется в Telegram-боте)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
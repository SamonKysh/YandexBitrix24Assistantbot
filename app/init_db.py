from app.database.db import engine, Base
from app.database import models
from app.logger import logger

# Создаём таблицы в базе данных
Base.metadata.create_all(bind=engine)
logger.info("✅ Таблицы 'users' и 'chat_history' успешно созданы в базе данных!")
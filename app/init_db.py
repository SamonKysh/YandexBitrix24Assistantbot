from app.database.db import engine, Base
from app.database import models

# Создаём таблицы в базе данных
Base.metadata.create_all(bind=engine)
print("✅ Таблицы 'users' и 'chat_history' успешно созданы в базе данных!")
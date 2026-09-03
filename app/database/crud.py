from sqlalchemy.orm import Session
from .models import User, ChatHistory

def get_or_create_user(db: Session, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Получить пользователя по telegram_id или создать нового."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def save_message(db: Session, user_id: int, question: str, answer: str):
    """Сохранить вопрос и ответ в историю чата."""
    message = ChatHistory(user_id=user_id, question=question, answer=answer)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

def get_user_history(db: Session, user_id: int, limit: int = 10):
    """Получить последние сообщения пользователя."""
    return (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
        .all()
    )
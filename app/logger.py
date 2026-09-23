import logging
import re
import sys

class TokenFilter(logging.Filter):
    """Скрывает токены и секреты в логах."""
    PATTERNS = [
        re.compile(r'\b\d{8,10}:[A-Za-z0-9_-]{35}\b'),  # Telegram bot token
        re.compile(r'AQVN[A-Za-z0-9_-]{30,}'),           # YC API key
        re.compile(r'password["\s:=]+[^\s,}]+', re.I),    # passwords in logs
    ]
    
    def filter(self, record):
        if isinstance(record.msg, str):
            for pattern in self.PATTERNS:
                record.msg = pattern.sub('[REDACTED]', record.msg)
        return True

def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Создаёт логгер с фильтрацией секретов."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        handler.addFilter(TokenFilter())
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger

# Глобальный логгер для всего проекта
logger = setup_logger('bitrix_bot')
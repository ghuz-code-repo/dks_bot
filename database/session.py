from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from .models import Base

DATABASE_URL = "sqlite:///./data/bot_data.db"

# Оптимизированный движок с пулом соединений для SQLite
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Используем статический пул для SQLite
    echo=False  # Отключаем логирование SQL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()

def _run_migrations():
    """Добавляем недостающие колонки в существующую базу данных"""
    with engine.connect() as conn:
        # Миграция для таблицы bookings
        result = conn.execute(text("PRAGMA table_info(bookings)"))
        bookings_columns = {row[1] for row in result.fetchall()}
        
        # Добавляем user_telegram_id если отсутствует
        if 'user_telegram_id' not in bookings_columns:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN user_telegram_id INTEGER"))
            conn.commit()
        
        # Добавляем is_cancelled если отсутствует
        if 'is_cancelled' not in bookings_columns:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN is_cancelled BOOLEAN DEFAULT 0"))
            conn.commit()
        
        # Миграция для таблицы user_languages
        result = conn.execute(text("PRAGMA table_info(user_languages)"))
        user_lang_columns = {row[1] for row in result.fetchall()}
        
        # Добавляем phone если отсутствует
        if user_lang_columns and 'phone' not in user_lang_columns:
            conn.execute(text("ALTER TABLE user_languages ADD COLUMN phone TEXT"))
            conn.commit()
        
        # Миграция для таблицы project_slots (добавление адресов)
        result = conn.execute(text("PRAGMA table_info(project_slots)"))
        project_slots_columns = {row[1] for row in result.fetchall()}
        
        if project_slots_columns and 'address_ru' not in project_slots_columns:
            conn.execute(text("ALTER TABLE project_slots ADD COLUMN address_ru TEXT"))
            conn.commit()
        
        if project_slots_columns and 'address_uz' not in project_slots_columns:
            conn.execute(text("ALTER TABLE project_slots ADD COLUMN address_uz TEXT"))
            conn.commit()
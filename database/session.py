import logging
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

        # Миграция для таблицы contracts
        result = conn.execute(text("PRAGMA table_info(contracts)"))
        contracts_columns = {row[1] for row in result.fetchall()}

        # Добавляем username если отсутствует
        if contracts_columns and 'username' not in contracts_columns:
            conn.execute(text("ALTER TABLE contracts ADD COLUMN username TEXT"))
            conn.commit()

        # Добавляем href если отсутствует
        if contracts_columns and 'href' not in contracts_columns:
            conn.execute(text("ALTER TABLE contracts ADD COLUMN href TEXT"))
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

        if project_slots_columns and 'latitude' not in project_slots_columns:
            conn.execute(text("ALTER TABLE project_slots ADD COLUMN latitude TEXT"))
            conn.commit()

        if project_slots_columns and 'longitude' not in project_slots_columns:
            conn.execute(text("ALTER TABLE project_slots ADD COLUMN longitude TEXT"))
            conn.commit()

        # Создаём таблицу holidays если её ещё нет
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS holidays ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "date DATE UNIQUE NOT NULL, "
            "description TEXT)"
        ))
        conn.commit()

        # Создаём таблицу журнала изменений привязки договора, если её ещё нет
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS contract_binding_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "contract_id INTEGER NOT NULL, "
            "contract_num TEXT, "
            "action TEXT NOT NULL, "
            "old_telegram_id INTEGER, "
            "old_username TEXT, "
            "new_telegram_id INTEGER, "
            "new_username TEXT, "
            "admin_telegram_id INTEGER NOT NULL, "
            "admin_username TEXT, "
            "created_at DATETIME NOT NULL, "
            "note TEXT)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_contract_binding_log_contract_id "
            "ON contract_binding_log(contract_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_contract_binding_log_contract_num "
            "ON contract_binding_log(contract_num)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_contract_binding_log_admin_telegram_id "
            "ON contract_binding_log(admin_telegram_id)"
        ))
        conn.commit()

        # Защита от гонки при одновременных заявках: на один договор+дату+время
        # не может быть двух активных (не отменённых) записей.
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_slot "
                "ON bookings(contract_id, date, time_slot) WHERE is_cancelled = 0"
            ))
            conn.commit()
        except Exception:
            logging.exception(
                "Не удалось создать ux_bookings_active_slot — в таблице bookings "
                "уже есть дублирующиеся активные записи, требуется ручная чистка"
            )
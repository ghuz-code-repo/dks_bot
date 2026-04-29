from sqlalchemy import Column, Integer, String, Date, Time, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Holiday(Base):
    """Праздничные/нерабочие дни"""
    __tablename__ = 'holidays'
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)  # Описание праздника


class UserLanguage(Base):
    """Настройки пользователей (язык, телефон)"""
    __tablename__ = 'user_languages'
    telegram_id = Column(Integer, primary_key=True)
    language = Column(String, default='ru')  # 'ru' или 'uz'
    phone = Column(String, nullable=True)  # Сохранённый номер телефона


class Contract(Base):
    __tablename__ = 'contracts'
    id = Column(Integer, primary_key=True)
    house_name = Column(String)
    apt_num = Column(String)
    entrance = Column(String)  # Новое поле: Подъезд
    floor = Column(Integer)
    contract_num = Column(String, unique=True, index=True)
    client_fio = Column(String)
    delivery_date = Column(Date)  # Новое поле: Дата сдачи
    telegram_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True)  # Telegram @username (без @), если есть
    href = Column(String, nullable=True)  # Ссылка на профиль: https://t.me/<username> или tg://user?id=<id>

    bookings = relationship("Booking", back_populates="contract")


class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(Integer)


class ProjectSlots(Base):
    """Лимиты слотов и адреса для каждого проекта"""
    __tablename__ = 'project_slots'
    project_name = Column(String, primary_key=True)  # Название проекта (house_name)
    slots_limit = Column(Integer, default=1)  # Лимит записей на один слот
    address_ru = Column(String, nullable=True)  # Адрес на русском
    address_uz = Column(String, nullable=True)  # Адрес на узбекском
    latitude = Column(String, nullable=True)  # Широта (сохраняется как строка для точности)
    longitude = Column(String, nullable=True)  # Долгота (сохраняется как строка для точности)


class Staff(Base):
    __tablename__ = 'staff'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    role = Column(String)

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    user_telegram_id = Column(Integer, index=True, nullable=True)  # Кто создал запись
    date = Column(Date, index=True)
    time_slot = Column(Time)
    client_phone = Column(String)
    reminder_day_sent = Column(Boolean, default=False)
    reminder_hour_sent = Column(Boolean, default=False)
    is_cancelled = Column(Boolean, default=False)  # Флаг отмены
    contract = relationship("Contract", back_populates="bookings")


class ContractBindingLog(Base):
    """Журнал изменений привязки договора к Telegram-аккаунту."""
    __tablename__ = 'contract_binding_log'
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('contracts.id'), index=True, nullable=False)
    contract_num = Column(String, index=True, nullable=True)
    action = Column(String, nullable=False)  # 'unbind' | 'rebind' | 'bind'
    old_telegram_id = Column(Integer, nullable=True)
    old_username = Column(String, nullable=True)
    new_telegram_id = Column(Integer, nullable=True)
    new_username = Column(String, nullable=True)
    admin_telegram_id = Column(Integer, index=True, nullable=False)
    admin_username = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    note = Column(String, nullable=True)
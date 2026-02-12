from sqlalchemy import Column, Integer, String, Date, Time, ForeignKey, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


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

    bookings = relationship("Booking", back_populates="contract")


class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(Integer)


class ProjectSlots(Base):
    """Лимиты слотов для каждого проекта"""
    __tablename__ = 'project_slots'
    project_name = Column(String, primary_key=True)  # Название проекта (house_name)
    slots_limit = Column(Integer, default=1)  # Лимит записей на один слот


class Staff(Base):
    __tablename__ = 'staff'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    role = Column(String)

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    date = Column(Date, index=True)
    time_slot = Column(Time)
    client_phone = Column(String)
    reminder_day_sent = Column(Boolean, default=False)
    reminder_hour_sent = Column(Boolean, default=False)
    contract = relationship("Contract", back_populates="bookings")
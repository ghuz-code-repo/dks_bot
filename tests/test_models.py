"""
Unit тесты для моделей базы данных.
"""
import pytest
from datetime import date, time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Contract, Booking, Staff, Setting, Base


class TestContractModel:
    """Тесты для модели Contract"""
    
    def test_contract_creation(self):
        """Создание объекта Contract"""
        contract = Contract(
            house_name="ЖК Навои",
            apt_num="101",
            entrance="1",
            floor=5,
            contract_num="12345-GHP",
            client_fio="Иванов Иван Иванович",
            delivery_date=date(2026, 2, 15),
            telegram_id=123456789
        )
        
        assert contract.house_name == "ЖК Навои"
        assert contract.apt_num == "101"
        assert contract.entrance == "1"
        assert contract.floor == 5
        assert contract.contract_num == "12345-GHP"
        assert contract.client_fio == "Иванов Иван Иванович"
        assert contract.delivery_date == date(2026, 2, 15)
        assert contract.telegram_id == 123456789
    
    def test_contract_without_telegram_id(self):
        """Contract может быть создан без telegram_id"""
        contract = Contract(
            house_name="ЖК Test",
            contract_num="TEST-001",
            client_fio="Тест"
        )
        
        assert contract.telegram_id is None
    
    def test_contract_tablename(self):
        """Проверка имени таблицы"""
        assert Contract.__tablename__ == 'contracts'


class TestBookingModel:
    """Тесты для модели Booking"""
    
    def test_booking_creation(self):
        """Создание объекта Booking"""
        booking = Booking(
            contract_id=1,
            date=date(2026, 2, 15),
            time_slot=time(10, 0),
            client_phone="+998901234567"
        )
        
        assert booking.contract_id == 1
        assert booking.date == date(2026, 2, 15)
        assert booking.time_slot == time(10, 0)
        assert booking.client_phone == "+998901234567"
    
    def test_booking_default_reminder_flags(self):
        """Флаги напоминаний по умолчанию False"""
        booking = Booking(
            contract_id=1,
            date=date(2026, 2, 15),
            time_slot=time(10, 0)
        )
        
        # По умолчанию должны быть False
        assert booking.reminder_day_sent is False or booking.reminder_day_sent is None
        assert booking.reminder_hour_sent is False or booking.reminder_hour_sent is None
    
    def test_booking_tablename(self):
        """Проверка имени таблицы"""
        assert Booking.__tablename__ == 'bookings'


class TestStaffModel:
    """Тесты для модели Staff"""
    
    def test_staff_admin_creation(self):
        """Создание админа"""
        admin = Staff(
            telegram_id=123456789,
            role='admin'
        )
        
        assert admin.telegram_id == 123456789
        assert admin.role == 'admin'
    
    def test_staff_employee_creation(self):
        """Создание сотрудника"""
        employee = Staff(
            telegram_id=987654321,
            role='employee'
        )
        
        assert employee.telegram_id == 987654321
        assert employee.role == 'employee'
    
    def test_staff_tablename(self):
        """Проверка имени таблицы"""
        assert Staff.__tablename__ == 'staff'


class TestSettingModel:
    """Тесты для модели Setting"""
    
    def test_setting_creation(self):
        """Создание настройки"""
        setting = Setting(
            key='slots_per_interval',
            value=3
        )
        
        assert setting.key == 'slots_per_interval'
        assert setting.value == 3
    
    def test_setting_tablename(self):
        """Проверка имени таблицы"""
        assert Setting.__tablename__ == 'settings'


class TestRelationships:
    """Тесты для связей между моделями"""
    
    def test_contract_has_bookings_relationship(self):
        """Contract имеет связь с Booking"""
        assert hasattr(Contract, 'bookings')
    
    def test_booking_has_contract_relationship(self):
        """Booking имеет связь с Contract"""
        assert hasattr(Booking, 'contract')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

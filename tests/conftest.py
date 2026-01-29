"""
Конфигурация pytest и общие фикстуры.
"""
import pytest
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Мокаем переменные окружения до импорта модулей
os.environ.setdefault('BOT_TOKEN', 'test_token')
os.environ.setdefault('ADMIN_ID', '123456789')
os.environ.setdefault('EMPLOYEE_IDS', '')


@pytest.fixture
def sample_contract_data():
    """Пример данных договора"""
    return {
        'house_name': 'ЖК Навои',
        'apt_num': '101',
        'entrance': '1',
        'floor': 5,
        'contract_num': '12345-GHP',
        'client_fio': 'Иванов Иван Иванович',
        'delivery_date': '2026-02-15',
        'telegram_id': 123456789
    }


@pytest.fixture
def sample_booking_data():
    """Пример данных бронирования"""
    from datetime import date, time
    return {
        'contract_id': 1,
        'date': date(2026, 2, 15),
        'time_slot': time(10, 0),
        'client_phone': '+998901234567'
    }


@pytest.fixture
def mock_bot():
    """Мок Telegram бота"""
    from unittest.mock import AsyncMock
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_location = AsyncMock()
    return bot


@pytest.fixture
def mock_message():
    """Мок сообщения Telegram"""
    from unittest.mock import AsyncMock, MagicMock
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 123456789
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_callback():
    """Мок callback query"""
    from unittest.mock import AsyncMock, MagicMock
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 123456789
    callback.message = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.fixture
def mock_state():
    """Мок FSM состояния"""
    from unittest.mock import AsyncMock
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state

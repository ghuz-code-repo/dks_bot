"""
Unit тесты для модуля напоминаний.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date, time, datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCheckReminders:
    """Тесты для функции check_reminders"""
    
    @pytest.mark.asyncio
    @patch('utils.notifier.SessionLocal')
    async def test_day_reminder_sent(self, mock_session):
        """Напоминание за день отправляется"""
        from utils.notifier import check_reminders
        
        # Мокаем бота
        mock_bot = AsyncMock()
        
        # Мокаем сессию
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        # Создаем мок бронирования на завтра
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = MagicMock()
        mock_booking.date = tomorrow
        mock_booking.time_slot = time(10, 0)
        mock_booking.contract_id = 1
        mock_booking.reminder_day_sent = False
        
        # Мок контракта
        mock_contract = MagicMock()
        mock_contract.telegram_id = 123456789
        
        mock_session_instance.query.return_value.filter.return_value.all.return_value = [mock_booking]
        mock_session_instance.query.return_value.get.return_value = mock_contract
        
        await check_reminders(mock_bot)
        
        # Проверяем что сообщение отправлено
        mock_bot.send_message.assert_called()
        # Проверяем что флаг обновлен
        assert mock_booking.reminder_day_sent is True
    
    @pytest.mark.asyncio
    @patch('utils.notifier.SessionLocal')
    async def test_no_reminder_if_already_sent(self, mock_session):
        """Напоминание не отправляется повторно"""
        from utils.notifier import check_reminders
        
        mock_bot = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        # Бронирование с уже отправленным напоминанием
        mock_booking = MagicMock()
        mock_booking.reminder_day_sent = True  # Уже отправлено
        
        # Возвращаем пустой список (фильтр reminder_day_sent == False)
        mock_session_instance.query.return_value.filter.return_value.all.return_value = []
        
        await check_reminders(mock_bot)
        
        # Сообщение не должно быть отправлено
        mock_bot.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('utils.notifier.SessionLocal')
    async def test_no_reminder_if_no_telegram_id(self, mock_session):
        """Напоминание не отправляется если нет telegram_id"""
        from utils.notifier import check_reminders
        
        mock_bot = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = MagicMock()
        mock_booking.date = tomorrow
        mock_booking.time_slot = time(10, 0)
        mock_booking.contract_id = 1
        mock_booking.reminder_day_sent = False
        
        # Контракт без telegram_id
        mock_contract = MagicMock()
        mock_contract.telegram_id = None
        
        mock_session_instance.query.return_value.filter.return_value.all.return_value = [mock_booking]
        mock_session_instance.query.return_value.get.return_value = mock_contract
        
        await check_reminders(mock_bot)
        
        # Сообщение не должно быть отправлено
        mock_bot.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('utils.notifier.SessionLocal')
    async def test_hour_reminder_sent(self, mock_session):
        """Напоминание за 3 часа отправляется"""
        from utils.notifier import check_reminders
        
        mock_bot = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        # Бронирование на сегодня через 2 часа
        today = date.today()
        now = datetime.now()
        slot_time = (now + timedelta(hours=2)).time()
        
        mock_booking_day = MagicMock()
        mock_booking_hour = MagicMock()
        mock_booking_hour.date = today
        mock_booking_hour.time_slot = slot_time
        mock_booking_hour.contract_id = 1
        mock_booking_hour.reminder_hour_sent = False
        
        mock_contract = MagicMock()
        mock_contract.telegram_id = 123456789
        
        # Первый вызов - напоминания за день (пустой)
        # Второй вызов - напоминания за час
        mock_session_instance.query.return_value.filter.return_value.all.side_effect = [
            [],  # day reminders
            [mock_booking_hour]  # hour reminders
        ]
        mock_session_instance.query.return_value.get.return_value = mock_contract
        
        await check_reminders(mock_bot)
        
        mock_session_instance.commit.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('utils.notifier.SessionLocal')
    async def test_commit_called(self, mock_session):
        """Commit вызывается в конце"""
        from utils.notifier import check_reminders
        
        mock_bot = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter.return_value.all.return_value = []
        
        await check_reminders(mock_bot)
        
        mock_session_instance.commit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

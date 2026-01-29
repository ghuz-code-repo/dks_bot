"""
Unit тесты для обработчиков (handlers).
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date, time, datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAdminHandlers:
    """Тесты для административных обработчиков"""
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_add_admin_new_user(self, mock_session):
        """Добавление нового администратора"""
        from handlers.admin import add_admin_cmd
        
        mock_message = AsyncMock()
        mock_message.text = "/add_admin 123456789"
        mock_message.from_user.id = 1  # Admin ID
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        await add_admin_cmd(mock_message)
        
        mock_message.answer.assert_called()
        assert "123456789" in str(mock_message.answer.call_args)
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_add_admin_existing_user(self, mock_session):
        """Обновление роли существующего пользователя на администратора"""
        from handlers.admin import add_admin_cmd
        
        mock_message = AsyncMock()
        mock_message.text = "/add_admin 123456789"
        
        existing_staff = MagicMock()
        existing_staff.role = 'employee'
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = existing_staff
        
        await add_admin_cmd(mock_message)
        
        assert existing_staff.role == 'admin'
    
    @pytest.mark.asyncio
    async def test_add_admin_invalid_format(self):
        """Неверный формат команды add_admin"""
        from handlers.admin import add_admin_cmd
        
        mock_message = AsyncMock()
        mock_message.text = "/add_admin"  # Без ID
        
        await add_admin_cmd(mock_message)
        
        mock_message.answer.assert_called()
        assert "Использование" in str(mock_message.answer.call_args)
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_add_employee(self, mock_session):
        """Добавление сотрудника"""
        from handlers.admin import add_employee_cmd
        
        mock_message = AsyncMock()
        mock_message.text = "/add_employee 987654321"
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        await add_employee_cmd(mock_message)
        
        mock_message.answer.assert_called()
        assert "987654321" in str(mock_message.answer.call_args)
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_list_staff_empty(self, mock_session):
        """Пустой список персонала"""
        from handlers.admin import list_staff
        
        mock_message = AsyncMock()
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.all.return_value = []
        
        await list_staff(mock_message)
        
        mock_message.answer.assert_called()
        assert "пуст" in str(mock_message.answer.call_args).lower()
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_list_staff_with_members(self, mock_session):
        """Список персонала с участниками"""
        from handlers.admin import list_staff
        
        mock_message = AsyncMock()
        
        staff1 = MagicMock()
        staff1.telegram_id = 111
        staff1.role = 'admin'
        
        staff2 = MagicMock()
        staff2.telegram_id = 222
        staff2.role = 'employee'
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.all.return_value = [staff1, staff2]
        
        await list_staff(mock_message)
        
        call_text = str(mock_message.answer.call_args)
        assert "111" in call_text
        assert "222" in call_text
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_set_slots(self, mock_session):
        """Установка лимита слотов"""
        from handlers.admin import cmd_set_slots
        
        mock_message = AsyncMock()
        mock_message.text = "/set_slots 5"
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        await cmd_set_slots(mock_message)
        
        mock_message.answer.assert_called()
        assert "5" in str(mock_message.answer.call_args)
    
    @pytest.mark.asyncio
    @patch('handlers.admin.SessionLocal')
    async def test_remove_staff(self, mock_session):
        """Удаление сотрудника"""
        from handlers.admin import remove_staff_cmd
        
        mock_message = AsyncMock()
        mock_message.text = "/del_staff 123456789"
        
        mock_staff = MagicMock()
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = mock_staff
        
        await remove_staff_cmd(mock_message)
        
        mock_session_instance.delete.assert_called_with(mock_staff)
        mock_message.answer.assert_called()


class TestCommonHandlers:
    """Тесты для общих обработчиков"""
    
    @pytest.mark.asyncio
    @patch('handlers.common.is_admin')
    @patch('handlers.common.SessionLocal')
    async def test_start_for_admin(self, mock_session, mock_is_admin):
        """Команда /start для администратора"""
        from handlers.common import cmd_start
        
        mock_is_admin.return_value = True
        
        mock_message = AsyncMock()
        mock_message.from_user.id = 123456789
        
        mock_state = AsyncMock()
        
        await cmd_start(mock_message, mock_state)
        
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called()
        # Проверяем что показано админ-меню
        call_text = str(mock_message.answer.call_args)
        assert "Админ" in call_text or "report" in call_text.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.common.is_admin')
    @patch('handlers.common.SessionLocal')
    async def test_start_for_client(self, mock_session, mock_is_admin):
        """Команда /start для клиента"""
        from handlers.common import cmd_start
        
        mock_is_admin.return_value = False
        
        mock_message = AsyncMock()
        mock_message.from_user.id = 999999999
        
        mock_state = AsyncMock()
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = ['ЖК Навои']
        
        await cmd_start(mock_message, mock_state)
        
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called()
    
    @pytest.mark.asyncio
    @patch('handlers.common.is_admin')
    @patch('handlers.common.SessionLocal')
    async def test_start_no_houses_available(self, mock_session, mock_is_admin):
        """Команда /start когда нет доступных домов"""
        from handlers.common import cmd_start
        
        mock_is_admin.return_value = False
        
        mock_message = AsyncMock()
        mock_state = AsyncMock()
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = []
        
        await cmd_start(mock_message, mock_state)
        
        call_text = str(mock_message.answer.call_args).lower()
        assert "нет" in call_text or "пуст" in call_text


class TestClientHandlers:
    """Тесты для клиентских обработчиков"""
    
    @pytest.mark.asyncio
    async def test_house_selected(self):
        """Выбор дома"""
        from handlers.client import house_selected
        
        mock_callback = AsyncMock()
        mock_callback.data = "house_ЖК Навои"
        mock_callback.message = AsyncMock()
        
        mock_state = AsyncMock()
        
        await house_selected(mock_callback, mock_state)
        
        mock_state.update_data.assert_called_with(selected_house="ЖК Навои")
        mock_callback.answer.assert_called()
    
    @pytest.mark.asyncio
    @patch('handlers.client.SessionLocal')
    async def test_contract_not_found(self, mock_session):
        """Договор не найден"""
        from handlers.client import contract_entered
        
        mock_message = AsyncMock()
        mock_message.text = "INVALID-CONTRACT"
        
        mock_state = AsyncMock()
        mock_state.get_data.return_value = {'selected_house': 'ЖК Навои'}
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter.return_value.first.return_value = None
        
        await contract_entered(mock_message, mock_state)
        
        mock_message.answer.assert_called()
        call_text = str(mock_message.answer.call_args).lower()
        assert "не найден" in call_text or "topilmadi" in call_text.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.client.SessionLocal')
    @patch('handlers.client.get_min_booking_date')
    async def test_date_before_min_date_rejected(self, mock_min_date, mock_session):
        """Дата раньше минимальной отклоняется"""
        from handlers.client import date_selected
        
        mock_min_date.return_value = date(2026, 2, 5)
        
        mock_callback = AsyncMock()
        mock_callback.data = "date_2026-02-03"  # Раньше минимальной
        
        mock_state = AsyncMock()
        
        await date_selected(mock_callback, mock_state)
        
        mock_callback.answer.assert_called()
        call_args = mock_callback.answer.call_args
        assert call_args.kwargs.get('show_alert') is True
    
    @pytest.mark.asyncio
    @patch('handlers.client.SessionLocal')
    @patch('handlers.client.get_min_booking_date')
    async def test_weekend_date_rejected(self, mock_min_date, mock_session):
        """Выходные дни отклоняются"""
        from handlers.client import date_selected
        
        mock_min_date.return_value = date(2026, 1, 29)
        
        mock_callback = AsyncMock()
        mock_callback.data = "date_2026-01-31"  # Суббота
        
        mock_state = AsyncMock()
        
        await date_selected(mock_callback, mock_state)
        
        mock_callback.answer.assert_called()
        call_text = str(mock_callback.answer.call_args)
        assert "рабочие дни" in call_text.lower() or "пн-пт" in call_text.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.client.SessionLocal')
    async def test_time_slot_full_rejected(self, mock_session):
        """Занятый слот отклоняется"""
        from handlers.client import time_selected
        
        mock_callback = AsyncMock()
        mock_callback.data = "time_2026-02-02_10:00"
        
        mock_state = AsyncMock()
        
        # Мокаем что слот полностью занят
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        mock_setting = MagicMock()
        mock_setting.value = 2
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = mock_setting
        mock_session_instance.query.return_value.filter.return_value.count.return_value = 2  # Полностью занят
        
        await time_selected(mock_callback, mock_state)
        
        mock_callback.answer.assert_called()
        call_args = mock_callback.answer.call_args
        assert call_args.kwargs.get('show_alert') is True


class TestIsAdminFilter:
    """Тесты для фильтра IsAdminFilter"""
    
    @pytest.mark.asyncio
    @patch('handlers.admin.is_admin')
    async def test_admin_passes_filter(self, mock_is_admin):
        """Администратор проходит фильтр"""
        from handlers.admin import IsAdminFilter
        
        mock_is_admin.return_value = True
        
        filter_instance = IsAdminFilter()
        mock_message = MagicMock()
        mock_message.from_user.id = 123456789
        
        result = await filter_instance(mock_message)
        
        assert result is True
    
    @pytest.mark.asyncio
    @patch('handlers.admin.is_admin')
    async def test_non_admin_fails_filter(self, mock_is_admin):
        """Не-администратор не проходит фильтр"""
        from handlers.admin import IsAdminFilter
        
        mock_is_admin.return_value = False
        
        filter_instance = IsAdminFilter()
        mock_message = MagicMock()
        mock_message.from_user.id = 999999999
        
        result = await filter_instance(mock_message)
        
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

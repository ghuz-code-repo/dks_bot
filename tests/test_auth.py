"""
Unit тесты для модуля авторизации.
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIsAdmin:
    """Тесты для функции is_admin"""
    
    @patch('utils.auth.ADMIN_ID', 123456789)
    @patch('utils.auth.SessionLocal')
    def test_super_admin_returns_true(self, mock_session):
        """Супер-админ из config.py возвращает True"""
        from utils.auth import is_admin
        
        result = is_admin(123456789)
        assert result is True
        # База не должна вызываться для супер-админа
        mock_session.assert_not_called()
    
    @patch('utils.auth.ADMIN_ID', 123456789)
    @patch('utils.auth.SessionLocal')
    def test_db_admin_returns_true(self, mock_session):
        """Админ из базы данных возвращает True"""
        from utils.auth import is_admin
        
        # Мокаем сессию и запрос
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        # Создаем мок объекта Staff с ролью admin
        mock_staff = MagicMock()
        mock_staff.role = 'admin'
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = mock_staff
        
        result = is_admin(987654321)
        assert result is True
    
    @patch('utils.auth.ADMIN_ID', 123456789)
    @patch('utils.auth.SessionLocal')
    def test_employee_returns_false(self, mock_session):
        """Сотрудник (не админ) возвращает False"""
        from utils.auth import is_admin
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        result = is_admin(111222333)
        assert result is False
    
    @patch('utils.auth.ADMIN_ID', 123456789)
    @patch('utils.auth.SessionLocal')
    def test_unknown_user_returns_false(self, mock_session):
        """Неизвестный пользователь возвращает False"""
        from utils.auth import is_admin
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        result = is_admin(999999999)
        assert result is False


class TestGetStaffIds:
    """Тесты для функции get_staff_ids"""
    
    @patch('utils.auth.SessionLocal')
    def test_get_all_staff(self, mock_session):
        """Получение всех сотрудников"""
        from utils.auth import get_staff_ids
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        # Мокаем результат запроса
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = [
            111, 222, 333
        ]
        
        result = get_staff_ids()
        assert result == [111, 222, 333]
    
    @patch('utils.auth.SessionLocal')
    def test_get_admins_only(self, mock_session):
        """Получение только админов"""
        from utils.auth import get_staff_ids
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = [111]
        
        result = get_staff_ids(role='admin')
        assert result == [111]
    
    @patch('utils.auth.SessionLocal')
    def test_get_employees_only(self, mock_session):
        """Получение только сотрудников"""
        from utils.auth import get_staff_ids
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = [222, 333]
        
        result = get_staff_ids(role='employee')
        assert result == [222, 333]
    
    @patch('utils.auth.SessionLocal')
    def test_empty_result(self, mock_session):
        """Пустой результат"""
        from utils.auth import get_staff_ids
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.execute.return_value.scalars.return_value.all.return_value = []
        
        result = get_staff_ids()
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

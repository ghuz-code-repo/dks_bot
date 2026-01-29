"""
Unit тесты для модуля обработки Excel файлов.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProcessExcelFile:
    """Тесты для функции process_excel_file"""
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_process_new_contracts(self, mock_read_excel, mock_session):
        """Обработка новых договоров"""
        from utils.excel_reader import process_excel_file
        
        # Создаем тестовый DataFrame
        test_data = pd.DataFrame({
            'Номер договора': ['12345-GHP', '67890-ABC'],
            'Название дома': ['ЖК Навои', 'ЖК Sunrise'],
            'Номер квартиры': ['101', '202'],
            'Подьезд': ['1', '2'],
            'Этаж': [5, 10],
            'ФИО клиента': ['Иванов Иван', 'Петров Петр'],
            'Дата сдачи': ['15.02.2026', '20.03.2026']
        })
        mock_read_excel.return_value = test_data
        
        # Мокаем сессию
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        result = process_excel_file("test.xlsx")
        
        assert result == 2
        assert mock_session_instance.add.call_count == 2
        mock_session_instance.commit.assert_called_once()
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_update_existing_contract(self, mock_read_excel, mock_session):
        """Обновление существующего договора"""
        from utils.excel_reader import process_excel_file
        
        test_data = pd.DataFrame({
            'Номер договора': ['12345-GHP'],
            'Название дома': ['ЖК Навои Обновленный'],
            'Номер квартиры': ['101'],
            'Подьезд': ['1'],
            'Этаж': [5],
            'ФИО клиента': ['Иванов Иван Иванович'],
            'Дата сдачи': ['15.02.2026']
        })
        mock_read_excel.return_value = test_data
        
        # Мокаем существующий договор
        existing_contract = MagicMock()
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = existing_contract
        
        result = process_excel_file("test.xlsx")
        
        assert result == 1
        # Не должен добавлять новый, а обновить существующий
        mock_session_instance.add.assert_not_called()
        # Проверяем что атрибуты обновлены
        assert existing_contract.house_name == 'ЖК Навои Обновленный'
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_contract_number_normalized(self, mock_read_excel, mock_session):
        """Номер договора нормализуется (убираются пробелы, верхний регистр)"""
        from utils.excel_reader import process_excel_file
        
        test_data = pd.DataFrame({
            'Номер договора': ['  12345-ghp  '],  # С пробелами и в нижнем регистре
            'Название дома': ['ЖК Test'],
            'Номер квартиры': ['101'],
            'Подьезд': ['1'],
            'Этаж': [5],
            'ФИО клиента': ['Тест'],
            'Дата сдачи': ['15.02.2026']
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        process_excel_file("test.xlsx")
        
        # Проверяем что номер договора нормализован
        call_args = mock_session_instance.add.call_args[0][0]
        assert call_args.contract_num == '12345-GHP'
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_date_parsing_string_format(self, mock_read_excel, mock_session):
        """Парсинг даты из строкового формата"""
        from utils.excel_reader import process_excel_file
        
        test_data = pd.DataFrame({
            'Номер договора': ['12345-GHP'],
            'Название дома': ['ЖК Test'],
            'Номер квартиры': ['101'],
            'Подьезд': ['1'],
            'Этаж': [5],
            'ФИО клиента': ['Тест'],
            'Дата сдачи': ['25.12.2026']  # Строковый формат
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        process_excel_file("test.xlsx")
        
        call_args = mock_session_instance.add.call_args[0][0]
        assert call_args.delivery_date == date(2026, 12, 25)
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_date_parsing_datetime_format(self, mock_read_excel, mock_session):
        """Парсинг даты из datetime формата"""
        from utils.excel_reader import process_excel_file
        from datetime import datetime
        
        test_data = pd.DataFrame({
            'Номер договора': ['12345-GHP'],
            'Название дома': ['ЖК Test'],
            'Номер квартиры': ['101'],
            'Подьезд': ['1'],
            'Этаж': [5],
            'ФИО клиента': ['Тест'],
            'Дата сдачи': [datetime(2026, 12, 25)]  # datetime формат
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        process_excel_file("test.xlsx")
        
        call_args = mock_session_instance.add.call_args[0][0]
        assert call_args.delivery_date == date(2026, 12, 25)
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_empty_dataframe(self, mock_read_excel, mock_session):
        """Обработка пустого файла"""
        from utils.excel_reader import process_excel_file
        
        test_data = pd.DataFrame(columns=[
            'Номер договора', 'Название дома', 'Номер квартиры',
            'Подьезд', 'Этаж', 'ФИО клиента', 'Дата сдачи'
        ])
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        result = process_excel_file("test.xlsx")
        
        assert result == 0
        mock_session_instance.add.assert_not_called()
    
    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_column_names_stripped(self, mock_read_excel, mock_session):
        """Пробелы в названиях колонок убираются"""
        from utils.excel_reader import process_excel_file
        
        # Колонки с пробелами
        test_data = pd.DataFrame({
            '  Номер договора  ': ['12345-GHP'],
            ' Название дома': ['ЖК Test'],
            'Номер квартиры ': ['101'],
            ' Подьезд ': ['1'],
            'Этаж': [5],
            'ФИО клиента': ['Тест'],
            'Дата сдачи': ['15.02.2026']
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        # Не должно вызывать ошибку
        result = process_excel_file("test.xlsx")
        assert result == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

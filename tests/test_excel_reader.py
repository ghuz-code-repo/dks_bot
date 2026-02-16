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
            'Подъезд': ['1', '2'],
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
        
        assert result == (2, 'ЖК Навои')
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
            'Подъезд': ['1'],
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
        
        assert result == (1, 'ЖК Навои Обновленный')
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
            'Подъезд': ['1'],
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
            'Подъезд': ['1'],
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
            'Подъезд': ['1'],
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
            'Подъезд', 'Этаж', 'ФИО клиента', 'Дата сдачи'
        ])
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        
        result = process_excel_file("test.xlsx")
        
        assert result == (0, None)
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
            ' Подъезд ': ['1'],
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
        assert result == (1, 'ЖК Test')

    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_positional_fallback_when_headers_wrong(self, mock_read_excel, mock_session):
        """Позиционный доступ когда заголовки не совпадают"""
        from utils.excel_reader import process_excel_file
        
        # Столбцы названы по-другому, но данные в правильном порядке
        test_data = pd.DataFrame({
            'House': ['ЖК Навои'],
            'Apt': ['101'],
            'Entrance': ['1'],
            'Floor': [5],
            'Contract': ['12345-GHP'],
            'FIO': ['Иванов Иван'],
            'Date': ['15.02.2026']
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        result = process_excel_file("test.xlsx")
        
        assert result == (1, 'ЖК Навои')
        call_args = mock_session_instance.add.call_args[0][0]
        assert call_args.house_name == 'ЖК Навои'
        assert call_args.apt_num == '101'
        assert call_args.contract_num == '12345-GHP'
        assert call_args.client_fio == 'Иванов Иван'

    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_positional_fallback_too_few_columns(self, mock_read_excel, mock_session):
        """Ошибка если столбцов меньше чем ожидается и заголовки не совпадают"""
        from utils.excel_reader import process_excel_file
        
        # Только 3 столбца с неправильными именами
        test_data = pd.DataFrame({
            'A': ['val1'],
            'B': ['val2'],
            'C': ['val3'],
        })
        mock_read_excel.return_value = test_data
        
        with pytest.raises(ValueError, match="столбцов"):
            process_excel_file("test.xlsx")

    @patch('utils.excel_reader.SessionLocal')
    @patch('utils.excel_reader.pd.read_excel')
    def test_partial_headers_uses_positional(self, mock_read_excel, mock_session):
        """Если только часть заголовков совпадает — используется позиционный доступ"""
        from utils.excel_reader import process_excel_file
        
        # Часть заголовков правильная, часть — нет
        test_data = pd.DataFrame({
            'Название дома': ['ЖК Навои'],
            'Номер квартиры': ['101'],
            'Подъезд': ['1'],
            'Этаж': [5],
            'Contract Number': ['12345-GHP'],   # Неправильное название
            'ФИО клиента': ['Иванов Иван'],
            'Дата сдачи': ['15.02.2026']
        })
        mock_read_excel.return_value = test_data
        
        mock_session_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter_by.return_value.first.return_value = None
        
        result = process_excel_file("test.xlsx")
        
        # Должен использовать позиционный маппинг
        assert result == (1, 'ЖК Навои')
        call_args = mock_session_instance.add.call_args[0][0]
        assert call_args.house_name == 'ЖК Навои'
        assert call_args.contract_num == '12345-GHP'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

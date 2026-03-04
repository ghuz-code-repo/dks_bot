"""
Unit тесты для функциональности праздничных дней.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date, datetime
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Holiday


class TestHolidayModel:
    """Тесты для модели Holiday"""

    def test_holiday_creation(self):
        """Создание объекта Holiday"""
        h = Holiday(date=date(2026, 3, 8), description="Международный женский день")
        assert h.date == date(2026, 3, 8)
        assert h.description == "Международный женский день"

    def test_holiday_without_description(self):
        """Holiday может быть создан без описания"""
        h = Holiday(date=date(2026, 1, 1))
        assert h.description is None

    def test_holiday_tablename(self):
        """Проверка имени таблицы"""
        assert Holiday.__tablename__ == 'holidays'


class TestGetHolidayDates:
    """Тесты для функции get_holiday_dates"""

    @patch('utils.holidays.SessionLocal')
    def test_returns_dates_in_range(self, mock_session):
        """Возвращает даты в указанном диапазоне"""
        from utils.holidays import get_holiday_dates

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_sess.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            (date(2026, 3, 8),),
            (date(2026, 3, 21),),
        ]

        result = get_holiday_dates(date(2026, 3, 1), date(2026, 3, 31))
        assert date(2026, 3, 8) in result
        assert date(2026, 3, 21) in result
        assert len(result) == 2

    @patch('utils.holidays.SessionLocal')
    def test_returns_empty_set_when_no_holidays(self, mock_session):
        """Пустое множество когда праздников нет"""
        from utils.holidays import get_holiday_dates

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_sess.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = get_holiday_dates(date(2026, 1, 1), date(2026, 1, 31))
        assert result == set()

    def test_returns_empty_set_on_db_error(self):
        """Возвращает пустое множество при ошибке БД"""
        from utils.holidays import get_holiday_dates

        with patch('utils.holidays.SessionLocal', side_effect=Exception("no table")):
            result = get_holiday_dates(date(2026, 1, 1), date(2026, 12, 31))
            assert result == set()


class TestGenerateHolidaysExcel:
    """Тесты для функции generate_holidays_excel"""

    @patch('utils.holidays.get_all_holidays')
    @patch('utils.holidays.pd.DataFrame.to_excel')
    def test_generates_file_with_holidays(self, mock_to_excel, mock_get_all):
        """Генерирует Excel с текущими праздниками"""
        from utils.holidays import generate_holidays_excel

        h1 = MagicMock()
        h1.date = date(2026, 1, 1)
        h1.description = "Новый год"
        h2 = MagicMock()
        h2.date = date(2026, 3, 8)
        h2.description = ""
        mock_get_all.return_value = [h1, h2]

        result = generate_holidays_excel()
        assert result.endswith(".xlsx")
        mock_to_excel.assert_called_once()

    @patch('utils.holidays.get_all_holidays')
    @patch('utils.holidays.pd.DataFrame.to_excel')
    def test_generates_empty_template(self, mock_to_excel, mock_get_all):
        """Генерирует пустой шаблон если праздников нет"""
        from utils.holidays import generate_holidays_excel

        mock_get_all.return_value = []

        result = generate_holidays_excel()
        assert result.endswith(".xlsx")
        mock_to_excel.assert_called_once()


class TestImportHolidaysFromExcel:
    """Тесты для функции import_holidays_from_excel"""

    @patch('utils.holidays.SessionLocal')
    @patch('utils.holidays.pd.read_excel')
    def test_import_valid_file(self, mock_read_excel, mock_session):
        """Импорт корректного файла"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': ['01.01.2026', '08.03.2026', '09.05.2026'],
            'Описание': ['Новый год', 'Женский день', 'День Победы'],
        })

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        result = import_holidays_from_excel("test.xlsx")
        assert result == 3
        mock_sess.query.return_value.delete.assert_called_once()
        assert mock_sess.add.call_count == 3
        mock_sess.commit.assert_called_once()

    @patch('utils.holidays.SessionLocal')
    @patch('utils.holidays.pd.read_excel')
    def test_import_empty_file_clears_holidays(self, mock_read_excel, mock_session):
        """Пустой файл удаляет все праздники"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': [],
            'Описание': [],
        })

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        result = import_holidays_from_excel("test.xlsx")
        assert result == 0
        mock_sess.query.return_value.delete.assert_called_once()
        assert mock_sess.add.call_count == 0

    @patch('utils.holidays.SessionLocal')
    @patch('utils.holidays.pd.read_excel')
    def test_import_deduplicates_dates(self, mock_read_excel, mock_session):
        """Дубликаты дат пропускаются"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': ['01.01.2026', '01.01.2026', '08.03.2026'],
            'Описание': ['Новый год', 'Дубль', 'Женский день'],
        })

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        result = import_holidays_from_excel("test.xlsx")
        assert result == 2  # Только 2 уникальные даты

    @patch('utils.holidays.pd.read_excel')
    def test_import_invalid_date_raises_error(self, mock_read_excel):
        """Некорректная дата вызывает ValueError"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': ['not-a-date'],
            'Описание': ['Тест'],
        })

        with pytest.raises(ValueError, match="не удалось распознать дату"):
            import_holidays_from_excel("test.xlsx")

    @patch('utils.holidays.SessionLocal')
    @patch('utils.holidays.pd.read_excel')
    def test_import_without_description_column(self, mock_read_excel, mock_session):
        """Импорт файла без столбца Описание"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': ['01.01.2026'],
        })

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        result = import_holidays_from_excel("test.xlsx")
        assert result == 1

    @patch('utils.holidays.SessionLocal')
    @patch('utils.holidays.pd.read_excel')
    def test_import_various_date_formats(self, mock_read_excel, mock_session):
        """Импорт дат в различных форматах"""
        from utils.holidays import import_holidays_from_excel

        mock_read_excel.return_value = pd.DataFrame({
            'Дата': ['01.01.2026', '2026-03-08', '09/05/2026'],
            'Описание': ['ДД.ММ.ГГГГ', 'ГГГГ-ММ-ДД', 'ДД/ММ/ГГГГ'],
        })

        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        result = import_holidays_from_excel("test.xlsx")
        assert result == 3


class TestParseDate:
    """Тесты для функции _parse_date"""

    def test_parse_dd_mm_yyyy(self):
        from utils.holidays import _parse_date
        assert _parse_date("01.01.2026") == date(2026, 1, 1)

    def test_parse_yyyy_mm_dd(self):
        from utils.holidays import _parse_date
        assert _parse_date("2026-03-08") == date(2026, 3, 8)

    def test_parse_dd_slash_mm_slash_yyyy(self):
        from utils.holidays import _parse_date
        assert _parse_date("08/03/2026") == date(2026, 3, 8)

    def test_parse_datetime_object(self):
        from utils.holidays import _parse_date
        dt = datetime(2026, 5, 9, 12, 0)
        assert _parse_date(dt) == date(2026, 5, 9)

    def test_parse_date_object(self):
        from utils.holidays import _parse_date
        d = date(2026, 1, 1)
        assert _parse_date(d) == date(2026, 1, 1)

    def test_parse_invalid_returns_none(self):
        from utils.holidays import _parse_date
        assert _parse_date("not-a-date-at-all") is None


class TestCalendarHolidayIntegration:
    """Тесты интеграции праздников с календарём"""

    @patch('keyboards.inline.get_holiday_dates')
    def test_holiday_date_not_selectable(self, mock_holidays):
        """Праздничный день не доступен для записи"""
        from keyboards.inline import generate_calendar

        holiday = date(2026, 4, 15)  # Среда
        mock_holidays.return_value = {holiday}

        with patch('keyboards.inline.get_min_booking_date', return_value=date(2026, 4, 1)):
            markup = generate_calendar(
                year=2026, month=4,
                min_date=date(2026, 4, 1),
            )

        # Получаем все callback_data из кнопок
        all_callbacks = []
        for row in markup.inline_keyboard:
            for btn in row:
                all_callbacks.append(btn.callback_data)

        # Праздничная дата НЕ должна быть доступна
        assert f"date_{holiday}" not in all_callbacks

    @patch('keyboards.inline.get_holiday_dates')
    def test_non_holiday_weekday_still_selectable(self, mock_holidays):
        """Обычный рабочий день остаётся доступным"""
        from keyboards.inline import generate_calendar

        mock_holidays.return_value = set()  # Нет праздников

        with patch('keyboards.inline.get_min_booking_date', return_value=date(2026, 4, 1)):
            markup = generate_calendar(
                year=2026, month=4,
                min_date=date(2026, 4, 1),
            )

        # Среда 15 апреля — обычный рабочий день, должна быть доступна
        all_callbacks = []
        for row in markup.inline_keyboard:
            for btn in row:
                all_callbacks.append(btn.callback_data)

        assert f"date_2026-04-15" in all_callbacks

    @patch('keyboards.inline.get_holiday_dates')
    def test_get_next_working_day_skips_holidays(self, mock_holidays):
        """get_next_working_day пропускает праздники"""
        from keyboards.inline import get_next_working_day

        # Вторник — праздник, поэтому следующий рабочий после понедельника — среда
        mock_holidays.return_value = {date(2026, 1, 27)}  # Вторник

        result = get_next_working_day(date(2026, 1, 26))  # Понедельник
        assert result == date(2026, 1, 28)  # Среда


class TestAdminHolidayStates:
    """Тесты для состояний FSM праздников"""

    def test_holidays_waiting_excel_state_exists(self):
        """Состояние holidays_waiting_excel существует"""
        from utils.states import AdminSteps
        assert hasattr(AdminSteps, 'holidays_waiting_excel')

    def test_holidays_state_in_admin_steps(self):
        """Состояние holidays_waiting_excel — часть AdminSteps"""
        from utils.states import AdminSteps
        state = AdminSteps.holidays_waiting_excel
        assert state is not None

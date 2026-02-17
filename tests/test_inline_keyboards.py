"""
Unit тесты для функций генерации клавиатур и расчёта дат.
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from keyboards.inline import (
    get_next_working_day,
    get_min_booking_date,
    generate_time_slots,
    generate_houses_kb,
    generate_calendar,
    get_fully_booked_dates,
    SLOTS_PER_DAY
)


class TestGetNextWorkingDay:
    """Тесты для функции get_next_working_day"""
    
    def test_monday_returns_tuesday(self):
        """Понедельник -> Вторник"""
        monday = date(2026, 1, 26)  # Понедельник
        result = get_next_working_day(monday)
        assert result == date(2026, 1, 27)  # Вторник
        assert result.weekday() == 1  # 1 = Вторник
    
    def test_tuesday_returns_wednesday(self):
        """Вторник -> Среда"""
        tuesday = date(2026, 1, 27)
        result = get_next_working_day(tuesday)
        assert result == date(2026, 1, 28)  # Среда
    
    def test_wednesday_returns_thursday(self):
        """Среда -> Четверг"""
        wednesday = date(2026, 1, 28)
        result = get_next_working_day(wednesday)
        assert result == date(2026, 1, 29)  # Четверг
    
    def test_thursday_returns_friday(self):
        """Четверг -> Пятница"""
        thursday = date(2026, 1, 29)
        result = get_next_working_day(thursday)
        assert result == date(2026, 1, 30)  # Пятница
    
    def test_friday_returns_monday(self):
        """Пятница -> Понедельник (пропускает выходные)"""
        friday = date(2026, 1, 30)
        result = get_next_working_day(friday)
        assert result == date(2026, 2, 2)  # Понедельник
        assert result.weekday() == 0  # 0 = Понедельник
    
    def test_saturday_returns_monday(self):
        """Суббота -> Понедельник"""
        saturday = date(2026, 1, 31)
        result = get_next_working_day(saturday)
        assert result == date(2026, 2, 2)  # Понедельник
    
    def test_sunday_returns_monday(self):
        """Воскресенье -> Понедельник"""
        sunday = date(2026, 2, 1)
        result = get_next_working_day(sunday)
        assert result == date(2026, 2, 2)  # Понедельник


class TestGetMinBookingDate:
    """Тесты для функции get_min_booking_date"""
    
    def test_before_noon_wednesday_returns_thursday(self):
        """Среда 11:59 -> Четверг (следующий рабочий день)"""
        mock_time = datetime(2026, 1, 28, 11, 59)  # Среда 11:59
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 1, 29)  # Четверг
    
    def test_after_noon_wednesday_returns_friday(self):
        """Среда 12:01 -> Пятница (через один рабочий день)"""
        mock_time = datetime(2026, 1, 28, 12, 1)  # Среда 12:01
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 1, 30)  # Пятница
    
    def test_before_noon_thursday_returns_friday(self):
        """Четверг 11:59 -> Пятница"""
        mock_time = datetime(2026, 1, 29, 11, 59)  # Четверг 11:59
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 1, 30)  # Пятница
    
    def test_after_noon_thursday_returns_monday(self):
        """Четверг 12:01 -> Понедельник (пропускает пятницу и выходные)"""
        mock_time = datetime(2026, 1, 29, 12, 1)  # Четверг 12:01
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 2, 2)  # Понедельник
    
    def test_before_noon_friday_returns_monday(self):
        """Пятница 11:59 -> Понедельник"""
        mock_time = datetime(2026, 1, 30, 11, 59)  # Пятница 11:59
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 2, 2)  # Понедельник
    
    def test_after_noon_friday_returns_monday(self):
        """Пятница 12:01 -> Понедельник (пятница весь день — запись на понедельник)"""
        mock_time = datetime(2026, 1, 30, 12, 1)  # Пятница 12:01
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 2, 2)  # Понедельник
    
    def test_exactly_noon_returns_next_working_day(self):
        """Ровно 12:00 -> следующий рабочий день (граница)"""
        mock_time = datetime(2026, 1, 28, 12, 0)  # Среда 12:00
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            # hour >= 12, поэтому пропускаем день
            assert result == date(2026, 1, 30)  # Пятница
    
    def test_saturday_before_noon(self):
        """Суббота 10:00 -> Вторник"""
        mock_time = datetime(2026, 1, 31, 10, 0)  # Суббота 10:00
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 2, 3)  # Вторник
    
    def test_saturday_after_noon(self):
        """Суббота 14:00 -> Вторник"""
        mock_time = datetime(2026, 1, 31, 14, 0)  # Суббота 14:00
        with patch('keyboards.inline.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = get_min_booking_date()
            assert result == date(2026, 2, 3)  # Вторник


class TestGenerateTimeSlots:
    """Тесты для функции generate_time_slots"""
    
    def test_all_slots_available(self):
        """Все слоты свободны"""
        date_str = "2026-02-02"
        booked_slots = {}
        limit = 2
        
        markup = generate_time_slots(date_str, booked_slots, limit)
        buttons = markup.inline_keyboard
        
        # Должно быть 6 слотов + 1 кнопка "назад"
        assert len(buttons) == 7
        
        # Первые 6 слотов должны быть доступны (с ✅)
        for row in buttons[:6]:
            assert "✅" in row[0].text
            assert row[0].callback_data.startswith("time_")
        
        # Последняя кнопка - "Назад"
        assert "Назад" in buttons[6][0].text or "back" in buttons[6][0].callback_data
    
    def test_some_slots_full(self):
        """Некоторые слоты заняты"""
        from datetime import time
        
        date_str = "2026-02-02"
        booked_slots = {
            time(9, 0): 2,   # Занят
            time(10, 0): 1,  # Свободен (1 из 2)
            time(11, 0): 2,  # Занят
        }
        limit = 2
        
        markup = generate_time_slots(date_str, booked_slots, limit)
        buttons = markup.inline_keyboard
        
        # 09:00 - занят
        assert "❌" in buttons[0][0].text
        assert buttons[0][0].callback_data == "full"
        
        # 10:00 - свободен
        assert "✅" in buttons[1][0].text
        
        # 11:00 - занят
        assert "❌" in buttons[2][0].text
    
    def test_all_slots_full(self):
        """Все слоты заняты"""
        from datetime import time
        
        date_str = "2026-02-02"
        booked_slots = {
            time(9, 0): 5,
            time(10, 0): 5,
            time(11, 0): 5,
            time(13, 0): 5,
            time(14, 0): 5,
            time(16, 0): 5,
        }
        limit = 2
        
        markup = generate_time_slots(date_str, booked_slots, limit)
        buttons = markup.inline_keyboard
        
        # Первые 6 рядов - слоты времени
        for row in buttons[:6]:
            assert "❌" in row[0].text
            assert row[0].callback_data == "full"
        
        # Последняя кнопка - "Назад"
        assert "Назад" in buttons[6][0].text or "back" in buttons[6][0].callback_data
    
    def test_correct_time_format_in_buttons(self):
        """Правильный формат времени в кнопках"""
        date_str = "2026-02-02"
        booked_slots = {}
        limit = 1
        
        markup = generate_time_slots(date_str, booked_slots, limit)
        buttons = markup.inline_keyboard
        
        expected_times = [
            "09:00 - 10:00",
            "10:00 - 11:00",
            "11:00 - 12:00",
            "13:00 - 14:00",
            "14:00 - 15:00",
            "16:00 - 17:00"
        ]
        
        for i, expected in enumerate(expected_times):
            assert expected in buttons[i][0].text


class TestGenerateHousesKb:
    """Тесты для функции generate_houses_kb"""
    
    def test_single_house(self):
        """Один дом"""
        houses = ["ЖК Навои"]
        markup = generate_houses_kb(houses)
        
        assert len(markup.inline_keyboard) == 1
        assert markup.inline_keyboard[0][0].text == "ЖК Навои"
        assert markup.inline_keyboard[0][0].callback_data == "house_ЖК Навои"
    
    def test_multiple_houses(self):
        """Несколько домов"""
        houses = ["ЖК Навои", "ЖК Sunrise", "ЖК Mega City"]
        markup = generate_houses_kb(houses)
        
        assert len(markup.inline_keyboard) == 3
        
        for i, house in enumerate(houses):
            assert markup.inline_keyboard[i][0].text == house
    
    def test_long_house_name_truncated(self):
        """Длинное название дома обрезается в callback_data"""
        long_name = "А" * 50  # 50 символов
        houses = [long_name]
        markup = generate_houses_kb(houses)
        
        callback = markup.inline_keyboard[0][0].callback_data
        # callback_data должен быть ограничен: "house_" + 40 символов
        assert len(callback) <= 46  # "house_" (6) + 40
    
    def test_empty_list(self):
        """Пустой список домов"""
        houses = []
        markup = generate_houses_kb(houses)
        
        assert len(markup.inline_keyboard) == 0


class TestGenerateCalendar:
    """Тесты для функции generate_calendar"""
    
    def test_calendar_has_navigation_buttons(self):
        """Календарь имеет кнопки навигации"""
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 1, 29)
            
            markup = generate_calendar(year=2026, month=2)
            buttons = markup.inline_keyboard
            
            # Последняя строка - навигация
            nav_row = buttons[-1]
            assert len(nav_row) == 2
            # Должна быть кнопка ">>" для следующего месяца
            assert any(">>" in btn.text for btn in nav_row)
    
    def test_calendar_has_weekday_headers(self):
        """Календарь имеет заголовки дней недели"""
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 1, 29)
            
            markup = generate_calendar(year=2026, month=2)
            buttons = markup.inline_keyboard
            
            # Вторая строка - дни недели
            weekdays = [btn.text for btn in buttons[1]]
            assert weekdays == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    def test_calendar_has_month_header(self):
        """Календарь имеет заголовок с названием месяца"""
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 1, 29)
            
            markup = generate_calendar(year=2026, month=2)
            buttons = markup.inline_keyboard
            
            # Первая строка - название месяца
            assert "Февраль 2026" in buttons[0][0].text
    
    def test_weekends_not_available(self):
        """Выходные дни недоступны для записи"""
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 2, 1)  # Воскресенье
            
            markup = generate_calendar(year=2026, month=2)
            
            # Проверяем, что суббота и воскресенье помечены как недоступные
            all_buttons = []
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data and btn.callback_data.startswith("date_"):
                        # Проверяем, что это рабочий день
                        date_str = btn.callback_data.split("_")[1]
                        d = date.fromisoformat(date_str)
                        assert d.weekday() < 5  # Пн-Пт
    
    def test_min_date_respected(self):
        """Даты раньше min_date недоступны"""
        min_date_val = date(2026, 2, 15)
        
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 2, 10)
            
            # min_date из аргумента должен использоваться если он позже
            markup = generate_calendar(year=2026, month=2, min_date=min_date_val)
            
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data and btn.callback_data.startswith("date_") and btn.callback_data != "date_full":
                        date_str = btn.callback_data.split("_")[1]
                        d = date.fromisoformat(date_str)
                        # Дата должна быть >= min_date
                        assert d >= min_date_val
    
    def test_fully_booked_dates_marked(self):
        """Полностью занятые даты помечаются крестиком"""
        fully_booked = {date(2026, 2, 16), date(2026, 2, 17)}
        
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 2, 10)
            
            markup = generate_calendar(
                year=2026, 
                month=2, 
                fully_booked_dates=fully_booked
            )
            
            found_booked = 0
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data == "date_full":
                        assert btn.text == "❌"
                        found_booked += 1
            
            # Должны быть помечены 2 даты (16 и 17 февраля - пн и вт)
            assert found_booked == 2
    
    def test_fully_booked_dates_not_selectable(self):
        """Полностью занятые даты нельзя выбрать"""
        fully_booked = {date(2026, 2, 16)}
        
        with patch('keyboards.inline.get_min_booking_date') as mock_min_date:
            mock_min_date.return_value = date(2026, 2, 10)
            
            markup = generate_calendar(
                year=2026, 
                month=2, 
                fully_booked_dates=fully_booked
            )
            
            for row in markup.inline_keyboard:
                for btn in row:
                    # Убеждаемся, что date_2026-02-16 не существует
                    assert btn.callback_data != "date_2026-02-16"


class TestGetFullyBookedDates:
    """Тесты для функции get_fully_booked_dates"""
    
    def test_returns_empty_set_when_no_bookings(self):
        """Возвращает пустое множество когда нет бронирований"""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []
        
        result = get_fully_booked_dates(
            mock_session,
            date(2026, 2, 1),
            date(2026, 2, 28),
            slots_limit=2
        )
        
        assert result == set()
    
    def test_returns_fully_booked_dates(self):
        """Возвращает даты где все слоты заняты"""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        
        # 6 слотов * 2 лимит = 12 записей для полной занятости
        mock_query.all.return_value = [
            (date(2026, 2, 16), 12),  # Полностью занят
            (date(2026, 2, 17), 6),   # Частично занят
        ]
        
        result = get_fully_booked_dates(
            mock_session,
            date(2026, 2, 1),
            date(2026, 2, 28),
            slots_limit=2
        )
        
        assert date(2026, 2, 16) in result
        assert date(2026, 2, 17) not in result
    
    def test_partial_booking_not_in_result(self):
        """Частично занятые даты не включаются в результат"""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        
        # 6 слотов * 3 лимит = 18 записей для полной занятости
        mock_query.all.return_value = [
            (date(2026, 2, 16), 17),  # Почти полностью (не хватает 1)
            (date(2026, 2, 17), 18),  # Ровно полный
            (date(2026, 2, 18), 20),  # Больше максимума
        ]
        
        result = get_fully_booked_dates(
            mock_session,
            date(2026, 2, 1),
            date(2026, 2, 28),
            slots_limit=3
        )
        
        assert date(2026, 2, 16) not in result  # 17 < 18
        assert date(2026, 2, 17) in result      # 18 >= 18
        assert date(2026, 2, 18) in result      # 20 >= 18


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

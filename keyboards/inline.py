from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import time, datetime, timedelta, date
import calendar
from aiogram import types

# Количество слотов в день
TIME_SLOTS = ["09:00", "10:00", "11:00", "13:00", "14:00", "16:00"]
SLOTS_PER_DAY = len(TIME_SLOTS)  # 6 слотов


def get_next_working_day(from_date: date) -> date:
    """Возвращает следующий рабочий день после указанной даты"""
    next_day = from_date + timedelta(days=1)
    while next_day.weekday() >= 5:  # Пропускаем выходные (5=Сб, 6=Вс)
        next_day += timedelta(days=1)
    return next_day


def get_min_booking_date() -> date:
    """
    Рассчитывает минимальную дату для записи:
    - До 12:00 — следующий рабочий день
    - После 12:00 — через один рабочий день
    """
    now = datetime.now()
    today = now.date()
    cutoff_hour = 12  # Граница — 12:00
    
    # Находим следующий рабочий день
    next_working = get_next_working_day(today)
    
    if now.hour < cutoff_hour:
        # До 12:00 — можно записаться на следующий рабочий день
        return next_working
    else:
        # После 12:00 — пропускаем один рабочий день
        return get_next_working_day(next_working)


def get_fully_booked_dates(session, start_date: date, end_date: date, slots_limit: int) -> set:
    """
    Возвращает множество дат, где все слоты заняты.
    
    Args:
        session: SQLAlchemy сессия
        start_date: Начало периода
        end_date: Конец периода  
        slots_limit: Лимит записей на один слот
    
    Returns:
        set[date]: Множество полностью занятых дат
    """
    from sqlalchemy import func
    from database.models import Booking
    
    # Общее количество возможных записей в день = слоты * лимит на слот
    max_bookings_per_day = SLOTS_PER_DAY * slots_limit
    
    # Считаем количество записей по датам
    bookings_per_date = session.query(
        Booking.date,
        func.count(Booking.id).label('count')
    ).filter(
        Booking.date >= start_date,
        Booking.date <= end_date
    ).group_by(Booking.date).all()
    
    # Возвращаем даты где записей >= максимума
    fully_booked = set()
    for booking_date, count in bookings_per_date:
        if count >= max_bookings_per_day:
            fully_booked.add(booking_date)
    
    return fully_booked


def generate_time_slots(date_str, booked_slots, limit):
    builder = InlineKeyboardBuilder()

    # Преобразуем выбранную пользователем дату из строки в объект date
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    target_slots = [
        "09:00", "10:00", "11:00",
        "13:00", "14:00",
        "16:00"
    ]

    for slot_str in target_slots:
        slot_time = datetime.strptime(slot_str, "%H:%M").time()

        count = booked_slots.get(slot_time, 0)
        end_hour = slot_time.hour + 1
        display_text = f"{slot_str} - {end_hour:02d}:00"

        # Проверка: Занято ли место по лимиту
        is_full = count >= limit

        if is_full:
            builder.button(text=f"❌ {display_text}", callback_data="full")
        else:
            builder.button(text=f"✅ {display_text}", callback_data=f"time_{date_str}_{slot_str}")

    builder.adjust(1)
    return builder.as_markup()

def generate_houses_kb(houses):
    builder = InlineKeyboardBuilder()
    for house in houses:
        # Ограничиваем длину callback_data (макс 64 байта)
        builder.button(text=house, callback_data=f"house_{house[:40]}")
    builder.adjust(1)
    return builder.as_markup()


def generate_calendar(year: int = None, month: int = None, min_date: date = None, 
                      fully_booked_dates: set = None, slots_limit: int = 1):
    """
    Генерация календаря с учётом занятых дат.
    
    Args:
        year: Год для отображения
        month: Месяц для отображения  
        min_date: Минимальная дата (дата сдачи объекта)
        fully_booked_dates: Множество дат, где все слоты заняты
        slots_limit: Лимит записей на слот (для справки)
    """
    if fully_booked_dates is None:
        fully_booked_dates = set()
        
    today = date.today()
    if year is None: year = today.year
    if month is None: month = today.month

    # Вычисляем минимальную дату для записи по новым правилам
    booking_min_date = get_min_booking_date()
    
    # Если передана дата сдачи объекта, берём максимум из двух ограничений
    if min_date:
        effective_min_date = max(booking_min_date, min_date)
    else:
        effective_min_date = booking_min_date

    # Если минимальная дата позже выбранного месяца,
    # переключаем календарь на нужный месяц
    if date(year, month, calendar.monthrange(year, month)[1]) < effective_min_date:
        year = effective_min_date.year
        month = effective_min_date.month

    builder = InlineKeyboardBuilder()

    # Заголовок: Месяц и Год
    month_names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    builder.button(text=f"{month_names[month - 1]} {year}", callback_data="ignore")
    builder.adjust(1)

    # Дни недели
    for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        builder.button(text=day, callback_data="ignore")
    builder.adjust(1, 7)

    # Календарная сетка
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        for day in week:
            if day == 0:
                builder.button(text=" ", callback_data="ignore")
            else:
                current_date = date(year, month, day)
                # Кнопка активна ТОЛЬКО если:
                # 1. Это рабочий день (пн-пт)
                # 2. Дата >= минимальной даты записи (с учётом правила 12:00)
                # 3. Дата >= даты сдачи объекта (если указана)
                # 4. На эту дату есть свободные слоты
                is_weekday = current_date.weekday() < 5
                is_date_valid = is_weekday and current_date >= effective_min_date
                is_fully_booked = current_date in fully_booked_dates

                if is_date_valid and not is_fully_booked:
                    builder.button(text=str(day), callback_data=f"date_{current_date}")
                elif is_date_valid and is_fully_booked:
                    # Дата доступна, но все слоты заняты
                    builder.button(text="❌", callback_data="date_full")
                else:
                    builder.button(text="·", callback_data="ignore")  # Неактивный день
        builder.adjust(1, 7, 7, 7, 7, 7, 7)

    # Кнопки навигации (Назад / Вперед)
    nav_buttons = []
    # Назад можно только если текущий вид позже, чем effective_min_date
    can_go_back = date(year, month, 1) > effective_min_date

    if can_go_back:
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        nav_buttons.append(types.InlineKeyboardButton(text="<<", callback_data=f"cal_{prev_year}_{prev_month}"))
    else:
        nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    nav_buttons.append(types.InlineKeyboardButton(text=">>", callback_data=f"cal_{next_year}_{next_month}"))

    builder.row(*nav_buttons)
    return builder.as_markup()
"""Утилиты для работы с праздничными днями (импорт/экспорт Excel)."""

import logging
import os
from datetime import datetime, date

import pandas as pd
from database.models import Holiday
from database.session import SessionLocal


HOLIDAYS_TEMPLATE_PATH = "data/holidays_template.xlsx"
EXPECTED_COLUMNS = ["Дата", "Описание"]


def get_all_holidays() -> list[Holiday]:
    """Получить все праздничные дни из базы, отсортированные по дате."""
    with SessionLocal() as session:
        return session.query(Holiday).order_by(Holiday.date).all()


def get_holiday_dates(start_date: date = None, end_date: date = None) -> set[date]:
    """
    Получить множество праздничных дат для указанного периода.

    Args:
        start_date: Начало периода (включительно). Если None — без ограничения.
        end_date: Конец периода (включительно). Если None — без ограничения.

    Returns:
        set[date]: Множество праздничных дат.
    """
    try:
        with SessionLocal() as session:
            query = session.query(Holiday.date)
            if start_date:
                query = query.filter(Holiday.date >= start_date)
            if end_date:
                query = query.filter(Holiday.date <= end_date)
            return {row[0] for row in query.all()}
    except Exception:
        # Таблица может не существовать (в тестах или при первом запуске)
        return set()


def generate_holidays_excel() -> str:
    """
    Генерирует Excel-файл с текущими праздниками (шаблон для импорта).

    Returns:
        str: Путь к сгенерированному файлу.
    """
    holidays = get_all_holidays()

    data = {
        "Дата": [h.date.strftime("%d.%m.%Y") for h in holidays],
        "Описание": [h.description or "" for h in holidays],
    }

    df = pd.DataFrame(data, columns=EXPECTED_COLUMNS)
    if df.empty:
        # Пустой шаблон с заголовками и примером
        df = pd.DataFrame(columns=EXPECTED_COLUMNS)

    os.makedirs(os.path.dirname(HOLIDAYS_TEMPLATE_PATH), exist_ok=True)
    df.to_excel(HOLIDAYS_TEMPLATE_PATH, index=False)
    return HOLIDAYS_TEMPLATE_PATH


def import_holidays_from_excel(file_path: str) -> int:
    """
    Полностью заменяет праздничные дни в базе данными из Excel-файла.

    Файл должен содержать столбцы:
        - Дата (формат ДД.ММ.ГГГГ или любой распознаваемый pandas)
        - Описание (необязательно)

    Args:
        file_path: Путь к Excel-файлу.

    Returns:
        int: Количество загруженных праздников.

    Raises:
        ValueError: Если файл не содержит нужных столбцов или данные некорректны.
    """
    df = pd.read_excel(file_path)
    stripped = [c.strip() for c in df.columns]
    df.columns = stripped

    # Определяем маппинг столбцов
    if "Дата" in df.columns:
        date_col = "Дата"
    elif len(df.columns) >= 1:
        date_col = df.columns[0]
    else:
        raise ValueError("Файл не содержит столбцов. Ожидается минимум столбец «Дата».")

    desc_col = None
    if "Описание" in df.columns:
        desc_col = "Описание"
    elif len(df.columns) >= 2:
        desc_col = df.columns[1]

    # Парсим даты
    new_holidays: list[tuple[date, str]] = []
    seen_dates: set[date] = set()

    for idx, row in df.iterrows():
        raw_date = row[date_col]
        if pd.isna(raw_date):
            continue

        parsed_date = _parse_date(raw_date)
        if parsed_date is None:
            raise ValueError(
                f"Строка {idx + 2}: не удалось распознать дату «{raw_date}». "
                f"Ожидается формат ДД.ММ.ГГГГ"
            )

        if parsed_date in seen_dates:
            continue  # Пропускаем дубликаты
        seen_dates.add(parsed_date)

        description = ""
        if desc_col is not None and not pd.isna(row[desc_col]):
            description = str(row[desc_col]).strip()

        new_holidays.append((parsed_date, description))

    # Полная замена данных в таблице
    with SessionLocal() as session:
        session.query(Holiday).delete()
        for h_date, h_desc in new_holidays:
            session.add(Holiday(date=h_date, description=h_desc or None))
        session.commit()

    logging.info("Импортировано %d праздничных дней.", len(new_holidays))
    return len(new_holidays)


def _parse_date(value) -> date | None:
    """Пытается распознать дату из различных форматов."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    s = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Попробовать pandas
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None

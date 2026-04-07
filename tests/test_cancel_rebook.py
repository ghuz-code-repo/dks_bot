"""
Тесты логики отмены записи и повторной записи.

Проверяют: после успешной отмены записи пользователь может записаться
на любой доступный слот любого доступного дня, как будто отменённой записи
и не было. Двухнедельный период ожидания НЕ должен учитывать отменённые записи.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date, time, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session as SASession, sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Base, Contract, Booking, ProjectSlots


USER_ID = 100500


# ==================== Фикстуры ====================

@pytest.fixture
def db_engine():
    """In-memory SQLite engine с общим подключением."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Транзакционная сессия для юнит-тестов запросов."""
    with SASession(db_engine) as session:
        yield session


@pytest.fixture
def contract(db_session):
    """Тестовый договор."""
    c = Contract(
        id=1,
        house_name="ЖК Тест",
        apt_num="42",
        entrance="1",
        floor=3,
        contract_num="C-001",
        client_fio="Тестов Тест",
        delivery_date=date(2026, 1, 1),
        telegram_id=None,
    )
    db_session.add(c)
    db_session.commit()
    return c


def _make_booking(contract_id, user_id, booking_date, is_cancelled=False, slot=time(10, 0)):
    """Хелпер: создать запись (Booking)."""
    return Booking(
        contract_id=contract_id,
        user_telegram_id=user_id,
        date=booking_date,
        time_slot=slot,
        client_phone="+998900000000",
        is_cancelled=is_cancelled,
    )


# ==================== 1. Отменённая запись ≠ активная ====================

class TestCancelledBookingNotActive:
    """Отменённая запись не должна считаться активной."""

    def test_cancelled_future_booking_is_not_active(self, db_session, contract):
        """Отменённая будущая запись НЕ блокирует повторную запись."""
        db_session.add(
            _make_booking(contract.id, USER_ID, date.today() + timedelta(days=5), is_cancelled=True)
        )
        db_session.commit()

        active = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.date >= date.today(),
                Booking.is_cancelled == False,
            )
            .first()
        )
        assert active is None, "Отменённая запись не должна считаться активной"

    def test_non_cancelled_future_booking_is_active(self, db_session, contract):
        """Неотменённая будущая запись корректно определяется как активная."""
        db_session.add(
            _make_booking(contract.id, USER_ID, date.today() + timedelta(days=5), is_cancelled=False)
        )
        db_session.commit()

        active = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.date >= date.today(),
                Booking.is_cancelled == False,
            )
            .first()
        )
        assert active is not None, "Неотменённая запись должна считаться активной"


# ==================== 2. Двухнедельное ожидание и отменённые записи ====================

class TestTwoWeekWaitAfterCancellation:
    """Двухнедельный период ожидания НЕ должен учитывать отменённые записи."""

    def test_only_cancelled_bookings_no_wait(self, db_session, contract):
        """Все записи отменены → нет 2-недельного ограничения."""
        db_session.add(
            _make_booking(contract.id, USER_ID, date.today() - timedelta(days=1), is_cancelled=True)
        )
        db_session.commit()

        past = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.user_telegram_id == USER_ID,
                Booking.is_cancelled == False,
            )
            .first()
        )
        assert past is None, "Отменённая запись не должна вызывать 2-недельное ожидание"

    def test_non_cancelled_booking_triggers_wait(self, db_session, contract):
        """Неотменённая прошедшая запись → 2-недельное ожидание применяется."""
        booking_date = date.today() - timedelta(days=5)
        db_session.add(
            _make_booking(contract.id, USER_ID, booking_date, is_cancelled=False)
        )
        db_session.commit()

        last = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.user_telegram_id == USER_ID,
                Booking.is_cancelled == False,
            )
            .order_by(Booking.date.desc())
            .first()
        )
        assert last is not None, "Неотменённая запись должна быть найдена"
        min_date = last.date + timedelta(days=14)
        assert min_date == booking_date + timedelta(days=14)

    def test_mixed_bookings_use_non_cancelled_only(self, db_session, contract):
        """
        Недавняя отменённая + старая неотменённая записи →
        2-недельное ожидание считается от СТАРОЙ неотменённой, а не от недавней отменённой.
        """
        old_date = date.today() - timedelta(days=20)
        recent_date = date.today() - timedelta(days=2)

        db_session.add_all([
            _make_booking(contract.id, USER_ID, old_date, is_cancelled=False),
            _make_booking(contract.id, USER_ID, recent_date, is_cancelled=True),
        ])
        db_session.commit()

        last = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.user_telegram_id == USER_ID,
                Booking.is_cancelled == False,
            )
            .order_by(Booking.date.desc())
            .first()
        )
        assert last is not None
        assert last.date == old_date, \
            "Должна использоваться дата неотменённой записи, а не недавней отменённой"
        two_weeks_from_last = last.date + timedelta(days=14)
        assert two_weeks_from_last == old_date + timedelta(days=14)

    def test_all_cancelled_multiple_bookings_no_restriction(self, db_session, contract):
        """Несколько отменённых записей → нет никакого ограничения."""
        for days_ago in [3, 7, 14]:
            db_session.add(
                _make_booking(contract.id, USER_ID, date.today() - timedelta(days=days_ago), is_cancelled=True)
            )
        db_session.commit()

        past = (
            db_session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.user_telegram_id == USER_ID,
                Booking.is_cancelled == False,
            )
            .first()
        )
        assert past is None, "Только отменённые записи → нет 2-недельного ожидания"


# ==================== 3. Освобождение слота после отмены ====================

class TestCancelledBookingFreesSlot:
    """Отменённая запись не должна занимать слот."""

    def test_slot_freed_after_cancellation(self, db_session, contract):
        """Отменённая запись освобождает слот."""
        target_date = date.today() + timedelta(days=5)
        target_time = time(10, 0)

        db_session.add(
            _make_booking(contract.id, USER_ID, target_date, is_cancelled=True, slot=target_time)
        )
        db_session.commit()

        count = (
            db_session.query(func.count(Booking.id))
            .filter(
                Booking.date == target_date,
                Booking.time_slot == target_time,
                Booking.is_cancelled == False,
            )
            .scalar()
        )
        assert count == 0, "Отменённая запись не должна занимать слот"

    def test_slot_occupied_when_not_cancelled(self, db_session, contract):
        """Неотменённая запись занимает слот."""
        target_date = date.today() + timedelta(days=5)
        target_time = time(10, 0)

        db_session.add(
            _make_booking(contract.id, USER_ID, target_date, is_cancelled=False, slot=target_time)
        )
        db_session.commit()

        count = (
            db_session.query(func.count(Booking.id))
            .filter(
                Booking.date == target_date,
                Booking.time_slot == target_time,
                Booking.is_cancelled == False,
            )
            .scalar()
        )
        assert count == 1, "Неотменённая запись должна занимать слот"


# ==================== 4. Интеграционные тесты хендлера contract_entered ====================

class TestContractEnteredAfterCancellation:
    """
    Интеграционные тесты: хендлер contract_entered должен
    разрешать повторную запись без 2-недельного ожидания после отмены.
    """

    @pytest.mark.asyncio
    @patch("handlers.client.get_message", return_value="test")
    @patch("handlers.client.get_fully_booked_dates", return_value=set())
    @patch("handlers.client.generate_calendar", return_value=MagicMock())
    @patch("handlers.client.get_user_language", return_value="ru")
    @patch("handlers.client.get_min_booking_date")
    async def test_rebooking_after_cancel_uses_standard_min_date(
        self, mock_min_booking_date, mock_lang, mock_calendar,
        mock_booked_dates, mock_get_message, db_engine
    ):
        """
        Сценарий:
        1. У пользователя была запись на договор, он её отменил
        2. Пользователь вводит тот же договор снова

        Ожидание: min_booking_date = стандартная минимальная дата,
        БЕЗ сдвига на 2 недели от отменённой записи.
        """
        from handlers.client import contract_entered

        base_min = date(2026, 2, 18)
        mock_min_booking_date.return_value = base_min

        # Подготавливаем данные в БД
        Factory = sessionmaker(bind=db_engine)
        with Factory() as s:
            c = Contract(
                id=10, house_name="ЖК Тест", apt_num="42",
                entrance="1", floor=3, contract_num="REBK-001",
                client_fio="Тестов Тест", delivery_date=date(2026, 1, 1),
                telegram_id=None,
            )
            s.add(c)
            s.flush()
            # Отменённая запись (в пределах 2 недель от base_min)
            s.add(Booking(
                contract_id=c.id, user_telegram_id=USER_ID,
                date=base_min + timedelta(days=2),
                time_slot=time(10, 0), client_phone="+998900000000",
                is_cancelled=True,
            ))
            s.add(ProjectSlots(project_name="ЖК Тест", slots_limit=1))
            s.commit()

        # Мокаем Telegram-объекты
        mock_message = AsyncMock()
        mock_message.text = "REBK-001"
        mock_message.from_user.id = USER_ID

        captured_data = {}
        async def capture_update_data(**kwargs):
            captured_data.update(kwargs)

        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={})
        mock_state.update_data = capture_update_data

        with patch("handlers.client.SessionLocal", Factory):
            await contract_entered(mock_message, mock_state)

        # Проверяем: delivery_date НЕ сдвинута на 2 недели от отменённой записи
        assert "delivery_date" in captured_data, \
            "Хендлер должен дойти до выбора календаря (установить delivery_date)"
        stored_date = date.fromisoformat(captured_data["delivery_date"])
        assert stored_date == base_min, (
            f"После отмены min_date должна быть {base_min}, "
            f"а получили {stored_date} (2-недельное ожидание ошибочно применено)"
        )

    @pytest.mark.asyncio
    @patch("handlers.client.get_message", return_value="test")
    @patch("handlers.client.get_fully_booked_dates", return_value=set())
    @patch("handlers.client.generate_calendar", return_value=MagicMock())
    @patch("handlers.client.get_user_language", return_value="ru")
    @patch("handlers.client.get_min_booking_date")
    async def test_non_cancelled_past_booking_applies_two_week_wait(
        self, mock_min_booking_date, mock_lang, mock_calendar,
        mock_booked_dates, mock_get_message, db_engine
    ):
        """
        Сценарий: у пользователя есть неотменённая прошедшая запись.
        Ожидание: min_booking_date сдвинута на 2 недели от даты той записи.
        """
        from handlers.client import contract_entered

        base_min = date(2026, 2, 18)
        mock_min_booking_date.return_value = base_min

        past_booking_date = base_min - timedelta(days=5)  # 13 февраля

        Factory = sessionmaker(bind=db_engine)
        with Factory() as s:
            c = Contract(
                id=20, house_name="ЖК Тест2", apt_num="99",
                entrance="2", floor=7, contract_num="REBK-002",
                client_fio="Петров Пётр", delivery_date=date(2026, 1, 1),
                telegram_id=None,
            )
            s.add(c)
            s.flush()
            # Неотменённая прошедшая запись
            s.add(Booking(
                contract_id=c.id, user_telegram_id=USER_ID,
                date=past_booking_date,
                time_slot=time(10, 0), client_phone="+998900000000",
                is_cancelled=False,
            ))
            s.add(ProjectSlots(project_name="ЖК Тест2", slots_limit=1))
            s.commit()

        mock_message = AsyncMock()
        mock_message.text = "REBK-002"
        mock_message.from_user.id = USER_ID

        captured_data = {}
        async def capture_update_data(**kwargs):
            captured_data.update(kwargs)

        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={})
        mock_state.update_data = capture_update_data

        with patch("handlers.client.SessionLocal", Factory):
            await contract_entered(mock_message, mock_state)

        # 2 недели от прошедшей записи = 13 фев + 14 = 27 февраля
        expected_min = past_booking_date + timedelta(days=14)
        assert "delivery_date" in captured_data
        stored_date = date.fromisoformat(captured_data["delivery_date"])
        assert stored_date == expected_min, (
            f"С неотменённой записью min_date должна быть {expected_min}, "
            f"а получили {stored_date}"
        )

    @pytest.mark.asyncio
    @patch("handlers.client.get_message", return_value="test")
    @patch("handlers.client.get_fully_booked_dates", return_value=set())
    @patch("handlers.client.generate_calendar", return_value=MagicMock())
    @patch("handlers.client.get_user_language", return_value="ru")
    @patch("handlers.client.get_min_booking_date")
    async def test_active_booking_auto_cancelled_on_rebooking(
        self, mock_min_booking_date, mock_lang, mock_calendar,
        mock_booked_dates, mock_get_message, db_engine
    ):
        """
        Сценарий:
        1. У пользователя есть активная (неотменённая) запись на будущую дату
        2. Пользователь вводит тот же договор через «первичная запись»

        Ожидание: старая запись автоматически отменяется,
        пользователь продолжает к выбору даты.
        """
        from handlers.client import contract_entered

        base_min = date.today() + timedelta(days=7)
        mock_min_booking_date.return_value = base_min

        Factory = sessionmaker(bind=db_engine)
        with Factory() as s:
            c = Contract(
                id=30, house_name="ЖК Авто", apt_num="77",
                entrance="1", floor=5, contract_num="AUTO-001",
                client_fio="Иванов Иван", delivery_date=date(2026, 1, 1),
                telegram_id=USER_ID,
            )
            s.add(c)
            s.flush()
            # Активная запись на будущую дату
            active_booking = Booking(
                contract_id=c.id, user_telegram_id=USER_ID,
                date=base_min + timedelta(days=3),
                time_slot=time(10, 0), client_phone="+998900000000",
                is_cancelled=False,
            )
            s.add(active_booking)
            s.add(ProjectSlots(project_name="ЖК Авто", slots_limit=1))
            s.commit()
            active_booking_id = active_booking.id

        mock_message = AsyncMock()
        mock_message.text = "AUTO-001"
        mock_message.from_user.id = USER_ID

        captured_data = {}
        async def capture_update_data(**kwargs):
            captured_data.update(kwargs)

        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={})
        mock_state.update_data = capture_update_data

        with patch("handlers.client.SessionLocal", Factory):
            await contract_entered(mock_message, mock_state)

        # Проверяем: хендлер дошёл до календаря (не заблокировал)
        assert "delivery_date" in captured_data, \
            "Хендлер должен пройти дальше, а не блокировать сообщением has_active_booking"

        # Проверяем: старая запись НЕ отменена сразу — отмена отложена до создания новой записи
        with Factory() as s:
            booking = s.query(Booking).filter(Booking.id == active_booking_id).first()
            assert booking.is_cancelled is False, \
                "Активная запись не должна отменяться сразу — отмена отложена до создания новой"

        # Проверяем: ID старой записи сохранён в FSM для отложенной отмены
        assert captured_data.get('pending_cancel_booking_id') == active_booking_id, \
            "ID старой записи должен быть сохранён в FSM state для отложенной отмены"

    @pytest.mark.asyncio
    @patch("handlers.client.get_message", return_value="test")
    @patch("handlers.client.get_fully_booked_dates", return_value=set())
    @patch("handlers.client.generate_calendar", return_value=MagicMock())
    @patch("handlers.client.get_user_language", return_value="ru")
    @patch("handlers.client.get_min_booking_date")
    async def test_rebooking_with_telegram_id_set_no_two_week_wait(
        self, mock_min_booking_date, mock_lang, mock_calendar,
        mock_booked_dates, mock_get_message, db_engine
    ):
        """
        Сценарий:
        1. У пользователя была запись, contract.telegram_id уже установлен
        2. Запись была отменена
        3. Пользователь вводит тот же договор через «первичная запись»

        Ожидание: отсутствие 2-недельного ожидания (отменённые не считаются).
        """
        from handlers.client import contract_entered

        base_min = date(2026, 3, 10)
        mock_min_booking_date.return_value = base_min

        Factory = sessionmaker(bind=db_engine)
        with Factory() as s:
            c = Contract(
                id=40, house_name="ЖК ТГ", apt_num="15",
                entrance="2", floor=3, contract_num="TG-001",
                client_fio="Сидоров Сергей", delivery_date=date(2026, 1, 1),
                telegram_id=USER_ID,
            )
            s.add(c)
            s.flush()
            s.add(Booking(
                contract_id=c.id, user_telegram_id=USER_ID,
                date=base_min + timedelta(days=1),
                time_slot=time(10, 0), client_phone="+998900000000",
                is_cancelled=True,
            ))
            s.add(ProjectSlots(project_name="ЖК ТГ", slots_limit=1))
            s.commit()

        mock_message = AsyncMock()
        mock_message.text = "TG-001"
        mock_message.from_user.id = USER_ID

        captured_data = {}
        async def capture_update_data(**kwargs):
            captured_data.update(kwargs)

        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={})
        mock_state.update_data = capture_update_data

        with patch("handlers.client.SessionLocal", Factory):
            await contract_entered(mock_message, mock_state)

        assert "delivery_date" in captured_data, \
            "Хендлер должен дойти до календаря даже при установленном telegram_id"
        stored_date = date.fromisoformat(captured_data["delivery_date"])
        assert stored_date == base_min, (
            f"При telegram_id и только отменённых записях min_date={base_min}, "
            f"получили {stored_date}"
        )

"""
Тесты для новой логики авторизации договоров.

Правила (после рефакторинга):
- Contract.telegram_id — единственный источник истины о привязке.
- Booking.user_telegram_id — хранит создателя записи, используется только
  для cooldown-логики (2 недели), но не для авторизации/фильтрации.
- При отвязке admin'ом договор становится свободным: любой может записаться.
- Фильтры "мои записи / отмена / перезапись" ищут по Contract.telegram_id,
  а не по Booking.user_telegram_id.
"""
import os
import sys
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOT_TOKEN", "test_token")
os.environ.setdefault("ADMIN_ID", "999999")
os.environ.setdefault("EMPLOYEE_IDS", "")

from database.models import Base, Booking, Contract


# ---------------------------------------------------------------------------
# Вспомогательные фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture()
def Session():
    """Изолированная in-memory SQLite БД на каждый тест."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield S
    engine.dispose()


def _make_contract(session, *, contract_num="100-GHP", telegram_id=None, username=None):
    c = Contract(
        house_name="ЖК Тест",
        apt_num="10",
        entrance="1",
        floor=2,
        contract_num=contract_num,
        client_fio="Иванов И.И.",
        delivery_date=date(2025, 1, 1),
        telegram_id=telegram_id,
        username=username,
    )
    session.add(c)
    session.flush()
    return c


def _make_booking(session, contract, *, user_telegram_id, booking_date, is_cancelled=False):
    b = Booking(
        contract_id=contract.id,
        user_telegram_id=user_telegram_id,
        date=booking_date,
        time_slot=time(10, 0),
        client_phone="+998901234567",
        is_cancelled=is_cancelled,
    )
    session.add(b)
    session.flush()
    return b


def _make_message(user_id: int, text: str = "100-GHP"):
    msg = AsyncMock()
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.username = f"user_{user_id}"
    msg.from_user.language_code = "ru"
    msg.answer = AsyncMock()
    return msg


def _make_state(data: dict | None = None):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# Блок 1. contract_entered — авторизация при вводе номера договора
# ---------------------------------------------------------------------------

class TestContractEnteredAuth:
    """Contract.telegram_id — единственный гейткипер."""

    @pytest.mark.asyncio
    async def test_free_contract_allows_any_user(self, Session):
        """Договор без привязки (telegram_id=None) доступен любому."""
        with Session() as s:
            _make_contract(s, telegram_id=None)
            s.commit()

        msg = _make_message(user_id=42)
        state = _make_state()

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        # Прошли авторизацию — state обновлён и не было 'contract_unavailable'
        state.update_data.assert_called()
        state.set_state.assert_called()

    @pytest.mark.asyncio
    async def test_bound_contract_blocks_other_user(self, Session):
        """Договор привязан к user A — user B должен получить отказ."""
        USER_A, USER_B = 100, 200
        with Session() as s:
            _make_contract(s, telegram_id=USER_A)
            s.commit()

        msg = _make_message(user_id=USER_B)
        state = _make_state()

        # contract_unavailable → get_message вернёт метку, answer будет вызван с ней
        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_message", return_value="contract_unavailable_msg"):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        msg.answer.assert_awaited()
        # state не перешёл дальше
        state.set_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_bound_contract_allows_owner(self, Session):
        """Договор привязан к user A — user A сам может войти."""
        USER_A = 100
        with Session() as s:
            _make_contract(s, telegram_id=USER_A)
            s.commit()

        msg = _make_message(user_id=USER_A)
        state = _make_state()

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        state.update_data.assert_called()
        state.set_state.assert_called()

    @pytest.mark.asyncio
    async def test_after_unbind_any_user_can_enter(self, Session):
        """После снятия привязки (telegram_id=None) любой пользователь проходит."""
        USER_A, USER_B = 100, 200
        with Session() as s:
            c = _make_contract(s, telegram_id=None)  # уже отвязан
            # Старая запись от user_A (created_by), договор уже разрешён
            _make_booking(s, c, user_telegram_id=USER_A,
                          booking_date=date.today() + timedelta(days=5))
            s.commit()

        msg = _make_message(user_id=USER_B)
        state = _make_state()

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        state.set_state.assert_called()

    @pytest.mark.asyncio
    async def test_after_unbind_old_booking_marked_for_cancel(self, Session):
        """
        После unbind, когда user_B входит и на договоре есть активная запись,
        та запись должна быть помечена для отложенной отмены (pending_cancel).
        """
        USER_A, USER_B = 100, 200
        with Session() as s:
            c = _make_contract(s, telegram_id=None)
            b = _make_booking(s, c, user_telegram_id=USER_A,
                              booking_date=date.today() + timedelta(days=5))
            s.commit()
            booking_id = b.id

        msg = _make_message(user_id=USER_B)
        state = _make_state()

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        # pending_cancel_booking_id должен быть установлен
        update_calls = [
            call for call in state.update_data.await_args_list
            if "pending_cancel_booking_id" in (call.kwargs or {})
               or (call.args and "pending_cancel_booking_id" in str(call.args))
        ]
        assert any(
            call.kwargs.get("pending_cancel_booking_id") == booking_id
            for call in state.update_data.await_args_list
        ), "pending_cancel_booking_id должен быть установлен на id старой записи"

    @pytest.mark.asyncio
    async def test_booking_user_telegram_id_does_not_block_other_user(self, Session):
        """
        Booking.user_telegram_id != user_B, но Contract.telegram_id == None →
        user_B должен пройти (поле в Booking больше не авторизует).
        """
        USER_A, USER_B = 100, 200
        with Session() as s:
            c = _make_contract(s, telegram_id=None)
            _make_booking(s, c, user_telegram_id=USER_A,
                          booking_date=date.today() + timedelta(days=3))
            s.commit()

        msg = _make_message(user_id=USER_B)
        state = _make_state()

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        state.set_state.assert_called()


# ---------------------------------------------------------------------------
# Блок 2. Cooldown (2 недели) — только по Booking.user_telegram_id
# ---------------------------------------------------------------------------

class TestCooldownLogic:
    """Cooldown считается по записям, созданным текущим пользователем."""

    @pytest.mark.asyncio
    async def test_cooldown_applied_for_user_who_created_booking(self, Session):
        """Если user_A сам создавал запись — cooldown применяется."""
        USER_A = 100
        last_booking_date = date.today() - timedelta(days=5)  # 5 дней назад

        with Session() as s:
            c = _make_contract(s, telegram_id=USER_A)
            _make_booking(s, c, user_telegram_id=USER_A, booking_date=last_booking_date)
            s.commit()

        msg = _make_message(user_id=USER_A)
        state = _make_state()
        captured_data = {}

        async def capture_update(**kwargs):
            captured_data.update(kwargs)

        state.update_data = AsyncMock(side_effect=capture_update)

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        # Дата должна быть = last_booking_date + 14 дней
        expected_min = last_booking_date + timedelta(days=14)
        assert captured_data.get("delivery_date") == expected_min.isoformat()

    @pytest.mark.asyncio
    async def test_no_cooldown_for_new_user_after_unbind(self, Session):
        """
        USER_B записывается на договор после unbind.
        Записи USER_A существуют, но они не должны давать cooldown для USER_B.
        """
        USER_A, USER_B = 100, 200
        last_booking_date = date.today() - timedelta(days=5)

        with Session() as s:
            c = _make_contract(s, telegram_id=None)  # отвязан
            _make_booking(s, c, user_telegram_id=USER_A, booking_date=last_booking_date)
            s.commit()

        msg = _make_message(user_id=USER_B)
        state = _make_state()
        captured_data = {}

        async def capture_update(**kwargs):
            captured_data.update(kwargs)

        state.update_data = AsyncMock(side_effect=capture_update)

        with patch("handlers.client.SessionLocal", Session), \
             patch("handlers.client.get_user_language", return_value="ru"), \
             patch("handlers.client.get_min_booking_date", return_value=date(2025, 1, 1)), \
             patch("handlers.client.get_fully_booked_dates", return_value=set()), \
             patch("handlers.client.generate_calendar", return_value=MagicMock()), \
             patch("handlers.client.get_message", return_value="ok"), \
             patch("handlers.client.get_project_slot_limit", return_value=1):
            from handlers.client import contract_entered
            await contract_entered(msg, state)

        # Cooldown от USER_A не применился — delivery_date от delivery_date контракта
        assert captured_data.get("delivery_date") == date(2025, 1, 1).isoformat()


# ---------------------------------------------------------------------------
# Блок 3. Фильтр "мои записи" по Contract.telegram_id
# ---------------------------------------------------------------------------

class TestMyBookingsFilter:
    """
    Запросы к БД в cancel_booking_button, my_bookings_button,
    view_calendar_button используют Contract.telegram_id, а не
    Booking.user_telegram_id.
    """

    def _seed(self, Session, owner_id: int, creator_id: int, future: bool = True):
        """Создаёт договор с привязкой owner_id и запись созданную creator_id."""
        with Session() as s:
            c = _make_contract(s, telegram_id=owner_id)
            booking_date = date.today() + timedelta(days=5) if future \
                else date.today() - timedelta(days=5)
            _make_booking(s, c, user_telegram_id=creator_id, booking_date=booking_date)
            s.commit()

    def test_owner_sees_booking_created_by_someone_else(self, Session):
        """
        Contract.telegram_id = OWNER, Booking.user_telegram_id = OTHER.
        OWNER должен видеть эту запись в своих записях.
        """
        OWNER, OTHER = 100, 200
        self._seed(Session, owner_id=OWNER, creator_id=OTHER)

        with Session() as s:
            from sqlalchemy import select
            from database.models import Booking as B, Contract as C
            result = (
                s.query(B, C)
                .join(C, B.contract_id == C.id)
                .filter(
                    C.telegram_id == OWNER,
                    B.date >= date.today(),
                    B.is_cancelled == False,
                )
                .all()
            )
        assert len(result) == 1

    def test_other_user_does_not_see_booking(self, Session):
        """
        OTHER не является владельцем договора →
        запись не должна появляться в его списке.
        """
        OWNER, OTHER = 100, 200
        self._seed(Session, owner_id=OWNER, creator_id=OTHER)

        with Session() as s:
            from database.models import Booking as B, Contract as C
            result = (
                s.query(B, C)
                .join(C, B.contract_id == C.id)
                .filter(
                    C.telegram_id == OTHER,
                    B.date >= date.today(),
                    B.is_cancelled == False,
                )
                .all()
            )
        assert len(result) == 0

    def test_unbound_contract_not_visible_to_anyone(self, Session):
        """Договор без привязки никому не показывается в «моих записях»."""
        with Session() as s:
            c = _make_contract(s, telegram_id=None)
            _make_booking(s, c, user_telegram_id=42,
                          booking_date=date.today() + timedelta(days=3))
            s.commit()

        with Session() as s:
            from database.models import Booking as B, Contract as C
            result = (
                s.query(B, C)
                .join(C, B.contract_id == C.id)
                .filter(
                    C.telegram_id == 42,
                    B.date >= date.today(),
                    B.is_cancelled == False,
                )
                .all()
            )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Блок 4. Contract.telegram_id устанавливается при первой записи
# ---------------------------------------------------------------------------

class TestContractBindingOnFirstBooking:
    """При первой записи contract.telegram_id должен устанавливаться."""

    def test_contract_bound_when_telegram_id_was_null(self, Session):
        """Если contract.telegram_id == None и пользователь записывается — поле заполняется."""
        USER = 42
        with Session() as s:
            c = _make_contract(s, telegram_id=None)
            cid = c.id
            s.commit()

        with Session() as s:
            contract = s.query(Contract).get(cid)
            assert contract.telegram_id is None
            # Симулируем логику из process_phone_booking
            if not contract.telegram_id:
                contract.telegram_id = USER
                contract.username = f"user_{USER}"
            s.commit()

        with Session() as s:
            contract = s.query(Contract).get(cid)
            assert contract.telegram_id == USER

    def test_contract_not_rebound_by_different_user(self, Session):
        """Если contract.telegram_id уже установлен, другой пользователь не перезаписывает его."""
        USER_A, USER_B = 100, 200
        with Session() as s:
            c = _make_contract(s, telegram_id=USER_A)
            cid = c.id
            s.commit()

        with Session() as s:
            contract = s.query(Contract).get(cid)
            # Логика из process_phone_booking: обновляем только если telegram_id == user_id
            if not contract.telegram_id:
                contract.telegram_id = USER_B
            elif contract.telegram_id == USER_B:
                contract.username = f"user_{USER_B}"
            s.commit()

        with Session() as s:
            contract = s.query(Contract).get(cid)
            assert contract.telegram_id == USER_A  # не изменился


# ---------------------------------------------------------------------------
# Блок 5. Pending cancel — при повторной записи старая отменяется атомарно
# ---------------------------------------------------------------------------

class TestPendingCancelBooking:
    """Старая запись помечается is_cancelled=True при создании новой (атомарность)."""

    def test_old_booking_cancelled_when_same_contract_rebooking(self, Session):
        """
        Если pending_cancel_booking_id установлен и запись не отменена —
        она отменяется при создании новой.
        """
        USER = 42
        with Session() as s:
            c = _make_contract(s, telegram_id=USER)
            old = _make_booking(s, c, user_telegram_id=USER,
                                booking_date=date.today() + timedelta(days=7))
            s.commit()
            old_id = old.id

        # Симулируем атомарную отмену из process_phone_booking
        with Session() as s:
            old_booking = s.query(Booking).get(old_id)
            assert old_booking.is_cancelled is False
            old_booking.is_cancelled = True
            new = Booking(
                contract_id=old_booking.contract_id,
                user_telegram_id=USER,
                date=date.today() + timedelta(days=14),
                time_slot=time(11, 0),
                client_phone="+998901234567",
            )
            s.add(new)
            s.commit()
            new_id = new.id

        with Session() as s:
            assert s.query(Booking).get(old_id).is_cancelled is True
            assert s.query(Booking).get(new_id).is_cancelled is False

    def test_already_cancelled_booking_not_double_cancelled(self, Session):
        """Уже отменённая запись не должна быть затронута повторно."""
        USER = 42
        with Session() as s:
            c = _make_contract(s, telegram_id=USER)
            old = _make_booking(s, c, user_telegram_id=USER,
                                booking_date=date.today() + timedelta(days=7),
                                is_cancelled=True)
            s.commit()
            old_id = old.id

        with Session() as s:
            old_booking = s.query(Booking).get(old_id)
            # Условие из process_phone_booking: if not old_booking.is_cancelled
            if old_booking and not old_booking.is_cancelled:
                old_booking.is_cancelled = True
            s.commit()

        with Session() as s:
            # Запись была already cancelled, флаг не трогали лишний раз
            assert s.query(Booking).get(old_id).is_cancelled is True

"""
Тесты для функционала смены/отвязки привязки договора к Telegram-аккаунту
(админская функция «🔍 Информация по договору»).
"""
import os
import sys
from datetime import date, time, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Base, Contract, Booking, ContractBindingLog
from utils.states import AdminSteps


# ---------- Общие фикстуры in-memory БД ------------------------------------

@pytest.fixture
def memory_session_factory():
    """Создаёт изолированную in-memory SQLite БД и фабрику сессий."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield Session
    engine.dispose()


@pytest.fixture
def seed_contract(memory_session_factory):
    """Создаёт один договор в БД и возвращает (Session, contract_id)."""
    Session = memory_session_factory
    with Session() as s:
        c = Contract(
            house_name="ЖК Тест",
            apt_num="42",
            entrance="1",
            floor=3,
            contract_num="12345-GHP",
            client_fio="Иванов И. И.",
            delivery_date=date(2026, 6, 1),
            telegram_id=111,
            username="oldname",
            href="https://t.me/oldname",
        )
        s.add(c)
        s.commit()
        cid = c.id
    return Session, cid


# ============================================================================
# Чистые функции (без БД и сети)
# ============================================================================

class TestNormalizeContractNum:
    def test_only_digits_appends_ghp(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("12345") == "12345-GHP"

    def test_lowercase_ghp_uppercased(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("12345-ghp") == "12345-GHP"

    def test_mixed_case_ghp_uppercased(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("12345-GhP") == "12345-GHP"

    def test_other_letters_keep_case(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("aB12-ghp-Cd") == "aB12-GHP-Cd"

    def test_strips_spaces(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("  12 345 -ghp ") == "12345-GHP"

    def test_empty_input(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("") == ""

    def test_already_canonical(self):
        from handlers.admin import _normalize_contract_num
        assert _normalize_contract_num("12345-GHP") == "12345-GHP"


class TestHtmlEscape:
    def test_escapes_specials(self):
        from handlers.admin import _h
        assert _h("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"

    def test_none_to_empty(self):
        from handlers.admin import _h
        assert _h(None) == ""


class TestFormatUserBrief:
    def test_no_user(self):
        from handlers.admin import _format_user_brief
        assert _format_user_brief(None, None) == "—"

    def test_id_only(self):
        from handlers.admin import _format_user_brief
        s = _format_user_brief(123, None)
        assert "<code>123</code>" in s
        assert "tg://user?id=123" in s

    def test_id_and_username(self):
        from handlers.admin import _format_user_brief
        s = _format_user_brief(123, "alice")
        assert "<code>123</code>" in s
        assert "@alice" in s
        assert 'href="https://t.me/alice"' in s

    def test_username_special_chars_escaped(self):
        from handlers.admin import _format_user_brief
        # Telegram username не может содержать <, но проверяем безопасность
        s = _format_user_brief(1, "a<b")
        assert "&lt;" in s and "<a<b" not in s


class TestKeyboards:
    def test_actions_kb_with_binding(self):
        from handlers.admin import _build_contract_actions_kb
        c = MagicMock(spec=Contract)
        c.id = 7
        c.telegram_id = 999
        markup = _build_contract_actions_kb(c)
        labels = [b.text for row in markup.inline_keyboard for b in row]
        assert "🔓 Отвязать аккаунт" in labels
        assert "🔁 Сменить аккаунт" in labels
        cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "cbind:unbind:7" in cbs
        assert "cbind:rebind:7" in cbs

    def test_actions_kb_without_binding(self):
        from handlers.admin import _build_contract_actions_kb
        c = MagicMock(spec=Contract)
        c.id = 8
        c.telegram_id = None
        markup = _build_contract_actions_kb(c)
        labels = [b.text for row in markup.inline_keyboard for b in row]
        assert labels == ["🔗 Привязать аккаунт"]
        cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert cbs == ["cbind:rebind:8"]

    def test_confirm_kb(self):
        from handlers.admin import _confirm_kb
        markup = _confirm_kb("unbind", 5)
        cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "cbind:unbind_yes:5" in cbs
        assert "cbind:cancel:5" in cbs


# ============================================================================
# Работа с БД
# ============================================================================

class TestLookupUsernameInDb:
    def test_finds_existing(self, seed_contract):
        from handlers.admin import _lookup_username_in_db
        Session, _ = seed_contract
        with Session() as s:
            tid, uname = _lookup_username_in_db(s, "oldname")
        assert tid == 111
        assert uname == "oldname"

    def test_case_insensitive(self, seed_contract):
        from handlers.admin import _lookup_username_in_db
        Session, _ = seed_contract
        with Session() as s:
            tid, _ = _lookup_username_in_db(s, "OLDNAME")
        assert tid == 111

    def test_strips_at_sign(self, seed_contract):
        from handlers.admin import _lookup_username_in_db
        Session, _ = seed_contract
        with Session() as s:
            tid, _ = _lookup_username_in_db(s, "@oldname")
        assert tid == 111

    def test_not_found(self, seed_contract):
        from handlers.admin import _lookup_username_in_db
        Session, _ = seed_contract
        with Session() as s:
            tid, uname = _lookup_username_in_db(s, "ghost")
        assert tid is None
        assert uname == "ghost"

    def test_empty(self, seed_contract):
        from handlers.admin import _lookup_username_in_db
        Session, _ = seed_contract
        with Session() as s:
            tid, uname = _lookup_username_in_db(s, "")
        assert tid is None and uname is None


class TestLogBindingChange:
    def test_writes_record(self, seed_contract):
        from handlers.admin import _log_binding_change
        Session, cid = seed_contract
        with Session() as s:
            contract = s.query(Contract).get(cid)
            _log_binding_change(
                s,
                contract=contract,
                action="unbind",
                old_telegram_id=111,
                old_username="oldname",
                new_telegram_id=None,
                new_username=None,
                admin_telegram_id=42,
                admin_username="root",
                note="test note",
            )
            s.commit()

            entries = s.query(ContractBindingLog).all()
        assert len(entries) == 1
        e = entries[0]
        assert e.contract_id == cid
        assert e.contract_num == "12345-GHP"
        assert e.action == "unbind"
        assert e.old_telegram_id == 111
        assert e.old_username == "oldname"
        assert e.new_telegram_id is None
        assert e.admin_telegram_id == 42
        assert e.admin_username == "root"
        assert e.note == "test note"
        assert isinstance(e.created_at, datetime)


# ============================================================================
# Резолверы через Bot API (мокаем bot.get_chat)
# ============================================================================

class TestResolveUsernameViaBot:
    @pytest.mark.asyncio
    async def test_returns_id_for_private_user(self):
        from handlers.admin import _resolve_username_via_bot
        bot = MagicMock()
        chat = MagicMock()
        chat.id = 777
        chat.type = "private"
        chat.username = "alice"
        bot.get_chat = AsyncMock(return_value=chat)
        tid, uname = await _resolve_username_via_bot(bot, "alice")
        assert tid == 777
        assert uname == "alice"
        bot.get_chat.assert_awaited_once_with("@alice")

    @pytest.mark.asyncio
    async def test_strips_leading_at(self):
        from handlers.admin import _resolve_username_via_bot
        bot = MagicMock()
        chat = MagicMock()
        chat.id = 1
        chat.type = "private"
        chat.username = "u"
        bot.get_chat = AsyncMock(return_value=chat)
        await _resolve_username_via_bot(bot, "@u")
        bot.get_chat.assert_awaited_once_with("@u")

    @pytest.mark.asyncio
    async def test_returns_none_for_channel(self):
        from handlers.admin import _resolve_username_via_bot
        bot = MagicMock()
        chat = MagicMock()
        chat.id = 1
        chat.type = "channel"
        bot.get_chat = AsyncMock(return_value=chat)
        tid, uname = await _resolve_username_via_bot(bot, "channel")
        assert tid is None and uname is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from handlers.admin import _resolve_username_via_bot
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=Exception("not found"))
        tid, uname = await _resolve_username_via_bot(bot, "ghost")
        assert tid is None and uname is None

    @pytest.mark.asyncio
    async def test_empty_input(self):
        from handlers.admin import _resolve_username_via_bot
        bot = MagicMock()
        bot.get_chat = AsyncMock()
        tid, uname = await _resolve_username_via_bot(bot, "")
        assert tid is None and uname is None
        bot.get_chat.assert_not_called()


class TestResolveIdViaBot:
    @pytest.mark.asyncio
    async def test_returns_username(self):
        from handlers.admin import _resolve_id_via_bot
        bot = MagicMock()
        chat = MagicMock()
        chat.type = "private"
        chat.username = "bob"
        bot.get_chat = AsyncMock(return_value=chat)
        assert await _resolve_id_via_bot(bot, 555) == "bob"

    @pytest.mark.asyncio
    async def test_returns_none_for_non_private(self):
        from handlers.admin import _resolve_id_via_bot
        bot = MagicMock()
        chat = MagicMock()
        chat.type = "group"
        chat.username = "g"
        bot.get_chat = AsyncMock(return_value=chat)
        assert await _resolve_id_via_bot(bot, 555) is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from handlers.admin import _resolve_id_via_bot
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=Exception("forbidden"))
        assert await _resolve_id_via_bot(bot, 1) is None


# ============================================================================
# Inline-callbacks: подтверждение и применение отвязки
# ============================================================================

def _make_callback(data: str, admin_id: int = 42, admin_username: str = "root"):
    cb = AsyncMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = admin_id
    cb.from_user.username = admin_username
    cb.message = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


class TestUnbindFlow:
    @pytest.mark.asyncio
    async def test_unbind_request_shows_confirmation(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        cb = _make_callback(f"cbind:unbind:{cid}")
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_unbind_request(cb, AsyncMock())
        cb.message.answer.assert_awaited()
        kwargs = cb.message.answer.await_args.kwargs
        text = cb.message.answer.await_args.args[0]
        assert "Подтвердите" in text and "12345-GHP" in text
        assert kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_unbind_request_invalid_id(self):
        from handlers import admin as admin_mod
        cb = _make_callback("cbind:unbind:notanumber")
        await admin_mod.cb_unbind_request(cb, AsyncMock())
        cb.answer.assert_awaited_with("Некорректные данные.", show_alert=True)

    @pytest.mark.asyncio
    async def test_unbind_request_already_unbound(self, memory_session_factory):
        from handlers import admin as admin_mod
        Session = memory_session_factory
        with Session() as s:
            c = Contract(contract_num="X", client_fio="X", telegram_id=None)
            s.add(c)
            s.commit()
            cid = c.id
        cb = _make_callback(f"cbind:unbind:{cid}")
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_unbind_request(cb, AsyncMock())
        cb.answer.assert_awaited_with("Договор и так не привязан.", show_alert=True)

    @pytest.mark.asyncio
    async def test_unbind_apply_clears_fields_and_logs(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        cb = _make_callback(f"cbind:unbind_yes:{cid}", admin_id=42, admin_username="root")
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_unbind_apply(cb, AsyncMock())

        with Session() as s:
            contract = s.query(Contract).get(cid)
            assert contract.telegram_id is None
            assert contract.username is None
            assert contract.href is None
            log = s.query(ContractBindingLog).first()
            assert log.action == "unbind"
            assert log.old_telegram_id == 111
            assert log.old_username == "oldname"
            assert log.new_telegram_id is None
            assert log.admin_telegram_id == 42
            assert log.admin_username == "root"

        # Карточка отправлена + сообщение об успехе
        assert cb.message.answer.await_count >= 2
        cb.answer.assert_awaited_with("Готово")


# ============================================================================
# Inline-callbacks: запрос смены и применение
# ============================================================================

class TestRebindRequest:
    @pytest.mark.asyncio
    async def test_sets_state_and_stores_contract_id(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        cb = _make_callback(f"cbind:rebind:{cid}")
        state = AsyncMock()
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_rebind_request(cb, state)
        state.set_state.assert_awaited_with(AdminSteps.waiting_for_rebind_target)
        state.update_data.assert_awaited_with(rebind_contract_id=cid)
        cb.message.answer.assert_awaited()


class TestProcessRebindTarget:
    """Парсинг forward / @username / telegram_id."""

    def _make_message(self, text=None, forward_origin=None, forward_from=None):
        msg = AsyncMock()
        msg.text = text
        msg.forward_origin = forward_origin
        msg.forward_from = forward_from
        msg.bot = MagicMock()
        msg.bot.get_chat = AsyncMock()
        return msg

    @pytest.mark.asyncio
    async def test_no_context_aborts(self):
        from handlers import admin as admin_mod
        msg = self._make_message(text="123")
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})
        await admin_mod.process_rebind_target(msg, state)
        msg.answer.assert_awaited()
        state.set_state.assert_awaited_with(AdminSteps.waiting_for_contract_lookup)

    @pytest.mark.asyncio
    async def test_forward_origin_user(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        sender = MagicMock()
        sender.id = 555
        sender.username = "newuser"
        forward_origin = MagicMock()
        forward_origin.sender_user = sender
        msg = self._make_message(text=None, forward_origin=forward_origin)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        # Сохранили new_id + new_username и показали подтверждение
        state.update_data.assert_any_await(rebind_new_id=555, rebind_new_username="newuser")
        msg.answer.assert_awaited()
        text = msg.answer.await_args.args[0]
        assert "Подтвердите" in text and "newuser" in text

    @pytest.mark.asyncio
    async def test_forward_origin_hidden(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        forward_origin = MagicMock(spec=[])  # без sender_user
        msg = self._make_message(text=None, forward_origin=forward_origin)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        msg.answer.assert_awaited()
        text = msg.answer.await_args.args[0]
        assert "скрыта пересылка" in text

    @pytest.mark.asyncio
    async def test_forward_from_legacy(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        ff = MagicMock()
        ff.id = 777
        ff.username = "legacy"
        msg = self._make_message(text=None, forward_origin=None, forward_from=ff)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        state.update_data.assert_any_await(rebind_new_id=777, rebind_new_username="legacy")

    @pytest.mark.asyncio
    async def test_telegram_id_numeric(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        msg = self._make_message(text="987654321")
        # bot.get_chat вернёт chat без username
        chat = MagicMock()
        chat.type = "private"
        chat.username = None
        msg.bot.get_chat = AsyncMock(return_value=chat)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        state.update_data.assert_any_await(
            rebind_new_id=987654321, rebind_new_username=None
        )

    @pytest.mark.asyncio
    async def test_telegram_id_resolves_username(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        msg = self._make_message(text="987654321")
        chat = MagicMock()
        chat.type = "private"
        chat.username = "resolved"
        msg.bot.get_chat = AsyncMock(return_value=chat)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        state.update_data.assert_any_await(
            rebind_new_id=987654321, rebind_new_username="resolved"
        )

    @pytest.mark.asyncio
    async def test_username_resolved_via_db_cache(self, memory_session_factory):
        """Если @username уже встречается в базе — резолвим без обращения к API."""
        from handlers import admin as admin_mod
        Session = memory_session_factory
        with Session() as s:
            # Договор «жертвы» (его меняем) и договор-источник с известным username
            c1 = Contract(contract_num="A-GHP", client_fio="A", telegram_id=1, username="a")
            c2 = Contract(
                contract_num="B-GHP", client_fio="B",
                telegram_id=222, username="cached", href="https://t.me/cached",
            )
            s.add_all([c1, c2])
            s.commit()
            cid = c1.id
        msg = self._make_message(text="@cached")
        msg.bot.get_chat = AsyncMock()  # не должен вызываться
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        msg.bot.get_chat.assert_not_called()
        state.update_data.assert_any_await(rebind_new_id=222, rebind_new_username="cached")

    @pytest.mark.asyncio
    async def test_username_resolved_via_bot(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        msg = self._make_message(text="@stranger")
        chat = MagicMock()
        chat.id = 333
        chat.type = "private"
        chat.username = "stranger"
        msg.bot.get_chat = AsyncMock(return_value=chat)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        state.update_data.assert_any_await(rebind_new_id=333, rebind_new_username="stranger")

    @pytest.mark.asyncio
    async def test_username_unresolved_asks_again(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        msg = self._make_message(text="@ghost")
        msg.bot.get_chat = AsyncMock(side_effect=Exception("not found"))
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        msg.answer.assert_awaited()
        text = msg.answer.await_args.args[0]
        assert "ghost" in text and "переслать" in text.lower()

    @pytest.mark.asyncio
    async def test_same_user_short_circuit(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract  # contract.telegram_id = 111
        msg = self._make_message(text="111")
        chat = MagicMock()
        chat.type = "private"
        chat.username = "oldname"
        msg.bot.get_chat = AsyncMock(return_value=chat)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"rebind_contract_id": cid})
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.process_rebind_target(msg, state)
        msg.answer.assert_awaited()
        text = msg.answer.await_args.args[0]
        assert "уже привязан" in text


class TestRebindApply:
    @pytest.mark.asyncio
    async def test_apply_writes_fields_and_logs(self, seed_contract):
        from handlers import admin as admin_mod
        Session, cid = seed_contract
        cb = _make_callback(f"cbind:rebind_yes:{cid}", admin_id=42, admin_username="root")
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "rebind_contract_id": cid,
            "rebind_new_id": 999,
            "rebind_new_username": "newone",
        })
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_rebind_apply(cb, state)

        with Session() as s:
            c = s.query(Contract).get(cid)
            assert c.telegram_id == 999
            assert c.username == "newone"
            assert c.href == "https://t.me/newone"
            log = s.query(ContractBindingLog).first()
            assert log.action == "rebind"
            assert log.old_telegram_id == 111
            assert log.old_username == "oldname"
            assert log.new_telegram_id == 999
            assert log.new_username == "newone"
            assert log.admin_telegram_id == 42

        state.set_state.assert_awaited_with(AdminSteps.waiting_for_contract_lookup)
        cb.answer.assert_awaited_with("Готово")

    @pytest.mark.asyncio
    async def test_apply_first_bind_logs_as_bind(self, memory_session_factory):
        from handlers import admin as admin_mod
        Session = memory_session_factory
        with Session() as s:
            c = Contract(contract_num="EMPTY", client_fio="X", telegram_id=None)
            s.add(c)
            s.commit()
            cid = c.id
        cb = _make_callback(f"cbind:rebind_yes:{cid}", admin_id=10, admin_username="adm")
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "rebind_contract_id": cid,
            "rebind_new_id": 5,
            "rebind_new_username": None,
        })
        with patch.object(admin_mod, "SessionLocal", Session):
            await admin_mod.cb_rebind_apply(cb, state)
        with Session() as s:
            c = s.query(Contract).get(cid)
            assert c.telegram_id == 5
            assert c.href == "tg://user?id=5"
            log = s.query(ContractBindingLog).first()
            assert log.action == "bind"
            assert log.old_telegram_id is None

    @pytest.mark.asyncio
    async def test_apply_context_mismatch(self):
        from handlers import admin as admin_mod
        cb = _make_callback("cbind:rebind_yes:7")
        state = AsyncMock()
        # state хранит другой contract_id
        state.get_data = AsyncMock(return_value={"rebind_contract_id": 999})
        await admin_mod.cb_rebind_apply(cb, state)
        cb.answer.assert_awaited_with("Контекст истёк. Начните операцию заново.", show_alert=True)


# ============================================================================
# Cancel callback
# ============================================================================

class TestCancelCallback:
    @pytest.mark.asyncio
    async def test_cancel_clears_rebind_state(self):
        from handlers import admin as admin_mod
        cb = _make_callback("cbind:cancel:1")
        state = AsyncMock()
        state.get_state = AsyncMock(return_value=AdminSteps.waiting_for_rebind_target)
        await admin_mod.cb_cancel(cb, state)
        state.set_state.assert_awaited_with(AdminSteps.waiting_for_contract_lookup)
        state.update_data.assert_awaited_with(rebind_contract_id=None)
        cb.message.answer.assert_awaited_with("Операция отменена.")

    @pytest.mark.asyncio
    async def test_cancel_outside_rebind(self):
        from handlers import admin as admin_mod
        cb = _make_callback("cbind:cancel:1")
        state = AsyncMock()
        state.get_state = AsyncMock(return_value=AdminSteps.waiting_for_contract_lookup)
        await admin_mod.cb_cancel(cb, state)
        state.set_state.assert_not_called()
        cb.message.answer.assert_awaited_with("Операция отменена.")

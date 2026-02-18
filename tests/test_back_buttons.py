"""
Тесты для кнопок «Назад» во всех потоках админ-панели.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.states import AdminSteps


# ==============================================================
#  Тесты клавиатур — наличие кнопки «Назад» в inline-клавиатурах
# ==============================================================

class TestUpdateContractsKeyboards:
    """Клавиатуры потока «Изменение списка договоров»"""

    def test_confirming_keyboard_has_back_button(self):
        """_build_update_contracts_keyboard содержит кнопку Назад"""
        from handlers.admin import _build_update_contracts_keyboard
        builder = _build_update_contracts_keyboard(new_count=3, minor_count=2, review_count=1)
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_buttons = [b for b in all_buttons if b.callback_data == "uc_back"]
        assert len(back_buttons) == 1
        assert "Назад" in back_buttons[0].text

    def test_confirming_keyboard_back_in_bottom_row(self):
        """Кнопка Назад в нижнем ряду вместе с действием и отменой"""
        from handlers.admin import _build_update_contracts_keyboard
        builder = _build_update_contracts_keyboard(new_count=1, minor_count=0, review_count=0)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        assert len(bottom_row) == 3
        callbacks = {b.callback_data for b in bottom_row}
        assert "uc_back" in callbacks
        assert "uc_cancel" in callbacks

    def test_confirming_keyboard_no_selection(self):
        """Без выбора: кнопка-заглушка + назад + отмена"""
        from handlers.admin import _build_update_contracts_keyboard
        builder = _build_update_contracts_keyboard(new_count=2, minor_count=0, review_count=0)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        callbacks = {b.callback_data for b in bottom_row}
        assert "uc_noop" in callbacks
        assert "uc_back" in callbacks
        assert "uc_cancel" in callbacks

    def test_confirming_keyboard_with_review(self):
        """С обзором: кнопка далее + назад + отмена"""
        from handlers.admin import _build_update_contracts_keyboard
        builder = _build_update_contracts_keyboard(new_count=0, minor_count=0, review_count=5)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        callbacks = {b.callback_data for b in bottom_row}
        assert "uc_proceed" in callbacks
        assert "uc_back" in callbacks
        assert "uc_cancel" in callbacks

    def test_review_contract_keyboard_has_back_button(self):
        """_build_review_contract_keyboard содержит кнопку Назад"""
        from handlers.admin import _build_review_contract_keyboard
        contract = {"telegram_id": 123, "active_bookings_count": 1}
        builder = _build_review_contract_keyboard(contract)
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_buttons = [b for b in all_buttons if b.callback_data == "ucrev_back"]
        assert len(back_buttons) == 1
        assert "Назад" in back_buttons[0].text

    def test_review_contract_keyboard_bottom_row(self):
        """Нижний ряд обзора: Готово + Назад + Отменить"""
        from handlers.admin import _build_review_contract_keyboard
        contract = {"telegram_id": None, "active_bookings_count": 0}
        builder = _build_review_contract_keyboard(contract)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        assert len(bottom_row) == 3
        callbacks = {b.callback_data for b in bottom_row}
        assert "ucrev_done" in callbacks
        assert "ucrev_back" in callbacks
        assert "uc_cancel" in callbacks


class TestBookingsKeyboards:
    """Клавиатуры потока «Список записей»"""

    def test_weeks_keyboard_has_no_back_button(self):
        """_build_weeks_keyboard не содержит inline-кнопку Назад"""
        from handlers.admin import _build_weeks_keyboard
        weeks = [(date(2026, 2, 16), date(2026, 2, 22))]
        builder = _build_weeks_keyboard(weeks)
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_buttons = [b for b in all_buttons if b.callback_data == "bkweek_back"]
        assert len(back_buttons) == 0

    def test_weeks_keyboard_bottom_row(self):
        """Нижний ряд недель: выбор/подтверждение + пропустить"""
        from handlers.admin import _build_weeks_keyboard
        weeks = [(date(2026, 2, 16), date(2026, 2, 22))]
        builder = _build_weeks_keyboard(weeks)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        assert len(bottom_row) == 2
        callbacks = {b.callback_data for b in bottom_row}
        assert "bkweek_noop" in callbacks or "bkweek_confirm" in callbacks
        assert "bkweek_skip" in callbacks

    def test_weeks_keyboard_with_selection_no_back(self):
        """С выбранными неделями — inline-кнопки Назад нет"""
        from handlers.admin import _build_weeks_keyboard
        weeks = [(date(2026, 2, 16), date(2026, 2, 22))]
        selected = {date(2026, 2, 16).isoformat()}
        builder = _build_weeks_keyboard(weeks, selected)
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_buttons = [b for b in all_buttons if b.callback_data == "bkweek_back"]
        assert len(back_buttons) == 0

    def test_days_keyboard_has_no_back_button(self):
        """_build_days_keyboard не содержит inline-кнопку Назад"""
        from handlers.admin import _build_days_keyboard
        dates = [date(2026, 2, 17), date(2026, 2, 18)]
        builder = _build_days_keyboard(dates)
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_buttons = [b for b in all_buttons if b.callback_data == "bkday_back"]
        assert len(back_buttons) == 0

    def test_days_keyboard_bottom_row(self):
        """Нижний ряд дней: выбор + пропустить"""
        from handlers.admin import _build_days_keyboard
        dates = [date(2026, 2, 17)]
        builder = _build_days_keyboard(dates)
        markup = builder.as_markup()
        bottom_row = markup.inline_keyboard[-1]
        assert len(bottom_row) == 2
        callbacks = {b.callback_data for b in bottom_row}
        assert "bkday_skip" in callbacks

    def test_projects_keyboard_no_back_button(self):
        """_build_projects_keyboard НЕ содержит кнопку Назад (первый этап)"""
        from handlers.admin import _build_projects_keyboard
        builder = _build_projects_keyboard(["ЖК Навои", "ЖК Алгоритм"])
        markup = builder.as_markup()
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        back_cbs = [b for b in all_buttons if "back" in b.callback_data]
        assert len(back_cbs) == 0


# ==============================================================
#  Тесты reply-клавиатур — полное меню + кнопка Назад сверху
# ==============================================================

class TestReplyKeyboardsUseBack:
    """Проверяем, что start-обработчики показывают полное меню с кнопкой Назад сверху"""

    def _assert_admin_keyboard_with_back(self, kb):
        """Проверить, что клавиатура содержит Назад сверху + полное меню"""
        assert kb is not None
        buttons = [btn.text for row in kb.keyboard for btn in row]
        # Назад есть и это первая кнопка
        assert "🔙 Назад" in buttons
        assert kb.keyboard[0][0].text == "🔙 Назад"
        # Полное меню тоже присутствует
        assert "👥 Управление персоналом" in buttons
        assert "⚙️ Настройки проектов" in buttons

    @pytest.mark.asyncio
    async def test_start_add_admin_uses_back_keyboard(self):
        """start_add_admin отправляет reply-клавиатуру с кнопкой Назад"""
        from handlers.admin import start_add_admin

        msg = AsyncMock()
        state = AsyncMock()
        await start_add_admin(msg, state)

        msg.answer.assert_called_once()
        kb = msg.answer.call_args.kwargs.get("reply_markup")
        self._assert_admin_keyboard_with_back(kb)

    @pytest.mark.asyncio
    async def test_start_add_employee_uses_back_keyboard(self):
        """клавиатура с Назад + полное меню"""
        from handlers.admin import start_add_employee

        msg = AsyncMock()
        state = AsyncMock()
        await start_add_employee(msg, state)

        kb = msg.answer.call_args.kwargs.get("reply_markup")
        self._assert_admin_keyboard_with_back(kb)

    @pytest.mark.asyncio
    async def test_start_delete_staff_uses_back_keyboard(self):
        """клавиатура с Назад + полное меню"""
        from handlers.admin import start_delete_staff

        msg = AsyncMock()
        state = AsyncMock()
        await start_delete_staff(msg, state)

        kb = msg.answer.call_args.kwargs.get("reply_markup")
        self._assert_admin_keyboard_with_back(kb)

    @pytest.mark.asyncio
    async def test_start_add_project_uses_back_keyboard(self):
        """клавиатура с Назад + полное меню"""
        from handlers.admin import start_add_project

        msg = AsyncMock()
        state = AsyncMock()
        await start_add_project(msg, state)

        kb = msg.answer.call_args.kwargs.get("reply_markup")
        self._assert_admin_keyboard_with_back(kb)

    @pytest.mark.asyncio
    async def test_back_button_always_first_in_admin_keyboard(self):
        """Назад всегда первая кнопка в get_admin_keyboard(with_back=True)"""
        from keyboards.reply import get_admin_keyboard
        kb = get_admin_keyboard(with_back=True)
        assert kb.keyboard[0][0].text == "🔙 Назад"
        assert len(kb.keyboard) == 4  # back + 3 rows of menu

    @pytest.mark.asyncio
    async def test_admin_keyboard_without_back(self):
        """get_admin_keyboard() без кнопки Назад"""
        from keyboards.reply import get_admin_keyboard
        kb = get_admin_keyboard()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "🔙 Назад" not in buttons
        assert len(kb.keyboard) == 3

    @pytest.mark.asyncio
    async def test_back_button_first_in_staff_keyboard(self):
        """Назад первая кнопка в get_staff_management_keyboard"""
        from keyboards.reply import get_staff_management_keyboard
        kb = get_staff_management_keyboard()
        assert kb.keyboard[0][0].text == "🔙 Назад"

    @pytest.mark.asyncio
    async def test_back_button_first_in_slots_keyboard(self):
        """Назад первая кнопка в get_slots_management_keyboard"""
        from keyboards.reply import get_slots_management_keyboard
        kb = get_slots_management_keyboard()
        assert kb.keyboard[0][0].text == "🔙 Назад"


# ==============================================================
#  Тесты _handle_back_navigation — маршрутизация «Назад»
# ==============================================================

class TestHandleBackNavigation:
    """Маршрутизация кнопки «Назад» по текущему состоянию"""

    @pytest.fixture
    def msg(self):
        m = AsyncMock()
        m.text = "🔙 Назад"
        m.from_user = MagicMock()
        m.from_user.id = 1
        return m

    @pytest.fixture
    def fsm(self):
        s = AsyncMock()
        s.get_data = AsyncMock(return_value={})
        s.update_data = AsyncMock()
        s.set_state = AsyncMock()
        s.clear = AsyncMock()
        return s

    # --- Добавление проекта ---

    @pytest.mark.asyncio
    async def test_back_from_address_ru_clears_state(self, msg, fsm):
        """add_project_address_ru → главное меню"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_address_ru)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Главное меню" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_address_uz_to_address_ru(self, msg, fsm):
        """add_project_address_uz → add_project_address_ru"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_address_uz)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.add_project_address_ru)
        assert "русском" in str(msg.answer.call_args).lower()

    @pytest.mark.asyncio
    async def test_back_from_slots_limit_to_address_uz(self, msg, fsm):
        """add_project_slots_limit → add_project_address_uz"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_slots_limit)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.add_project_address_uz)
        assert "узбекском" in str(msg.answer.call_args).lower()

    @pytest.mark.asyncio
    async def test_back_from_latitude_to_slots(self, msg, fsm):
        """add_project_latitude → add_project_slots_limit"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_latitude)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.add_project_slots_limit)
        assert "лимит" in str(msg.answer.call_args).lower()

    @pytest.mark.asyncio
    async def test_back_from_longitude_to_latitude(self, msg, fsm):
        """add_project_longitude → add_project_latitude"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_longitude)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.add_project_latitude)
        assert "широту" in str(msg.answer.call_args).lower()

    @pytest.mark.asyncio
    async def test_back_from_excel_to_latitude(self, msg, fsm):
        """add_project_excel → add_project_latitude"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.add_project_excel)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.add_project_latitude)
        assert "широту" in str(msg.answer.call_args).lower()

    # --- Настройки проектов: первые шаги ---

    @pytest.mark.asyncio
    async def test_back_from_selecting_project_for_slots(self, msg, fsm):
        """selecting_project_for_slots → меню настроек"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.selecting_project_for_slots)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Настройки проектов" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_selecting_project_for_address(self, msg, fsm):
        """selecting_project_for_address → меню настроек"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.selecting_project_for_address)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Настройки проектов" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_edit_project_select(self, msg, fsm):
        """edit_project_select → меню настроек"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.edit_project_select)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Настройки проектов" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_update_contracts_selecting_project(self, msg, fsm):
        """update_contracts_selecting_project → меню настроек"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.update_contracts_selecting_project)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Настройки проектов" in str(msg.answer.call_args)

    # --- Установка лимита ---

    @pytest.mark.asyncio
    @patch("handlers.admin.SessionLocal")
    async def test_back_from_slot_limit(self, mock_session, msg, fsm):
        """ждущий_лимит → выбор проекта"""
        from handlers.admin import _handle_back_navigation
        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["ЖК Навои"]
        mock_sess.execute.return_value = mock_result

        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_slot_limit)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.selecting_project_for_slots)
        assert "Выберите проект" in str(msg.answer.call_args)

    # --- Установка адреса ---

    @pytest.mark.asyncio
    @patch("handlers.admin.SessionLocal")
    async def test_back_from_address_ru_settings(self, mock_session, msg, fsm):
        """адрес_ru → выбор проекта"""
        from handlers.admin import _handle_back_navigation
        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["ЖК Навои"]
        mock_sess.execute.return_value = mock_result

        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_address_ru)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.selecting_project_for_address)
        assert "Выберите проект" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_address_uz_to_ru(self, msg, fsm):
        """waiting_for_address_uz → waiting_for_address_ru"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_address_uz)
        fsm.get_data = AsyncMock(return_value={"selected_project": "ЖК Навои"})
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.waiting_for_address_ru)
        assert "русском" in str(msg.answer.call_args).lower()

    # --- Установка координат ---

    @pytest.mark.asyncio
    @patch("handlers.admin.SessionLocal")
    async def test_back_from_edit_latitude(self, mock_session, msg, fsm):
        """широта → выбор проекта"""
        from handlers.admin import _handle_back_navigation
        mock_sess = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_sess)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["ЖК Навои"]
        mock_sess.execute.return_value = mock_result

        fsm.get_state = AsyncMock(return_value=AdminSteps.edit_project_latitude)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.edit_project_select)
        assert "Выберите проект" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_edit_longitude_to_latitude(self, msg, fsm):
        """edit_project_longitude → edit_project_latitude"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.edit_project_longitude)
        fsm.get_data = AsyncMock(return_value={"selected_project": "ЖК Навои"})
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.edit_project_latitude)
        assert "широту" in str(msg.answer.call_args).lower()

    # --- Изменение списка договоров: ожидание Excel ---

    @pytest.mark.asyncio
    @patch("handlers.admin.SessionLocal")
    async def test_back_from_waiting_excel_to_project_list(self, mock_session, msg, fsm):
        """update_contracts_waiting_excel → update_contracts_selecting_project"""
        from handlers.admin import _handle_back_navigation

        mock_sess = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_sess
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["ЖК Навои"]
        mock_sess.execute.return_value = mock_result

        fsm.get_state = AsyncMock(return_value=AdminSteps.update_contracts_waiting_excel)
        await _handle_back_navigation(msg, fsm)
        fsm.set_state.assert_called_with(AdminSteps.update_contracts_selecting_project)
        assert "Выберите проект" in str(msg.answer.call_args)

    # --- Управление персоналом ---

    @pytest.mark.asyncio
    async def test_back_from_waiting_admin_id(self, msg, fsm):
        """waiting_for_admin_id → меню управления персоналом"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_admin_id)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Управление персоналом" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_waiting_employee_id(self, msg, fsm):
        """waiting_for_employee_id → меню управления персоналом"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_employee_id)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Управление персоналом" in str(msg.answer.call_args)

    @pytest.mark.asyncio
    async def test_back_from_waiting_staff_delete_id(self, msg, fsm):
        """waiting_for_staff_id_to_delete → меню управления персоналом"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value=AdminSteps.waiting_for_staff_id_to_delete)
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Управление персоналом" in str(msg.answer.call_args)

    # --- Дефолт ---

    @pytest.mark.asyncio
    async def test_back_from_unknown_state_goes_to_main(self, msg, fsm):
        """Неизвестное состояние → главное меню"""
        from handlers.admin import _handle_back_navigation
        fsm.get_state = AsyncMock(return_value="SomeUnknownState:step")
        await _handle_back_navigation(msg, fsm)
        fsm.clear.assert_called_once()
        assert "Главное меню" in str(msg.answer.call_args)


# ==============================================================
#  Тесты inline-обработчиков «Назад» в потоке записей
# ==============================================================

# ==============================================================
#  Тесты inline-обработчиков «Назад» в потоке обновления договоров
# ==============================================================

class TestUpdateContractsBackHandlers:
    """Обработчики inline-кнопок «Назад» в потоке обновления договоров"""

    @pytest.mark.asyncio
    async def test_review_back_first_contract_to_confirming(self):
        """ucrev_back на первом договоре → экран подтверждения"""
        from handlers.admin import update_contracts_review_action

        callback = AsyncMock()
        callback.data = "ucrev_back"
        callback.message = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "uc_review_contracts": [{"type": "fio_change", "apt_num": "1", "changes": {"client_fio": {"old": "A", "new": "B"}}}],
            "uc_review_index": 0,
            "uc_review_decisions": {},
            "uc_analysis": {"new_contracts": [], "changed_contracts": []},
            "uc_project": "ЖК Навои",
            "uc_minor_updates": [],
            "uc_selected": [],
        })

        bot = AsyncMock()
        await update_contracts_review_action(callback, state, bot)

        state.set_state.assert_called_with(AdminSteps.update_contracts_confirming)

    @pytest.mark.asyncio
    @patch("handlers.admin._show_review_contract", new_callable=AsyncMock)
    async def test_review_back_second_contract_to_first(self, mock_show_review):
        """ucrev_back на втором договоре → первый договор"""
        from handlers.admin import update_contracts_review_action

        contracts = [
            {"type": "fio_change", "apt_num": "1", "changes": {"client_fio": {"old": "A", "new": "B"}}},
            {"type": "fio_change", "apt_num": "2", "changes": {"client_fio": {"old": "C", "new": "D"}}},
        ]

        callback = AsyncMock()
        callback.data = "ucrev_back"
        callback.message = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "uc_review_contracts": contracts,
            "uc_review_index": 1,
            "uc_review_decisions": {},
        })

        bot = AsyncMock()
        await update_contracts_review_action(callback, state, bot)

        # Должен установить индекс 0 и показать первый договор
        state.update_data.assert_called_with(uc_review_index=0)
        mock_show_review.assert_called_once_with(callback, state)

    @pytest.mark.asyncio
    @patch("handlers.admin._show_review_contract", new_callable=AsyncMock)
    async def test_final_summary_back_to_last_review(self, mock_show_review):
        """uc_back_to_review из итогового экрана → последний обзорный договор"""
        from handlers.admin import update_contracts_back_to_review

        contracts = [
            {"type": "fio_change", "apt_num": "1", "changes": {"client_fio": {"old": "A", "new": "B"}}},
            {"type": "fio_change", "apt_num": "2", "changes": {"client_fio": {"old": "C", "new": "D"}}},
            {"type": "contract_change", "apt_num": "3", "old_contract_num": "X", "new_contract_num": "Y",
             "telegram_id": None, "active_bookings_count": 0, "changes": {}},
        ]

        callback = AsyncMock()
        callback.message = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "uc_review_contracts": contracts,
            "uc_review_index": 3,
            "uc_review_decisions": {},
        })

        await update_contracts_back_to_review(callback, state)

        # Должен установить индекс на последний (2)
        state.update_data.assert_called_with(uc_review_index=2)
        mock_show_review.assert_called_once_with(callback, state)

    @pytest.mark.asyncio
    @patch("handlers.admin.SessionLocal")
    async def test_confirming_back_to_project_selection(self, mock_session):
        """uc_back из экрана подтверждения → выбор проекта"""
        from handlers.admin import update_contracts_back_to_projects

        mock_sess = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_sess
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["ЖК Навои", "ЖК Алгоритм"]
        mock_sess.execute.return_value = mock_result

        callback = AsyncMock()
        callback.message = AsyncMock()

        state = AsyncMock()

        await update_contracts_back_to_projects(callback, state)

        state.set_state.assert_called_with(AdminSteps.update_contracts_selecting_project)
        callback.message.edit_text.assert_called_once()
        assert "Выберите проект" in str(callback.message.edit_text.call_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

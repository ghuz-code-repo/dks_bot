"""Обработчики для сотрудников (не администраторов)"""
import os
from datetime import datetime, date, timedelta
import pandas as pd
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from database.models import Booking, Contract
from database.session import SessionLocal
from keyboards.reply import get_employee_keyboard
from utils.auth import is_staff
from utils.states import EmployeeSteps

router = Router()


class IsStaffFilter(BaseFilter):
    """Фильтр для сотрудников (не админов)"""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        from utils.auth import is_admin
        # Только сотрудники, но не админы
        return is_staff(event.from_user.id) and not is_admin(event.from_user.id)


# Применяем фильтр ко всему роутеру
router.message.filter(IsStaffFilter())
router.callback_query.filter(IsStaffFilter())


@router.message(Command("menu"))
async def show_employee_menu(message: types.Message):
    """Показать меню сотрудника"""
    await message.answer(
        "👔 Панель сотрудника", 
        reply_markup=get_employee_keyboard()
    )


@router.message(F.text == "🔙 Скрыть меню")
async def hide_menu(message: types.Message):
    """Возврат в главное меню"""
    await message.answer("Главное меню:", reply_markup=get_employee_keyboard())


@router.message(F.text == "📊 Выгрузить отчет")
async def export_report_employee(message: types.Message):
    """Выгрузить отчет (для сотрудников)"""
    # Отправляем сообщение о выполнении операции
    loading_msg = await message.answer("⏳ Ваша операция выполняется, подождите...")
    
    try:
        with SessionLocal() as session:
            query = (
                select(
                    Booking.date.label("Дата визита"),
                    Booking.time_slot.label("Время"),
                    Contract.client_fio.label("ФИО Клиента"),
                    Booking.client_phone.label("Телефон клиента"),
                    Contract.contract_num.label("Договор"),
                    Contract.house_name.label("Дом"),
                    Contract.entrance.label("Подъезд"),
                    Contract.apt_num.label("Кв")
                )
                .join(Contract, Booking.contract_id == Contract.id)
                .filter(Booking.is_cancelled == False)
                .order_by(Booking.date.desc(), Booking.time_slot.desc())
            )

            results = session.execute(query).all()

            if not results:
                await loading_msg.delete()
                return await message.answer("Записи в базе данных отсутствуют.", reply_markup=get_employee_keyboard())

            df = pd.DataFrame(results, columns=[
                "Дата визита", "Время", "ФИО Клиента", "Телефон клиента",
                "Договор", "Дом", "Подъезд", "Кв"
            ])

            df['Время'] = df['Время'].apply(lambda x: x.strftime('%H:%M') if x else "")

            report_path = "data/bookings_report.xlsx"
            df.to_excel(report_path, index=False)

        # Удаляем сообщение о загрузке
        await loading_msg.delete()
        
        await message.answer_document(
            FSInputFile(report_path),
            caption=f"Отчет о записях на {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        os.remove(report_path)
    except Exception as e:
        try:
            await loading_msg.delete()
        except:
            pass
        await message.answer(f"❌ Ошибка при формировании отчета: {e}", reply_markup=get_employee_keyboard())


@router.message(F.text == "📋 Список записей")
async def show_bookings_list_employee(message: types.Message, state: FSMContext):
    """Показать выбор проекта для просмотра записей (сотрудник)"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]

    if not projects:
        return await message.answer("❌ В базе нет проектов.", reply_markup=get_employee_keyboard())

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for project in projects:
        builder.button(text=project, callback_data=f"empbk_{project[:40]}")
    builder.button(text="⏩ Пропустить", callback_data="empbk_skip_project")
    builder.adjust(1)

    await state.set_state(EmployeeSteps.selecting_project_for_bookings)
    await message.answer(
        "📋 Выберите проект для просмотра записей:",
        reply_markup=builder.as_markup()
    )


def _emp_get_booking_weeks(session, project_name=None):
    """Получить список недель с активными записями (для сотрудника)."""
    today = date.today()
    query = (
        session.query(Booking.date)
        .join(Contract, Booking.contract_id == Contract.id)
        .filter(Booking.date >= today, Booking.is_cancelled == False)
    )
    if project_name:
        query = query.filter(Contract.house_name == project_name)
    dates = sorted(set(d[0] for d in query.all()))
    if not dates:
        return []
    weeks = []
    seen = set()
    for d in dates:
        week_start = d - timedelta(days=d.weekday())
        if week_start in seen:
            continue
        seen.add(week_start)
        week_end = week_start + timedelta(days=6)
        weeks.append((week_start, week_end))
    return weeks


def _emp_build_weeks_keyboard(weeks, selected=None):
    """Построить клавиатуру выбора недель для сотрудника."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()
    builder = InlineKeyboardBuilder()
    for ws, we in weeks:
        label = f"{ws.strftime('%d.%m')}-{we.strftime('%d.%m')}"
        key = ws.isoformat()
        if key in selected:
            label = "✅ " + label
        builder.button(text=label, callback_data=f"empwk_{key}")
    # Нижний ряд: подтвердить + пропустить (всегда 2 кнопки)
    if selected:
        builder.button(text="✅ Подтвердить выбор", callback_data="empwk_confirm")
    else:
        builder.button(text="▫️ Выберите неделю", callback_data="empwk_noop")
    builder.button(text="⏩ Пропустить", callback_data="empwk_skip")
    week_rows = [2] * (len(weeks) // 2)
    if len(weeks) % 2:
        week_rows.append(1)
    builder.adjust(*week_rows, 2)
    return builder


@router.callback_query(F.data.startswith("empbk_"))
async def emp_on_project_selected(callback: types.CallbackQuery, state: FSMContext):
    """Сотрудник: выбор проекта → показать выбор недель."""
    raw = callback.data.split("_", 1)[1]
    project_name = None if raw == "skip_project" else raw

    await state.update_data(bk_project=project_name, bk_selected_weeks=[], bk_date_from=None, bk_date_to=None)

    with SessionLocal() as session:
        weeks = _emp_get_booking_weeks(session, project_name)

    if not weeks:
        label = f"проекту **{project_name}**" if project_name else "всем проектам"
        await callback.message.edit_text(f"📋 По {label} активных записей нет.", parse_mode="Markdown")
        await callback.message.answer("Панель сотрудника:", reply_markup=get_employee_keyboard())
        await state.clear()
        await callback.answer()
        return

    builder = _emp_build_weeks_keyboard(weeks)
    await state.set_state(EmployeeSteps.selecting_weeks_for_bookings)
    await callback.message.edit_text(
        "📅 Выберите недели для просмотра (можно несколько):",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("empwk_"), EmployeeSteps.selecting_weeks_for_bookings)
async def emp_on_week_toggled(callback: types.CallbackQuery, state: FSMContext):
    """Сотрудник: мультивыбор недель."""
    action = callback.data.split("_", 1)[1]

    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    project_name = data.get("bk_project")
    selected = set(data.get("bk_selected_weeks", []))

    if action == "skip":
        await state.update_data(bk_selected_weeks=[], bk_date_from=None, bk_date_to=None)
        await _emp_show_filtered_bookings(callback, state)
        return

    if action == "confirm":
        selected_list = sorted(selected)
        if len(selected_list) == 1:
            ws = date.fromisoformat(selected_list[0])
            we = ws + timedelta(days=6)
            await state.update_data(bk_selected_weeks=selected_list)
            await _emp_show_day_selection(callback, state, ws, we, project_name)
            return
        else:
            all_starts = [date.fromisoformat(s) for s in selected_list]
            date_from = min(all_starts)
            date_to = max(all_starts) + timedelta(days=6)
            await state.update_data(bk_selected_weeks=selected_list, bk_date_from=date_from.isoformat(), bk_date_to=date_to.isoformat())
            await _emp_show_filtered_bookings(callback, state)
            return

    week_key = action
    if week_key in selected:
        selected.discard(week_key)
    else:
        selected.add(week_key)

    await state.update_data(bk_selected_weeks=list(selected))

    with SessionLocal() as session:
        weeks = _emp_get_booking_weeks(session, project_name)
    builder = _emp_build_weeks_keyboard(weeks, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


def _emp_build_days_keyboard(booking_dates, selected=None):
    """Построить клавиатуру мультивыбора дней для сотрудника."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()
    builder = InlineKeyboardBuilder()
    for d in booking_dates:
        label = d.strftime('%d.%m.%Y')
        key = d.isoformat()
        if key in selected:
            label = "✅ " + label
        builder.button(text=label, callback_data=f"empdy_{key}")
    # Нижний ряд: подтвердить + пропустить (всегда 2 кнопки)
    if selected:
        builder.button(text="✅ Подтвердить выбор", callback_data="empdy_confirm")
    else:
        builder.button(text="▫️ Выберите день", callback_data="empdy_noop")
    builder.button(text="⏩ Пропустить (вся неделя)", callback_data="empdy_skip")
    day_rows = [2] * (len(booking_dates) // 2)
    if len(booking_dates) % 2:
        day_rows.append(1)
    builder.adjust(*day_rows, 2)
    return builder


def _emp_get_booking_dates_in_week(session, week_start, week_end, project_name=None):
    """Получить даты с записями внутри недели (для сотрудника)."""
    today = date.today()
    query = (
        session.query(Booking.date)
        .join(Contract, Booking.contract_id == Contract.id)
        .filter(
            Booking.date >= max(week_start, today),
            Booking.date <= week_end,
            Booking.is_cancelled == False,
        )
    )
    if project_name:
        query = query.filter(Contract.house_name == project_name)
    return sorted(set(d[0] for d in query.all()))


async def _emp_show_day_selection(callback, state, week_start, week_end, project_name):
    """Сотрудник: выбор конкретных дней внутри недели (мультивыбор)."""
    with SessionLocal() as session:
        booking_dates = _emp_get_booking_dates_in_week(session, week_start, week_end, project_name)

    if not booking_dates:
        await state.update_data(bk_date_from=week_start.isoformat(), bk_date_to=week_end.isoformat())
        await _emp_show_filtered_bookings(callback, state)
        return

    await state.update_data(bk_selected_days=[])
    builder = _emp_build_days_keyboard(booking_dates)

    await state.set_state(EmployeeSteps.selecting_day_for_bookings)
    await callback.message.edit_text(
        f"📅 Выберите дни ({week_start.strftime('%d.%m')}-{week_end.strftime('%d.%m')}), можно несколько:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("empdy_"), EmployeeSteps.selecting_day_for_bookings)
async def emp_on_day_selected(callback: types.CallbackQuery, state: FSMContext):
    """Сотрудник: мультивыбор дней."""
    action = callback.data.split("_", 1)[1]

    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    project_name = data.get("bk_project")
    selected = set(data.get("bk_selected_days", []))
    selected_weeks = data.get("bk_selected_weeks", [])

    if action == "skip":
        if selected_weeks:
            ws = date.fromisoformat(selected_weeks[0])
            we = ws + timedelta(days=6)
            await state.update_data(bk_date_from=ws.isoformat(), bk_date_to=we.isoformat(), bk_dates=None)
        await _emp_show_filtered_bookings(callback, state)
        return

    if action == "confirm":
        await state.update_data(bk_dates=sorted(selected), bk_date_from=None, bk_date_to=None)
        await _emp_show_filtered_bookings(callback, state)
        return

    # Toggle конкретного дня
    day_key = action
    if day_key in selected:
        selected.discard(day_key)
    else:
        selected.add(day_key)

    await state.update_data(bk_selected_days=list(selected))

    if selected_weeks:
        ws = date.fromisoformat(selected_weeks[0])
        we = ws + timedelta(days=6)
    else:
        ws = date.today()
        we = ws + timedelta(days=6)

    with SessionLocal() as session:
        booking_dates = _emp_get_booking_dates_in_week(session, ws, we, project_name)
    builder = _emp_build_days_keyboard(booking_dates, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


async def _emp_show_filtered_bookings(callback: types.CallbackQuery, state: FSMContext):
    """Сотрудник: показать отфильтрованные записи."""
    data = await state.get_data()
    project_name = data.get("bk_project")
    date_from_str = data.get("bk_date_from")
    date_to_str = data.get("bk_date_to")
    bk_dates = data.get("bk_dates")  # Список конкретных дат (ISO)
    await state.clear()

    with SessionLocal() as session:
        today = date.today()
        query = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(Booking.is_cancelled == False)
        )

        if project_name:
            query = query.filter(Contract.house_name == project_name)

        if bk_dates:
            date_objects = [date.fromisoformat(d) for d in bk_dates]
            query = query.filter(Booking.date.in_(date_objects), Booking.date >= today)
        elif date_from_str and date_to_str:
            d_from = date.fromisoformat(date_from_str)
            d_to = date.fromisoformat(date_to_str)
            query = query.filter(Booking.date >= max(d_from, today), Booking.date <= d_to)
        else:
            query = query.filter(Booking.date >= today)

        bookings = (
            query
            .order_by(Booking.date, Contract.house_name, Contract.entrance, Contract.floor, Booking.time_slot)
            .all()
        )

        if not bookings:
            label = f"проекту **{project_name}**" if project_name else "всем проектам"
            await callback.message.edit_text(f"📋 По {label} записей не найдено.", parse_mode="Markdown")
            await callback.message.answer("Панель сотрудника:", reply_markup=get_employee_keyboard())
            await callback.answer()
            return

        # Определяем первую (самую раннюю) запись для каждого договора
        from sqlalchemy import func as sa_func
        contract_ids = set(contract.id for _, contract in bookings)
        first_booking_subq = (
            session.query(
                Booking.contract_id,
                sa_func.min(Booking.id).label("first_booking_id")
            )
            .filter(Booking.contract_id.in_(contract_ids), Booking.is_cancelled == False)
            .group_by(Booking.contract_id)
            .all()
        )
        first_booking_ids = {row.first_booking_id for row in first_booking_subq}

        # Заголовок
        if project_name:
            header = f"📋 **{project_name}**"
        else:
            header = "📋 **Все проекты**"

        if bk_dates:
            date_objects = sorted([date.fromisoformat(d) for d in bk_dates])
            header += " — " + ", ".join(d.strftime('%d.%m') for d in date_objects)
        elif date_from_str and date_to_str:
            d_from = date.fromisoformat(date_from_str)
            d_to = date.fromisoformat(date_to_str)
            if d_from == d_to:
                header += f" — {d_from.strftime('%d.%m.%Y')}"
            else:
                header += f" — {d_from.strftime('%d.%m')}-{d_to.strftime('%d.%m')}"
        else:
            header += " — все записи"

        text = header + "\n"
        current_date = None
        current_house = None
        current_entrance = None
        current_floor = None

        for booking, contract in bookings:
            if booking.date != current_date:
                current_date = booking.date
                current_house = None
                current_entrance = None
                current_floor = None
                text += f"\n📅 **{booking.date.strftime('%d.%m')}**\n"

            if not project_name and contract.house_name != current_house:
                current_house = contract.house_name
                current_entrance = None
                current_floor = None
                text += f"🏠 **{contract.house_name}**\n"

            if contract.entrance and contract.entrance != current_entrance:
                current_entrance = contract.entrance
                current_floor = None
                text += f"  🚪 Подъезд {contract.entrance}\n"

            if contract.floor is not None and contract.floor != current_floor:
                current_floor = contract.floor
                text += f"    🔹 Этаж {contract.floor}\n"

            text += (
                f"      🕐 {booking.time_slot.strftime('%H:%M')} — "
                f"{contract.client_fio} (кв.{contract.apt_num})"
                f"{' _(повторная)_' if booking.id not in first_booking_ids else ''}\n"
            )

    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await callback.message.edit_text(text, parse_mode="Markdown")
    else:
        await callback.message.delete()
        parts = []
        current_part = ""
        for line in text.split("\n"):
            if len(current_part) + len(line) + 1 > MAX_LEN:
                parts.append(current_part)
                current_part = line + "\n"
            else:
                current_part += line + "\n"
        if current_part.strip():
            parts.append(current_part)
        for part in parts:
            await callback.message.answer(part, parse_mode="Markdown")

    await callback.message.answer("Панель сотрудника:", reply_markup=get_employee_keyboard())
    await callback.answer()


@router.message(F.text == "🏠 Список проектов")
async def show_projects_list_employee(message: types.Message):
    """Показать список всех проектов (для сотрудников)"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]
        
        if not projects:
            return await message.answer("❌ В базе нет проектов.", reply_markup=get_employee_keyboard())
        
        text = "🏠 **Список проектов:**\n\n"
        for idx, project in enumerate(sorted(projects), 1):
            count = session.query(Contract).filter_by(house_name=project).count()
            text += f"{idx}. **{project}** — {count} договоров\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_employee_keyboard())

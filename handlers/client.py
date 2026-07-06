import logging
import re
import asyncio
from datetime import datetime, timedelta, date

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func

from config import ADMIN_ID, DKS_CONTACTS
from database.models import Booking, Setting, Contract, Staff, ProjectSlots
from database.session import SessionLocal
from keyboards.inline import generate_time_slots, generate_calendar, get_min_booking_date, get_fully_booked_dates, SLOTS_PER_DAY, TASHKENT_TZ, build_tg_profile_kb
from utils.holidays import get_holiday_dates
from keyboards.reply import get_phone_request_keyboard, get_client_keyboard, BUTTON_TEXTS
from utils.states import ClientSteps
from utils.language import get_user_language, toggle_language, get_message, get_user_phone, set_user_phone, build_tg_href, format_tg_contact_md

router = Router()

# Адреса по умолчанию (используются только для раздела "Контакты")
DEFAULT_ADDRESS_RU = "г. Ташкент, Яшнабадский район, ул. Фаргона йули 27 (O'Z Zamin)"
DEFAULT_ADDRESS_UZ = "Toshkent sh., Yashnobod tumani, Farg'ona yo'li ko'chasi 27 (O'Z Zamin)"
OFFICE_LAT = DKS_CONTACTS.get("latitude", 41.302006)
OFFICE_LON = DKS_CONTACTS.get("longitude", 69.292259)
OFFICE_PHONE = "+998781485115"


def get_project_address(project_name: str, lang: str = 'ru') -> str | None:
    """Получить адрес проекта из базы. Возвращает None если не установлен."""
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        if project_slot:
            if lang == 'uz' and project_slot.address_uz:
                return project_slot.address_uz
            elif project_slot.address_ru:
                return project_slot.address_ru
    return None


def get_project_coordinates(project_name: str) -> tuple[float, float] | None:
    """
    Получить координаты проекта из базы.
    
    Args:
        project_name: Название проекта
    
    Returns:
        tuple: (широта, долгота) или None если координаты не установлены
    """
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        if project_slot and project_slot.latitude and project_slot.longitude:
            try:
                return float(project_slot.latitude), float(project_slot.longitude)
            except (ValueError, TypeError):
                return None
    return None


def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Валидация номера телефона.
    Разрешены только номера Узбекистана (+998), России (+7) и Казахстана (+7).
    
    Args:
        phone: Введённый номер телефона
    
    Returns:
        tuple: (is_valid, cleaned_phone) - валиден ли номер и очищенная версия
    """
    # Удаляем все пробелы, дефисы, скобки
    cleaned = re.sub(r'[\s\-\(\)]+', '', phone)
    
    # Проверяем, что остались только цифры и возможно + в начале
    if not re.match(r'^\+?\d+$', cleaned):
        return False, ""
    
    # Удаляем + для унификации
    digits_only = cleaned.lstrip('+')
    
    # Нормализация: если ввели через 8 (Россия/Казахстан) — заменяем на 7
    if digits_only.startswith('8') and len(digits_only) == 11:
        digits_only = '7' + digits_only[1:]
    
    # Узбекистан: +998 XX XXX XX XX (12 цифр)
    if digits_only.startswith('998') and len(digits_only) == 12:
        return True, '+' + digits_only
    
    # Россия / Казахстан: +7 XXX XXX XX XX (11 цифр)
    if digits_only.startswith('7') and len(digits_only) == 11:
        return True, '+' + digits_only
    
    return False, ""


def get_project_slot_limit(session, project_name: str) -> int:
    """
    Получить лимит слотов для конкретного проекта.
    
    Args:
        session: SQLAlchemy сессия
        project_name: Название проекта (house_name)
    
    Returns:
        int: Лимит записей на один слот (default 1 если проект не найден)
    """
    # Проверяем индивидуальный лимит для проекта
    project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
    if project_slot:
        return project_slot.slots_limit
    
    # Если проекта нет в ProjectSlots, возвращаем default=1
    # (для обратной совместимости со старыми проектами)
    return 1


def get_min_cancellation_date() -> date:
    """
    Рассчитывает минимальную дату для отмены записи (аналогично записи):
    - До 12:00 — следующий рабочий день
    - После 12:00 — через один рабочий день
    """
    return get_min_booking_date()


def can_cancel_booking(booking_date: date, booking_time) -> bool:
    """Проверяет, можно ли отменить запись на указанную дату"""
    # Если запись на выходной или праздник — можно отменить до времени записи
    holiday_dates = get_holiday_dates(booking_date, booking_date)
    if booking_date.weekday() >= 5 or booking_date in holiday_dates:
        now = datetime.now(TASHKENT_TZ)
        booking_dt = datetime.combine(booking_date, booking_time, tzinfo=TASHKENT_TZ)
        return now < booking_dt
    min_date = get_min_cancellation_date()
    return booking_date >= min_date


# ========== КНОПКИ КЛИЕНТСКОЙ КЛАВИАТУРЫ ==========

@router.message(F.text.in_([BUTTON_TEXTS['add_booking']['ru'], BUTTON_TEXTS['add_booking']['uz']]))
async def add_booking_button(message: types.Message, state: FSMContext):
    """Начало процесса добавления записи — сразу запрашиваем номер договора"""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language(user_id)

    await state.set_state(ClientSteps.entering_contract)
    await message.answer(
        get_message('enter_contract', lang)
    )


@router.message(F.text.in_([BUTTON_TEXTS['cancel_booking']['ru'], BUTTON_TEXTS['cancel_booking']['uz']]))
async def cancel_booking_button(message: types.Message, state: FSMContext):
    """Начало процесса отмены записи"""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    
    with SessionLocal() as session:
        # Показываем записи по привязке договора — единственный источник истины
        today = date.today()
        bookings = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )
        
        if not bookings:
            await message.answer(
                get_message('no_bookings_to_cancel', lang),
                reply_markup=get_client_keyboard(lang)
            )
            return
        
        # Формируем текст со списком записей и кнопки
        builder = InlineKeyboardBuilder()
        cancellable_found = False
        
        if lang == 'uz':
            text_lines = ["📋 **Sizning yozuvlaringiz:**\n"]
        else:
            text_lines = ["📋 **Ваши записи:**\n"]
        
        for idx, (booking, contract) in enumerate(bookings, 1):
            can_cancel = can_cancel_booking(booking.date, booking.time_slot)
            date_str = booking.date.strftime('%d.%m.%Y')
            time_str = booking.time_slot.strftime('%H:%M')
            
            if can_cancel:
                cancellable_found = True
                text_lines.append(f"**{idx}.** 📅 {date_str} ⏰ {time_str}")
                text_lines.append(f"    🏠 {contract.house_name}, кв. {contract.apt_num}\n")
                builder.button(
                    text=f"❌ Отменить #{idx}" if lang == 'ru' else f"❌ Bekor qilish #{idx}",
                    callback_data=f"cancel_{booking.id}"
                )
            else:
                text_lines.append(f"**{idx}.** 🔒 {date_str} ⏰ {time_str}")
                text_lines.append(f"    🏠 {contract.house_name}, кв. {contract.apt_num}")
                if lang == 'uz':
                    text_lines.append(f"    _(bekor qilib bo'lmaydi)_\n")
                else:
                    text_lines.append(f"    _(отмена недоступна)_\n")
        
        builder.button(text=get_message('back', lang), callback_data="cancel_back")
        builder.adjust(1)
        
        text = "\n".join(text_lines)
        if not cancellable_found:
            text += "\n" + get_message('all_bookings_blocked', lang)
        else:
            if lang == 'uz':
                text += "\nBekor qilish uchun tugmani bosing:"
            else:
                text += "\nНажмите кнопку для отмены:"
        
        await state.set_state(ClientSteps.cancel_selecting_booking)
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.message(F.text.in_([BUTTON_TEXTS['my_bookings']['ru'], BUTTON_TEXTS['my_bookings']['uz']]))
async def my_bookings_button(message: types.Message, state: FSMContext):
    """Показать все записи пользователя"""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    
    with SessionLocal() as session:
        today = date.today()
        # Показываем записи по привязке договора — единственный источник истины
        bookings = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )
        
        if not bookings:
            await message.answer(
                get_message('no_bookings', lang),
                reply_markup=get_client_keyboard(lang)
            )
            return
        
        text = get_message('my_bookings_header', lang) + "\n\n"
        
        for booking, contract in bookings:
            date_str = booking.date.strftime('%d.%m.%Y')
            time_str = booking.time_slot.strftime('%H:%M')
            text += get_message('booking_item', lang, 
                               date=date_str, 
                               time=time_str, 
                               house=contract.house_name, 
                               apt=contract.apt_num) + "\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_client_keyboard(lang))


@router.message(F.text.in_([BUTTON_TEXTS['contacts']['ru'], BUTTON_TEXTS['contacts']['uz']]))
async def contacts_button(message: types.Message, state: FSMContext):
    """Показать контакты отдела ДКС"""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    
    if lang == 'ru':
        address = DKS_CONTACTS['address_ru']
        hours = DKS_CONTACTS['working_hours_ru']
    else:
        address = DKS_CONTACTS['address_uz']
        hours = DKS_CONTACTS['working_hours_uz']
    
    text = get_message('contacts', lang, 
                      phone=DKS_CONTACTS['phone'],
                      address=address,
                      hours=hours)
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_client_keyboard(lang))
    
    # Отправляем геолокацию офиса (для раздела "Контакты")
    await message.bot.send_location(
        chat_id=message.from_user.id,
        latitude=OFFICE_LAT,
        longitude=OFFICE_LON
    )


# ========== КАЛЕНДАРЬ ЗАПИСЕЙ ==========

@router.message(F.text.in_([BUTTON_TEXTS['view_calendar']['ru'], BUTTON_TEXTS['view_calendar']['uz']]))
async def view_calendar_button(message: types.Message, state: FSMContext):
    """Перезапись: показать активные записи пользователя для выбора"""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    today = date.today()

    with SessionLocal() as session:
        # Показываем записи по привязке договора — единственный источник истины
        active_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )

        if not active_bookings:
            await message.answer(
                get_message('no_active_bookings_rebook', lang),
                reply_markup=get_client_keyboard(lang)
            )
            return

        if len(active_bookings) == 1:
            # Одна запись — сразу показываем календарь для перезаписи
            booking = active_bookings[0]
            contract = session.query(Contract).filter(Contract.id == booking.contract_id).first()
            await _show_calendar_for_house(message, state, user_id, lang, contract.house_name, contract, session)
        else:
            # Несколько записей — даём выбор
            builder = InlineKeyboardBuilder()
            for b in active_bookings:
                contract = session.query(Contract).filter(Contract.id == b.contract_id).first()
                date_str = b.date.strftime('%d.%m.%Y')
                time_str = b.time_slot.strftime('%H:%M')
                house = contract.house_name if contract else '?'
                apt = contract.apt_num if contract else '?'
                if lang == 'uz':
                    label = f"📅 {date_str} {time_str} | {house}, kv. {apt}"
                else:
                    label = f"📅 {date_str} {time_str} | {house}, кв. {apt}"
                builder.button(text=label, callback_data=f"calbooking_{b.id}")
            builder.adjust(1)
            await state.set_state(ClientSteps.calendar_selecting_booking)
            await message.answer(
                get_message('select_booking_rebook', lang),
                reply_markup=builder.as_markup()
            )


async def _show_calendar_for_house(message_or_callback, state: FSMContext, user_id: int, lang: str,
                                    house_name: str, contract, session):
    """Показать календарь для конкретного ЖК"""
    today = date.today()
    min_booking_dt = get_min_booking_date()

    # Берём delivery_date контракта если она позже
    if contract.delivery_date and contract.delivery_date > min_booking_dt:
        min_booking_dt = contract.delivery_date

    # Получаем лимит слотов для проекта
    slots_limit = get_project_slot_limit(session, house_name)

    # Проверяем наличие активной записи по привязке договора
    active_booking = (
        session.query(Booking)
        .join(Contract, Booking.contract_id == Contract.id)
        .filter(
            Contract.telegram_id == user_id,
            Contract.house_name == house_name,
            Booking.date >= today,
            Booking.is_cancelled == False
        )
        .order_by(Booking.date)
        .first()
    )

    active_booking_date = None
    active_booking_id = None
    active_booking_time = None
    active_contract_apt = None
    if active_booking:
        active_booking_date = active_booking.date.isoformat()
        active_booking_id = active_booking.id
        active_booking_time = active_booking.time_slot.strftime('%H:%M')
        active_contract = session.query(Contract).filter(Contract.id == active_booking.contract_id).first()
        active_contract_apt = active_contract.apt_num if active_contract else ''

    await state.update_data(
        cal_house_name=house_name,
        cal_contract_id=contract.id,
        cal_client_fio=contract.client_fio,
        cal_apt_num=contract.apt_num,
        cal_delivery_date=min_booking_dt.isoformat(),
        cal_slots_limit=slots_limit,
        cal_active_booking_date=active_booking_date,
        cal_active_booking_id=active_booking_id,
        cal_active_booking_time=active_booking_time,
        cal_active_contract_apt=active_contract_apt,
    )

    # Определяем период для проверки занятых дат
    start_date = min_booking_dt
    end_date = today + timedelta(days=90)
    fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, house_name)

    markup = generate_calendar(
        min_date=min_booking_dt,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )

    await state.set_state(ClientSteps.calendar_viewing)

    text = get_message('calendar_header', lang, house=house_name)

    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=markup)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=markup)
        await message_or_callback.answer()


@router.callback_query(F.data.startswith("calbooking_"), ClientSteps.calendar_selecting_booking)
async def calendar_booking_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбор записи для перезаписи"""
    booking_id = int(callback.data.split("_", 1)[1])
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    with SessionLocal() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        contract = session.query(Contract).filter(Contract.id == booking.contract_id).first()
        if not contract:
            await callback.answer("Договор не найден", show_alert=True)
            return

        await _show_calendar_for_house(callback, state, user_id, lang, contract.house_name, contract, session)


@router.callback_query(F.data.startswith("cal_"), ClientSteps.calendar_viewing)
async def calendar_view_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Навигация по месяцам в режиме просмотра календаря"""
    parts = callback.data.split("_")
    year = int(parts[1])
    month = int(parts[2])

    user_data = await state.get_data()
    delivery_date_str = user_data.get('cal_delivery_date')
    slots_limit = user_data.get('cal_slots_limit', 1)
    house_name = user_data.get('cal_house_name')

    if delivery_date_str:
        from datetime import datetime as dt
        delivery_date = dt.fromisoformat(delivery_date_str).date()
    else:
        delivery_date = None

    import calendar as cal_module
    first_day = date(year, month, 1)
    last_day = date(year, month, cal_module.monthrange(year, month)[1])

    with SessionLocal() as session:
        fully_booked = get_fully_booked_dates(session, first_day, last_day, slots_limit, house_name)

    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    new_calendar = generate_calendar(
        year=year,
        month=month,
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )

    await callback.message.edit_reply_markup(reply_markup=new_calendar)
    await callback.answer()


@router.callback_query(F.data == "date_full", ClientSteps.calendar_viewing)
async def calendar_view_date_full(callback: types.CallbackQuery):
    """Нажатие на полностью занятую дату в режиме просмотра"""
    await callback.answer(
        "❌ На эту дату все слоты заняты.\nПожалуйста, выберите другую дату.",
        show_alert=True
    )


@router.callback_query(F.data.startswith("date_"), ClientSteps.calendar_viewing)
async def calendar_view_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбор даты в режиме просмотра календаря"""
    selected_date_str = callback.data.split("_")[1]
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    min_booking_date = get_min_booking_date()

    if selected_date < min_booking_date:
        now = datetime.now()
        if now.hour < 12:
            hint = "Запись возможна на следующий рабочий день или позже."
        else:
            hint = "После 12:00 запись возможна только через один рабочий день."
        await callback.answer(f"⚠️ Выбранная дата недоступна.\n{hint}", show_alert=True)
        return

    if selected_date.weekday() >= 5:
        await callback.answer("⚠️ Запись доступна только в рабочие дни (пн-пт).", show_alert=True)
        return

    user_data = await state.get_data()
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    house_name = user_data.get('cal_house_name')
    contract_id = user_data.get('cal_contract_id')
    slots_limit = user_data.get('cal_slots_limit', 1)

    # Показываем слоты времени (проверка на перезапись будет при выборе времени)
    await _show_time_slots_for_calendar(callback, state, selected_date_str, selected_date,
                                        contract_id, house_name, slots_limit, lang)


async def _show_time_slots_for_calendar(callback, state, selected_date_str, selected_date,
                                         contract_id, house_name, slots_limit, lang):
    """Показать слоты времени для выбранной даты в режиме календаря"""
    with SessionLocal() as session:
        contract = session.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            await callback.answer("Ошибка: данные договора не найдены.", show_alert=True)
            return

        bookings = (
            session.query(Booking.time_slot, func.count(Booking.id))
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .group_by(Booking.time_slot)
            .all()
        )
        booked_dict = {row[0]: row[1] for row in bookings}

    await state.update_data(cal_selected_date=selected_date_str)
    await state.set_state(ClientSteps.calendar_selecting_time)

    time_kb = generate_time_slots(selected_date_str, booked_dict, slots_limit, lang)

    sel_date_fmt = selected_date.strftime('%d.%m.%Y')
    delivery_date_str = (await state.get_data()).get('cal_delivery_date', '')
    if delivery_date_str:
        from datetime import datetime as dt
        del_date_fmt = dt.fromisoformat(delivery_date_str).date().strftime('%d.%m.%Y')
    else:
        del_date_fmt = '-'

    message_text = get_message('date_selected_choose_time', lang,
                               selected_date=sel_date_fmt,
                               delivery_date=del_date_fmt)

    await callback.message.edit_text(message_text, reply_markup=time_kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "rebook_no", ClientSteps.calendar_rebook_confirming)
async def rebook_declined(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь отказался от перезаписи"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    await state.clear()
    try:
        await callback.message.edit_text(get_message('rebook_cancelled', lang))
    except Exception:
        pass
    await callback.message.answer(
        get_message('welcome', lang),
        reply_markup=get_client_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rebook_yes_"), ClientSteps.calendar_rebook_confirming)
async def rebook_accepted(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Пользователь согласился на перезапись — отменяем старую и показываем выбор договора"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    user_data = await state.get_data()

    active_booking_id = user_data.get('cal_active_booking_id')
    # callback_data: rebook_yes_YYYY-MM-DD_HH:MM
    parts = callback.data.split("_", 3)  # ['rebook', 'yes', 'YYYY-MM-DD', 'HH:MM']
    selected_date_str = parts[2]
    selected_time_str = parts[3]
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    house_name = user_data.get('cal_house_name')

    with SessionLocal() as session:
        # Отменяем текущую запись
        old_booking = session.query(Booking).filter(Booking.id == active_booking_id).first()
        if old_booking and not can_cancel_booking(old_booking.date, old_booking.time_slot):
            await state.clear()
            await callback.answer(
                "⚠️ Отмена невозможна - прошёл срок отмены",
                show_alert=True
            )
            await callback.message.answer(
                get_message('welcome', lang),
                reply_markup=get_client_keyboard(lang)
            )
            return
        if old_booking:
            old_booking.is_cancelled = True
            old_contract = session.query(Contract).filter(Contract.id == old_booking.contract_id).first()

            old_date_str = old_booking.date.strftime('%d.%m.%Y')
            old_time_str = old_booking.time_slot.strftime('%H:%M')

            session.commit()

            # Уведомляем сотрудников об отмене.
            # TG-контакт берём из записи (создатель), а не из договора (привязка могла смениться).
            creator_id = old_booking.user_telegram_id
            creator_username = (
                old_contract.username
                if old_contract and old_contract.telegram_id == creator_id
                else None
            )
            notification_text = (
                f"🔄 **Запись отменена (перезапись)!**\n\n"
                f"👤 Клиент: {old_contract.client_fio if old_contract else 'N/A'}\n"
                f"📞 Тел: {old_booking.client_phone or '—'}\n"
                f"💬 TG: {format_tg_contact_md(creator_id, creator_username)}\n"
                f"🏠 Объект: {house_name}\n"
            )
            if old_contract:
                notification_text += (
                    f"🏢 Кв. {old_contract.apt_num}, подъезд {old_contract.entrance}, этаж {old_contract.floor}\n"
                    f"📄 Договор: {old_contract.contract_num}\n"
                )
            notification_text += (
                f"📅 Дата: {old_date_str}\n"
                f"⏰ Время: {old_time_str}\n\n"
                f"Клиент перезаписывается на {selected_date.strftime('%d.%m.%Y')} {selected_time_str}"
            )

            recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
            if ADMIN_ID not in recipients:
                recipients.append(ADMIN_ID)

            tg_kb = build_tg_profile_kb(creator_id, creator_username)

            async def send_rebook_notifications():
                for emp_id in recipients:
                    try:
                        await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown", reply_markup=tg_kb)
                    except Exception as e:
                        logging.error(f"Ошибка уведомления {emp_id}: {e}")

            asyncio.create_task(send_rebook_notifications())

    # Обновляем данные — активной записи больше нет
    await state.update_data(
        cal_active_booking_date=None,
        cal_active_booking_id=None,
        cal_active_booking_time=None,
        cal_active_contract_apt=None,
        cal_selected_date=selected_date_str,
        cal_selected_time=selected_time_str,
        cal_is_rebook=True,
    )

    # Показываем ввод телефона (договор уже известен из выбранной записи)
    await _show_phone_entry(callback, state, user_id, lang)


@router.callback_query(F.data == "back_to_calendar", ClientSteps.calendar_selecting_time)
async def calendar_view_back_to_calendar(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к календарю из выбора времени (режим просмотра)"""
    user_data = await state.get_data()
    delivery_date_str = user_data.get('cal_delivery_date')
    slots_limit = user_data.get('cal_slots_limit', 1)
    house_name = user_data.get('cal_house_name')

    if delivery_date_str:
        from datetime import datetime as dt
        delivery_date = dt.fromisoformat(delivery_date_str).date()
    else:
        delivery_date = None

    today = date.today()
    start_date = delivery_date if delivery_date else today
    end_date = today + timedelta(days=90)

    with SessionLocal() as session:
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, house_name)

    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    calendar_markup = generate_calendar(
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )

    await state.set_state(ClientSteps.calendar_viewing)
    await callback.message.edit_text(
        get_message('calendar_header', lang, house=house_name),
        reply_markup=calendar_markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("time_"), ClientSteps.calendar_selecting_time)
async def calendar_view_time_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбор времени в режиме просмотра календаря"""
    parts = callback.data.split("_")
    date_str = parts[1]
    time_str = parts[2]

    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    selected_time = datetime.strptime(time_str, '%H:%M').time()

    user_data = await state.get_data()
    slots_limit = user_data.get('cal_slots_limit', 1)
    house_name = user_data.get('cal_house_name')
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    with SessionLocal() as session:
        current_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Booking.time_slot == selected_time,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .count()
        )

        if current_bookings >= slots_limit:
            await callback.answer("Извините, это время только что заняли.", show_alert=True)
            return

    await state.update_data(cal_selected_date=date_str, cal_selected_time=time_str)

    # Проверяем наличие активной записи — предлагаем отменить и перезаписаться
    active_booking_date_str = user_data.get('cal_active_booking_date')
    active_booking_id = user_data.get('cal_active_booking_id')

    if active_booking_date_str and active_booking_id:
        from datetime import datetime as dt
        active_date = dt.fromisoformat(active_booking_date_str).date()
        active_time_str = user_data.get('cal_active_booking_time', '')
        active_apt = user_data.get('cal_active_contract_apt', '')

        builder = InlineKeyboardBuilder()
        builder.button(
            text=get_message('rebook_confirm_yes', lang),
            callback_data=f"rebook_yes_{date_str}_{time_str}"
        )
        builder.button(
            text=get_message('rebook_confirm_no', lang),
            callback_data="rebook_no"
        )
        builder.adjust(1)

        await state.set_state(ClientSteps.calendar_rebook_confirming)
        await callback.message.edit_text(
            get_message('rebook_confirm', lang,
                       old_date=active_date.strftime('%d.%m.%Y'),
                       old_time=active_time_str,
                       house=house_name,
                       apt=active_apt,
                       new_date=selected_date.strftime('%d.%m.%Y'),
                       new_time=time_str),
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    # Нет активной записи — переходим к вводу телефона
    await _show_phone_entry(callback, state, user_id, lang)

    await callback.answer()


async def _show_phone_entry(callback, state: FSMContext, user_id: int, lang: str):
    """Показать ввод телефона"""
    saved_phone = get_user_phone(user_id)

    if saved_phone:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=get_message('use_saved_phone', lang, phone=saved_phone),
            callback_data=f"calphone_{saved_phone}"
        )
        builder.button(
            text=get_message('enter_new_phone', lang),
            callback_data="calnewphone"
        )
        builder.adjust(1)

        await state.set_state(ClientSteps.calendar_entering_phone)
        await callback.message.edit_text(
            get_message('phone_choice', lang),
            reply_markup=builder.as_markup()
        )
    else:
        await state.set_state(ClientSteps.calendar_entering_phone)
        await callback.message.answer(
            get_message('enter_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        await callback.message.delete()


@router.callback_query(F.data.startswith("calphone_"), ClientSteps.calendar_entering_phone)
async def calendar_use_saved_phone(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Использовать сохранённый номер в режиме календаря"""
    saved_phone = callback.data.replace("calphone_", "")
    await callback.message.delete()
    await _process_calendar_booking(callback, state, bot, saved_phone, is_callback=True)
    await callback.answer()


@router.callback_query(F.data == "calnewphone", ClientSteps.calendar_entering_phone)
async def calendar_enter_new_phone(callback: types.CallbackQuery, state: FSMContext):
    """Ввести новый номер в режиме календаря"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    await callback.message.edit_text(get_message('enter_phone', lang))
    await callback.message.answer(
        get_message('enter_phone', lang),
        reply_markup=get_phone_request_keyboard(lang)
    )
    await callback.answer()


@router.message(ClientSteps.calendar_entering_phone, F.contact)
async def calendar_phone_contact_received(message: types.Message, state: FSMContext, bot: Bot):
    """Получение телефона через контакт в режиме календаря"""
    user_phone = message.contact.phone_number
    if not user_phone.startswith('+'):
        user_phone = '+' + user_phone
    
    is_valid, cleaned_phone = validate_phone_number(user_phone)
    if not is_valid:
        lang = get_user_language(message.from_user.id)
        await message.answer(
            get_message('invalid_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        return
    
    await _process_calendar_booking(message, state, bot, cleaned_phone, is_callback=False)


@router.message(ClientSteps.calendar_entering_phone)
async def calendar_phone_entered(message: types.Message, state: FSMContext, bot: Bot):
    """Ввод телефона вручную в режиме календаря"""
    user_phone = message.text.strip()
    user_id = message.from_user.id
    lang = get_user_language(user_id)

    is_valid, cleaned_phone = validate_phone_number(user_phone)
    if not is_valid:
        await message.answer(
            get_message('invalid_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        return

    await _process_calendar_booking(message, state, bot, cleaned_phone, is_callback=False)


async def _process_calendar_booking(source, state: FSMContext, bot: Bot, user_phone: str, is_callback: bool):
    """Создание записи через режим календаря"""
    user_data = await state.get_data()

    if is_callback:
        user_id = source.from_user.id
        send_message = source.message.answer
    else:
        user_id = source.from_user.id
        send_message = source.answer

    lang = get_user_language(user_id)
    set_user_phone(user_id, user_phone)

    selected_date = datetime.strptime(user_data['cal_selected_date'], '%Y-%m-%d').date()
    time_str = user_data['cal_selected_time']
    selected_time = datetime.strptime(time_str, '%H:%M').time()
    contract_id = user_data['cal_contract_id']
    house_name = user_data.get('cal_house_name', '')
    client_fio = user_data.get('cal_client_fio', '')
    apt_num = user_data.get('cal_apt_num', '')

    with SessionLocal() as session:
        contract = session.query(Contract).filter(Contract.id == contract_id).first()
        if contract and not contract.telegram_id:
            contract.telegram_id = user_id
            contract.username = source.from_user.username
            contract.href = build_tg_href(user_id, source.from_user.username)
        elif contract and contract.telegram_id == user_id:
            contract.username = source.from_user.username
            contract.href = build_tg_href(user_id, source.from_user.username)

        # Отменяем все активные записи по договорам этого пользователя на ЖК
        today = date.today()
        active_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Contract.house_name == house_name,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .all()
        )
        
        cancelled_info = []
        for old_booking in active_bookings:
            old_booking.is_cancelled = True
            old_contract = session.query(Contract).filter(Contract.id == old_booking.contract_id).first()
            # TG-контакт берём из записи (создатель), а не из договора (привязка могла смениться).
            b_creator_id = old_booking.user_telegram_id
            b_creator_username = (
                old_contract.username
                if old_contract and old_contract.telegram_id == b_creator_id
                else None
            )
            cancelled_info.append({
                'date': old_booking.date.strftime('%d.%m.%Y'),
                'time': old_booking.time_slot.strftime('%H:%M'),
                'fio': old_contract.client_fio if old_contract else 'N/A',
                'apt_num': old_contract.apt_num if old_contract else 'N/A',
                'entrance': old_contract.entrance if old_contract else 'N/A',
                'floor': old_contract.floor if old_contract else 'N/A',
                'contract_num': old_contract.contract_num if old_contract else 'N/A',
                'phone': old_booking.client_phone,
                'tg_id': b_creator_id,
                'username': b_creator_username,
            })

        new_booking = Booking(
            contract_id=contract_id,
            user_telegram_id=user_id,
            date=selected_date,
            time_slot=selected_time,
            client_phone=user_phone
        )
        session.add(new_booking)
        session.commit()

        # Уведомляем сотрудников об отменённых записях
        if cancelled_info:
            for ci in cancelled_info:
                cancel_notification = (
                    f"🔄 **Запись отменена (перезапись)!**\n\n"
                    f"👤 Клиент: {ci['fio']}\n"
                    f"📞 Тел: {ci['phone'] or '—'}\n"
                    f"💬 TG: {format_tg_contact_md(ci['tg_id'], ci['username'])}\n"
                    f"🏠 Объект: {house_name}\n"
                    f"🏢 Кв. {ci['apt_num']}, подъезд {ci['entrance']}, этаж {ci['floor']}\n"
                    f"📄 Договор: {ci['contract_num']}\n"
                    f"📅 Дата: {ci['date']}\n"
                    f"⏰ Время: {ci['time']}\n\n"
                    f"Клиент перезаписался на {selected_date.strftime('%d.%m.%Y')} {time_str}"
                )

                recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
                if ADMIN_ID not in recipients:
                    recipients.append(ADMIN_ID)

                tg_kb = build_tg_profile_kb(ci.get('tg_id'), ci.get('username'))

                async def _send_cancel(text=cancel_notification, recips=list(recipients), kb=tg_kb):
                    for emp_id in recips:
                        try:
                            await bot.send_message(chat_id=emp_id, text=text, parse_mode="Markdown", reply_markup=kb)
                        except Exception as e:
                            logging.error(f"Ошибка уведомления {emp_id}: {e}")

                asyncio.create_task(_send_cancel())

        # Если это перезапись — уведомление уже отправлено в rebook_accepted, второе не шлём
        if not cancelled_info and not user_data.get('cal_is_rebook'):
            notification_text = (
                f"🔔 **Новая запись на прием!**\n\n"
                f"👤 Клиент: {client_fio}\n"
                f"📞 Тел: {user_phone}\n"
                f"💬 TG: {format_tg_contact_md(contract.telegram_id, contract.username)}\n"
                f"🏠 Объект: {house_name}\n"
                f"🏢 Кв. {apt_num}, подъезд {contract.entrance}, этаж {contract.floor}\n"
                f"📄 Договор: {contract.contract_num}\n"
                f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
                f"⏰ Время: {time_str}"
            )

            recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
            if ADMIN_ID not in recipients:
                recipients.append(ADMIN_ID)

            tg_kb = build_tg_profile_kb(contract.telegram_id, contract.username)

            async def send_booking_notifications():
                for emp_id in recipients:
                    try:
                        await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown", reply_markup=tg_kb)
                    except Exception as e:
                        logging.error(f"Ошибка уведомления {emp_id}: {e}")

            asyncio.create_task(send_booking_notifications())

    project_address = get_project_address(house_name, lang)
    address_line = f"📍 {project_address}\n" if project_address else ""

    if lang == 'uz':
        success_text = (
            f"Kvartirangizni topshirish uchun uchrashuv tasdiqlandi.\n\n"
            f"{address_line}"
            f"🏠 Kvartira raqami {apt_num}\n"
            f"📅 Sana: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Vaqt: {time_str}\n"
            f"📞 Telefon: {OFFICE_PHONE}\n\n"
            f"Kalitni topshirish faqat ulushdorlarga yoki notarial tasdiqlangan ishonchnomaga ega bo'lgan vakillarga topshiriladi.\n\n"
            f"O'zingiz bilan pasport/shaxsni tasdiqlovchi hujjat va ulushdorlik shartnomasi bo'lishi kerak.\n\n"
            f"Agar 15 daqiqadan ko'proq kechiksangiz, topshirish qayta rejalashtirilishi mumkin. Iltimos, vaqtida keling.\n\n"
            f"Agar qatnasha olmasangiz, iltimos, bizga oldindan xabar bering.\n\n"
            f"Oldindan yozilmasdan kalitlarni topshirish mumkin emas."
        )
    else:
        success_text = (
            f"Ваша запись на передачу квартиры подтверждена.\n\n"
            f"{address_line}"
            f"🏠 Квартира № {apt_num}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}\n"
            f"📞 Телефон: {OFFICE_PHONE}\n\n"
            f"Передача ключей строго дольщику, либо представителю дольщика, по нотариально оформленной доверенности.\n"
            f"При себе необходимо иметь паспорт/ID и договор долевого участия.\n\n"
            f"В случае опоздания более чем на 15 минут передача может быть перенесена. Просим прибыть вовремя.\n\n"
            f"В случае невозможности визита — сообщите заранее.\n\n"
            f"Передача без записи невозможна."
        )

    await send_message(success_text, parse_mode="Markdown", reply_markup=get_client_keyboard(lang))

    coords = get_project_coordinates(house_name)
    if coords:
        lat, lon = coords
    else:
        lat, lon = OFFICE_LAT, OFFICE_LON

    await bot.send_location(chat_id=user_id, latitude=lat, longitude=lon)
    await state.clear()


# ========== ПЕРЕКЛЮЧЕНИЕ ЯЗЫКА ==========


async def _resend_cancel_selecting_booking(message: types.Message, user_id: int, lang: str):
    """Переотправить список записей для отмены на новом языке"""
    with SessionLocal() as session:
        today = date.today()
        bookings = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )

        if not bookings:
            return

        builder = InlineKeyboardBuilder()
        cancellable_found = False

        if lang == 'uz':
            text_lines = ["📋 **Sizning yozuvlaringiz:**\n"]
        else:
            text_lines = ["📋 **Ваши записи:**\n"]

        for idx, (booking, contract) in enumerate(bookings, 1):
            can_cancel_flag = can_cancel_booking(booking.date, booking.time_slot)
            date_str = booking.date.strftime('%d.%m.%Y')
            time_str = booking.time_slot.strftime('%H:%M')

            if can_cancel_flag:
                cancellable_found = True
                text_lines.append(f"**{idx}.** 📅 {date_str} ⏰ {time_str}")
                text_lines.append(f"    🏠 {contract.house_name}, кв. {contract.apt_num}\n")
                builder.button(
                    text=f"❌ Отменить #{idx}" if lang == 'ru' else f"❌ Bekor qilish #{idx}",
                    callback_data=f"cancel_{booking.id}"
                )
            else:
                text_lines.append(f"**{idx}.** 🔒 {date_str} ⏰ {time_str}")
                text_lines.append(f"    🏠 {contract.house_name}, кв. {contract.apt_num}")
                if lang == 'uz':
                    text_lines.append(f"    _(bekor qilib bo'lmaydi)_\n")
                else:
                    text_lines.append(f"    _(отмена недоступна)_\n")

        builder.button(text=get_message('back', lang), callback_data="cancel_back")
        builder.adjust(1)

        text = "\n".join(text_lines)
        if not cancellable_found:
            text += "\n" + get_message('all_bookings_blocked', lang)
        else:
            if lang == 'uz':
                text += "\nBekor qilish uchun tugmani bosing:"
            else:
                text += "\nНажмите кнопку для отмены:"

        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


async def _resend_cancel_confirming(message: types.Message, state: FSMContext, lang: str):
    """Переотправить подтверждение отмены на новом языке"""
    data = await state.get_data()
    booking_id = data.get('cancel_booking_id')
    if not booking_id:
        return

    with SessionLocal() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return

        date_str = booking.date.strftime('%d.%m.%Y')
        time_str = booking.time_slot.strftime('%H:%M')

        builder = InlineKeyboardBuilder()
        builder.button(text=get_message('confirm', lang), callback_data=f"confirm_cancel_{booking_id}")
        builder.button(text=get_message('reject', lang), callback_data="cancel_back")
        builder.adjust(1)

        await message.answer(
            get_message('confirm_cancel', lang, date=date_str, time=time_str),
            reply_markup=builder.as_markup()
        )


async def _resend_calendar_selecting_booking(message: types.Message, user_id: int, lang: str):
    """Переотправить список записей для перезаписи на новом языке"""
    today = date.today()

    with SessionLocal() as session:
        active_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Contract.telegram_id == user_id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )

        if not active_bookings or len(active_bookings) < 2:
            return

        builder = InlineKeyboardBuilder()
        for b in active_bookings:
            contract = session.query(Contract).filter(Contract.id == b.contract_id).first()
            date_str = b.date.strftime('%d.%m.%Y')
            time_str = b.time_slot.strftime('%H:%M')
            house = contract.house_name if contract else '?'
            apt = contract.apt_num if contract else '?'
            if lang == 'uz':
                label = f"📅 {date_str} {time_str} | {house}, kv. {apt}"
            else:
                label = f"📅 {date_str} {time_str} | {house}, кв. {apt}"
            builder.button(text=label, callback_data=f"calbooking_{b.id}")
        builder.adjust(1)

        await message.answer(
            get_message('select_booking_rebook', lang),
            reply_markup=builder.as_markup()
        )


async def _resend_calendar_viewing(message: types.Message, state: FSMContext, lang: str):
    """Переотправить календарь на новом языке"""
    data = await state.get_data()
    delivery_date_str = data.get('cal_delivery_date')
    slots_limit = data.get('cal_slots_limit', 1)
    house_name = data.get('cal_house_name')

    if not delivery_date_str or not house_name:
        return

    from datetime import datetime as dt
    min_booking_date = dt.fromisoformat(delivery_date_str).date()
    today = date.today()
    start_date = min_booking_date
    end_date = today + timedelta(days=90)

    with SessionLocal() as session:
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, house_name)

    markup = generate_calendar(
        min_date=min_booking_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )

    await message.answer(
        get_message('calendar_header', lang, house=house_name),
        reply_markup=markup
    )


async def _resend_calendar_selecting_time(message: types.Message, state: FSMContext, lang: str):
    """Переотправить слоты времени (calendar flow) на новом языке"""
    data = await state.get_data()
    selected_date_str = data.get('cal_selected_date')
    house_name = data.get('cal_house_name')
    slots_limit = data.get('cal_slots_limit', 1)
    delivery_date_str = data.get('cal_delivery_date', '')

    if not selected_date_str or not house_name:
        return

    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    with SessionLocal() as session:
        bookings = (
            session.query(Booking.time_slot, func.count(Booking.id))
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .group_by(Booking.time_slot)
            .all()
        )
        booked_dict = {row[0]: row[1] for row in bookings}

    time_kb = generate_time_slots(selected_date_str, booked_dict, slots_limit, lang)

    sel_date_fmt = selected_date.strftime('%d.%m.%Y')
    if delivery_date_str:
        from datetime import datetime as dt
        del_date_fmt = dt.fromisoformat(delivery_date_str).date().strftime('%d.%m.%Y')
    else:
        del_date_fmt = '-'

    message_text = get_message('date_selected_choose_time', lang,
                               selected_date=sel_date_fmt,
                               delivery_date=del_date_fmt)

    await message.answer(message_text, reply_markup=time_kb, parse_mode="Markdown")


async def _resend_calendar_rebook_confirming(message: types.Message, state: FSMContext, lang: str):
    """Переотправить подтверждение перезаписи на новом языке"""
    data = await state.get_data()
    date_str = data.get('cal_selected_date')
    time_str = data.get('cal_selected_time')
    house_name = data.get('cal_house_name')
    active_booking_date_str = data.get('cal_active_booking_date')
    active_booking_time = data.get('cal_active_booking_time', '')
    active_apt = data.get('cal_active_contract_apt', '')

    if not date_str or not time_str or not active_booking_date_str:
        return

    from datetime import datetime as dt
    active_date = dt.fromisoformat(active_booking_date_str).date()
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_message('rebook_confirm_yes', lang),
        callback_data=f"rebook_yes_{date_str}_{time_str}"
    )
    builder.button(
        text=get_message('rebook_confirm_no', lang),
        callback_data="rebook_no"
    )
    builder.adjust(1)

    await message.answer(
        get_message('rebook_confirm', lang,
                   old_date=active_date.strftime('%d.%m.%Y'),
                   old_time=active_booking_time,
                   house=house_name,
                   apt=active_apt,
                   new_date=selected_date.strftime('%d.%m.%Y'),
                   new_time=time_str),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


async def _resend_selecting_time(message: types.Message, state: FSMContext, lang: str):
    """Переотправить слоты времени (primary flow) на новом языке"""
    data = await state.get_data()
    selected_date_str = data.get('selected_date')
    contract_id = data.get('contract_id')
    house_name = data.get('house_name')
    slots_limit = data.get('slots_limit', 1)

    if not selected_date_str or not contract_id or not house_name:
        return

    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    with SessionLocal() as session:
        contract = session.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            return

        bookings = (
            session.query(Booking.time_slot, func.count(Booking.id))
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .group_by(Booking.time_slot)
            .all()
        )
        booked_dict = {row[0]: row[1] for row in bookings}

        del_date_fmt = contract.delivery_date.strftime('%d.%m.%Y') if contract.delivery_date else '-'

    time_kb = generate_time_slots(selected_date_str, booked_dict, slots_limit, lang)
    sel_date_fmt = selected_date.strftime('%d.%m.%Y')

    message_text = get_message('date_selected_choose_time', lang,
                               selected_date=sel_date_fmt,
                               delivery_date=del_date_fmt)

    await message.answer(message_text, reply_markup=time_kb, parse_mode="Markdown")


# --- Обработчики смены языка для каждого состояния ---

@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.entering_phone)
async def language_toggle_during_phone(message: types.Message, state: FSMContext):
    """Переключение языка во время ввода телефона (без потери прогресса)"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)
    
    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_phone_request_keyboard(new_lang)
    )
    
    saved_phone = get_user_phone(user_id)
    
    if saved_phone:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=get_message('use_saved_phone', new_lang, phone=saved_phone),
            callback_data=f"use_phone_{saved_phone}"
        )
        builder.button(
            text=get_message('enter_new_phone', new_lang),
            callback_data="new_phone"
        )
        builder.adjust(1)
        
        await message.answer(
            get_message('phone_choice', new_lang),
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            get_message('enter_phone', new_lang),
            reply_markup=get_phone_request_keyboard(new_lang)
        )


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.entering_contract)
async def language_toggle_during_contract(message: types.Message, state: FSMContext):
    """Переключение языка во время ввода договора (без потери прогресса)"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)
    
    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await message.answer(
        get_message('enter_contract', new_lang)
    )


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.selecting_date)
async def language_toggle_during_date_selection(message: types.Message, state: FSMContext):
    """Переключение языка во время выбора даты (обновляет календарь)"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)
    
    data = await state.get_data()
    delivery_date_str = data.get('delivery_date')
    slots_limit = data.get('slots_limit', 1)
    contract_id = data.get('contract_id')
    client_fio = data.get('client_fio')
    house_name = data.get('house_name')
    
    if not delivery_date_str or not contract_id:
        await message.answer(
            get_message('language_changed', new_lang),
            reply_markup=get_client_keyboard(new_lang)
        )
        return
    
    from datetime import datetime as dt
    min_booking_date = dt.fromisoformat(delivery_date_str).date()
    today = date.today()
    
    with SessionLocal() as session:
        start_date = min_booking_date
        end_date = today + timedelta(days=90)
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, house_name)
    
    markup = generate_calendar(
        min_date=min_booking_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=new_lang
    )
    
    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await message.answer(
        get_message('contract_confirmed', new_lang,
                   fio=client_fio,
                   date=min_booking_date.strftime('%d.%m.%Y')),
        reply_markup=markup
    )


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.selecting_time)
async def language_toggle_during_time_selection(message: types.Message, state: FSMContext):
    """Переключение языка во время выбора времени"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_selecting_time(message, state, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.cancel_selecting_booking)
async def language_toggle_during_cancel_selecting(message: types.Message, state: FSMContext):
    """Переключение языка при выборе записи для отмены"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_cancel_selecting_booking(message, user_id, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.cancel_confirming)
async def language_toggle_during_cancel_confirming(message: types.Message, state: FSMContext):
    """Переключение языка при подтверждении отмены"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_cancel_confirming(message, state, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.calendar_selecting_booking)
async def language_toggle_during_cal_selecting(message: types.Message, state: FSMContext):
    """Переключение языка при выборе записи для перезаписи"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_calendar_selecting_booking(message, user_id, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.calendar_viewing)
async def language_toggle_during_cal_viewing(message: types.Message, state: FSMContext):
    """Переключение языка при просмотре календаря"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_calendar_viewing(message, state, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.calendar_selecting_time)
async def language_toggle_during_cal_time(message: types.Message, state: FSMContext):
    """Переключение языка при выборе времени (calendar flow)"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_calendar_selecting_time(message, state, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.calendar_rebook_confirming)
async def language_toggle_during_cal_rebook(message: types.Message, state: FSMContext):
    """Переключение языка при подтверждении перезаписи"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await _resend_calendar_rebook_confirming(message, state, new_lang)


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]), ClientSteps.calendar_entering_phone)
async def language_toggle_during_calendar_phone(message: types.Message, state: FSMContext):
    """Переключение языка во время ввода телефона в режиме календаря"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)

    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_phone_request_keyboard(new_lang)
    )

    saved_phone = get_user_phone(user_id)

    if saved_phone:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=get_message('use_saved_phone', new_lang, phone=saved_phone),
            callback_data=f"calphone_{saved_phone}"
        )
        builder.button(
            text=get_message('enter_new_phone', new_lang),
            callback_data="calnewphone"
        )
        builder.adjust(1)

        await message.answer(
            get_message('phone_choice', new_lang),
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            get_message('enter_phone', new_lang),
            reply_markup=get_phone_request_keyboard(new_lang)
        )


@router.message(F.text.in_([BUTTON_TEXTS['language']['ru'], BUTTON_TEXTS['language']['uz']]))
async def language_toggle_button(message: types.Message, state: FSMContext):
    """Переключение языка интерфейса"""
    user_id = message.from_user.id
    new_lang = toggle_language(user_id)
    
    await message.answer(
        get_message('language_changed', new_lang),
        reply_markup=get_client_keyboard(new_lang)
    )
    await message.answer(
        get_message('welcome', new_lang)
    )


# ========== ОБРАБОТЧИКИ ОТМЕНЫ ЗАПИСИ ==========

@router.callback_query(F.data == "cancel_back", ClientSteps.cancel_selecting_booking)
async def cancel_back_handler(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню из отмены"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    await state.clear()
    try:
        await callback.message.edit_text(get_message('cancel_aborted', lang))
    except Exception:
        pass
    await callback.message.answer(
        get_message('welcome', lang),
        reply_markup=get_client_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_blocked", ClientSteps.cancel_selecting_booking)
async def cancel_blocked_handler(callback: types.CallbackQuery):
    """Обработчик при нажатии на заблокированную для отмены запись"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    await callback.answer(
        get_message('all_bookings_blocked', lang)[:200],  # Telegram limit
        show_alert=True
    )


@router.callback_query(F.data == "cancel_back", ClientSteps.cancel_confirming)
async def cancel_back_from_confirming(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню из подтверждения отмены"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    await state.clear()
    try:
        await callback.message.edit_text(get_message('cancel_aborted', lang))
    except Exception:
        pass
    await callback.message.answer(
        get_message('welcome', lang),
        reply_markup=get_client_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"), ClientSteps.cancel_selecting_booking)
async def cancel_booking_selected(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение отмены записи"""
    booking_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    
    with SessionLocal() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            await callback.answer("Запись не найдена", show_alert=True)
            return
        
        contract = session.query(Contract).filter(Contract.id == booking.contract_id).first()
        
        date_str = booking.date.strftime('%d.%m.%Y')
        time_str = booking.time_slot.strftime('%H:%M')
        
        builder = InlineKeyboardBuilder()
        builder.button(text=get_message('confirm', lang), callback_data=f"confirm_cancel_{booking_id}")
        builder.button(text=get_message('reject', lang), callback_data="cancel_back")
        builder.adjust(1)
        
        await state.set_state(ClientSteps.cancel_confirming)
        await state.update_data(cancel_booking_id=booking_id)
        await callback.message.edit_text(
            get_message('confirm_cancel', lang, date=date_str, time=time_str),
            reply_markup=builder.as_markup()
        )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel_"), ClientSteps.cancel_confirming)
async def confirm_cancel_booking(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение отмены записи"""
    booking_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    
    with SessionLocal() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            await state.clear()
            await callback.answer("Запись не найдена", show_alert=True)
            return
        
        # Проверяем возможность отмены ещё раз
        if not can_cancel_booking(booking.date, booking.time_slot):
            await state.clear()
            await callback.answer(
                "⚠️ Отмена невозможна - прошёл срок отмены",
                show_alert=True
            )
            await callback.message.answer(
                get_message('welcome', lang),
                reply_markup=get_client_keyboard(lang)
            )
            return
        
        contract = session.query(Contract).filter(Contract.id == booking.contract_id).first()
        
        # Отмечаем запись как отменённую
        booking.is_cancelled = True
        session.commit()
        
        date_str = booking.date.strftime('%d.%m.%Y')
        time_str = booking.time_slot.strftime('%H:%M')
        
        # Уведомляем сотрудников об отмене
        notification_text = (
            f"❌ **Запись отменена!**\n\n"
            f"👤 Клиент: {contract.client_fio}\n"
            f"📞 Тел: {booking.client_phone}\n"
            f"💬 TG: {format_tg_contact_md(contract.telegram_id, contract.username)}\n"
            f"🏠 Объект: {contract.house_name}\n"
            f"🏢 Кв. {contract.apt_num}, подъезд {contract.entrance}, этаж {contract.floor}\n"
            f"📄 Договор: {contract.contract_num}\n"
            f"📅 Дата: {date_str}\n"
            f"⏰ Время: {time_str}"
        )
        
        recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
        if ADMIN_ID not in recipients:
            recipients.append(ADMIN_ID)
        
        tg_kb = build_tg_profile_kb(contract.telegram_id, contract.username)
        
        # Отправляем уведомления в фоновом режиме
        async def send_cancel_notifications():
            for emp_id in recipients:
                try:
                    await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown", reply_markup=tg_kb)
                except Exception as e:
                    logging.error(f"Ошибка уведомления {emp_id}: {e}")
        
        asyncio.create_task(send_cancel_notifications())
    
    await state.clear()
    try:
        await callback.message.edit_text(
            get_message('booking_cancelled', lang, date=date_str, time=time_str)
        )
    except Exception:
        pass
    await callback.message.answer(
        get_message('welcome', lang),
        reply_markup=get_client_keyboard(lang)
    )
    await callback.answer()


# ========== ОСНОВНОЙ ФЛОУ ЗАПИСИ ==========




@router.message(ClientSteps.entering_contract)
async def contract_entered(message: types.Message, state: FSMContext):
    user_contract = message.text.replace(" ", "").upper()
    user_id = message.from_user.id
    lang = get_user_language(user_id)

    with SessionLocal() as session:
        contract = session.query(Contract).filter(
            Contract.contract_num == user_contract
        ).first()

        # Если договор НЕ найден - просим ввести заново
        if not contract:
            await message.answer(
                get_message('contract_not_found', lang)
            )
            # Остаёмся в том же состоянии, ожидая повторный ввод
            return

        # Проверяем, привязан ли договор к другому пользователю
        if contract.telegram_id and contract.telegram_id != user_id:
            await message.answer(
                get_message('contract_unavailable', lang)
            )
            return

        # Проверяем существующие активные записи на этот договор
        today = date.today()
        existing_booking = (
            session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.date >= today,
                Booking.is_cancelled == False
            )
            .first()
        )

        if existing_booking:
            # Договор не привязан (прошли выше проверку), значит запись могла создать
            # предыдущая привязка. Помечаем для отложенной отмены — она произойдёт
            # атомарно при создании новой записи.
            await state.update_data(pending_cancel_booking_id=existing_booking.id)
            logging.info(
                f"Отложенная отмена записи #{existing_booking.id} (user={user_id}, "
                f"date={existing_booking.date}) при повторной первичной записи"
            )

        # Определяем минимальную дату для записи
        min_booking_date = get_min_booking_date()

        # Cooldown 2 недели: считаем по записям, созданным этим пользователем.
        # Авторитет — contract.telegram_id; user_telegram_id в записях используем
        # только для cooldown-логики, не для определения "владельца".
        last_user_booking = (
            session.query(Booking)
            .filter(
                Booking.contract_id == contract.id,
                Booking.user_telegram_id == user_id,
                Booking.is_cancelled == False
            )
            .order_by(Booking.date.desc())
            .first()
        )

        if last_user_booking:
            two_weeks_from_last_booking = last_user_booking.date + timedelta(days=14)
            min_booking_date = max(min_booking_date, two_weeks_from_last_booking)
        
        # Если delivery_date позже - берём её
        if contract.delivery_date and contract.delivery_date > min_booking_date:
            min_booking_date = contract.delivery_date
        
        # Получаем лимит слотов для проекта
        slots_limit = get_project_slot_limit(session, contract.house_name)

        await state.update_data(
            contract_id=contract.id,
            client_fio=contract.client_fio,
            apt_num=contract.apt_num,
            house_name=contract.house_name,
            selected_house=contract.house_name,
            delivery_date=min_booking_date.isoformat(),
            slots_limit=slots_limit
        )

        # Определяем период для проверки занятых дат (90 дней вперёд)
        start_date = min_booking_date
        end_date = today + timedelta(days=90)
        
        # Получаем полностью занятые даты ДЛЯ ЭТОГО ПРОЕКТА
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, contract.house_name)

        # Создаем клавиатуру с учётом занятых дат
        markup = generate_calendar(
            min_date=min_booking_date,
            fully_booked_dates=fully_booked,
            slots_limit=slots_limit,
            lang=lang
        )
        await state.set_state(ClientSteps.selecting_date)

        await message.answer(
            get_message('contract_confirmed', lang,
                       fio=contract.client_fio,
                       date=min_booking_date.strftime('%d.%m.%Y')),
            reply_markup=markup
        )


@router.callback_query(F.data.startswith("cal_"), ClientSteps.selecting_date)
async def calendar_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик навигации по календарю (переключение месяцев)"""
    parts = callback.data.split("_")
    year = int(parts[1])
    month = int(parts[2])
    
    user_data = await state.get_data()
    delivery_date_str = user_data.get('delivery_date')
    # Используем кешированный лимит из состояния
    slots_limit = user_data.get('slots_limit', 1)
    
    if delivery_date_str:
        from datetime import datetime as dt
        delivery_date = dt.fromisoformat(delivery_date_str).date()
    else:
        delivery_date = None
    
    # Определяем период только для выбранного месяца
    import calendar as cal_module
    first_day = date(year, month, 1)
    last_day = date(year, month, cal_module.monthrange(year, month)[1])
    
    # Получаем house_name из состояния
    house_name = user_data.get('house_name')
    
    with SessionLocal() as session:
        # Запрашиваем занятые даты только для текущего месяца И ПРОЕКТА
        fully_booked = get_fully_booked_dates(session, first_day, last_day, slots_limit, house_name)
    
    # Перерисовываем календарь с новым месяцем/годом
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    
    new_calendar = generate_calendar(
        year=year, 
        month=month, 
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )
    
    await callback.message.edit_reply_markup(reply_markup=new_calendar)
    await callback.answer()


@router.callback_query(F.data == "date_full", ClientSteps.selecting_date)
async def date_full_handler(callback: types.CallbackQuery):
    """Обработчик нажатия на полностью занятую дату"""
    await callback.answer(
        "❌ На эту дату все слоты заняты.\n"
        "Пожалуйста, выберите другую дату.",
        show_alert=True
    )


@router.callback_query(F.data == "back_to_calendar", ClientSteps.selecting_time)
async def back_to_calendar(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору даты из экрана выбора времени"""
    user_data = await state.get_data()
    delivery_date_str = user_data.get('delivery_date')
    slots_limit = user_data.get('slots_limit', 1)
    house_name = user_data.get('house_name')  # Получаем название проекта
    
    if delivery_date_str:
        from datetime import datetime as dt
        delivery_date = dt.fromisoformat(delivery_date_str).date()
    else:
        delivery_date = None
    
    today = date.today()
    
    # Запрашиваем занятые даты на 90 дней вперёд ДЛЯ ЭТОГО ПРОЕКТА
    start_date = delivery_date if delivery_date else today
    end_date = today + timedelta(days=90)
    
    with SessionLocal() as session:
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, house_name)
    
    # Генерируем календарь
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    
    calendar_markup = generate_calendar(
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit,
        lang=lang
    )
    
    await state.set_state(ClientSteps.selecting_date)
    
    await callback.message.edit_text(
        "📅 Выберите дату для записи:",
        reply_markup=calendar_markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("date_"), ClientSteps.selecting_date)
async def date_selected(callback: types.CallbackQuery, state: FSMContext):
    selected_date_str = callback.data.split("_")[1]
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    
    # Получаем минимальную дату для записи по новым правилам
    min_booking_date = get_min_booking_date()

    # Проверка даты
    if selected_date < min_booking_date:
        now = datetime.now()
        if now.hour < 12:
            hint = "Запись возможна на следующий рабочий день или позже."
        else:
            hint = "После 12:00 запись возможна только через один рабочий день."
        await callback.answer(
            f"⚠️ Выбранная дата недоступна.\n{hint}",
            show_alert=True
        )
        return

    # Проверка рабочего дня (пн-пт)
    if selected_date.weekday() >= 5:  # 5=Сб, 6=Вс
        await callback.answer(
            "⚠️ Запись доступна только в рабочие дни (пн-пт).",
            show_alert=True
        )
        return

    user_data = await state.get_data()
    contract_id = user_data.get('contract_id')
    slots_limit = user_data.get('slots_limit', 1)  # Используем кешированный лимит проекта
    house_name = user_data.get('house_name')  # Получаем название проекта

    with SessionLocal() as session:
        contract = session.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            await callback.answer("Ошибка: данные договора не найдены.", show_alert=True)
            await state.clear()
            return

        # Получаем текущие бронирования для выбранной даты ТОЛЬКО ДЛЯ ЭТОГО ПРОЕКТА
        bookings = (
            session.query(
                Booking.time_slot,
                func.count(Booking.id)
            )
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .group_by(Booking.time_slot)
            .all()
        )

        booked_dict = {row[0]: row[1] for row in bookings}

    # Сохраняем выбранную дату в состояние
    await state.update_data(selected_date=selected_date_str)
    await state.set_state(ClientSteps.selecting_time)

    # Получаем язык пользователя
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    # Генерируем клавиатуру со слотами времени
    time_kb = generate_time_slots(selected_date_str, booked_dict, slots_limit, lang)
    
    # Форматируем даты
    sel_date_fmt = selected_date.strftime('%d.%m.%Y')
    del_date_fmt = contract.delivery_date.strftime('%d.%m.%Y') if contract.delivery_date else '-'

    # Формируем текст на нужном языке
    message_text = get_message('date_selected_choose_time', lang,
                               selected_date=sel_date_fmt,
                               delivery_date=del_date_fmt)
    
    # Обновляем сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=time_kb,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("time_"), ClientSteps.selecting_time)
async def time_selected(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    date_str = parts[1]
    time_str = parts[2]

    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    selected_time = datetime.strptime(time_str, '%H:%M').time()

    user_data = await state.get_data()
    slots_limit = user_data.get('slots_limit', 1)  # Используем кешированный лимит проекта
    house_name = user_data.get('house_name')  # Получаем название проекта
    user_id = callback.from_user.id
    lang = get_user_language(user_id)

    with SessionLocal() as session:
        # Проверяем количество бронирований для этого времени ТОЛЬКО ДЛЯ ЭТОГО ПРОЕКТА
        current_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Booking.time_slot == selected_time,
                Contract.house_name == house_name,
                Booking.is_cancelled == False
            )
            .count()
        )

        if current_bookings >= slots_limit:
            await callback.answer("Извините, это время только что заняли.", show_alert=True)
            return

    # Сохраняем выбранное время в state
    await state.update_data(selected_date=date_str, selected_time=time_str)
    
    # Проверяем, есть ли сохранённый телефон
    saved_phone = get_user_phone(user_id)
    
    if saved_phone:
        # Показываем выбор: использовать сохранённый или ввести новый
        builder = InlineKeyboardBuilder()
        builder.button(
            text=get_message('use_saved_phone', lang, phone=saved_phone),
            callback_data=f"use_phone_{saved_phone}"
        )
        builder.button(
            text=get_message('enter_new_phone', lang),
            callback_data="new_phone"
        )
        builder.adjust(1)
        
        await state.set_state(ClientSteps.entering_phone)
        await callback.message.edit_text(
            get_message('phone_choice', lang),
            reply_markup=builder.as_markup()
        )
    else:
        # Нет сохранённого телефона - запрашиваем ввод
        await state.set_state(ClientSteps.entering_phone)
        await callback.message.answer(
            get_message('enter_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        await callback.message.delete()
    
    await callback.answer()


@router.callback_query(F.data.startswith("use_phone_"), ClientSteps.entering_phone)
async def use_saved_phone(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Использовать сохранённый номер телефона"""
    saved_phone = callback.data.replace("use_phone_", "")
    
    # Создаём фейковое сообщение для унификации обработки
    await callback.message.delete()
    await process_phone_booking_callback(callback, state, bot, saved_phone)
    await callback.answer()


@router.callback_query(F.data == "new_phone", ClientSteps.entering_phone)
async def enter_new_phone(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь хочет ввести новый номер"""
    user_id = callback.from_user.id
    lang = get_user_language(user_id)
    
    await callback.message.edit_text(get_message('enter_phone', lang))
    await callback.message.answer(
        get_message('enter_phone', lang),
        reply_markup=get_phone_request_keyboard(lang)
    )
    await callback.answer()


async def process_phone_booking_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, user_phone: str):
    """Обработка бронирования при использовании сохранённого номера (через callback)"""
    user_data = await state.get_data()
    user_id = callback.from_user.id
    username = callback.from_user.username
    lang = get_user_language(user_id)

    # Извлекаем данные для подстановки в текст
    selected_date = datetime.strptime(user_data['selected_date'], '%Y-%m-%d').date()
    time_str = user_data['selected_time']
    selected_time = datetime.strptime(time_str, '%H:%M').time()

    with SessionLocal() as session:
        # Привязываем договор к пользователю (первая запись = владелец)
        contract = session.query(Contract).filter(Contract.id == user_data['contract_id']).first()
        if contract and not contract.telegram_id:
            contract.telegram_id = user_id
            contract.username = username
            contract.href = build_tg_href(user_id, username)
        elif contract and contract.telegram_id == user_id:
            contract.username = username
            contract.href = build_tg_href(user_id, username)
        
        # Отложенная отмена старой записи (если есть) — атомарно с созданием новой
        pending_cancel_id = user_data.get('pending_cancel_booking_id')
        if pending_cancel_id:
            old_booking = session.query(Booking).filter(Booking.id == pending_cancel_id).first()
            if old_booking and not old_booking.is_cancelled:
                old_booking.is_cancelled = True
                logging.info(
                    f"Автоотмена записи #{old_booking.id} (user={user_id}, "
                    f"date={old_booking.date}) при создании новой записи"
                )

        # Сохранение записи в базу данных
        new_booking = Booking(
            contract_id=user_data['contract_id'],
            user_telegram_id=user_id,
            date=selected_date,
            time_slot=selected_time,
            client_phone=user_phone
        )
        session.add(new_booking)
        session.commit()

        # Уведомление сотрудников
        notification_text = (
            f"🔔 **Новая запись на прием!**\n\n"
            f"👤 Клиент: {contract.client_fio}\n"
            f"📞 Тел: {user_phone}\n"
            f"💬 TG: {format_tg_contact_md(contract.telegram_id, contract.username)}\n"
            f"🏠 Объект: {contract.house_name}\n"
            f"🏢 Кв. {contract.apt_num}, подъезд {contract.entrance}, этаж {contract.floor}\n"
            f"📄 Договор: {contract.contract_num}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}"
        )

        # Получаем список ID всех сотрудников и админа для рассылки
        recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
        if ADMIN_ID not in recipients:
            recipients.append(ADMIN_ID)

        tg_kb = build_tg_profile_kb(contract.telegram_id, contract.username)

        # Отправляем уведомления в фоновом режиме
        async def send_booking_notifications():
            for emp_id in recipients:
                try:
                    await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown", reply_markup=tg_kb)
                except Exception as e:
                    logging.error(f"Ошибка уведомления {emp_id}: {e}")
        
        asyncio.create_task(send_booking_notifications())

    # Отправляем подтверждение
    project_address = get_project_address(user_data.get('selected_house', ''), lang)
    address_line = f"📍 {project_address}\n" if project_address else ""
    
    if lang == 'uz':
        success_text = (
            f"Kvartirangizni topshirish uchun uchrashuv tasdiqlandi.\n\n"
            f"{address_line}"
            f"🏠 Kvartira raqami {user_data['apt_num']}\n"
            f"📅 Sana: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Vaqt: {time_str}\n"
            f"📞 Telefon: {OFFICE_PHONE}\n\n"
            f"Kalitni topshirish faqat ulushdorlarga yoki notarial tasdiqlangan ishonchnomaga ega bo'lgan vakillarga topshiriladi.\n\n"
            f"O'zingiz bilan pasport/shaxsni tasdiqlovchi hujjat va ulushdorlik shartnomasi bo'lishi kerak.\n\n"
            f"Agar 15 daqiqadan ko'proq kechiksangiz, topshirish qayta rejalashtirilishi mumkin. Iltimos, vaqtida keling.\n\n"
            f"Agar qatnasha olmasangiz, iltimos, bizga oldindan xabar bering.\n\n"
            f"Oldindan yozilmasdan kalitlarni topshirish mumkin emas."
        )
    else:
        success_text = (
            f"Ваша запись на передачу квартиры подтверждена.\n\n"
            f"{address_line}"
            f"🏠 Квартира № {user_data['apt_num']}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}\n"
            f"📞 Телефон: {OFFICE_PHONE}\n\n"
            f"Передача ключей строго дольщику, либо представителю дольщика, по нотариально оформленной доверенности.\n"
            f"При себе необходимо иметь паспорт/ID и договор долевого участия.\n\n"
            f"В случае опоздания более чем на 15 минут передача может быть перенесена. Просим прибыть вовремя.\n\n"
            f"В случае невозможности визита — сообщите заранее.\n\n"
            f"Передача без записи невозможна."
        )

    await callback.message.answer(success_text, parse_mode="Markdown", reply_markup=get_client_keyboard(lang))

    # Отправка геолокации проекта (или офиса по умолчанию)
    coords = get_project_coordinates(user_data.get('selected_house', ''))
    if coords:
        lat, lon = coords
    else:
        lat, lon = OFFICE_LAT, OFFICE_LON
    
    await bot.send_location(
        chat_id=callback.from_user.id,
        latitude=lat,
        longitude=lon
    )

    await state.clear()


@router.message(ClientSteps.entering_phone, F.contact)
async def phone_contact_received(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка номера телефона, полученного через кнопку Telegram"""
    user_phone = message.contact.phone_number
    
    # Добавляем + если его нет
    if not user_phone.startswith('+'):
        user_phone = '+' + user_phone
    
    is_valid, cleaned_phone = validate_phone_number(user_phone)
    if not is_valid:
        lang = get_user_language(message.from_user.id)
        await message.answer(
            get_message('invalid_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        return
    
    await process_phone_booking(message, state, bot, cleaned_phone)


@router.message(ClientSteps.entering_phone)
async def phone_entered(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка номера телефона, введённого вручную"""
    user_phone = message.text.strip()
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    
    # Валидация номера
    is_valid, cleaned_phone = validate_phone_number(user_phone)
    
    if not is_valid:
        await message.answer(
            get_message('invalid_phone', lang),
            reply_markup=get_phone_request_keyboard(lang)
        )
        return
    
    await process_phone_booking(message, state, bot, cleaned_phone)


async def process_phone_booking(message: types.Message, state: FSMContext, bot: Bot, user_phone: str):
    """Общая логика обработки бронирования после получения номера телефона"""
    user_data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username
    lang = get_user_language(user_id)
    
    # Сохраняем номер телефона для будущих записей
    set_user_phone(user_id, user_phone)

    # Извлекаем данные для подстановки в текст
    selected_date = datetime.strptime(user_data['selected_date'], '%Y-%m-%d').date()
    time_str = user_data['selected_time']
    selected_time = datetime.strptime(time_str, '%H:%M').time()

    with SessionLocal() as session:
        # Привязываем договор к пользователю (первая запись = владелец)
        contract = session.query(Contract).filter(Contract.id == user_data['contract_id']).first()
        if contract and not contract.telegram_id:
            contract.telegram_id = user_id
            contract.username = username
            contract.href = build_tg_href(user_id, username)
        elif contract and contract.telegram_id == user_id:
            contract.username = username
            contract.href = build_tg_href(user_id, username)
        
        # Отложенная отмена старой записи (если есть) — атомарно с созданием новой
        pending_cancel_id = user_data.get('pending_cancel_booking_id')
        if pending_cancel_id:
            old_booking = session.query(Booking).filter(Booking.id == pending_cancel_id).first()
            if old_booking and not old_booking.is_cancelled:
                old_booking.is_cancelled = True
                logging.info(
                    f"Автоотмена записи #{old_booking.id} (user={user_id}, "
                    f"date={old_booking.date}) при создании новой записи"
                )

        # Сохранение записи в базу данных
        new_booking = Booking(
            contract_id=user_data['contract_id'],
            user_telegram_id=user_id,  # Сохраняем ID пользователя, создавшего запись
            date=selected_date,
            time_slot=selected_time,
            client_phone=user_phone
        )
        session.add(new_booking)
        session.commit()

        # Уведомление сотрудников
        notification_text = (
            f"🔔 **Новая запись на прием!**\n\n"
            f"👤 Клиент: {contract.client_fio}\n"
            f"📞 Тел: {user_phone}\n"
            f"💬 TG: {format_tg_contact_md(contract.telegram_id, contract.username)}\n"
            f"🏠 Объект: {contract.house_name}\n"
            f"🏢 Кв. {contract.apt_num}, подъезд {contract.entrance}, этаж {contract.floor}\n"
            f"📄 Договор: {contract.contract_num}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}"
        )

        # Получаем список ID всех сотрудников и админа для рассылки
        recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
        if ADMIN_ID not in recipients:
            recipients.append(ADMIN_ID)

        tg_kb = build_tg_profile_kb(contract.telegram_id, contract.username)

        # Отправляем уведомления в фоновом режиме
        async def send_booking_notifications():
            for emp_id in recipients:
                try:
                    await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown", reply_markup=tg_kb)
                except Exception as e:
                    logging.error(f"Ошибка уведомления {emp_id}: {e}")
        
        asyncio.create_task(send_booking_notifications())

    # Убираем клавиатуру и отправляем подтверждение
    project_address = get_project_address(user_data.get('selected_house', ''), lang)
    address_line = f"📍 {project_address}\n" if project_address else ""
    
    if lang == 'uz':
        success_text = (
            f"Kvartirangizni topshirish uchun uchrashuv tasdiqlandi.\n\n"
            f"{address_line}"
            f"🏠 Kvartira raqami {user_data['apt_num']}\n"
            f"📅 Sana: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Vaqt: {time_str}\n"
            f"📞 Telefon: {OFFICE_PHONE}\n\n"
            f"Kalitni topshirish faqat ulushdorlarga yoki notarial tasdiqlangan ishonchnomaga ega bo'lgan vakillarga topshiriladi.\n\n"
            f"O'zingiz bilan pasport/shaxsni tasdiqlovchi hujjat va ulushdorlik shartnomasi bo'lishi kerak.\n\n"
            f"Agar 15 daqiqadan ko'proq kechiksangiz, topshirish qayta rejalashtirilishi mumkin. Iltimos, vaqtida keling.\n\n"
            f"Agar qatnasha olmasangiz, iltimos, bizga oldindan xabar bering.\n\n"
            f"Oldindan yozilmasdan kalitlarni topshirish mumkin emas."
        )
    else:
        success_text = (
            f"Ваша запись на передачу квартиры подтверждена.\n\n"
            f"{address_line}"
            f"🏠 Квартира № {user_data['apt_num']}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}\n"
            f"📞 Телефон: {OFFICE_PHONE}\n\n"
            f"Передача ключей строго дольщику, либо представителю дольщика, по нотариально оформленной доверенности.\n"
            f"При себе необходимо иметь паспорт/ID и договор долевого участия.\n\n"
            f"В случае опоздания более чем на 15 минут передача может быть перенесена. Просим прибыть вовремя.\n\n"
            f"В случае невозможности визита — сообщите заранее.\n\n"
            f"Передача без записи невозможна."
        )

    await message.answer(success_text, parse_mode="Markdown", reply_markup=get_client_keyboard(lang))

    # Отправка геолокации проекта (или офиса по умолчанию)
    coords = get_project_coordinates(user_data.get('selected_house', ''))
    if coords:
        lat, lon = coords
    else:
        lat, lon = OFFICE_LAT, OFFICE_LON
    
    await bot.send_location(
        chat_id=message.from_user.id,
        latitude=lat,
        longitude=lon
    )

    await state.clear()
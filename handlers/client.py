import logging
import re
from datetime import datetime, timedelta, date

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy import select, func

from config import ADMIN_ID
from database.models import Booking, Setting, Contract, Staff, ProjectSlots
from database.session import SessionLocal
from keyboards import inline
from keyboards.inline import generate_time_slots, generate_calendar, get_min_booking_date, get_fully_booked_dates, SLOTS_PER_DAY
from keyboards.reply import get_phone_request_keyboard
from utils.states import ClientSteps

router = Router()

OFFICE_ADDRESS = "г. Ташкент, Яшнабадский район, ул. Фаргона йули 27 (O'Z Zamin)"
OFFICE_LAT = 41.281067
OFFICE_LON = 69.306903
OFFICE_PHONE = "+998781485115"


def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Валидация номера телефона.
    
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
    
    # Удаляем + для подсчёта цифр
    digits_only = cleaned.lstrip('+')
    
    # Проверяем длину (от 9 до 15 цифр - международный стандарт)
    if len(digits_only) < 9 or len(digits_only) > 15:
        return False, ""
    
    # Если номер начинается не с +, добавляем +
    if not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    
    return True, cleaned


def get_project_slot_limit(session, project_name: str) -> int:
    """
    Получить лимит слотов для конкретного проекта.
    Если лимит не установлен для проекта, используется глобальный лимит.
    
    Args:
        session: SQLAlchemy сессия
        project_name: Название проекта (house_name)
    
    Returns:
        int: Лимит записей на один слот
    """
    # Проверяем индивидуальный лимит для проекта
    project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
    if project_slot:
        return project_slot.slots_limit
    
    # Если нет индивидуального - используем глобальный
    global_setting = session.query(Setting).filter_by(key='slots_per_interval').first()
    return global_setting.value if global_setting else 1


@router.message(F.text == "/start")
async def client_start(message: types.Message, state: FSMContext):
    with SessionLocal() as session:
        houses = session.execute(select(Contract.house_name).distinct()).scalars().all()

    if not houses:
        await message.answer("В базе пока нет доступных объектов.")
        return

    await state.set_state(ClientSteps.selecting_house)
    await message.answer(
        "Выберите дом, в котором вы приобрели квартиру:",
        reply_markup=inline.generate_houses_kb(houses)
    )


@router.callback_query(F.data.startswith("house_"))
async def house_selected(callback: types.CallbackQuery, state: FSMContext):
    house_name = callback.data.split("_")[1]
    await state.update_data(selected_house=house_name)
    await state.set_state(ClientSteps.entering_contract)

    await callback.message.edit_text(
        f"🏘 Объект: **{house_name}**\n\nUlushdorlik shartnomasi raqamingizni kiriting, masalan, 12345-GHP\n"
        "———————\n"
        "Введите номер Вашего договора долевого участия по примеру 12345-GHP"
    )
    await callback.answer()


@router.message(ClientSteps.entering_contract)
async def contract_entered(message: types.Message, state: FSMContext):
    user_contract = message.text.replace(" ", "").upper()
    data = await state.get_data()
    selected_house = data.get('selected_house')

    with SessionLocal() as session:
        contract = session.query(Contract).filter(
            Contract.contract_num == user_contract,
            Contract.house_name == selected_house
        ).first()

        # Если договор НЕ найден
        if not contract:
            error_text = (
                f"{user_contract}-shartnoma topilmadi.\n"
                f"Malumotlatni tekshiring yoki qo'llab-quvvatlash xizmatiga murojaat qiling:\n"
                f"{OFFICE_PHONE}\n"
                f"————\n\n"
                f"Договор {user_contract} не найден.\n"
                f"Проверьте данные или свяжитесь с поддержкой:\n"
                f"{OFFICE_PHONE}"
            )
            await message.answer(error_text)
            return

        # Если договор найден, проверяем существующие записи
        today = date.today()
        last_booking = session.query(Booking).filter(
            Booking.contract_id == contract.id
        ).order_by(Booking.date.desc()).first()

        if last_booking:
            if last_booking.date >= today:
                await message.answer(
                    f"У вас уже есть активная запись на {last_booking.date.strftime('%d.%m.%Y')}.\n"
                    "Вторая запись невозможна до завершения текущего визита."
                )
                await state.clear()
                return

            allowed_from_date = last_booking.date + timedelta(days=2)
            if today < allowed_from_date:
                await message.answer(
                    f"Повторная запись будет доступна только с {allowed_from_date.strftime('%d.%m.%Y')}.\n"
                    "Между визитами должен пройти как минимум один полный день."
                )
                await state.clear()
                return

        if not contract.telegram_id:
            contract.telegram_id = message.from_user.id
            session.commit()

        # Получаем лимит слотов для проекта
        slots_limit = get_project_slot_limit(session, contract.house_name)

        await state.update_data(
            contract_id=contract.id,
            client_fio=contract.client_fio,
            apt_num=contract.apt_num,
            house_name=contract.house_name,  # Сохраняем проект для получения правильного лимита
            delivery_date=contract.delivery_date.isoformat(),
            slots_limit=slots_limit  # Кешируем лимит проекта
        )

        # Определяем период для проверки занятых дат (90 дней вперёд)
        start_date = contract.delivery_date
        end_date = date.today() + timedelta(days=90)
        
        # Получаем полностью занятые даты ДЛЯ ЭТОГО ПРОЕКТА
        fully_booked = get_fully_booked_dates(session, start_date, end_date, slots_limit, contract.house_name)

        # Создаем клавиатуру с учётом занятых дат
        markup = generate_calendar(
            min_date=contract.delivery_date,
            fully_booked_dates=fully_booked,
            slots_limit=slots_limit
        )
        await state.set_state(ClientSteps.selecting_date)

        await message.answer(
            f"✅ Shartnoma tasdiqlandi: {contract.client_fio}\n"
            f"Obyektni topshirish sanasi: {contract.delivery_date.strftime('%d.%m.%Y')}\n\n"
            f"Taqvimda mavjud sanani tanlang:\n"
            f"————————————————-\n"
            f"✅ Договор подтвержден: {contract.client_fio}\n"
            f"Дата сдачи объекта: {contract.delivery_date.strftime('%d.%m.%Y')}\n\n"
            "Выберите доступную дату в календаре:",
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
    new_calendar = generate_calendar(
        year=year, 
        month=month, 
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit
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
    calendar_markup = generate_calendar(
        min_date=delivery_date,
        fully_booked_dates=fully_booked,
        slots_limit=slots_limit
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
                Contract.house_name == house_name
            )
            .group_by(Booking.time_slot)
            .all()
        )

        booked_dict = {row[0]: row[1] for row in bookings}

    # Сохраняем выбранную дату в состояние
    await state.update_data(selected_date=selected_date_str)
    await state.set_state(ClientSteps.selecting_time)

    # 1. Сначала генерируем клавиатуру со слотами времени
    time_kb = generate_time_slots(selected_date_str, booked_dict, slots_limit)

    # 2. Подготавливаем переменные для текста
    sel_date_fmt = selected_date.strftime('%d.%m.%Y')
    del_date_fmt = contract.delivery_date.strftime('%d.%m.%Y')

    # 3. Формируем ваш двуязычный текст
    message_text = (
        f"📅 Siz sanani tanladingiz: **{sel_date_fmt}**\n"
        f"🏠 Xonadoningizning topshirish sanasi: {del_date_fmt}\n\n"
        f"Endi qulay vaqt oralig‘ini tanlang:\n"
        f"————————————————\n"
        f"📅 Вы выбрали дату: **{sel_date_fmt}**\n"
        f"🏠 Дата сдачи вашей квартиры: {del_date_fmt}\n\n"
        f"Теперь выберите удобный временной интервал:"
    )
    # 4. Обновляем сообщение
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

    with SessionLocal() as session:
        # Проверяем количество бронирований для этого времени ТОЛЬКО ДЛЯ ЭТОГО ПРОЕКТА
        current_bookings = (
            session.query(Booking)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date == selected_date,
                Booking.time_slot == selected_time,
                Contract.house_name == house_name
            )
            .count()
        )

        if current_bookings >= slots_limit:
            await callback.answer("Извините, это время только что заняли.", show_alert=True)
            return

    # Сохраняем выбранное время в state и запрашиваем телефон
    await state.update_data(selected_date=date_str, selected_time=time_str)
    await state.set_state(ClientSteps.entering_phone)

    await callback.message.answer(
        "📞 Iltimos, joriy aloqa telefon raqamingizni kiriting yoki pastdagi tugmani bosing:\n"
        "———————\n"
        "📞 Пожалуйста, введите ваш актуальный номер телефона для связи или нажмите кнопку ниже:\n\n"
        "Формат: +998901234567 или 998901234567",
        reply_markup=get_phone_request_keyboard()
    )
    await callback.message.delete()
    await callback.answer()

@router.message(ClientSteps.entering_phone, F.contact)
async def phone_contact_received(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка номера телефона, полученного через кнопку Telegram"""
    user_phone = message.contact.phone_number
    
    # Добавляем + если его нет
    if not user_phone.startswith('+'):
        user_phone = '+' + user_phone
    
    await process_phone_booking(message, state, bot, user_phone)


@router.message(ClientSteps.entering_phone)
async def phone_entered(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка номера телефона, введённого вручную"""
    user_phone = message.text.strip()
    
    # Валидация номера
    is_valid, cleaned_phone = validate_phone_number(user_phone)
    
    if not is_valid:
        await message.answer(
            "❌ Неверный формат номера телефона.\n\n"
            "Noto'g'ri telefon raqam formati.\n\n"
            "Используйте формат: +998901234567 или 998901234567\n"
            "Format: +998901234567 yoki 998901234567",
            reply_markup=get_phone_request_keyboard()
        )
        return
    
    await process_phone_booking(message, state, bot, cleaned_phone)


async def process_phone_booking(message: types.Message, state: FSMContext, bot: Bot, user_phone: str):
    """Общая логика обработки бронирования после получения номера телефона"""
    user_data = await state.get_data()

    # Извлекаем данные для подстановки в текст
    selected_date = datetime.strptime(user_data['selected_date'], '%Y-%m-%d').date()
    time_str = user_data['selected_time']
    selected_time = datetime.strptime(time_str, '%H:%M').time()

    with SessionLocal() as session:
        # Сохранение записи в базу данных
        new_booking = Booking(
            contract_id=user_data['contract_id'],
            date=selected_date,
            time_slot=selected_time,
            client_phone=user_phone
        )
        session.add(new_booking)
        session.commit()

        # Уведомление сотрудников
        notification_text = (
            f"🔔 **Новая запись на прием!**\n\n"
            f"👤 Клиент: {user_data['client_fio']}\n"
            f"📞 Тел: {user_phone}\n"
            f"🏠 Объект: {user_data['selected_house']}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}"
        )

        # Получаем список ID всех сотрудников и админа для рассылки
        recipients = [r[0] for r in session.query(Staff.telegram_id).all()]
        if ADMIN_ID not in recipients:
            recipients.append(ADMIN_ID)

        for emp_id in recipients:
            try:
                await bot.send_message(chat_id=emp_id, text=notification_text, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Ошибка уведомления {emp_id}: {e}")

    # Убираем клавиатуру и отправляем подтверждение
    success_text = (
        f"Kvartirangizni topshirish uchun uchrashuv tasdiqlandi.\n\n"
        f"📍 {OFFICE_ADDRESS}\n"
        f"🏠 Kvartira raqami {user_data['apt_num']}\n"
        f"📅 Sana: {selected_date.strftime('%d.%m.%Y')}\n"
        f"⏰ Vaqt: {time_str}\n"
        f"📞 Telefon: {OFFICE_PHONE}\n\n"
        f"Kalitni topshirish faqat ulushdorlarga yoki notarial tasdiqlangan ishonchnomaga ega bo'lgan vakillarga topshiriladi.\n\n"
        f"O'zingiz bilan pasport/shaxsni tasdiqlovchi hujjat va ulushdorlik shartnomasi bo'lishi kerak.\n\n"
        f"Agar 15 daqiqadan ko'proq kechiksangiz, topshirish qayta rejalashtirilishi mumkin. Iltimos, vaqtida keling.\n\n"
        f"Agar qatnasha olmasangiz, iltimos, bizga oldindan xabar bering.\n\n"
        f"Oldindan yozilmasdan kalitlarni topshirish mumkin emas.\n"
        f"———————————————————-\n"
        f"Ваша запись на передачу квартиры подтверждена.\n\n"
        f"📍 {OFFICE_ADDRESS}\n"
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

    await message.answer(success_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

    # Отправка геолокации офиса
    await bot.send_location(
        chat_id=message.from_user.id,
        latitude=OFFICE_LAT,
        longitude=OFFICE_LON
    )

    await state.clear()
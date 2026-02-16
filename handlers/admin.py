import logging
import os
import asyncio
from datetime import datetime
from utils.auth import is_admin, is_staff
import pandas as pd
from aiogram import Bot
from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from sqlalchemy import select
from database.models import Staff, ProjectSlots
from aiogram.filters import BaseFilter
from config import ADMIN_ID
from database.models import Booking, Contract
from database.models import Setting
from database.session import SessionLocal
from utils.excel_reader import process_excel_file
from utils.states import AdminSteps
from keyboards.reply import (
    get_admin_keyboard, get_staff_management_keyboard, 
    get_slots_management_keyboard, get_back_keyboard, get_cancel_keyboard
)
from keyboards.inline import generate_houses_kb

router = Router()


class IsAdminFilter(BaseFilter):
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        # Поддержка как Message, так и CallbackQuery
        user_id = event.from_user.id
        result = is_admin(user_id)
        if isinstance(event, types.CallbackQuery):
            print(f"[IsAdminFilter] callback_query user={user_id}, is_admin={result}, data={event.data}")
        return result


router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())  # Применяем фильтр и к inline кнопкам


# Список кнопок главного меню администратора (для сброса состояния)
ADMIN_MENU_BUTTONS = [
    "👥 Управление персоналом", "⚙️ Настройки проектов",
    "📊 Выгрузить отчет", "📋 Список записей",
    "➕ Добавление проектов", "🏠 Список проектов",
    "🔙 Скрыть меню", "📝 Установить лимит для проекта",
    "📍 Установить адрес проекта", "🗺 Установить координаты проекта",
    "📊 Текущие настройки проектов", "◀️ Назад",
    "➕ Добавить администратора", "➕ Добавить сотрудника",
    "📋 Список персонала", "❌ Удалить из персонала"
]


# Обработчик для кнопок меню при активном состоянии - очищает состояние и перенаправляет
@router.message(StateFilter(AdminSteps), F.text.in_(ADMIN_MENU_BUTTONS))
async def reset_state_on_menu_button(message: types.Message, state: FSMContext):
    """Сброс состояния при нажатии кнопки меню и перенаправление"""
    await state.clear()
    
    # Перенаправляем на соответствующий обработчик
    text = message.text
    
    if text == "👥 Управление персоналом":
        await message.answer("👥 Управление персоналом\n\nВыберите действие:", reply_markup=get_staff_management_keyboard())
    elif text == "⚙️ Настройки проектов":
        await message.answer("⚙️ Настройки проектов\n\nВыберите действие:", reply_markup=get_slots_management_keyboard())
    elif text == "◀️ Назад":
        await message.answer("Главное меню:", reply_markup=get_admin_keyboard())
    elif text == "📊 Текущие настройки проектов":
        await show_project_settings(message)
    elif text == "📝 Установить лимит для проекта":
        await start_set_project_slots(message, state)
    elif text == "📍 Установить адрес проекта":
        await start_set_project_address(message, state)
    elif text == "🗺 Установить координаты проекта":
        await start_set_project_coordinates(message, state)
    elif text == "➕ Добавление проектов":
        await start_add_project(message, state)
    elif text == "🏠 Список проектов":
        await show_projects_list(message)
    elif text == "📊 Выгрузить отчет":
        await export_report(message)
    elif text == "📋 Список записей":
        await show_bookings_list(message, state)
    elif text == "➕ Добавить администратора":
        await start_add_admin(message, state)
    elif text == "➕ Добавить сотрудника":
        await start_add_employee(message, state)
    elif text == "📋 Список персонала":
        await show_staff_list_button(message)
    elif text == "❌ Удалить из персонала":
        await start_delete_staff(message, state)
    elif text == "🔙 Скрыть меню":
        await hide_menu(message, state)
    else:
        await message.answer("Главное меню:", reply_markup=get_admin_keyboard())


@router.message(Command("add_admin"))
async def add_admin_cmd(message: types.Message):
    try:
        new_id = int(message.text.split()[1])
        with SessionLocal() as session:
            existing = session.query(Staff).filter_by(telegram_id=new_id).first()
            if existing:
                existing.role = 'admin'
            else:
                session.add(Staff(telegram_id=new_id, role='admin'))
            session.commit()
        await message.answer(f"✅ Пользователь {new_id} теперь администратор.", reply_markup=get_admin_keyboard())
    except (IndexError, ValueError):
        await message.answer("Использование: `/add_admin [ID]`", reply_markup=get_admin_keyboard())


@router.message(Command("add_employee"))
async def add_employee_cmd(message: types.Message):
    try:
        new_id = int(message.text.split()[1])
        with SessionLocal() as session:
            existing = session.query(Staff).filter_by(telegram_id=new_id).first()
            if existing:
                existing.role = 'employee'
            else:
                session.add(Staff(telegram_id=new_id, role='employee'))
            session.commit()
        await message.answer(f"✅ Пользователь {new_id} добавлен как сотрудник.", reply_markup=get_admin_keyboard())
    except (IndexError, ValueError):
        await message.answer("Использование: `/add_employee [ID]`", reply_markup=get_admin_keyboard())


@router.message(Command("staff_list"))
async def list_staff(message: types.Message):
    with SessionLocal() as session:
        staff_members = session.query(Staff).all()
        if not staff_members:
            return await message.answer("Список персонала пуст.", reply_markup=get_admin_keyboard())

        text = "👥 **Персонал в базе:**\n"
        for s in staff_members:
            text += f"• `{s.telegram_id}` — {s.role}\n"
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


@router.message(Command("set_slots"))
async def cmd_set_slots(message: types.Message):
    try:
        val = int(message.text.split()[1])
        with SessionLocal() as session:
            setting = session.query(Setting).filter_by(key='slots_per_interval').first()
            if not setting:
                session.add(Setting(key='slots_per_interval', value=val))
            else:
                setting.value = val
            session.commit()
        await message.answer(f"Лимит одновременных записей установлен на: {val}", reply_markup=get_admin_keyboard())
    except (IndexError, ValueError):
        await message.answer("Использование: /set_slots [число]", reply_markup=get_admin_keyboard())

@router.message(Command("del_staff"))
async def remove_staff_cmd(message: types.Message):
    try:
        target_id = int(message.text.split()[1])
        with SessionLocal() as session:
            staff = session.query(Staff).filter_by(telegram_id=target_id).first()
            if staff:
                session.delete(staff)
                session.commit()
                await message.answer(f"❌ Пользователь {target_id} удален из списка персонала.", reply_markup=get_admin_keyboard())
            else:
                await message.answer("Пользователь не найден в базе.", reply_markup=get_admin_keyboard())
    except (IndexError, ValueError):
        await message.answer("Использование: `/del_staff [ID]`", reply_markup=get_admin_keyboard())

@router.message(Command("report"))
async def export_report(message: types.Message):
    # Отправляем сообщение о выполнении операции
    loading_msg = await message.answer("⏳ Ваша операция выполняется, подождите...")
    
    try:
        with SessionLocal() as session:
            # SQL Join для объединения данных записи и контракта с новыми полями
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
                return await message.answer("Записи в базе данных отсутствуют.", reply_markup=get_admin_keyboard())

            # Преобразование в DataFrame с обновленными колонками
            df = pd.DataFrame(results, columns=[
                "Дата визита", "Время", "ФИО Клиента", "Телефон клиента",
                "Договор", "Дом", "Подъезд", "Кв"
            ])

            # Форматирование времени для Excel
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
        await message.answer(f"❌ Ошибка при формировании отчета: {e}", reply_markup=get_admin_keyboard())


@router.message(Command("menu"))
async def show_admin_menu(message: types.Message):
    """Показать админ-меню"""
    await message.answer(
        "🔧 Админ-панель", 
        reply_markup=get_admin_keyboard()
    )


# ========== ОБРАБОТЧИКИ КНОПОК КЛАВИАТУРЫ ==========

@router.message(F.text == "🔙 Скрыть меню")
async def hide_menu(message: types.Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_admin_keyboard())


@router.message(F.text == "◀️ Назад")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_admin_keyboard())


# ========== УПРАВЛЕНИЕ ПЕРСОНАЛОМ ==========

@router.message(F.text == "👥 Управление персоналом")
async def staff_management_menu(message: types.Message):
    """Меню управления персоналом"""
    await message.answer(
        "👥 Управление персоналом\n\nВыберите действие:",
        reply_markup=get_staff_management_keyboard()
    )


@router.message(F.text == "➕ Добавить администратора")
async def start_add_admin(message: types.Message, state: FSMContext):
    """Начало добавления администратора"""
    await state.set_state(AdminSteps.waiting_for_admin_id)
    await message.answer(
        "Отправьте Telegram ID нового администратора:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.waiting_for_admin_id, F.text == "❌ Отменить")
async def cancel_add_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_admin_id, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_add_admin(message: types.Message, state: FSMContext):
    """Обработка добавления администратора"""
    try:
        new_id = int(message.text.strip())
        with SessionLocal() as session:
            existing = session.query(Staff).filter_by(telegram_id=new_id).first()
            if existing:
                existing.role = 'admin'
            else:
                session.add(Staff(telegram_id=new_id, role='admin'))
            session.commit()
        await state.clear()
        await message.answer(
            f"✅ Пользователь {new_id} добавлен как администратор.",
            reply_markup=get_admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Введите числовой ID:", reply_markup=get_cancel_keyboard())


@router.message(F.text == "➕ Добавить сотрудника")
async def start_add_employee(message: types.Message, state: FSMContext):
    """Начало добавления сотрудника"""
    await state.set_state(AdminSteps.waiting_for_employee_id)
    await message.answer(
        "Отправьте Telegram ID нового сотрудника:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.waiting_for_employee_id, F.text == "❌ Отменить")
async def cancel_add_employee(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_employee_id, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_add_employee(message: types.Message, state: FSMContext):
    """Обработка добавления сотрудника"""
    try:
        new_id = int(message.text.strip())
        with SessionLocal() as session:
            existing = session.query(Staff).filter_by(telegram_id=new_id).first()
            if existing:
                existing.role = 'employee'
            else:
                session.add(Staff(telegram_id=new_id, role='employee'))
            session.commit()
        await state.clear()
        await message.answer(
            f"✅ Пользователь {new_id} добавлен как сотрудник.",
            reply_markup=get_admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Введите числовой ID:", reply_markup=get_cancel_keyboard())


@router.message(F.text == "📋 Список персонала")
async def show_staff_list_button (message: types.Message):
    """Показать список персонала через кнопку"""
    with SessionLocal() as session:
        staff_members = session.query(Staff).all()
        if not staff_members:
            return await message.answer("Список персонала пуст.", reply_markup=get_admin_keyboard())

        text = "👥 **Персонал в базе:**\n\n"
        for s in staff_members:
            role_emoji = "👑" if s.role == 'admin' else "👤"
            text += f"{role_emoji} `{s.telegram_id}` — {s.role}\n"
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


@router.message(F.text == "❌ Удалить из персонала")
async def start_delete_staff(message: types.Message, state: FSMContext):
    """Начало удаления из персонала"""
    await state.set_state(AdminSteps.waiting_for_staff_id_to_delete)
    await message.answer(
        "Отправьте Telegram ID пользователя для удаления:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.waiting_for_staff_id_to_delete, F.text == "❌ Отменить")
async def cancel_delete_staff(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_staff_id_to_delete, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_delete_staff(message: types.Message, state: FSMContext):
    """Обработка удаления из персонала"""
    try:
        target_id = int(message.text.strip())
        with SessionLocal() as session:
            staff = session.query(Staff).filter_by(telegram_id=target_id).first()
            if staff:
                session.delete(staff)
                session.commit()
                await state.clear()
                await message.answer(
                    f"✅ Пользователь {target_id} удален из персонала.",
                    reply_markup=get_admin_keyboard()
                )
            else:
                await message.answer("❌ Пользователь не найден в базе.", reply_markup=get_cancel_keyboard())
    except ValueError:
        await message.answer("❌ Неверный формат. Введите числовой ID:", reply_markup=get_cancel_keyboard())


# ========== УПРАВЛЕНИЕ СЛОТАМИ ==========

@router.message(F.text == "⚙️ Настройки проектов")
async def slots_management_menu(message: types.Message):
    """Меню управления проектами"""
    await message.answer(
        "⚙️ Настройки проектов\n\nВыберите действие:",
        reply_markup=get_slots_management_keyboard()
    )


@router.message(F.text == "📝 Установить лимит для проекта")
async def start_set_project_slots(message: types.Message, state: FSMContext):
    """Начало установки лимита слотов для проекта"""
    print("[DEBUG] start_set_project_slots called")
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]
        
        if not projects:
            return await message.answer(
                "❌ В базе нет проектов. Сначала загрузите контракты.",
                reply_markup=get_back_keyboard()
            )
        
        # Создаем inline-клавиатуру с проектами
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for project in projects:
            builder.button(text=project, callback_data=f"setslot_{project[:40]}")
        builder.adjust(1)
        
        await state.set_state(AdminSteps.selecting_project_for_slots)
        await message.answer(
            "Выберите проект:",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("setslot_"))
async def project_selected_for_slots(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора проекта для установки лимита"""
    print(f"[DEBUG] project_selected_for_slots called, data={callback.data}")
    project_name = callback.data.split("_", 1)[1]
    await state.update_data(selected_project=project_name)
    await state.set_state(AdminSteps.waiting_for_slot_limit)
    
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        current_limit = project_slot.slots_limit if project_slot else "не установлен"
    
    await callback.message.edit_text(
        f"🏘 Проект: **{project_name}**\n"
        f"Текущий лимит: {current_limit}\n\n"
        f"Введите новый лимит записей на один слот (например, 2):",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminSteps.waiting_for_slot_limit, F.text == "◀️ Назад")
async def cancel_set_slot_limit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_slot_limit, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_slot_limit(message: types.Message, state: FSMContext):
    """Обработка установки лимита слотов"""
    try:
        limit = int(message.text.strip())
        if limit < 1:
            return await message.answer("❌ Лимит должен быть больше 0", reply_markup=get_back_keyboard())
        
        user_data = await state.get_data()
        project_name = user_data.get('selected_project')
        
        with SessionLocal() as session:
            project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
            if project_slot:
                project_slot.slots_limit = limit
            else:
                session.add(ProjectSlots(project_name=project_name, slots_limit=limit))
            session.commit()
        
        await state.clear()
        await message.answer(
            f"✅ Лимит для проекта **{project_name}** установлен: {limit}",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:", reply_markup=get_back_keyboard())


@router.message(F.text == "📊 Текущие настройки проектов")
async def show_project_settings(message: types.Message):
    """Показать текущие настройки проектов (лимиты, адреса и координаты)"""
    with SessionLocal() as session:
        # Получаем все проекты
        all_projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        all_projects = [h for h in all_projects if h]
        
        if not all_projects:
            return await message.answer("❌ В базе нет проектов.", reply_markup=get_admin_keyboard())
        
        # Получаем настроенные лимиты, адреса и координаты
        project_slots = session.query(ProjectSlots).all()
        slots_dict = {ps.project_name: ps for ps in project_slots}
        
        text = "📊 **Настройки проектов:**\n\n"
        
        for project in sorted(all_projects):
            ps = slots_dict.get(project)
            limit = ps.slots_limit if ps else "не установлен"
            address_ru = ps.address_ru if ps and ps.address_ru else "не установлен"
            
            # Координаты
            if ps and ps.latitude and ps.longitude:
                coords = f"{ps.latitude}, {ps.longitude}"
            else:
                coords = "не установлены"
            
            text += f"🏘 **{project}**\n"
            text += f"   └ Лимит: {limit}\n"
            text += f"   └ Адрес: {address_ru[:40]}{'...' if len(address_ru) > 40 else ''}\n"
            text += f"   └ Координаты: {coords}\n\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


# ========== УПРАВЛЕНИЕ АДРЕСАМИ ПРОЕКТОВ ==========

@router.message(F.text == "📍 Установить адрес проекта")
async def start_set_project_address(message: types.Message, state: FSMContext):
    """Начало установки адреса для проекта"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]
        
        if not projects:
            return await message.answer(
                "❌ В базе нет проектов. Сначала загрузите контракты.",
                reply_markup=get_back_keyboard()
            )
        
        # Создаем inline-клавиатуру с проектами
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for project in projects:
            builder.button(text=project, callback_data=f"setaddr_{project[:40]}")
        builder.adjust(1)
        
        await state.set_state(AdminSteps.selecting_project_for_address)
        await message.answer(
            "Выберите проект для установки адреса:",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("setaddr_"))
async def project_selected_for_address(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора проекта для установки адреса"""
    project_name = callback.data.split("_", 1)[1]
    await state.update_data(selected_project=project_name)
    await state.set_state(AdminSteps.waiting_for_address_ru)
    
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        current_address = project_slot.address_ru if project_slot and project_slot.address_ru else "не установлен"
        
        # Сохраняем текущие адреса в state
        if project_slot:
            await state.update_data(
                current_address_ru=project_slot.address_ru,
                current_address_uz=project_slot.address_uz
            )
    
    # Создаем inline кнопку для сохранения текущего адреса
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    if current_address != "не установлен":
        builder.button(text="✅ Оставить текущие адреса", callback_data="keep_current_addresses")
        builder.adjust(1)
    
    await callback.message.edit_text(
        f"🏘 Проект: **{project_name}**\n"
        f"Текущий адрес (RU): {current_address}\n\n"
        f"Введите адрес на **русском** языке:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup() if builder.buttons else None
    )
    await callback.answer()


@router.callback_query(F.data == "keep_current_addresses")
async def keep_current_addresses(callback: types.CallbackQuery, state: FSMContext):
    """Оставить текущие адреса без изменений"""
    await state.clear()
    await callback.message.edit_text("✅ Адреса оставлены без изменений.")
    await callback.message.answer(
        "Операция завершена.",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


@router.message(AdminSteps.waiting_for_address_ru, F.text == "◀️ Назад")
async def cancel_set_address(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_address_ru, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_address_ru(message: types.Message, state: FSMContext):
    """Обработка адреса на русском"""
    address_ru = message.text.strip()
    await state.update_data(address_ru=address_ru)
    await state.set_state(AdminSteps.waiting_for_address_uz)
    
    await message.answer(
        f"✅ Адрес (RU): {address_ru}\n\n"
        f"Теперь введите адрес на **узбекском** языке:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )


@router.message(AdminSteps.waiting_for_address_uz, F.text == "◀️ Назад")
async def cancel_set_address_uz(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.waiting_for_address_uz, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_address_uz(message: types.Message, state: FSMContext):
    """Обработка адреса на узбекском и сохранение"""
    address_uz = message.text.strip()
    user_data = await state.get_data()
    project_name = user_data.get('selected_project')
    address_ru = user_data.get('address_ru')
    
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        if project_slot:
            project_slot.address_ru = address_ru
            project_slot.address_uz = address_uz
        else:
            session.add(ProjectSlots(
                project_name=project_name, 
                slots_limit=1,
                address_ru=address_ru,
                address_uz=address_uz
            ))
        session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ Адреса для проекта **{project_name}** установлены:\n\n"
        f"🇷🇺 RU: {address_ru}\n"
        f"🇺🇿 UZ: {address_uz}",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )


# ========== УПРАВЛЕНИЕ КООРДИНАТАМИ ПРОЕКТОВ ==========

@router.message(F.text == "🗺 Установить координаты проекта")
async def start_set_project_coordinates(message: types.Message, state: FSMContext):
    """Начало установки координат для проекта"""
    print(f"[DEBUG] start_set_project_coordinates called, user={message.from_user.id}")
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]
        
        if not projects:
            return await message.answer(
                "❌ В базе нет проектов. Сначала загрузите контракты.",
                reply_markup=get_back_keyboard()
            )
        
        # Сохраняем список проектов в state для последующего использования
        await state.update_data(projects_list=projects)
        
        # Создаем inline-клавиатуру с проектами (используем индексы)
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for idx, project in enumerate(projects):
            builder.button(text=project, callback_data=f"coord_{idx}")
        builder.adjust(1)
        
        await state.set_state(AdminSteps.edit_project_select)
        await message.answer(
            "Выберите проект для установки координат:",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("coord_"))
async def project_selected_for_coordinates(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора проекта для установки координат"""
    print(f"[DEBUG] project_selected_for_coordinates called, data={callback.data}")
    project_idx = int(callback.data.split("_")[1])
    user_data = await state.get_data()
    projects_list = user_data.get('projects_list', [])
    
    if project_idx >= len(projects_list):
        await callback.answer("❌ Ошибка: проект не найден", show_alert=True)
        return
    
    project_name = projects_list[project_idx]
    await state.update_data(selected_project=project_name)
    
    with SessionLocal() as session:
        project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
        current_lat = project_slot.latitude if project_slot and project_slot.latitude else "не установлена"
        current_lon = project_slot.longitude if project_slot and project_slot.longitude else "не установлена"
    
    # Создаем inline кнопку для использования текущих координат
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    if current_lat != "не установлена" and current_lon != "не установлена":
        builder.button(text="✅ Оставить текущие координаты", callback_data="keep_current_coords")
        builder.adjust(1)
    
    await state.set_state(AdminSteps.edit_project_latitude)
    await callback.message.edit_text(
        f"🏘 Проект: **{project_name}**\n"
        f"Текущие координаты:\n"
        f"   └ Широта: {current_lat}\n"
        f"   └ Долгота: {current_lon}\n\n"
        f"Введите новую **широту** (latitude), например: 41.281067",
        parse_mode="Markdown",
        reply_markup=builder.as_markup() if builder.buttons else None
    )
    await callback.answer()


@router.callback_query(F.data == "keep_current_coords")
async def keep_current_coordinates(callback: types.CallbackQuery, state: FSMContext):
    """Оставить текущие координаты без изменений"""
    await state.clear()
    await callback.message.edit_text("✅ Координаты оставлены без изменений.")
    await callback.message.answer(
        "Операция завершена.",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


@router.message(AdminSteps.edit_project_latitude, F.text == "◀️ Назад")
async def cancel_set_coordinates(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.edit_project_latitude, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_latitude_edit(message: types.Message, state: FSMContext):
    """Обработка широты для проекта"""
    try:
        latitude = float(message.text.replace(',', '.').strip())
        if not (-90 <= latitude <= 90):
            return await message.answer(
                "⚠️ Широта должна быть в диапазоне от -90 до 90. Попробуйте снова:",
                reply_markup=get_back_keyboard()
            )
        
        await state.update_data(latitude=str(latitude))
        await state.set_state(AdminSteps.edit_project_longitude)
        
        await message.answer(
            f"✅ Широта: {latitude}\n\n"
            f"Теперь введите **долготу** (longitude), например: 69.306903",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число (можно с десятичной точкой):",
            reply_markup=get_back_keyboard()
        )


@router.message(AdminSteps.edit_project_longitude, F.text == "◀️ Назад")
async def cancel_set_longitude(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=get_admin_keyboard())


@router.message(AdminSteps.edit_project_longitude, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_longitude_edit(message: types.Message, state: FSMContext):
    """Обработка долготы и сохранение координат"""
    try:
        longitude = float(message.text.replace(',', '.').strip())
        if not (-180 <= longitude <= 180):
            return await message.answer(
                "⚠️ Долгота должна быть в диапазоне от -180 до 180. Попробуйте снова:",
                reply_markup=get_back_keyboard()
            )
        
        user_data = await state.get_data()
        project_name = user_data.get('selected_project')
        latitude = user_data.get('latitude')
        
        with SessionLocal() as session:
            project_slot = session.query(ProjectSlots).filter_by(project_name=project_name).first()
            if project_slot:
                project_slot.latitude = latitude
                project_slot.longitude = str(longitude)
            else:
                session.add(ProjectSlots(
                    project_name=project_name,
                    slots_limit=1,
                    latitude=latitude,
                    longitude=str(longitude)
                ))
            session.commit()
        
        await state.clear()
        await message.answer(
            f"✅ Координаты для проекта **{project_name}** установлены:\n\n"
            f"🌍 Широта: {latitude}\n"
            f"🌍 Долгота: {longitude}",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число (можно с десятичной точкой):",
            reply_markup=get_back_keyboard()
        )


# ========== ОСТАЛЬНЫЕ КНОПКИ ==========

@router.message(F.text == "📊 Выгрузить отчет")
async def export_report_button(message: types.Message):
    """Выгрузить отчет через кнопку"""
    await export_report(message)


@router.message(F.text == "📋 Список записей")
async def show_bookings_list(message: types.Message, state: FSMContext):
    """Показать выбор проекта для просмотра записей"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]

    if not projects:
        return await message.answer("❌ В базе нет проектов.", reply_markup=get_admin_keyboard())

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for project in projects:
        builder.button(text=project, callback_data=f"bookings_{project[:40]}")
    builder.adjust(1)

    await state.set_state(AdminSteps.selecting_project_for_bookings)
    await message.answer(
        "📋 Выберите проект для просмотра записей:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("bookings_"))
async def show_bookings_for_project(callback: types.CallbackQuery, state: FSMContext):
    """Показать записи по выбранному проекту"""
    from datetime import date, timedelta

    project_name = callback.data.split("_", 1)[1]
    await state.clear()

    with SessionLocal() as session:
        today = date.today()
        week_later = today + timedelta(days=7)

        bookings = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(
                Booking.date >= today,
                Booking.date <= week_later,
                Booking.is_cancelled == False,
                Contract.house_name == project_name
            )
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )

        if not bookings:
            await callback.message.edit_text(
                f"📋 По проекту **{project_name}** записей на ближайшую неделю нет.",
                parse_mode="Markdown"
            )
            await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
            await callback.answer()
            return

        text = f"📋 **{project_name}** — записи на неделю:\n"
        current_date = None

        for booking, contract in bookings:
            if booking.date != current_date:
                current_date = booking.date
                text += f"\n📅 **{booking.date.strftime('%d.%m')}**\n"

            text += (
                f"{booking.time_slot.strftime('%H:%M')}"
                f" | кв.{contract.apt_num}"
                f" | {contract.contract_num}\n"
            )

    # Разбиваем на части если текст слишком длинный
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await callback.message.edit_text(text, parse_mode="Markdown")
    else:
        await callback.message.delete()
        # Отправляем частями
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

    await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
    await callback.answer()


@router.message(F.text == "🏠 Список проектов")
async def show_projects_list(message: types.Message):
    """Показать список всех проектов"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]
        
        if not projects:
            return await message.answer("❌ В базе нет проектов.", reply_markup=get_admin_keyboard())
        
        text = "🏠 **Список проектов:**\n\n"
        for idx, project in enumerate(sorted(projects), 1):
            # Считаем количество контрактов
            count = session.query(Contract).filter_by(house_name=project).count()
            text += f"{idx}. **{project}** — {count} договоров\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


# ==================== ДОБАВЛЕНИЕ НОВОГО ПРОЕКТА ====================

@router.message(F.text == "➕ Добавление проектов")
async def start_add_project(message: types.Message, state: FSMContext):
    """Начало процесса добавления нового проекта"""
    await state.set_state(AdminSteps.add_project_address_ru)
    await message.answer(
        "🏗️ **Добавление нового проекта**\n\n"
        "Введите адрес проекта на русском языке:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.add_project_address_ru, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_address_ru(message: types.Message, state: FSMContext):
    """Обработка адреса на русском"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    await state.update_data(address_ru=message.text)
    await state.set_state(AdminSteps.add_project_address_uz)
    await message.answer(
        "Введите адрес проекта на узбекском языке:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.add_project_address_uz, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_address_uz(message: types.Message, state: FSMContext):
    """Обработка адреса на узбекском"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    await state.update_data(address_uz=message.text)
    await state.set_state(AdminSteps.add_project_slots_limit)
    await message.answer(
        "Введите лимит слотов для проекта (целое число):\n\n"
        "Например: 2 — означает, что на каждый временной слот можно записать 2 клиента.",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminSteps.add_project_slots_limit, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_slots_limit(message: types.Message, state: FSMContext):
    """Обработка лимита слотов"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    try:
        slots_limit = int(message.text)
        if slots_limit < 1:
            return await message.answer("⚠️ Лимит должен быть больше 0. Попробуйте снова:")
        
        await state.update_data(slots_limit=slots_limit)
        await state.set_state(AdminSteps.add_project_latitude)
        
        # Создаём inline кнопку для использования стандартных координат
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="📍 Использовать стандартные координаты", callback_data="use_default_coords")
        builder.adjust(1)
        
        await message.answer(
            "📍 Введите широту (latitude) для геолокации проекта\n\n"
            "Например: 41.281067\n\n"
            "Или используйте стандартные координаты офиса:",
            reply_markup=builder.as_markup()
        )
    except ValueError:
        await message.answer("⚠️ Введите целое число:")


@router.callback_query(F.data == "use_default_coords")
async def use_default_coordinates(callback: types.CallbackQuery, state: FSMContext):
    """Использовать стандартные координаты офиса"""
    current_state = await state.get_state()
    
    # Проверяем в каком состоянии мы находимся
    if current_state == AdminSteps.add_project_latitude:
        # Используем стандартные координаты из client.py
        from handlers.client import OFFICE_LAT, OFFICE_LON
        await state.update_data(latitude=str(OFFICE_LAT), longitude=str(OFFICE_LON))
        await state.set_state(AdminSteps.add_project_excel)
        
        await callback.message.edit_text(
            f"✅ Установлены стандартные координаты офиса:\n"
            f"Широта: {OFFICE_LAT}\n"
            f"Долгота: {OFFICE_LON}"
        )
        
        await callback.message.answer(
            "Теперь отправьте Excel-файл с контрактами.\n\n"
            "Файл должен содержать первой строкой названия колонок ,в следующем порядке:\n"
            "• Название дома\n"
            "• Номер квартиры\n"
            "• Подъезд\n"
            "• Этаж\n"
            "• Номер договора\n"
            "• ФИО клиента\n"
            "• Дата сдачи",
            reply_markup=get_cancel_keyboard()
        )
    await callback.answer()


@router.message(AdminSteps.add_project_latitude, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_latitude(message: types.Message, state: FSMContext):
    """Обработка широты"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    try:
        latitude = float(message.text.replace(',', '.'))
        if not (-90 <= latitude <= 90):
            return await message.answer("⚠️ Широта должна быть в диапазоне от -90 до 90. Попробуйте снова:")
        
        await state.update_data(latitude=str(latitude))
        await state.set_state(AdminSteps.add_project_longitude)
        await message.answer(
            "📍 Введите долготу (longitude) для геолокации проекта\n\n"
            "Например: 69.306903",
            reply_markup=get_cancel_keyboard()
        )
    except ValueError:
        await message.answer("⚠️ Введите число (можно с десятичной точкой):")


@router.message(AdminSteps.add_project_longitude, ~F.text.in_(ADMIN_MENU_BUTTONS))
async def process_project_longitude(message: types.Message, state: FSMContext):
    """Обработка долготы"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    try:
        longitude = float(message.text.replace(',', '.'))
        if not (-180 <= longitude <= 180):
            return await message.answer("⚠️ Долгота должна быть в диапазоне от -180 до 180. Попробуйте снова:")
        
        await state.update_data(longitude=str(longitude))
        await state.set_state(AdminSteps.add_project_excel)
        await message.answer(
            "Теперь отправьте Excel-файл с контрактами.\n\n"
            "Файл должен содержать первой строкой названия колонок ,в следующем порядке:\n"
            "• Название дома\n"
            "• Номер квартиры\n"
            "• Подъезд\n"
            "• Этаж\n"
            "• Номер договора\n"
            "• ФИО клиента\n"
            "• Дата сдачи",
            reply_markup=get_cancel_keyboard()
        )
    except ValueError:
        await message.answer("⚠️ Введите число (можно с десятичной точкой):")


@router.message(AdminSteps.add_project_excel, F.document)
async def process_project_excel(message: types.Message, bot: Bot, state: FSMContext):
    """Обработка Excel файла для нового проекта"""
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return await message.answer("⚠️ Пожалуйста, отправьте файл в формате Excel (.xlsx или .xls)")
    
    # Отправляем сообщение о выполнении операции
    loading_msg = await message.answer("⏳ Пожалуйста подождите, идет обработка...")
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        address_ru = data['address_ru']
        address_uz = data['address_uz']
        slots_limit = data['slots_limit']
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        # Скачиваем файл
        file_path = f"data/temp_{message.document.file_name}"
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)
        
        # Обрабатываем файл с новыми параметрами
        count, project_name = process_excel_file(
            file_path, 
            address_ru=address_ru, 
            address_uz=address_uz, 
            slots_limit=slots_limit,
            latitude=latitude,
            longitude=longitude
        )
        
        # Удаляем временный файл
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Удаляем сообщение о загрузке
        await loading_msg.delete()
        
        # Отправляем результат
        coords_info = ""
        if latitude and longitude:
            coords_info = f"\n📍 Координаты: {latitude}, {longitude}"
        
        await message.answer(
            f"✅ **Проект успешно добавлен!**\n\n"
            f"🏠 Проект: {project_name}\n"
            f"📍 Адрес (RU): {address_ru}\n"
            f"📍 Адрес (UZ): {address_uz}\n"
            f"⚙️ Лимит слотов: {slots_limit}{coords_info}\n"
            f"📊 Загружено контрактов: {count}",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
        
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка при добавлении проекта: {e}")
        try:
            await loading_msg.delete()
        except:
            pass
        await message.answer(
            f"❌ Ошибка при обработке файла.\n\nТехническая ошибка: {e}",
            reply_markup=get_admin_keyboard()
        )
        await state.clear()


@router.message(AdminSteps.add_project_excel)
async def process_project_excel_wrong_type(message: types.Message, state: FSMContext):
    """Обработка неверного типа файла"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    await message.answer("⚠️ Пожалуйста, отправьте Excel файл (.xlsx или .xls)")
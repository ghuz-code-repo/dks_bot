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
from utils.excel_reader import process_excel_file, analyze_excel_changes, apply_contract_changes
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
    "📄 Изменить список договоров",
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
    elif text == "📄 Изменить список договоров":
        await start_update_contracts(message, state)
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


# ========== ИЗМЕНЕНИЕ СПИСКА ДОГОВОРОВ ==========

@router.message(F.text == "📄 Изменить список договоров")
async def start_update_contracts(message: types.Message, state: FSMContext):
    """Начало процесса изменения списка договоров"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = [h for h in projects if h]

        if not projects:
            return await message.answer(
                "❌ В базе нет проектов. Сначала загрузите контракты.",
                reply_markup=get_back_keyboard()
            )

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for project in projects:
            builder.button(text=project, callback_data=f"ucproj_{project[:40]}")
        builder.adjust(1)

        await state.set_state(AdminSteps.update_contracts_selecting_project)
        await message.answer(
            "📄 Изменение списка договоров\n\nВыберите проект:",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("ucproj_"), AdminSteps.update_contracts_selecting_project)
async def update_contracts_project_selected(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора проекта для обновления договоров"""
    project_name = callback.data.split("_", 1)[1]
    await state.update_data(uc_project=project_name)
    await state.set_state(AdminSteps.update_contracts_waiting_excel)

    await callback.message.edit_text(
        f"🏘 Проект: **{project_name}**\n\n"
        f"Отправьте Excel-файл с актуальными договорами.\n\n"
        f"Файл должен содержать столбцы:\n"
        f"• Название дома\n"
        f"• Номер квартиры\n"
        f"• Подъезд\n"
        f"• Этаж\n"
        f"• Номер договора\n"
        f"• ФИО клиента\n"
        f"• Дата сдачи",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminSteps.update_contracts_waiting_excel, F.document)
async def update_contracts_process_excel(message: types.Message, bot: Bot, state: FSMContext):
    """Обработка Excel файла для обновления договоров"""
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return await message.answer("⚠️ Пожалуйста, отправьте файл в формате Excel (.xlsx или .xls)")

    loading_msg = await message.answer("⏳ Анализ файла, подождите...")

    try:
        data = await state.get_data()
        project_name = data['uc_project']

        file_path = f"data/temp_update_{message.document.file_name}"
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)

        analysis = analyze_excel_changes(file_path, project_name)

        if os.path.exists(file_path):
            os.remove(file_path)

        await loading_msg.delete()

        new_count = len(analysis["new_contracts"])
        upd_count = len(analysis["updated_contracts"])
        chg_count = len(analysis["changed_contracts"])

        if new_count == 0 and upd_count == 0 and chg_count == 0:
            await state.clear()
            return await message.answer(
                f"📄 Анализ файла для проекта **{project_name}**:\n\n"
                f"✅ Изменений не обнаружено. Все данные в базе актуальны.",
                parse_mode="Markdown",
                reply_markup=get_admin_keyboard()
            )

        # Формируем отчёт
        text = f"📄 Анализ файла для проекта **{project_name}**:\n\n"

        if new_count > 0:
            text += f"🆕 Новых квартир: {new_count}\n"
        if upd_count > 0:
            text += f"✏️ Обновлённых записей: {upd_count}\n"
        if chg_count > 0:
            total_bookings = sum(c["active_bookings_count"] for c in analysis["changed_contracts"])
            text += f"⚠️ Смена договора: {chg_count}\n"
            for c in analysis["changed_contracts"][:10]:
                bk_info = f", записей: {c['active_bookings_count']}" if c['active_bookings_count'] > 0 else ""
                text += f"   • Кв. {c['apt_num']} — {c['old_contract_num']} → {c['new_contract_num']}{bk_info}\n"
            if chg_count > 10:
                text += f"   ... и ещё {chg_count - 10}\n"
            if total_bookings > 0:
                text += f"\n❗ При смене договора будет аннулировано {total_bookings} записей\n"

        text += "\nВыберите действия для применения:"

        await state.update_data(uc_analysis=analysis, uc_selected=[])
        await state.set_state(AdminSteps.update_contracts_confirming)

        builder = _build_update_contracts_keyboard(analysis)
        await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Ошибка при анализе файла: {e}")
        try:
            await loading_msg.delete()
        except:
            pass
        await message.answer(
            f"❌ Ошибка при обработке файла.\n\n"
            f"Техническая ошибка: {e}\n\n"
            "Отправьте корректный файл или нажмите «❌ Отменить».",
            reply_markup=get_cancel_keyboard()
        )


@router.message(AdminSteps.update_contracts_waiting_excel)
async def update_contracts_wrong_type(message: types.Message, state: FSMContext):
    """Обработка неверного типа сообщения при ожидании файла"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Операция отменена.", reply_markup=get_admin_keyboard())
    await message.answer("⚠️ Пожалуйста, отправьте Excel файл (.xlsx или .xls)")


def _build_update_contracts_keyboard(analysis, selected=None):
    """Клавиатура мультивыбора для подтверждения изменений договоров."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()

    builder = InlineKeyboardBuilder()
    options = []

    if analysis["new_contracts"]:
        count = len(analysis["new_contracts"])
        options.append(("add", f"Подтвердить добавление ({count})"))
    if analysis["updated_contracts"]:
        count = len(analysis["updated_contracts"])
        options.append(("update", f"Подтвердить обновление ({count})"))
    for key, label in options:
        prefix = "✅" if key in selected else "☐"
        builder.button(text=f"{prefix} {label}", callback_data=f"ucsel_{key}")

    # Смена договоров — два взаимоисключающих варианта (радиокнопки)
    change_options = []
    if analysis["changed_contracts"]:
        count = len(analysis["changed_contracts"])
        change_options.append(("change_notify", f"Смена договоров с уведомлением ({count})"))
        change_options.append(("change_silent", f"Смена договоров без уведомления ({count})"))

    for key, label in change_options:
        prefix = "🔘" if key in selected else "○"
        builder.button(text=f"{prefix} {label}", callback_data=f"ucsel_{key}")

    total_options = len(options) + len(change_options)
    if selected:
        builder.button(text="▶️ Продолжить", callback_data="uc_proceed")
    else:
        builder.button(text="▫️ Выберите действие", callback_data="uc_noop")
    builder.button(text="❌ Отменить", callback_data="uc_cancel")

    rows = [1] * total_options + [2]
    builder.adjust(*rows)
    return builder


@router.callback_query(F.data.startswith("ucsel_"), AdminSteps.update_contracts_confirming)
async def update_contracts_toggle(callback: types.CallbackQuery, state: FSMContext):
    """Toggle выбора действия для обновления договоров"""
    action = callback.data.split("_", 1)[1]
    data = await state.get_data()
    selected = set(data.get("uc_selected", []))
    analysis = data["uc_analysis"]

    # change_notify и change_silent — взаимоисключающие (радиокнопки)
    if action in ("change_notify", "change_silent"):
        other = "change_silent" if action == "change_notify" else "change_notify"
        selected.discard(other)
        if action in selected:
            selected.discard(action)
        else:
            selected.add(action)
    else:
        if action in selected:
            selected.discard(action)
        else:
            selected.add(action)

    await state.update_data(uc_selected=list(selected))
    builder = _build_update_contracts_keyboard(analysis, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "uc_noop", AdminSteps.update_contracts_confirming)
async def update_contracts_noop(callback: types.CallbackQuery):
    """Кнопка-заглушка когда ничего не выбрано"""
    await callback.answer("Выберите хотя бы одно действие", show_alert=False)


@router.callback_query(F.data == "uc_cancel", AdminSteps.update_contracts_confirming)
async def update_contracts_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена обновления договоров"""
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "uc_proceed", AdminSteps.update_contracts_confirming)
async def update_contracts_proceed(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Применение выбранных изменений"""
    data = await state.get_data()
    selected = set(data.get("uc_selected", []))
    analysis = data["uc_analysis"]

    await callback.message.edit_text("⏳ Применение изменений...")

    try:
        apply_changed = "change_notify" in selected or "change_silent" in selected
        send_notifications = "change_notify" in selected

        result = apply_contract_changes(
            analysis,
            apply_new="add" in selected,
            apply_updates="update" in selected,
            apply_changed=apply_changed,
        )

        # Отправляем уведомления клиентам (только если выбрано "с уведомлением")
        notification_count = 0
        if not send_notifications:
            result["notifications"] = []
        for telegram_id in result["notifications"]:
            try:
                await bot.send_message(
                    telegram_id,
                    "⚠️ Ваша запись была аннулирована в связи с изменением номера договора.\n"
                    "Для повторной записи воспользуйтесь меню «📝 Первичная запись»."
                )
                notification_count += 1
            except Exception as e:
                logging.error(f"Ошибка отправки уведомления {telegram_id}: {e}")

        # Формируем итоговое сообщение
        text = "✅ Изменения применены:\n\n"
        if result["added"] > 0:
            text += f"🆕 Добавлено квартир: {result['added']}\n"
        if result["updated"] > 0:
            text += f"✏️ Обновлено записей: {result['updated']}\n"
        if result["contracts_changed"] > 0:
            text += f"🔄 Договоров изменено: {result['contracts_changed']}\n"
        if result["bookings_cancelled"] > 0:
            text += f"🚫 Записей аннулировано: {result['bookings_cancelled']}\n"
        if notification_count > 0:
            text += f"📨 Уведомлений отправлено: {notification_count}\n"

        await state.clear()
        await callback.message.edit_text(text)
        await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())

    except Exception as e:
        logging.error(f"Ошибка применения изменений: {e}")
        await state.clear()
        await callback.message.edit_text(f"❌ Ошибка при применении изменений: {e}")
        await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())

    await callback.answer()


# ========== ОСТАЛЬНЫЕ КНОПКИ ==========

@router.message(F.text == "📊 Выгрузить отчет")
async def export_report_button(message: types.Message):
    """Выгрузить отчет через кнопку"""
    await export_report(message)


@router.message(F.text == "📋 Список записей")
async def show_bookings_list(message: types.Message, state: FSMContext):
    """Показать выбор проекта для просмотра записей (мультивыбор)"""
    with SessionLocal() as session:
        projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        projects = sorted([h for h in projects if h])

    if not projects:
        return await message.answer("❌ В базе нет проектов.", reply_markup=get_admin_keyboard())

    await state.update_data(bk_all_projects=projects, bk_selected_projects=[])
    builder = _build_projects_keyboard(projects)
    await state.set_state(AdminSteps.selecting_project_for_bookings)
    await message.answer(
        "📋 Выберите проекты для просмотра записей (можно несколько):",
        reply_markup=builder.as_markup()
    )


def _build_projects_keyboard(projects, selected=None):
    """Построить клавиатуру мультивыбора проектов."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()
    builder = InlineKeyboardBuilder()
    for project in projects:
        label = project
        if project in selected:
            label = "✅ " + label
        builder.button(text=label, callback_data=f"bkproj_{project[:40]}")
    # Нижний ряд
    if selected:
        builder.button(text="✅ Подтвердить выбор", callback_data="bkproj_confirm")
    else:
        builder.button(text="▫️ Выберите проект", callback_data="bkproj_noop")
    builder.button(text="⏩ Все проекты", callback_data="bkproj_skip")
    rows = [1] * len(projects)
    builder.adjust(*rows, 2)
    return builder


def _get_booking_weeks(session, project_names=None):
    """Получить список недель, на которые есть активные записи."""
    from datetime import date, timedelta
    today = date.today()
    query = (
        session.query(Booking.date)
        .join(Contract, Booking.contract_id == Contract.id)
        .filter(Booking.date >= today, Booking.is_cancelled == False)
    )
    if project_names:
        if isinstance(project_names, str):
            query = query.filter(Contract.house_name == project_names)
        else:
            query = query.filter(Contract.house_name.in_(project_names))
    dates = sorted(set(d[0] for d in query.all()))
    if not dates:
        return []
    # Группируем по неделям (пн–вс)
    weeks = []
    seen = set()
    for d in dates:
        week_start = d - timedelta(days=d.weekday())  # Понедельник
        if week_start in seen:
            continue
        seen.add(week_start)
        week_end = week_start + timedelta(days=6)
        weeks.append((week_start, week_end))
    return weeks


def _build_weeks_keyboard(weeks, selected=None):
    """Построить клавиатуру выбора недель с мультивыбором."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()
    builder = InlineKeyboardBuilder()
    for ws, we in weeks:
        label = f"{ws.strftime('%d.%m')}-{we.strftime('%d.%m')}"
        key = ws.isoformat()
        if key in selected:
            label = "✅ " + label
        builder.button(text=label, callback_data=f"bkweek_{key}")
    # Нижний ряд: подтвердить + пропустить (всегда 2 кнопки)
    if selected:
        builder.button(text="✅ Подтвердить выбор", callback_data="bkweek_confirm")
    else:
        builder.button(text="▫️ Выберите неделю", callback_data="bkweek_noop")
    builder.button(text="⏩ Пропустить", callback_data="bkweek_skip")
    # Кнопки недель по 2, последние 2 — управление (всегда отдельный ряд)
    week_rows = [2] * (len(weeks) // 2)
    if len(weeks) % 2:
        week_rows.append(1)
    builder.adjust(*week_rows, 2)
    return builder


@router.callback_query(F.data.startswith("bkproj_"), AdminSteps.selecting_project_for_bookings)
async def on_project_toggled(callback: types.CallbackQuery, state: FSMContext):
    """Мультивыбор проектов: toggle / confirm / skip / noop."""
    action = callback.data.split("_", 1)[1]

    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    all_projects = data.get("bk_all_projects", [])
    selected = set(data.get("bk_selected_projects", []))

    if action == "skip":
        # Все проекты
        await state.update_data(bk_projects=None, bk_selected_weeks=[], bk_date_from=None, bk_date_to=None)
        await _proceed_to_weeks(callback, state, project_names=None)
        return

    if action == "confirm":
        selected_list = sorted(selected)
        await state.update_data(bk_projects=selected_list, bk_selected_weeks=[], bk_date_from=None, bk_date_to=None)
        await _proceed_to_weeks(callback, state, project_names=selected_list)
        return

    # Toggle конкретного проекта
    project_key = action
    # Находим полное имя проекта по усечённому callback_data
    matched = [p for p in all_projects if p[:40] == project_key]
    full_name = matched[0] if matched else project_key
    if full_name in selected:
        selected.discard(full_name)
    else:
        selected.add(full_name)

    await state.update_data(bk_selected_projects=list(selected))
    builder = _build_projects_keyboard(all_projects, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


async def _proceed_to_weeks(callback, state, project_names):
    """После выбора проектов — показать выбор недель."""
    with SessionLocal() as session:
        weeks = _get_booking_weeks(session, project_names)

    if not weeks:
        if project_names:
            label = "проектам: **" + ", ".join(project_names) + "**"
        else:
            label = "всем проектам"
        await callback.message.edit_text(f"📋 По {label} активных записей нет.", parse_mode="Markdown")
        await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
        await state.clear()
        await callback.answer()
        return

    builder = _build_weeks_keyboard(weeks)
    await state.set_state(AdminSteps.selecting_weeks_for_bookings)
    await callback.message.edit_text(
        "📅 Выберите недели для просмотра (можно несколько):",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bkweek_"), AdminSteps.selecting_weeks_for_bookings)
async def on_week_toggled(callback: types.CallbackQuery, state: FSMContext):
    """Мультивыбор недель: toggle / confirm / skip / noop."""
    action = callback.data.split("_", 1)[1]

    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    project_names = data.get("bk_projects")
    selected = set(data.get("bk_selected_weeks", []))

    if action == "skip":
        # Пропустить — показать все записи без фильтра по дате
        await state.update_data(bk_selected_weeks=[], bk_date_from=None, bk_date_to=None)
        await _show_filtered_bookings(callback, state)
        return

    if action == "confirm":
        selected_list = sorted(selected)
        if len(selected_list) == 1:
            # Ровно одна неделя — предложить выбор дня
            from datetime import date as dt_date, timedelta
            ws = dt_date.fromisoformat(selected_list[0])
            we = ws + timedelta(days=6)
            await state.update_data(bk_selected_weeks=selected_list)
            await _show_day_selection(callback, state, ws, we, project_names)
            return
        else:
            # Несколько недель — сразу показать записи
            from datetime import date as dt_date, timedelta
            all_starts = [dt_date.fromisoformat(s) for s in selected_list]
            date_from = min(all_starts)
            date_to = max(all_starts) + timedelta(days=6)
            await state.update_data(bk_selected_weeks=selected_list, bk_date_from=date_from.isoformat(), bk_date_to=date_to.isoformat())
            await _show_filtered_bookings(callback, state)
            return

    # Toggle конкретной недели
    week_key = action
    if week_key in selected:
        selected.discard(week_key)
    else:
        selected.add(week_key)

    await state.update_data(bk_selected_weeks=list(selected))

    # Перерисовываем клавиатуру
    with SessionLocal() as session:
        weeks = _get_booking_weeks(session, project_names)
    builder = _build_weeks_keyboard(weeks, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


def _build_days_keyboard(booking_dates, selected=None):
    """Построить клавиатуру мультивыбора дней."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    if selected is None:
        selected = set()
    builder = InlineKeyboardBuilder()
    for d in booking_dates:
        label = d.strftime('%d.%m.%Y')
        key = d.isoformat()
        if key in selected:
            label = "✅ " + label
        builder.button(text=label, callback_data=f"bkday_{key}")
    # Нижний ряд: подтвердить + пропустить (всегда 2 кнопки)
    if selected:
        builder.button(text="✅ Подтвердить выбор", callback_data="bkday_confirm")
    else:
        builder.button(text="▫️ Выберите день", callback_data="bkday_noop")
    builder.button(text="⏩ Пропустить (вся неделя)", callback_data="bkday_skip")
    day_rows = [2] * (len(booking_dates) // 2)
    if len(booking_dates) % 2:
        day_rows.append(1)
    builder.adjust(*day_rows, 2)
    return builder


def _get_booking_dates_in_week(session, week_start, week_end, project_names=None):
    """Получить даты с записями внутри недели."""
    from datetime import date as dt_date
    today = dt_date.today()
    query = (
        session.query(Booking.date)
        .join(Contract, Booking.contract_id == Contract.id)
        .filter(
            Booking.date >= max(week_start, today),
            Booking.date <= week_end,
            Booking.is_cancelled == False,
        )
    )
    if project_names:
        if isinstance(project_names, str):
            query = query.filter(Contract.house_name == project_names)
        else:
            query = query.filter(Contract.house_name.in_(project_names))
    return sorted(set(d[0] for d in query.all()))


async def _show_day_selection(callback, state, week_start, week_end, project_names):
    """Показать выбор конкретных дней внутри недели (мультивыбор)."""
    with SessionLocal() as session:
        booking_dates = _get_booking_dates_in_week(session, week_start, week_end, project_names)

    if not booking_dates:
        await state.update_data(bk_date_from=week_start.isoformat(), bk_date_to=week_end.isoformat())
        await _show_filtered_bookings(callback, state)
        return

    await state.update_data(bk_selected_days=[])
    builder = _build_days_keyboard(booking_dates)

    await state.set_state(AdminSteps.selecting_day_for_bookings)
    await callback.message.edit_text(
        f"📅 Выберите дни ({week_start.strftime('%d.%m')}-{week_end.strftime('%d.%m')}), можно несколько:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bkday_"), AdminSteps.selecting_day_for_bookings)
async def on_day_selected(callback: types.CallbackQuery, state: FSMContext):
    """Мультивыбор дней: toggle / confirm / skip / noop."""
    from datetime import date as dt_date, timedelta
    action = callback.data.split("_", 1)[1]

    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    project_names = data.get("bk_projects")
    selected = set(data.get("bk_selected_days", []))
    selected_weeks = data.get("bk_selected_weeks", [])

    if action == "skip":
        # Показать всю выбранную неделю
        if selected_weeks:
            ws = dt_date.fromisoformat(selected_weeks[0])
            we = ws + timedelta(days=6)
            await state.update_data(bk_date_from=ws.isoformat(), bk_date_to=we.isoformat(), bk_dates=None)
        await _show_filtered_bookings(callback, state)
        return

    if action == "confirm":
        # Подтвердить выбранные дни
        await state.update_data(bk_dates=sorted(selected), bk_date_from=None, bk_date_to=None)
        await _show_filtered_bookings(callback, state)
        return

    # Toggle конкретного дня
    day_key = action
    if day_key in selected:
        selected.discard(day_key)
    else:
        selected.add(day_key)

    await state.update_data(bk_selected_days=list(selected))

    # Перерисовываем клавиатуру
    if selected_weeks:
        ws = dt_date.fromisoformat(selected_weeks[0])
        we = ws + timedelta(days=6)
    else:
        ws = dt_date.today()
        we = ws + timedelta(days=6)

    with SessionLocal() as session:
        booking_dates = _get_booking_dates_in_week(session, ws, we, project_names)
    builder = _build_days_keyboard(booking_dates, selected)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


async def _show_filtered_bookings(callback: types.CallbackQuery, state: FSMContext):
    """Показать отфильтрованные записи — по одному сообщению на каждый проект."""
    from datetime import date as dt_date
    from collections import defaultdict

    data = await state.get_data()
    project_names = data.get("bk_projects")  # list или None (все)
    date_from_str = data.get("bk_date_from")
    date_to_str = data.get("bk_date_to")
    bk_dates = data.get("bk_dates")  # Список конкретных дат (ISO)
    await state.clear()

    with SessionLocal() as session:
        today = dt_date.today()
        query = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(Booking.is_cancelled == False)
        )

        if project_names:
            query = query.filter(Contract.house_name.in_(project_names))

        if bk_dates:
            date_objects = [dt_date.fromisoformat(d) for d in bk_dates]
            query = query.filter(Booking.date.in_(date_objects), Booking.date >= today)
        elif date_from_str and date_to_str:
            date_from = dt_date.fromisoformat(date_from_str)
            date_to = dt_date.fromisoformat(date_to_str)
            query = query.filter(Booking.date >= max(date_from, today), Booking.date <= date_to)
        else:
            query = query.filter(Booking.date >= today)

        bookings = query.all()

        if not bookings:
            if project_names:
                label = "проектам: **" + ", ".join(project_names) + "**"
            else:
                label = "всем проектам"
            await callback.message.edit_text(f"📋 По {label} записей не найдено.", parse_mode="Markdown")
            await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
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

        # Группируем по проектам
        projects_data = defaultdict(list)
        for booking, contract in bookings:
            projects_data[contract.house_name].append((booking, contract))

    # Удаляем исходное сообщение с кнопками
    try:
        await callback.message.delete()
    except:
        pass

    # Отправляем по одному сообщению на каждый проект
    for project_name in sorted(projects_data.keys()):
        project_bookings = projects_data[project_name]
        text = _format_project_bookings(project_name, project_bookings, first_booking_ids)
        await _send_long_message(callback.message, text)

    await callback.message.answer("Главное меню:", reply_markup=get_admin_keyboard())
    await callback.answer()


def _pluralize_records(n: int) -> str:
    """Склонение слова 'запись': 1 запись, 2 записи, 5 записей."""
    if 11 <= n % 100 <= 19:
        return "записей"
    last = n % 10
    if last == 1:
        return "запись"
    if 2 <= last <= 4:
        return "записи"
    return "записей"


def _format_project_bookings(project_name: str, bookings: list, first_booking_ids: set = None) -> str:
    """Форматирует записи одного проекта.
    
    Формат:
    📋 **Проект**
    
    📅 **ДД.ММ** (N записей)
      🕐 **ЧЧ:ММ** (M)
        Подъезд X, этаж Y, кв. Z — Договор
    
    Итого: K записей
    """
    from collections import defaultdict
    if first_booking_ids is None:
        first_booking_ids = set()

    total_count = len(bookings)

    # Группируем: дата → время → список записей
    dates_dict = defaultdict(lambda: defaultdict(list))
    for booking, contract in bookings:
        dates_dict[booking.date][booking.time_slot].append((booking, contract))

    text = f"📋 **{project_name}**\n"

    for bk_date in sorted(dates_dict.keys()):
        time_slots = dates_dict[bk_date]
        day_count = sum(len(items) for items in time_slots.values())
        text += f"\n📅 **{bk_date.strftime('%d.%m.%Y')}** ( {day_count} {_pluralize_records(day_count)} )\n"

        for time_slot in sorted(time_slots.keys()):
            items = time_slots[time_slot]
            slot_count = len(items)
            text += f"  🕐 **{time_slot.strftime('%H:%M')}** ( {slot_count} {_pluralize_records(slot_count)} )\n"

            # Сортируем по подъезду, этажу, квартире
            def _sort_key(item):
                _, c = item
                try:
                    entrance = int(c.entrance) if c.entrance else 0
                except (ValueError, TypeError):
                    entrance = 0
                floor = c.floor if c.floor is not None else 0
                try:
                    apt = int(c.apt_num) if c.apt_num else 0
                except (ValueError, TypeError):
                    apt = 0
                return (entrance, floor, apt)

            for booking, contract in sorted(items, key=_sort_key):
                entrance_str = f"подъезд {contract.entrance}" if contract.entrance else "—"
                floor_str = f"этаж {contract.floor}" if contract.floor is not None else "—"
                apt_str = f"кв. {contract.apt_num}" if contract.apt_num else "—"
                repeat_str = " _(повторная)_" if booking.id not in first_booking_ids else ""
                text += f"    {entrance_str}, {floor_str}, {apt_str} — {contract.contract_num}{repeat_str}\n"

    text += f"\n📊 Итого по проекту: **{total_count}** записей\n"
    return text


async def _send_long_message(message, text: str, max_len: int = 4000):
    """Отправить длинное сообщение, разбив на части при необходимости."""
    if len(text) <= max_len:
        await message.answer(text, parse_mode="Markdown")
    else:
        parts = []
        current_part = ""
        for line in text.split("\n"):
            if len(current_part) + len(line) + 1 > max_len:
                parts.append(current_part)
                current_part = line + "\n"
            else:
                current_part += line + "\n"
        if current_part.strip():
            parts.append(current_part)
        for part in parts:
            await message.answer(part, parse_mode="Markdown")


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
            f"❌ Ошибка при обработке файла.\n\n"
            f"Техническая ошибка: {e}\n\n"
            "Пожалуйста, отправьте корректный Excel-файл повторно или нажмите «❌ Отменить».",
            reply_markup=get_cancel_keyboard()
        )


@router.message(AdminSteps.add_project_excel)
async def process_project_excel_wrong_type(message: types.Message, state: FSMContext):
    """Обработка неверного типа файла"""
    if message.text == "❌ Отменить":
        await state.clear()
        return await message.answer("❌ Добавление проекта отменено.", reply_markup=get_admin_keyboard())
    
    await message.answer("⚠️ Пожалуйста, отправьте Excel файл (.xlsx или .xls)")
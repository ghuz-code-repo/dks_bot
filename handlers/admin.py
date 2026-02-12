import logging
import os
from datetime import datetime
from utils.auth import is_admin, is_staff
import pandas as pd
from aiogram import Bot
from aiogram import Router, F, types
from aiogram.filters import Command
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
    async def __call__(self, message: types.Message) -> bool:
        return is_admin(message.from_user.id)


router.message.filter(IsAdminFilter())  # Применяем ко всему роутеру


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
@router.message(F.document, F.from_user.id == ADMIN_ID)
async def handle_excel_upload(message: types.Message, bot: Bot, state: FSMContext):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return await message.answer("⚠️ Пожалуйста, отправьте файл в формате Excel (.xlsx)", reply_markup=get_admin_keyboard())

    try:
        await state.clear()
        file_path = f"data/temp_{message.document.file_name}"
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)

        count = process_excel_file(file_path)

        if os.path.exists(file_path):
            os.remove(file_path)

        await message.answer(f"✅ База обновлена успешно!\nЗагружено/обновлено записей: {count}", reply_markup=get_admin_keyboard())

    except Exception as e:
        logging.error(f"Ошибка при загрузке Excel: {e}")
        await message.answer(f"❌ Ошибка при чтении файла.\nТехническая ошибка: {e}", reply_markup=get_admin_keyboard())


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
            .order_by(Booking.date.desc(), Booking.time_slot.desc())
        )

        results = session.execute(query).all()

        if not results:
            return await message.answer("Записи в базе данных отсутствуют.")

        # Преобразование в DataFrame с обновленными колонками
        df = pd.DataFrame(results, columns=[
            "Дата визита", "Время", "ФИО Клиента", "Телефон клиента",
            "Договор", "Дом", "Подъезд", "Кв"
        ])

        # Форматирование времени для Excel
        df['Время'] = df['Время'].apply(lambda x: x.strftime('%H:%M') if x else "")

        report_path = "data/bookings_report.xlsx"
        df.to_excel(report_path, index=False)

    await message.answer_document(
        FSInputFile(report_path),
        caption=f"Отчет о записях на {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    os.remove(report_path)


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


@router.message(AdminSteps.waiting_for_admin_id)
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


@router.message(AdminSteps.waiting_for_employee_id)
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


@router.message(AdminSteps.waiting_for_staff_id_to_delete)
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

@router.message(F.text == "⚙️ Настройки слотов")
async def slots_management_menu(message: types.Message):
    """Меню управления слотами"""
    await message.answer(
        "⚙️ Настройки слотов\n\nВыберите действие:",
        reply_markup=get_slots_management_keyboard()
    )


@router.message(F.text == "📝 Установить лимит для проекта")
async def start_set_project_slots(message: types.Message, state: FSMContext):
    """Начало установки лимита слотов для проекта"""
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


@router.callback_query(F.data.startswith("setslot_"), AdminSteps.selecting_project_for_slots)
async def project_selected_for_slots(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора проекта для установки лимита"""
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


@router.message(AdminSteps.waiting_for_slot_limit)
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


@router.message(F.text == "📊 Текущие лимиты проектов")
async def show_project_slots(message: types.Message):
    """Показать текущие лимиты слотов по проектам"""
    with SessionLocal() as session:
        # Получаем все проекты
        all_projects = session.execute(select(Contract.house_name).distinct()).scalars().all()
        all_projects = [h for h in all_projects if h]
        
        if not all_projects:
            return await message.answer("❌ В базе нет проектов.", reply_markup=get_admin_keyboard())
        
        # Получаем настроенные лимиты
        project_slots = session.query(ProjectSlots).all()
        slots_dict = {ps.project_name: ps.slots_limit for ps in project_slots}
        
        # Глобальный лимит
        global_setting = session.query(Setting).filter_by(key='slots_per_interval').first()
        global_limit = global_setting.value if global_setting else 1
        
        text = "📊 **Лимиты слотов по проектам:**\n\n"
        text += f"🌐 Глобальный лимит (по умолчанию): {global_limit}\n\n"
        
        for project in sorted(all_projects):
            limit = slots_dict.get(project, "не установлен (используется глобальный)")
            text += f"🏘 **{project}**\n   └ Лимит: {limit}\n\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


# ========== ОСТАЛЬНЫЕ КНОПКИ ==========

@router.message(F.text == "📊 Выгрузить отчет")
async def export_report_button(message: types.Message):
    """Выгрузить отчет через кнопку"""
    await export_report(message)


@router.message(F.text == "📋 Список записей")
async def show_bookings_list(message: types.Message):
    """Показать список ближайших записей"""
    from datetime import date, timedelta
    
    with SessionLocal() as session:
        today = date.today()
        week_later = today + timedelta(days=7)
        
        bookings = (
            session.query(Booking, Contract)
            .join(Contract, Booking.contract_id == Contract.id)
            .filter(Booking.date >= today, Booking.date <= week_later)
            .order_by(Booking.date, Booking.time_slot)
            .all()
        )
        
        if not bookings:
            return await message.answer("📋 На ближайшую неделю записей нет.", reply_markup=get_admin_keyboard())
        
        text = "📋 **Записи на ближайшую неделю:**\n\n"
        current_date = None
        
        for booking, contract in bookings:
            if booking.date != current_date:
                current_date = booking.date
                text += f"\n📅 **{booking.date.strftime('%d.%m.%Y')}**\n"
            
            text += (
                f"🕐 {booking.time_slot.strftime('%H:%M')} — "
                f"{contract.client_fio} ({contract.house_name}, кв.{contract.apt_num})\n"
            )
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())


@router.message(F.text == "📤 Загрузить Excel")
async def request_excel_upload(message: types.Message):
    """Запрос на загрузку Excel"""
    await message.answer(
        "📤 Отправьте Excel-файл с контрактами для загрузки в базу.\n\n"
        "Файл должен содержать колонки:\n"
        "• Название дома\n"
        "• Номер квартиры\n"
        "• Подъезд\n"
        "• Этаж\n"
        "• Номер договора\n"
        "• ФИО клиента\n"
        "• Дата сдачи объекта",
        reply_markup=get_admin_keyboard()
    )


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
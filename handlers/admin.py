import logging
import os
from datetime import datetime
from utils.auth import is_admin
import pandas as pd
from aiogram import Bot
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from sqlalchemy import select
from database.models import Staff
from aiogram.filters import BaseFilter
from config import ADMIN_ID
from database.models import Booking, Contract
from database.models import Setting
from database.session import SessionLocal
from utils.excel_reader import process_excel_file

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
        await message.answer(f"✅ Пользователь {new_id} теперь администратор.")
    except (IndexError, ValueError):
        await message.answer("Использование: `/add_admin [ID]`")


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
        await message.answer(f"✅ Пользователь {new_id} добавлен как сотрудник.")
    except (IndexError, ValueError):
        await message.answer("Использование: `/add_employee [ID]`")


@router.message(Command("staff_list"))
async def list_staff(message: types.Message):
    with SessionLocal() as session:
        staff_members = session.query(Staff).all()
        if not staff_members:
            return await message.answer("Список персонала пуст.")

        text = "👥 **Персонал в базе:**\n"
        for s in staff_members:
            text += f"• `{s.telegram_id}` — {s.role}\n"
        await message.answer(text, parse_mode="Markdown")
@router.message(F.document, F.from_user.id == ADMIN_ID)
async def handle_excel_upload(message: types.Message, bot: Bot, state: FSMContext):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return await message.answer("⚠️ Пожалуйста, отправьте файл в формате Excel (.xlsx)")

    try:
        await state.clear()
        file_path = f"data/temp_{message.document.file_name}"
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)

        count = process_excel_file(file_path)

        if os.path.exists(file_path):
            os.remove(file_path)

        await message.answer(f"✅ База обновлена успешно!\nЗагружено/обновлено записей: {count}")

    except Exception as e:
        logging.error(f"Ошибка при загрузке Excel: {e}")
        await message.answer(f"❌ Ошибка при чтении файла.\nТехническая ошибка: {e}")


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
        await message.answer(f"Лимит одновременных записей установлен на: {val}")
    except (IndexError, ValueError):
        await message.answer("Использование: /set_slots [число]")

@router.message(Command("del_staff"))
async def remove_staff_cmd(message: types.Message):
    try:
        target_id = int(message.text.split()[1])
        with SessionLocal() as session:
            staff = session.query(Staff).filter_by(telegram_id=target_id).first()
            if staff:
                session.delete(staff)
                session.commit()
                await message.answer(f"❌ Пользователь {target_id} удален из списка персонала.")
            else:
                await message.answer("Пользователь не найден в базе.")
    except (IndexError, ValueError):
        await message.answer("Использование: `/del_staff [ID]`")

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
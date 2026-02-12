"""Обработчики для сотрудников (не администраторов)"""
import os
from datetime import datetime, date, timedelta
import pandas as pd
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.filters import BaseFilter
from sqlalchemy import select
from database.models import Booking, Contract
from database.session import SessionLocal
from keyboards.reply import get_employee_keyboard
from utils.auth import is_staff

router = Router()


class IsStaffFilter(BaseFilter):
    """Фильтр для сотрудников (не админов)"""
    async def __call__(self, message: types.Message) -> bool:
        from utils.auth import is_admin
        # Только сотрудники, но не админы
        return is_staff(message.from_user.id) and not is_admin(message.from_user.id)


# Применяем фильтр ко всему роутеру
router.message.filter(IsStaffFilter())


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
            .order_by(Booking.date.desc(), Booking.time_slot.desc())
        )

        results = session.execute(query).all()

        if not results:
            return await message.answer("Записи в базе данных отсутствуют.", reply_markup=get_employee_keyboard())

        df = pd.DataFrame(results, columns=[
            "Дата визита", "Время", "ФИО Клиента", "Телефон клиента",
            "Договор", "Дом", "Подъезд", "Кв"
        ])

        df['Время'] = df['Время'].apply(lambda x: x.strftime('%H:%M') if x else "")

        report_path = "data/bookings_report.xlsx"
        df.to_excel(report_path, index=False)

    await message.answer_document(
        FSInputFile(report_path),
        caption=f"Отчет о записях на {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    os.remove(report_path)


@router.message(F.text == "📋 Список записей")
async def show_bookings_list_employee(message: types.Message):
    """Показать список ближайших записей (для сотрудников)"""
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
            return await message.answer("📋 На ближайшую неделю записей нет.", reply_markup=get_employee_keyboard())
        
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
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_employee_keyboard())


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

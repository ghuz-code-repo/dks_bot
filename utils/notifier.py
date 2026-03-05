import logging
import asyncio
from datetime import datetime, timedelta
from database.session import SessionLocal
from database.models import Booking, Contract, ProjectSlots, UserLanguage
from aiogram import Bot
from utils.language import get_message


def _get_address(session, house_name: str, lang: str) -> str:
    project = session.query(ProjectSlots).filter(
        ProjectSlots.project_name == house_name
    ).first()
    if project:
        return project.address_uz if lang == 'uz' else project.address_ru
    return ''


def _get_lang(session, telegram_id: int) -> str:
    user_lang = session.query(UserLanguage).filter(
        UserLanguage.telegram_id == telegram_id
    ).first()
    return user_lang.language if user_lang else 'ru'


async def check_reminders(bot: Bot):
    now = datetime.now()
    today = now.date()

    with SessionLocal() as session:
        # 1. Напоминание за день до визита
        tomorrow = today + timedelta(days=1)
        day_bookings = session.query(Booking).filter(
            Booking.date == tomorrow,
            Booking.reminder_day_sent == False
        ).all()

        async def send_day_reminder(telegram_id, message_text):
            try:
                await bot.send_message(telegram_id, message_text)
                return True
            except Exception as e:
                logging.error(f"Ошибка напоминания за день: {e}")
                return False

        day_tasks = []
        for b in day_bookings:
            contract = session.query(Contract).get(b.contract_id)
            if contract.telegram_id:
                lang = _get_lang(session, contract.telegram_id)
                address = _get_address(session, contract.house_name, lang)
                message = get_message(
                    'reminder_day', lang,
                    date=tomorrow.strftime('%d.%m.%Y'),
                    time=b.time_slot.strftime('%H:%M'),
                    address=address
                )
                day_tasks.append((b, send_day_reminder(contract.telegram_id, message)))
        
        # Отправляем все напоминания за день параллельно
        if day_tasks:
            results = await asyncio.gather(*[task for _, task in day_tasks], return_exceptions=True)
            for (booking, _), success in zip(day_tasks, results):
                if success:
                    booking.reminder_day_sent = True

        # 2. Напоминание за 3 часа (если запись на сегодня)
        hour_threshold = now + timedelta(hours=3)
        urgent_bookings = session.query(Booking).filter(
            Booking.date == today,
            Booking.reminder_hour_sent == False
        ).all()

        async def send_hour_reminder(telegram_id, message_text):
            try:
                await bot.send_message(telegram_id, message_text)
                return True
            except Exception as e:
                logging.error(f"Ошибка напоминания за 3 часа: {e}")
                return False

        hour_tasks = []
        for b in urgent_bookings:
            slot_datetime = datetime.combine(b.date, b.time_slot)

            if now <= slot_datetime <= hour_threshold:
                contract = session.query(Contract).get(b.contract_id)
                if contract.telegram_id:
                    lang = _get_lang(session, contract.telegram_id)
                    address = _get_address(session, contract.house_name, lang)
                    message = get_message(
                        'reminder_hour', lang,
                        date=today.strftime('%d.%m.%Y'),
                        time=b.time_slot.strftime('%H:%M'),
                        address=address
                    )
                    hour_tasks.append((b, send_hour_reminder(contract.telegram_id, message)))
        
        # Отправляем все напоминания за 3 часа параллельно
        if hour_tasks:
            results = await asyncio.gather(*[task for _, task in hour_tasks], return_exceptions=True)
            for (booking, _), success in zip(hour_tasks, results):
                if success:
                    booking.reminder_hour_sent = True

        session.commit()
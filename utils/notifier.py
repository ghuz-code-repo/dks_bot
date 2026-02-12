import logging
import asyncio
from datetime import datetime, timedelta
from database.session import SessionLocal
from database.models import Booking, Contract
from aiogram import Bot


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
                message = (
                    f"🔔 Напоминание: Завтра ({tomorrow.strftime('%d.%m.%Y')}) "
                    f"в {b.time_slot.strftime('%H:%M')} ждем вас в офисе ДКС."
                )
                day_tasks.append((b, send_day_reminder(contract.telegram_id, message)))
        
        # Отправляем все напоминания за день параллельно
        if day_tasks:
            results = await asyncio.gather(*[task for _, task in day_tasks], return_exceptions=True)
            for (booking, _), success in zip(day_tasks, results):
                if success:
                    booking.reminder_day_sent = True

        # 2. Напоминание за час (если запись на сегодня)
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
                    message = f"⚡️ Напоминание: Визит через 3 часа в {b.time_slot.strftime('%H:%M')}!"
                    hour_tasks.append((b, send_hour_reminder(contract.telegram_id, message)))
        
        # Отправляем все напоминания за 3 часа параллельно
        if hour_tasks:
            results = await asyncio.gather(*[task for _, task in hour_tasks], return_exceptions=True)
            for (booking, _), success in zip(hour_tasks, results):
                if success:
                    booking.reminder_hour_sent = True

        session.commit()
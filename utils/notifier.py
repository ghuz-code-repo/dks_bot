import logging
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

        for b in day_bookings:
            try:
                contract = session.query(Contract).get(b.contract_id)
                if contract.telegram_id:
                    await bot.send_message(
                        contract.telegram_id,
                        f"🔔 Напоминание: Завтра ({tomorrow.strftime('%d.%m.%Y')}) "
                        f"в {b.time_slot.strftime('%H:%M')} ждем вас в офисе ДКС."
                    )
                    b.reminder_day_sent = True
            except Exception as e:
                logging.error(f"Ошибка напоминания за день: {e}")

        # 2. Напоминание за час (если запись на сегодня)
        hour_threshold = now + timedelta(hours=3)
        urgent_bookings = session.query(Booking).filter(
            Booking.date == today,
            Booking.reminder_hour_sent == False
        ).all()

        for b in urgent_bookings:
            slot_datetime = datetime.combine(b.date, b.time_slot)

            if now <= slot_datetime <= hour_threshold:
                try:
                    contract = session.query(Contract).get(b.contract_id)
                    if contract.telegram_id:
                        # Обновленный текст сообщения
                        await bot.send_message(
                            contract.telegram_id,
                            f"⚡️ Напоминание: Визит через 3 часа в {b.time_slot.strftime('%H:%M')}!"
                        )
                        b.reminder_hour_sent = True
                except Exception as e:
                    logging.error(f"Ошибка напоминания за 3 часа: {e}")

        session.commit()
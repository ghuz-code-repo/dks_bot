from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from config import ADMIN_ID
from database.session import SessionLocal
from database.models import Contract
from utils.states import ClientSteps
from keyboards.inline import generate_houses_kb
from utils.auth import is_admin

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    if is_admin(message.from_user.id):
        await message.answer(
            "💻 **Админ-панель**\n\n"
            "• `/report` — выгрузить все записи в Excel\n"
            "• `/set_slots [число]` — кол-во сотрудников\n"
            "• Отправьте `.xlsx` файл для обновления базы.\n"
            "/add_admin [ID] — назначает пользователя с указанным Telegram ID администратором.\n"
            "/add_employee [ID] — добавляет пользователя с указанным Telegram ID как сотрудника.\n"
            "/staff_list — выводит список всех зарегистрированных администраторов и сотрудников."
        )
        return

    with SessionLocal() as session:
        result = session.execute(select(Contract.house_name).distinct()).scalars().all()
        houses = [h for h in result if h]

    if not houses:
        await message.answer("🏠 Доступных объектов пока нет.")
        return

    await state.set_state(ClientSteps.selecting_house)

    # Текст приветствия на двух языках
    welcome_text = (
        "👋 Salom!\n"
        "Kalitlarni olishni rejalashtirish uchun, iltimos, turar-joy majmuangizni tanlang.\n"
        "——————————\n"
        "👋 Здравствуйте!\n"
        "Для записи на передачу ключей выберите свой жилой комплекс."
    )

    await message.answer(welcome_text, reply_markup=generate_houses_kb(houses))
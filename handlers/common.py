from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from config import ADMIN_ID
from database.session import SessionLocal
from database.models import Contract
from utils.states import ClientSteps
from keyboards.inline import generate_houses_kb
from keyboards.reply import get_admin_keyboard, get_employee_keyboard
from utils.auth import is_admin, is_staff

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # Проверка на администратора
    if is_admin(user_id):
        await message.answer(
            "🔧 **Админ-панель**\n\n"
            "Используйте кнопки ниже для управления ботом.\n"
            "Доступные команды:\n"
            "• /menu — показать меню\n"
            "• /start — перезапуск бота",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
        return
    
    # Проверка на сотрудника
    if is_staff(user_id):
        await message.answer(
            "👔 **Панель сотрудника**\n\n"
            "Используйте кнопки ниже для работы с записями.\n"
            "Доступные команды:\n"
            "• /menu — показать меню\n"
            "• /start — перезапуск бота",
            parse_mode="Markdown",
            reply_markup=get_employee_keyboard()
        )
        return

    # Обычный пользователь - показываем выбор проекта
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
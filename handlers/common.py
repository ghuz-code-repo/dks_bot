from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from config import ADMIN_ID
from database.session import SessionLocal
from database.models import Contract
from utils.states import ClientSteps
from keyboards.inline import generate_houses_kb
from keyboards.reply import get_admin_keyboard, get_employee_keyboard, get_client_keyboard
from utils.auth import is_admin, is_staff
from utils.language import get_user_language, get_message

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
            "• /start — перезапуск бота",
            parse_mode="Markdown",
            reply_markup=get_employee_keyboard()
        )
        return

    # Обычный пользователь - показываем клавиатуру клиента
    lang_code = message.from_user.language_code
    lang = get_user_language(user_id, language_code=lang_code)
    welcome_text = get_message('welcome', lang)

    await message.answer(welcome_text, reply_markup=get_client_keyboard(lang))
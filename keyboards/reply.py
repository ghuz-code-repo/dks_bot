from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для администратора"""
    keyboard = [
        [KeyboardButton(text="👥 Управление персоналом"), KeyboardButton(text="⚙️ Настройки слотов")],
        [KeyboardButton(text="📊 Выгрузить отчет"), KeyboardButton(text="📋 Список записей")],
        [KeyboardButton(text="📤 Загрузить Excel"), KeyboardButton(text="🏠 Список проектов")],
        [KeyboardButton(text="🔙 Скрыть меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_employee_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для сотрудника"""
    keyboard = [
        [KeyboardButton(text="📊 Выгрузить отчет"), KeyboardButton(text="📋 Список записей")],
        [KeyboardButton(text="🏠 Список проектов")],
        [KeyboardButton(text="🔙 Скрыть меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_staff_management_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура управления персоналом"""
    keyboard = [
        [KeyboardButton(text="➕ Добавить администратора"), KeyboardButton(text="➕ Добавить сотрудника")],
        [KeyboardButton(text="📋 Список персонала"), KeyboardButton(text="❌ Удалить из персонала")],
        [KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_slots_management_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура управления слотами"""
    keyboard = [
        [KeyboardButton(text="📝 Установить лимит для проекта")],
        [KeyboardButton(text="📊 Текущие лимиты проектов")],
        [KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой Назад"""
    keyboard = [[KeyboardButton(text="◀️ Назад")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой Отмена"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_phone_request_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для запроса номера телефона"""
    keyboard = [
        [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

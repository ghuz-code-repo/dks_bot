from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# Тексты кнопок на разных языках
BUTTON_TEXTS = {
    'add_booking': {'ru': '📝 Записаться', 'uz': '📝 ro\'yxatdan o\'tish'},
    'cancel_booking': {'ru': '❌ Отменить запись', 'uz': '❌ Yozuvni bekor qilish'},
    'my_bookings': {'ru': '📋 Мои записи', 'uz': '📋 Mening yozuvlarim'},
    'contacts': {'ru': '📞 Контакты', 'uz': '📞 Kontaktlar'},
    'language': {'ru': '🌐 O\'zbek tili', 'uz': '🌐 Русский язык'},
}


def get_client_keyboard(lang: str = 'ru') -> ReplyKeyboardMarkup:
    """Клавиатура для клиента с учетом языка (1+2x2)"""
    keyboard = [
        [KeyboardButton(text=BUTTON_TEXTS['language'][lang])],
        [KeyboardButton(text=BUTTON_TEXTS['add_booking'][lang]), KeyboardButton(text=BUTTON_TEXTS['cancel_booking'][lang])],
        [KeyboardButton(text=BUTTON_TEXTS['my_bookings'][lang]), KeyboardButton(text=BUTTON_TEXTS['contacts'][lang])]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для администратора"""
    keyboard = [
        [KeyboardButton(text="👥 Управление персоналом"), KeyboardButton(text="⚙️ Настройки проектов")],
        [KeyboardButton(text="📊 Выгрузить отчет"), KeyboardButton(text="📋 Список записей")],
        [KeyboardButton(text="➕ Добавление проектов"), KeyboardButton(text="🏠 Список проектов")],
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
    """Клавиатура управления слотами и проектами"""
    keyboard = [
        [KeyboardButton(text="📝 Установить лимит для проекта")],
        [KeyboardButton(text="📍 Установить адрес проекта")],
        [KeyboardButton(text="🗺 Установить координаты проекта")],
        [KeyboardButton(text="📊 Текущие настройки проектов")],
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


def get_phone_request_keyboard(lang: str = 'ru') -> ReplyKeyboardMarkup:
    """Клавиатура для запроса номера телефона"""
    if lang == 'uz':
        phone_text = "📱 Raqamimni yuborish"
    else:
        phone_text = "📱 Отправить мой номер"
    
    keyboard = [
        [KeyboardButton(text=BUTTON_TEXTS['language'][lang])],
        [KeyboardButton(text=phone_text, request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

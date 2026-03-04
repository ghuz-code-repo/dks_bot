from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# Тексты кнопок на разных языках
BUTTON_TEXTS = {
    'add_booking': {'ru': '📝 Первичная запись', 'uz': '📝 Uchrashuv belgilash'},
    'cancel_booking': {'ru': '❌ Отменить запись', 'uz': '❌ Yozuvni bekor qilish'},
    'my_bookings': {'ru': '📋 Мои записи', 'uz': '📋 Mening yozuvlarim'},
    'view_calendar': {'ru': '📅 Перезаписаться', 'uz': '📅 Uchrashuvni ko\'chirish'},
    'contacts': {'ru': '📞 Контакты', 'uz': '📞 Kontaktlar'},
    'language': {'ru': '🌐 O\'zbek tili', 'uz': '🌐 Русский язык'},
}


def get_client_keyboard(lang: str = 'ru') -> ReplyKeyboardMarkup:
    """Клавиатура для клиента с учетом языка"""
    keyboard = [
        [KeyboardButton(text=BUTTON_TEXTS['language'][lang])],
        [KeyboardButton(text=BUTTON_TEXTS['add_booking'][lang]), KeyboardButton(text=BUTTON_TEXTS['cancel_booking'][lang])],
        [KeyboardButton(text=BUTTON_TEXTS['my_bookings'][lang]), KeyboardButton(text=BUTTON_TEXTS['view_calendar'][lang])],
        [KeyboardButton(text=BUTTON_TEXTS['contacts'][lang])]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_admin_keyboard(with_back: bool = False) -> ReplyKeyboardMarkup:
    """Клавиатура для администратора"""
    keyboard = []
    if with_back:
        keyboard.append([KeyboardButton(text="🔙 Назад")])
    keyboard += [
        [KeyboardButton(text="👥 Управление персоналом"), KeyboardButton(text="⚙️ Настройки проектов")],
        [KeyboardButton(text="📊 Выгрузить отчет"), KeyboardButton(text="📋 Список записей")],
        [KeyboardButton(text="➕ Добавление проектов"), KeyboardButton(text="🏠 Список проектов")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_employee_keyboard(with_back: bool = False) -> ReplyKeyboardMarkup:
    """Клавиатура для сотрудника"""
    keyboard = []
    if with_back:
        keyboard.append([KeyboardButton(text="🔙 Назад")])
    keyboard += [
        [KeyboardButton(text="📊 Выгрузить отчет"), KeyboardButton(text="📋 Список записей")],
        [KeyboardButton(text="🏠 Список проектов")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_staff_management_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура управления персоналом"""
    keyboard = [
        [KeyboardButton(text="🔙 Назад")],
        [KeyboardButton(text="➕ Добавить администратора"), KeyboardButton(text="➕ Добавить сотрудника")],
        [KeyboardButton(text="📋 Список персонала"), KeyboardButton(text="❌ Удалить из персонала")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_slots_management_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура управления слотами и проектами"""
    keyboard = [
        [KeyboardButton(text="🔙 Назад")],
        [KeyboardButton(text="📝 Установить лимит для проекта"), KeyboardButton(text="📍 Установить адрес проекта")],
        [KeyboardButton(text="🗺 Установить координаты проекта"), KeyboardButton(text="📄 Изменить список договоров")],
        [KeyboardButton(text="🎉 Праздничные дни"), KeyboardButton(text="📊 Текущие настройки проектов")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой Назад"""
    keyboard = [[KeyboardButton(text="🔙 Назад")]]
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

"""
Модуль для работы с языковыми предпочтениями пользователей
"""
from database.models import UserLanguage
from database.session import SessionLocal


def get_user_language(telegram_id: int, language_code: str = None) -> str:
    """Получить язык пользователя. Для новых пользователей определяет по language_code Telegram."""
    with SessionLocal() as session:
        user_lang = session.query(UserLanguage).filter(
            UserLanguage.telegram_id == telegram_id
        ).first()
        if user_lang:
            return user_lang.language
        
        # Новый пользователь — определяем язык из Telegram
        if language_code and language_code.startswith('uz'):
            lang = 'uz'
        else:
            lang = 'ru'
        
        # Сохраняем выбор
        new_user = UserLanguage(telegram_id=telegram_id, language=lang)
        session.add(new_user)
        session.commit()
        return lang


def set_user_language(telegram_id: int, language: str) -> None:
    """Установить язык пользователя"""
    with SessionLocal() as session:
        user_lang = session.query(UserLanguage).filter(
            UserLanguage.telegram_id == telegram_id
        ).first()
        
        if user_lang:
            user_lang.language = language
        else:
            user_lang = UserLanguage(telegram_id=telegram_id, language=language)
            session.add(user_lang)
        
        session.commit()


def toggle_language(telegram_id: int) -> str:
    """Переключить язык и вернуть новый"""
    current = get_user_language(telegram_id)
    new_lang = 'uz' if current == 'ru' else 'ru'
    set_user_language(telegram_id, new_lang)
    return new_lang


def get_user_phone(telegram_id: int) -> str | None:
    """Получить сохранённый номер телефона пользователя"""
    with SessionLocal() as session:
        user = session.query(UserLanguage).filter(
            UserLanguage.telegram_id == telegram_id
        ).first()
        return user.phone if user else None


def set_user_phone(telegram_id: int, phone: str) -> None:
    """Сохранить номер телефона пользователя"""
    with SessionLocal() as session:
        user = session.query(UserLanguage).filter(
            UserLanguage.telegram_id == telegram_id
        ).first()
        
        if user:
            user.phone = phone
        else:
            user = UserLanguage(telegram_id=telegram_id, phone=phone)
            session.add(user)
        
        session.commit()


# Все тексты сообщений
MESSAGES = {
    # Приветственные сообщения
    'welcome': {
        'ru': '👋 Здравствуйте!\nДля записи на передачу ключей используйте кнопки ниже.',
        'uz': '👋 Salom!\nKalitlarni olishni rejalashtirish uchun quyidagi tugmalardan foydalaning.'
    },
    'welcome_admin': {
        'ru': '👋 Добро пожаловать, администратор!',
        'uz': '👋 Xush kelibsiz, administrator!'
    },
    'welcome_employee': {
        'ru': '👋 Добро пожаловать, сотрудник!',
        'uz': '👋 Xush kelibsiz, xodim!'
    },
    
    # Выбор ЖК и договора
    'select_house': {
        'ru': '🏠 Выберите жилой комплекс:',
        'uz': '🏠 Turar-joy majmuasini tanlang:'
    },
    'enter_contract': {
        'ru': '📝 Введите номер Вашего договора долевого участия по примеру 12345-GHP',
        'uz': '📝 Ulushdorlik shartnomasi raqamingizni kiriting, masalan, 12345-GHP'
    },
    'contract_not_found': {
        'ru': '❌ Договор не найден. Проверьте номер и введите заново:',
        'uz': '❌ Shartnoma topilmadi. Raqamni tekshirib, qaytadan kiriting:'
    },
    'contract_unavailable': {
        'ru': '⚠️ Запись на этот договор недоступна. Введите другой номер договора:',
        'uz': '⚠️ Bu shartnoma bo\'yicha yozuv mavjud emas. Boshqa shartnoma raqamini kiriting:'
    },
    
    # Активная запись
    'has_active_booking': {
        'ru': 'У вас уже есть активная запись на {date}. Введите другой номер договора:',
        'uz': 'Sizda {date} sanasiga allaqachon faol yozuv mavjud. Boshqa shartnoma raqamini kiriting:'
    },
    
    # Выбор даты и времени
    'contract_confirmed': {
        'ru': '✅ Договор подтвержден: {fio}\nЗапись доступна с: {date}\n\nВыберите доступную дату в календаре:',
        'uz': '✅ Shartnoma tasdiqlandi: {fio}\nYozuv mavjud sanadan: {date}\n\nTaqvimda mavjud sanani tanlang:'
    },
    'select_date': {
        'ru': '📅 Выберите дату для записи:',
        'uz': '📅 Yozuv uchun sanani tanlang:'
    },
    'date_not_available': {
        'ru': '❌ Эта дата недоступна. Выберите другую дату.',
        'uz': '❌ Bu sana mavjud emas. Boshqa sanani tanlang.'
    },
    'weekend_not_available': {
        'ru': '❌ Запись на выходные недоступна. Выберите рабочий день.',
        'uz': '❌ Dam olish kunlariga yozuv mavjud emas. Ish kunini tanlang.'
    },
    'select_time': {
        'ru': '⏰ Выберите время:\n📍 Адрес: {address}\n🏠 ЖК: {house}\n🏢 Кв: {apt}',
        'uz': '⏰ Vaqtni tanlang:\n📍 Manzil: {address}\n🏠 TJM: {house}\n🏢 Kv: {apt}'
    },
    'date_selected_choose_time': {
        'ru': '📅 Вы выбрали дату: **{selected_date}**\n🏠 Дата сдачи вашей квартиры: {delivery_date}\n\nТеперь выберите удобный временной интервал:',
        'uz': '📅 Siz sanani tanladingiz: **{selected_date}**\n🏠 Xonadoningizning topshirish sanasi: {delivery_date}\n\nEndi qulay vaqt oralig\'ini tanlang:'
    },
    'time_slot_full': {
        'ru': '❌ Это время уже занято. Выберите другое время.',
        'uz': '❌ Bu vaqt allaqachon band. Boshqa vaqtni tanlang.'
    },
    
    # Телефон
    'enter_phone': {
        'ru': '📱 Отправьте ваш номер телефона или введите его вручную:',
        'uz': '📱 Telefon raqamingizni yuboring yoki qo\'lda kiriting:'
    },
    'invalid_phone': {
        'ru': '❌ Допускаются только номера Узбекистана (+998), России (+7) и Казахстана (+7). Попробуйте снова.',
        'uz': '❌ Faqat O\'zbekiston (+998), Rossiya (+7) va Qozog\'iston (+7) raqamlari qabul qilinadi. Qayta urinib ko\'ring.'
    },
    'phone_choice': {
        'ru': '📱 Использовать сохранённый номер или ввести новый?',
        'uz': '📱 Saqlangan raqamni ishlatasizmi yoki yangisini kiritasizmi?'
    },
    'use_saved_phone': {
        'ru': '📱 Использовать {phone}',
        'uz': '📱 {phone} dan foydalanish'
    },
    'enter_new_phone': {
        'ru': '✏️ Ввести новый номер',
        'uz': '✏️ Yangi raqam kiritish'
    },
    
    # Подтверждение записи
    'booking_confirmed': {
        'ru': '✅ Вы записаны!\n\n📅 Дата: {date}\n⏰ Время: {time}\n📍 Адрес: {address}\n🏠 ЖК: {house}\n🏢 Квартира: {apt}\n👤 ФИО: {fio}\n📱 Телефон: {phone}',
        'uz': '✅ Siz yozildingiz!\n\n📅 Sana: {date}\n⏰ Vaqt: {time}\n📍 Manzil: {address}\n🏠 TJM: {house}\n🏢 Kvartira: {apt}\n👤 FIO: {fio}\n📱 Telefon: {phone}'
    },
    
    # Мои записи
    'my_bookings_header': {
        'ru': '📋 **Ваши записи:**',
        'uz': '📋 **Sizning yozuvlaringiz:**'
    },
    'no_bookings': {
        'ru': '📋 Записей нет.',
        'uz': '📋 Yozuvlar yo\'q.'
    },
    'booking_item': {
        'ru': '📅 Дата: {date}\n⏰ Время: {time}\n🏠 Адрес: {house}\n🏢 Квартира: {apt}\n———————',
        'uz': '📅 Sana: {date}\n⏰ Vaqt: {time}\n🏠 Manzil: {house}\n🏢 Kvartira: {apt}\n———————'
    },
    
    # Отмена записи
    'no_bookings_to_cancel': {
        'ru': '📋 У вас нет активных записей для отмены.',
        'uz': '📋 Sizda bekor qilish uchun faol yozuvlar yo\'q.'
    },
    'select_booking_to_cancel': {
        'ru': '📋 Выберите запись для отмены:\n🔒 - отмена невозможна (слишком поздно)',
        'uz': '📋 Bekor qilish uchun yozuvni tanlang:\n🔒 - bekor qilish mumkin emas (juda kech)'
    },
    'all_bookings_blocked': {
        'ru': '⚠️ Все ваши записи находятся в периоде, когда отмена невозможна.\nОтмена возможна не позднее чем за один рабочий день до визита (до 12:00) или за два рабочих дня (после 12:00).',
        'uz': '⚠️ Sizning barcha yozuvlaringiz bekor qilish mumkin bo\'lmagan davrda.\nBekor qilish tashrifdan bir ish kuni oldin (soat 12:00 gacha) yoki ikki ish kuni oldin (soat 12:00 dan keyin) mumkin.'
    },
    'confirm_cancel': {
        'ru': '⚠️ Вы уверены, что хотите отменить запись на {date} в {time}?',
        'uz': '⚠️ {date} kuni soat {time} dagi yozuvni bekor qilishni xohlaysizmi?'
    },
    'booking_cancelled': {
        'ru': '✅ Запись на {date} в {time} отменена.',
        'uz': '✅ {date} kuni soat {time} dagi yozuv bekor qilindi.'
    },
    'cancel_aborted': {
        'ru': '❌ Отмена записи отменена.',
        'uz': '❌ Yozuvni bekor qilish bekor qilindi.'
    },
    
    # Контакты
    'contacts': {
        'ru': '📞 **Контакты отдела ДКС**\n\n📱 Телефон: {phone}\n📍 Адрес: {address}\n🕐 Режим работы: {hours}',
        'uz': '📞 **DKS bo\'limi aloqa ma\'lumotlari**\n\n📱 Telefon: {phone}\n📍 Manzil: {address}\n🕐 Ish vaqti: {hours}'
    },
    
    # Язык переключён
    'language_changed': {
        'ru': '✅ Язык изменён на русский.',
        'uz': '✅ Til o\'zbek tiliga o\'zgartirildi.'
    },
    
    # Загрузка
    'loading': {
        'ru': '⏳ Загрузка...',
        'uz': '⏳ Yuklanmoqda...'
    },
    
    # Кнопки
    'back': {
        'ru': '🔙 Назад',
        'uz': '🔙 Orqaga'
    },
    'confirm': {
        'ru': '✅ Да, отменить',
        'uz': '✅ Ha, bekor qilish'
    },
    'reject': {
        'ru': '❌ Нет, оставить',
        'uz': '❌ Yo\'q, qoldirish'
    },
    
    # Напоминания
    'reminder_day': {
        'ru': '🔔 Напоминание!\n\nЗавтра у вас запись на получение ключей.\n\n📅 Дата: {date}\n⏰ Время: {time}\n📍 Адрес: {address}',
        'uz': '🔔 Eslatma!\n\nErtaga sizda kalitlarni olish uchun yozuv bor.\n\n📅 Sana: {date}\n⏰ Vaqt: {time}\n📍 Manzil: {address}'
    },
    'reminder_hour': {
        'ru': '🔔 Напоминание!\n\nЧерез 3 часа у вас запись на получение ключей.\n\n📅 Дата: {date}\n⏰ Время: {time}\n📍 Адрес: {address}',
        'uz': '🔔 Eslatma!\n\n3 soatdan keyin sizda kalitlarni olish uchun yozuv bor.\n\n📅 Sana: {date}\n⏰ Vaqt: {time}\n📍 Manzil: {address}'
    },
    
    # Нет доступных ЖК
    'no_houses_available': {
        'ru': '❌ В данный момент нет доступных жилых комплексов для записи.',
        'uz': '❌ Hozirda yozuv uchun mavjud turar-joy majmualari yo\'q.'
    },

    # Календарь записей
    'no_active_bookings_rebook': {
        'ru': '❌ У вас нет активных записей для перезаписи.\nСначала запишитесь через кнопку «📝 Первичная запись».',
        'uz': '❌ Sizda qayta yozish uchun faol yozuvlar yo\'q.\nAvval «📝 Uchrashuv belgilash» tugmasi orqali yozing.'
    },
    'select_booking_rebook': {
        'ru': '📋 Выберите запись, которую хотите перезаписать:',
        'uz': '📋 Qayta yozmoqchi bo\'lgan yozuvni tanlang:'
    },
    'calendar_header': {
        'ru': '📅 Календарь доступных дат для записи\n🏠 ЖК: {house}\n\nВыберите дату для записи:',
        'uz': '📅 Yozuv uchun mavjud sanalar taqvimi\n🏠 TJM: {house}\n\nYozuv uchun sanani tanlang:'
    },
    'rebook_confirm': {
        'ru': '⚠️ У вас уже есть активная запись:\n\n📅 Дата: {old_date}\n⏰ Время: {old_time}\n🏠 ЖК: {house}\n🏢 Кв: {apt}\n\nВы выбрали новую запись: **{new_date} {new_time}**\nДля этого необходимо отменить текущую запись.\n\nОтменить текущую запись и перезаписаться?',
        'uz': '⚠️ Sizda allaqachon faol yozuv mavjud:\n\n📅 Sana: {old_date}\n⏰ Vaqt: {old_time}\n🏠 TJM: {house}\n🏢 Kv: {apt}\n\nSiz yangi yozuvni tanladingiz: **{new_date} {new_time}**\nBuning uchun joriy yozuvni bekor qilish kerak.\n\nJoriy yozuvni bekor qilib, qayta yozilasizmi?'
    },
    'rebook_confirm_yes': {
        'ru': '✅ Да, перезаписаться',
        'uz': '✅ Ha, qayta yozilish'
    },
    'rebook_confirm_no': {
        'ru': '❌ Нет, оставить текущую',
        'uz': '❌ Yo\'q, joriyni qoldirish'
    },
    'rebook_cancelled': {
        'ru': '❌ Перезапись отменена. Ваша текущая запись сохранена.',
        'uz': '❌ Qayta yozilish bekor qilindi. Joriy yozuvingiz saqlandi.'
    },

}


def get_message(key: str, lang: str = 'ru', **kwargs) -> str:
    """Получить сообщение на нужном языке с подстановкой параметров"""
    msg = MESSAGES.get(key, {}).get(lang, MESSAGES.get(key, {}).get('ru', key))
    if kwargs:
        msg = msg.format(**kwargs)
    return msg

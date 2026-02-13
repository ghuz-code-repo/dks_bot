import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
EMPLOYEE_IDS = [int(i) for i in os.getenv("EMPLOYEE_IDS", "").split(",") if i]

# Контакты отдела ДКС
DKS_CONTACTS = {
    "phone": "+998781485115",
    "email": "dks@example.com",
    "address_ru": "г. Ташкент, улица Истикбол, 39Б",
    "address_uz": "Toshkent sh., Istiqbol ko'chasi, 39B",
    "working_hours_ru": "Пн-Пт: 9:00-18:00",
    "working_hours_uz": "Dush-Jum: 9:00-18:00",
    "latitude": 41.302006,     
    "longitude": 69.292259
}
import asyncio
import logging
import ssl
import warnings
import os
import aiohttp
import certifi
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN
from handlers import admin, client, common, employee
from database.session import init_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.notifier import check_reminders

# Полное отключение проверки SSL на уровне окружения
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", message="Unclosed client session")
warnings.filterwarnings("ignore", message="Unclosed connector")
warnings.filterwarnings("ignore", message=".*ssl.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*certificate.*")

# Создаём небезопасный SSL контекст
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


class DisabledSSLAiohttpSession(AiohttpSession):
    async def create_session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            ssl=False,
            force_close=True,
            enable_cleanup_closed=True
        )
        return aiohttp.ClientSession(
            connector=connector,
            json_serialize=self.json_dumps,
            trust_env=True
        )


async def main():
    # 3. ЖЕСТКАЯ НАСТРОЙКА ЛОГИРОВАНИЯ
    # Отключаем все логи ниже уровня CRITICAL для сторонних библиотек
    logging.getLogger("aiogram").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    # Настраиваем только основной логгер для вывода ваших сообщений
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    init_db()

    session = DisabledSSLAiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(employee.router)  # Роутер для сотрудников
    dp.include_router(common.router)
    dp.include_router(client.router)

    print("\n" + "=" * 40)
    print(" СТАТУС: БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
    print("=" * 40 + "\n")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders, 'interval', minutes=2, args=[bot])
    scheduler.start()
    try:
        await dp.start_polling(bot, handle_as_tasks=False)
    finally:
        await bot.session.close()
        await asyncio.sleep(0.250)  # Даем время на закрытие соединений


if __name__ == "__main__":
    # Установка контекста SSL на уровне процесса
    ssl._create_default_https_context = ssl._create_unverified_context

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
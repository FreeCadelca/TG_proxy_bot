import os
import logging
import asyncio
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from db.database import init_db
from utils.scheduler import init_scheduler
from utils.middlewares import RegisteredOnlyMiddleware
from handlers.admin import init_bot_instance_admin
from handlers.user import router as user_router
from handlers.admin import router as admin_router

# Настройка логирования (путь к файлу можно задать через LOG_FILE, например в docker)
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5)
    ]
)


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    # Незарегистрированным доступны только /start и ввод invite-кода
    dp.message.outer_middleware(RegisteredOnlyMiddleware())
    dp.include_router(user_router)
    dp.include_router(admin_router)

    await init_db()  # Create tables
    init_scheduler(bot)  # Start scheduler
    init_bot_instance_admin(bot)

    logging.info("Bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import os
from typing import List
from dotenv import load_dotenv, set_key
import logging

load_dotenv()


class Config:
    """Динамичный конфиг с обновлением .env и runtime."""

    def __init__(self):
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан в .env")

        self.ADMIN_IDS = [int(id_str) for id_str in os.getenv("ADMIN_IDS", "").split(",") if id_str]
        if not self.ADMIN_IDS:
            raise ValueError("ADMIN_IDS не заданы в .env")

        self.ADMIN_NICKNAMES = [nick.strip() for nick in os.getenv("ADMIN_NICKNAMES", "").split(",") if nick]
        self.DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///bot.db")
        self.MONTHLY_FEE = int(os.getenv("MONTHLY_FEE", "65.0"))
        self.PAYMENT_DAY = int(os.getenv("PAYMENT_DAY", "24"))
        self.REMIND_BEFORE_DAYS = int(os.getenv("REMIND_BEFORE_DAYS", "3"))
        self.REMIND_INTERVAL_DAYS = int(os.getenv("REMIND_INTERVAL_DAYS", "7"))
        self.ADMIN_PHONES = os.getenv("ADMIN_PHONES", "").split(",")
        self.HELP_GIST_URL = os.getenv("HELP_GIST_URL", "https://gist.github.com/your/default-help")
        self.CONFIG_GIST_URL = os.getenv("CONFIG_GIST_URL", "https://gist.github.com/your/default-config")

    def update_fee(self, new_fee: int):
        """Обновить MONTHLY_FEE в runtime, .env и os.environ."""
        if new_fee <= 0:
            raise ValueError("Цена должна быть больше 0")
        self.MONTHLY_FEE = new_fee
        os.environ['MONTHLY_FEE'] = str(new_fee)  # Обновляем для всех os.getenv
        set_key('.env', 'MONTHLY_FEE', str(new_fee))  # Обновляем файл
        logging.info(f"Updated MONTHLY_FEE to {new_fee}")


# Создаём экземпляр (используем как config.MONTHLY_FEE)
config = Config()

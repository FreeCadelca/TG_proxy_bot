import os
from typing import List
from dotenv import load_dotenv

load_dotenv()  # Загружаем .env файл из корня проекта

# Основные настройки бота
BOT_TOKEN: str = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

# Администраторы (список Telegram IDs, разделённые запятой в .env)
ADMIN_IDS: List[int] = [int(id_str) for id_str in os.getenv("ADMIN_IDS", "").split(",") if id_str]
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не заданы в .env")

# Администраторы (список Telegram IDs, разделённые запятой в .env)
ADMIN_NICKNAMES: List[str] = [nick.strip() for nick in os.getenv("ADMIN_NICKNAMES", "").split(",") if nick]
if not ADMIN_NICKNAMES:
    raise ValueError("ADMIN_IDS не заданы в .env")

# База данных (SQLite для простоты, легко сменить на postgres://...)
DB_URL: str = os.getenv("DB_URL", "sqlite+aiosqlite:///bot.db")

# Настройки оплат
MONTHLY_FEE: float = float(os.getenv("MONTHLY_FEE", "65.0"))  # Цена за месяц, динамичная
PAYMENT_DAY: int = int(os.getenv("PAYMENT_DAY", "24"))  # День платежа
REMIND_BEFORE_DAYS: int = int(os.getenv("REMIND_BEFORE_DAYS", "3"))  # За сколько дней начинать напоминать
REMIND_INTERVAL_DAYS: int = int(os.getenv("REMIND_INTERVAL_DAYS", "7"))  # Интервал повторных напоминаний

# Номера телефонов админов для переводов (разделённые запятой в .env)
ADMIN_PHONES: List[str] = os.getenv("ADMIN_PHONES", "").split(",")

HELP_GIST_URL: str = os.getenv("HELP_GIST_URL", "https://gist.github.com/your/default-help")
CONFIG_GIST_URL: str = os.getenv("CONFIG_GIST_URL", "https://gist.github.com/your/default-config")

# Для безопасности: Не экспортируем sensitive vars случайно
__all__ = [
    "BOT_TOKEN", "ADMIN_IDS", "ADMIN_NICKNAMES", "DB_URL", "MONTHLY_FEE", "PAYMENT_DAY",
    "REMIND_BEFORE_DAYS", "REMIND_INTERVAL_DAYS", "ADMIN_PHONES",
    "HELP_GIST_URL", "CONFIG_GIST_URL"
]

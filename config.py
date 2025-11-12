import os
from typing import List
from dotenv import load_dotenv, set_key
import logging
from pyzabbix import ZabbixAPI

load_dotenv()


def read_text_from_file(filepath: str) -> str:
    filepath = filepath.replace('/', os.sep)
    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            return ''.join([i for i in f.readlines()])
    except Exception as e:
        logging.error(f"Error while processing reading from file: {e}")


class Config:
    """Динамичный конфиг с обновлением .env и runtime."""

    def __init__(self):
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан в .env")

        self.ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN")
        if not self.ZABBIX_TOKEN:
            raise ValueError("ZABBIX_TOKEN не задан в .env")

        self.ZABBIX_USER = os.getenv("ZABBIX_USER")
        if not self.ZABBIX_USER:
            raise ValueError("ZABBIX_USER не задан в .env")

        self.ZABBIX_PASS = os.getenv("ZABBIX_PASS")
        if not self.ZABBIX_PASS:
            raise ValueError("ZABBIX_PASS не задан в .env")

        self.ZABBIX_URL = os.getenv("ZABBIX_URL")
        if not self.ZABBIX_URL:
            raise ValueError("ZABBIX_URL не задан в .env")

        self.ZABBIX_NETWORK_CHART_ID = int(os.getenv("ZABBIX_NETWORK_CHART_ID"))

        self.ADMIN_IDS = [int(id_str) for id_str in os.getenv("ADMIN_IDS", "").split(",") if id_str]
        if not self.ADMIN_IDS:
            raise ValueError("ADMIN_IDS не заданы в .env")

        self.ADMIN_NICKNAMES = [nick.strip() for nick in os.getenv("ADMIN_NICKNAMES", "").split(",") if nick]
        self.DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///bot.db")
        self.MONTHLY_FEE = int(os.getenv("MONTHLY_FEE", "65.0"))
        self.PAYMENT_DAY = int(os.getenv("PAYMENT_DAY", "24"))
        self.CACHE_TTL = int(os.getenv("CACHE_TTL", "120"))
        self.REMIND_BEFORE_DAYS = int(os.getenv("REMIND_BEFORE_DAYS", "3"))
        self.REMIND_INTERVAL_DAYS = int(os.getenv("REMIND_INTERVAL_DAYS", "7"))
        self.ADMIN_PHONES = os.getenv("ADMIN_PHONES", "").split(",")
        self.HELP_GIST_URL = os.getenv("HELP_GIST_URL", "https://gist.github.com/your/default-help")
        self.CONFIG_GIST_URL = os.getenv("CONFIG_GIST_URL", "https://gist.github.com/your/default-config")
        self.ADMIN_HELP_TEXT = read_text_from_file("payloads/admin_help_text.txt")
        self.HELP_TEXT = read_text_from_file("payloads/help_text.txt")

        self.zapi = ZabbixAPI("http://95.164.123.32/zabbix/")
        self.setup_zapi()

    def update_fee(self, new_fee: int):
        """Обновить MONTHLY_FEE в runtime, .env и os.environ."""
        if new_fee <= 0:
            raise ValueError("Цена должна быть больше 0")
        self.MONTHLY_FEE = new_fee
        os.environ['MONTHLY_FEE'] = str(new_fee)  # Обновляем для всех os.getenv
        set_key('.env', 'MONTHLY_FEE', str(new_fee))  # Обновляем файл
        logging.info(f"Updated MONTHLY_FEE to {new_fee}")

    def update_payment_day(self, new_day: int):
        """Обновить PAYMENT_DAY в runtime, .env и os.environ."""
        if new_day <= 0 or new_day >= 29:
            raise ValueError("Новый день месяца должен быть валидный")
        self.PAYMENT_DAY = new_day
        os.environ['PAYMENT_DAY'] = str(new_day)  # Обновляем для всех os.getenv
        set_key('.env', 'PAYMENT_DAY', str(new_day))  # Обновляем файл
        logging.info(f"Updated PAYMENT_DAY to {new_day}")


    def setup_zapi(self):
        self.zapi.login(api_token=self.ZABBIX_TOKEN)

        hosts = self.zapi.host.get(filter={"host": "Zabbix server"})
        host_id = hosts[0]['hostid']

        # # Найти item ID для сетевого трафика (incoming/outgoing)
        # items = self.zapi.item.get(hostids=host_id, search={"name": "Incoming network traffic on"})
        # item_id_in = items[0]['itemid'] if items else None

        # # Найти график по имени (например, "Network traffic on eth0")
        # graphs = self.zapi.graph.get(hostids=host_id, search={"name": "Network traffic"})
        # graph_id = graphs[0]['graphid'] if graphs else None



# Создаём экземпляр (используем как config.MONTHLY_FEE)
config = Config()

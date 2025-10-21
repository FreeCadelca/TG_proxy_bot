import logging

import aiogram
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
import datetime

from sqlalchemy import select

from db.database import get_user_by_identifier, generate_invite, add_key, confirm_payment, add_key_to_queue, get_session
from db.models import User  # Для list_mappings
from config import config
from db.database import AsyncSessionLocal  # Для сессии в list_mappings
from handlers.user import escape_markdown_v2
from utils.scheduler import daily_check

router = Router()
Bot = None


async def is_admin(tg_id: int) -> bool:
    return tg_id in config.ADMIN_IDS


@router.message(Command("generate_invite"))
async def generate_invite_handler(message: Message):
    """Генерировать invite: /generate_invite <nickname>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if not args:
        return await message.answer("Usage: /generate_invite <nickname>")
    nickname = args[0]
    try:
        code = await generate_invite(message.from_user.id, nickname)
        response = f"Новый invite код для {nickname}:\n```{escape_markdown_v2(code)}```"
        await message.answer(response, parse_mode="MarkdownV2")
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("add_key"))
async def add_key_handler(message: Message):
    """Добавить ключ: /add_key <identifier> <key_text>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.answer("Usage: /add_key <identifier> <key_text>")
    identifier = args[0]
    key_text = " ".join(args[1:])

    user = await get_user_by_identifier(identifier)
    if not user:
        # Пользователь не найден — добавляем в KeyInQueue
        if not isinstance(identifier, str):  # Если identifier — tg_id (int), ошибка
            return await message.answer("Пользователь не найден, используйте nickname для очереди.")
        if await add_key_to_queue(identifier, key_text):
            await message.answer(f"Ключ добавлен в очередь для {identifier}.")
        else:
            await message.answer("Ошибка добавления ключа в очередь.")
    else:
        # Пользователь существует — добавляем в Key (move_keys_to_user вызывается внутри)
        if await add_key(user.id, key_text):
            await message.answer(f"Ключ добавлен для {identifier}.")
        else:
            await message.answer("Лимит ключей достигнут.")


@router.message(Command("confirm_payment"))
async def confirm_payment_handler(message: Message):
    """Подтвердить пополнение (перевод): /confirm_payment <identifier> <amount>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.answer("Usage: /confirm_payment <identifier> <amount>")
    identifier = args[0]
    try:
        amount = int(args[1])
        user = await get_user_by_identifier(identifier)
        if not user:
            return await message.answer("Пользователь не найден по identifier.")
        current_month = datetime.datetime.now().strftime("%Y-%m")
        if await confirm_payment(user.id, amount, current_month, message.from_user.username):
            await message.answer("Платёж подтверждён.")
            await message.bot.send_message(user.telegram_id,
                                           f"@{message.from_user.username} проверил ваш платёж на {amount} руб. и обновил баланс и список платежей.")
    except ValueError:
        await message.answer("Неверная сумма или identifier.")


@router.message(Command("set_fee"))
async def set_fee_handler(message: Message):
    """Установить новую цену: /set_fee <new_fee>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if not args:
        return await message.answer("Usage: /set_fee <new_fee>")
    try:
        new_fee = int(args[0])
        config.update_fee(new_fee)  # Обновляем через метод
        await message.answer(f"Новая цена: {new_fee} руб./мес.")
    except ValueError:
        await message.answer("Неверная сумма.")


@router.message(Command("set_payment_day"))
async def set_payment_day_handler(message: Message):
    """Установить новый день сбора: /set_payment_day <new_day>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if not args:
        return await message.answer("Usage: /set_payment_day <new_day>")
    try:
        new_day = int(args[0])
        config.update_fee(new_day)  # Обновляем через метод
        await message.answer(f"Новый день месяца для сбора: {new_day}")
    except ValueError:
        await message.answer("Неверный день.")


@router.message(Command("daily_check"))
async def manual_daily_check(message: Message):
    """Произвести принудительную проверку платежей (daily_check function)"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    await daily_check(message.bot)  # Передаём bot
    await message.answer("Daily check completed.")


@router.message(Command("admin"))
async def manual_daily_check(message: Message):
    """Выводит примеры администраторских команд."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    await message.answer(config.ADMIN_HELP_TEXT)


@router.message(Command("list_mappings"))
async def list_mappings_handler(message: Message):
    """Вывод таблицы сопоставлений nickname - tg_id."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()
    if not users:
        return await message.answer("Нет пользователей.")
    table = ("ID|Nickname|TG_ID|Username|Balance\n"
             "")  # У тг свой размер для "-", поэтому приходится их больше писать для соответствия
    users_col_width = {"id": 0, "nick": 0, "tg_id": 0, "username": 0, "balance": 0}
    for user in users:
        users_col_width["id"] = max(users_col_width["id"], len(str(user.id)))
        users_col_width["nick"] = max(users_col_width["nick"], len(str(user.nickname) or 'N/A'))
        users_col_width["tg_id"] = max(users_col_width["tg_id"], len(str(user.telegram_id)))
        users_col_width["username"] = max(users_col_width["username"], len(str(user.username)))
        users_col_width["balance"] = max(users_col_width["balance"], len(str(user.balance)))

    for user in users:
        user_id = str(user.id).ljust(users_col_width["id"])
        user_nickname = str(user.nickname).ljust(users_col_width["nick"])
        user_telegram_id = str(user.telegram_id).ljust(users_col_width["tg_id"])
        user_username = str(user.username).ljust(users_col_width["username"]) if user.username \
            else 'N/A'.ljust(users_col_width["username"])
        user_balance = str(user.balance).ljust(users_col_width["balance"])
        table += f"{user_id} {user_nickname} {user_telegram_id} {user_username} {user_balance}\n"
    await message.answer('```' + escape_markdown_v2(table) + '```', parse_mode="MarkdownV2")


@router.message(Command("broadcast"))
async def list_mappings_handler(message: Message):
    """Рассылка объявления всем пользователям бота"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split(maxsplit=1)[1:]
    if len(args) < 1:
        return await message.answer("Usage: /broadcast <text>")
    boradcast_message = args[0]

    session = await get_session()
    users = await session.execute(select(User))
    count = 0
    for user in users.scalars().all():
        try:
            telegram_id = user.telegram_id  # Сохраняем telegram_id заранее
            Bot.send_message(telegram_id, boradcast_message)
            count += 1
        finally:
            pass

    logging.info(f"Broadcasted to {count} users next message: {boradcast_message}")


def init_bot_instance_admin(bot: aiogram.Bot):
    global Bot
    Bot = bot

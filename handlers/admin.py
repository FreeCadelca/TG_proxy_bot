import logging

import aiogram
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.types import ReactionTypeEmoji
import datetime

from sqlalchemy import select

from db.database import (get_user_by_identifier, generate_invite, add_key, confirm_payment, add_key_to_queue,
                         get_session, get_user_keys, get_key_by_id, edit_key, remove_key,
                         get_user_by_user_id)
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
    """Добавить ключ: /add_key <identifier> <Tag|None=_> <key_text>."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if len(args) < 3:
        return await message.answer("Usage: /add_key <identifier> <Tag|None=_> <key_text>")
    identifier = args[0]
    tag = None if args[1] == '_' else args[1]
    key_text = " ".join(args[2:])

    user = await get_user_by_identifier(identifier)
    if not user:
        # Пользователь не найден — добавляем в KeyInQueue
        if not isinstance(identifier, str):  # Если identifier — tg_id (int), ошибка
            return await message.answer("Пользователь не найден, используйте nickname для очереди.")
        if await add_key_to_queue(identifier, key_text, tag=tag):
            await message.answer(f"Ключ добавлен в очередь для {identifier}, tag={tag}.")
        else:
            await message.answer("Ошибка добавления ключа в очередь.")
    else:
        # Пользователь существует — добавляем в Key (move_keys_to_user вызывается внутри)
        if await add_key(user.id, key_text, tag=tag):
            await message.answer(f"Ключ добавлен для {identifier}, tag={tag}.")
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
        config.update_payment_day(new_day)  # Обновляем через метод
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
    await message.answer('```' + table + '```', parse_mode="MarkdownV2")


@router.message(Command("broadcast"))
async def broadcast_handler(message: Message):
    """Рассылка объявления всем пользователям бота: /broadcast <message>"""
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
            await Bot.send_message(telegram_id, escape_markdown_v2(boradcast_message), parse_mode="MarkdownV2")
            count += 1
        except Exception as e:
            logging.error(e)

    logging.info(f"Broadcasted to {count} users next message: {boradcast_message}")


@router.message(Command("see_keys"))
async def see_keys_handler(message: Message):
    """Посмотреть ключи указанного пользователя: /see_keys <identifier>"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    args = message.text.split()[1:]
    if len(args) < 1:
        return await message.answer("Usage: /see_keys <identifier>")
    user_identifier = args[0]

    user = await get_user_by_identifier(user_identifier)
    if not user:
        return await message.answer("Пользователь не найден")
    keys = await get_user_keys(user.id)
    if not keys:
        return await message.answer("У пользователя нет ключей")

    responses = [f"Ключи пользователя {user_identifier}:"]

    for i, k in enumerate(keys):
        if k.tag:
            responses.append(f"{i + 1} ключ \(id\={k.id}\) \(tag: {escape_markdown_v2(k.tag)}\):\n```{escape_markdown_v2(k.key_text)}```")
        else:
            responses.append(f"{i + 1} ключ \(id\={k.id}\):\n```{escape_markdown_v2(k.key_text)}```")
    for response in responses:
        await message.answer(response, parse_mode="MarkdownV2")


@router.message(Command("edit_key"))
async def edit_key_handler(message: Message):
    """Редактировать ключ с конкретным id: /edit_key <key_id> <new_identifier|~> <new_tag|None=_|~> <key_text|~>"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")

    args = message.text.split()[1:]
    if len(args) < 4:
        return await message.answer("Usage: /edit_key <key_id> <new_identifier|~> <new_tag|None=_|~> <key_text|~>")
    key_id = int(args[0])


    # Достаём ключ по id
    key = await get_key_by_id(key_id)
    if len(key) < 1:
        return await message.answer("Нет такого ключа")
    key = key[0]

    current_user = await get_user_by_user_id(key.user_id)
    current_user_tg_id = current_user.telegram_id

    # Вычисляем новые параметры (если они '~' - подаём в качестве новых данных такие же старые)

    new_identifier = args[1] if args[1] != '~' else current_user_tg_id

    new_tag = args[2]
    if new_tag == '~':
        new_tag = key.tag
    elif new_tag == '_':
        new_tag = None

    args[3] = " ".join(args[3:])
    new_text = args[3] if args[3] != '~' else key.key_text

    new_user = await get_user_by_identifier(new_identifier)
    if not new_user:
        # Пользователь не существует
        await message.answer(f"Пользователь не найден")
    else:
        # Пользователь существует — редактируем ключ
        if await edit_key(key_id, new_user.id, new_text, new_tag=new_tag):
            await message.answer(f"Ключ id = {key_id} изменён")
        else:
            await message.answer("Возникла ошибка изменения ключа")


@router.message(Command("remove_key"))
async def remove_key_handler(message: Message):
    """Удалить ключ по id: /remove_key <key_id>"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")

    args = message.text.split()[1:]
    if len(args) < 1:
        return await message.answer("Usage: /remove_key <key_id>")
    key_id = int(args[0])

    if await remove_key(key_id):
        await message.answer(f"Ключ id = {key_id} успешно удалён")
    else:
        await message.answer(f"Не удалось ключ с id = {key_id}")


@router.message(Command("whisper"))
async def remove_key_handler(message: Message):
    """Отправить сообщение пользователю по username: /whisper <nickname> <msg>"""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")

    args = message.text.split(maxsplit=2)[1:]
    if len(args) < 2:
        return await message.answer("Usage: /whisper <nickname> <msg>")
    whisper_to = args[0]
    whisper_message = args[1]

    session = await get_session()
    result = await session.execute(select(User).where(User.nickname == whisper_to))
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("User not found", reply_to_message_id=message.message_id)

    telegram_id = user.telegram_id
    try:
        await Bot.send_message(telegram_id, escape_markdown_v2(whisper_message), parse_mode="MarkdownV2")
        logging.info(f"{message.from_user.username} whispered to {whisper_to} next message: {whisper_message}")
        await Bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji="👌")]
        )
    except Exception as e:
        logging.error(e)
        await message.answer(str(e), reply_to_message_id=message.message_id)


@router.message()
async def catch_all(message: Message):
    logging.info(
        f"Unhandled message from user {message.from_user.id}: {message.text!r}"
    )

    await Bot.forward_message(
        chat_id=config.ADMIN_IDS[0],  # кому отправляем
        from_chat_id=message.chat.id,  # откуда
        message_id=message.message_id  # какое сообщение
    )


def init_bot_instance_admin(bot: aiogram.Bot):
    global Bot
    Bot = bot

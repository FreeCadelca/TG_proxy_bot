from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
import datetime

from sqlalchemy import select

from db.database import get_user_by_identifier, generate_invite, add_key, confirm_payment, add_key_to_queue
from db.models import User  # Для list_mappings
from config import config
from db.database import AsyncSessionLocal  # Для сессии в list_mappings
from handlers.user import escape_markdown_v2
from utils.scheduler import daily_check

router = Router()


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


@router.message(Command("daily_check"))
async def manual_daily_check(message: Message):
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    await daily_check(message.bot)  # Передаём bot
    await message.answer("Daily check completed.")


@router.message(Command("admin"))
async def manual_daily_check(message: Message):
    """Выводит информацию о боте и примеры команд."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    response = (
            "Команды для админов:" +
            "/daily_check - сделать срочную проверку счетов (высылается напоминание для должников / проходят оплаты в день сбора)\n" +
            "/list_mappings - вывести таблицу сопоставлений никнеймов и id и юзернеймов\n" +
            "/set_fee <new_fee> - выставить новое значение платы" +
            "/confirm_payment <tg_id|nickname> <amount> - подтвердить перевод, добавить деньги на счёт человека в боте\n" +
            "/add_key <tg_id|nickname> <key_text> - добавить ключ человеку или добавить в очередь на добавление, если он еще не зарегистрировался (в таком случае ключ будет мгновенно добавлен при регистрации чела)\n" +
            "/generate_invite <None|nickname> - сгенерировать инвайт код для нового пользователя. Желательно указать никнейм для нового человека для удобной работы\n"
    )
    await message.answer(response)


@router.message(Command("list_mappings"))
async def list_mappings_handler(message: Message):
    """Вывод таблицы сопоставлений nickname - tg_id."""
    if not await is_admin(message.from_user.id):
        return await message.answer("Доступ только для админов.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.nickname))
        users = result.scalars().all()
    if not users:
        return await message.answer("Нет пользователей.")
    table = "| Nickname | TG ID | Username |\n"
    for user in users:
        table += f"| {user.nickname or 'N/A'} | {user.telegram_id} | {user.username or 'N/A'} |\n"
    await message.answer(table, parse_mode="Markdown")

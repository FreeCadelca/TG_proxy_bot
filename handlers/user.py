import logging
import os
import time
from datetime import datetime

import requests
from aiogram import Router, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db.database import get_user_by_tg_id, add_user, get_invite_by_code, mark_invite_used, get_user_keys, \
    get_user_payments, move_keys_to_user
from config import config

router = Router()


class Registration(StatesGroup):
    invite_code = State()


TextOnButtons = ["🔑 Ключи", "💰 Платежи", "📖 Гайд", "⚙️ Файл конфига", "ℹ️ Помощь️"]

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=TextOnButtons[0]), KeyboardButton(text=TextOnButtons[1])],
        [KeyboardButton(text=TextOnButtons[2]), KeyboardButton(text=TextOnButtons[3])],
        [KeyboardButton(text=TextOnButtons[4])],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    input_field_placeholder="Выберите действие 🔽"
)


# === обработчики кнопок ===
@router.message(lambda msg: msg.text == TextOnButtons[0])
async def keys_btn_handler(message: types.Message):
    await keys_handler(message)


@router.message(lambda msg: msg.text == TextOnButtons[1])
async def payments_btn_handler(message: types.Message):
    await payments_handler(message)


@router.message(lambda msg: msg.text == TextOnButtons[2])
async def guide_btn_handler(message: types.Message):
    await guide_handler(message)


@router.message(lambda msg: msg.text == TextOnButtons[3])
async def help_btn_handler(message: types.Message):
    await config_handler(message)


@router.message(lambda msg: msg.text == TextOnButtons[4])
async def config_btn_handler(message: types.Message):
    await help_bot_handler(message)


# @router.message(lambda msg: msg.text == TextOnButtons[5])
# async def netstat_btn_handler(message: types.Message):
#     period = '1d'
#     try:
#         image_path = await get_graph_image(period)
#         photo = FSInputFile(image_path)
#         await message.reply_photo(photo=photo, reply_markup=main_keyboard)
#     except Exception as e:
#         await message.answer(f"Error: {str(e)}")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработка /start: Проверка регистрации, автодобавление админа, FSM для invite."""
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)
    if user:
        response = ("Используйте команды:\n"
                    "/keys, /payments, /help, /config, /guide")
        await message.answer(response, reply_markup=main_keyboard)
        return

    # Автодобавление, если админ (простая проверка для безопасности)
    if tg_id in config.ADMIN_IDS:
        try:
            index = config.ADMIN_IDS.index(tg_id)
            nickname = config.ADMIN_NICKNAMES[index]  # Берём соответствующий nick
        except (IndexError, ValueError):
            # Fallback если mismatch или not found (безопасность: не крашим)
            nickname = "admin_" + str(tg_id)
            logging.warning(f"Fallback nickname for admin {tg_id}: {nickname} (check ADMIN_NICKNAMES)")

        user_id = await add_user(
            tg_id=tg_id,
            username=message.from_user.username,
            nickname=nickname  # Теперь из config/fallback
        )
        if user_id:
            await message.answer("Авторегистрация админа успешна! Добро пожаловать."
                                 "\nДля помощи по боту используйте /help", reply_markup=main_keyboard)
        else:
            await message.answer("Ошибка авторегистрации админа.")
        return

    # Для обычных — invite
    await state.set_state(Registration.invite_code)
    await message.answer("Введите invite-код для регистрации (вам должны были прислать его)")


@router.message(Registration.invite_code)
async def process_invite(message: Message, state: FSMContext):
    """Валидация invite и регистрация с nickname."""
    try:
        code = message.text.strip()
    except AttributeError:
        await message.answer("Это не то, что я прошу...")
        return
    invite = await get_invite_by_code(code)
    if invite:
        user_id = await add_user(message.from_user.id, message.from_user.username, invite.nickname)
        if user_id:
            # Используем telegram_id для mark_invite_used и user_id для move_keys_to_user
            if await mark_invite_used(code, message.from_user.id):
                moved_count = await move_keys_to_user(invite.nickname, user_id)
                await state.clear()
                response = ("Регистрация успешна! Добро пожаловать ☺️\n"
                            "Для помощи по боту используйте /help")
                if moved_count > 0:
                    response += f"\nВам автоматически добавлено {moved_count} ключ(ей) из очереди."
                await message.answer(response, reply_markup=main_keyboard)
            else:
                await message.answer("Ошибка при пометке invite-кода как использованного.")
        else:
            await message.answer("Ошибка регистрации (возможно, duplicate nickname).")
    else:
        await message.answer("Неверный или истёкший invite-код.")


# Простая функция для экранирования MarkdownV2
def escape_markdown_v2(text: str) -> str:
    """Экранировать спецсимволы для Telegram MarkdownV2."""
    special_chars = r'_[]()~`>#*+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


@router.message(Command("keys"))
async def keys_handler(message: Message):
    """Показать ключи (всегда доступно)."""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        return await message.answer("Вы не зарегистрированы.")
    keys = await get_user_keys(user.id)
    if not keys:
        return await message.answer("У вас нет ключей((( Попросите администраторов добавить их вам")

    responses = ["Ваши ключи 🔑:"]

    for i, k in enumerate(keys):
        if k.tag:
            responses.append(
                f"{i + 1} ключ \(tag: {escape_markdown_v2(k.tag)}\):\n```{escape_markdown_v2(k.key_text)}```")
        else:
            responses.append(f"{i + 1} ключ:\n```{escape_markdown_v2(k.key_text)}```")
    for response in responses:
        await message.answer(response, parse_mode="MarkdownV2", reply_markup=main_keyboard)


@router.message(Command("payments"))
async def payments_handler(message: Message):
    """Показать оплаты, balance, fee, phones."""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        return await message.answer("Вы не зарегистрированы.")
    payments = await get_user_payments(user.id)
    response = (f""
                f"💰 Ваш баланс 💰: {user.balance} руб.\n"
                f"Текущая сумма сбора: {config.MONTHLY_FEE} руб./мес.\n"
                f"Номера для перевода: {', '.join(config.ADMIN_PHONES)}\n"
                f"Текущий день месяца для сбора: {config.PAYMENT_DAY}\n"
                f"\n"
                f"История оплат:\n")
    for p in payments:
        status = "Оплачено ✅" if p.paid else "Не оплачено ❌"
        response += f"{p.month_year}: {status} ({p.amount} руб.)\n"
    await message.answer(response, reply_markup=main_keyboard)


@router.message(Command("guide"))
async def guide_handler(message: Message):
    """Отправить ссылку на help gist."""
    await message.answer(f"📖 Гайд по подключению 📖: {config.HELP_GIST_URL}", reply_markup=main_keyboard)


@router.message(Command("help"))
async def help_bot_handler(message: Message):
    """Выводит информацию о боте и примеры команд."""
    await message.answer(config.HELP_TEXT, reply_markup=main_keyboard)


@router.message(Command("config"))
async def config_handler(message: Message):
    """Отправить ссылку на config gist."""
    await message.answer(f"Конфиг для роутинга: {config.CONFIG_GIST_URL}", reply_markup=main_keyboard)


async def get_graph_image(period: str):
    # Сначала проверка на то, что зарендеренный ответ уже закеширован
    image_path = f"cached_charts/traffic_{period}.png"
    image_path = image_path.replace('/', os.sep)

    if os.path.exists(image_path):
        mtime = os.path.getmtime(image_path)
        age = time.time() - mtime
        if age <= config.CACHE_TTL:
            return image_path
    # Если нет в кеше или он не свежий, то создаем сессию и авторизуемся
    session = requests.Session()
    login_data = {
        "name": config.ZABBIX_USER,
        "password": config.ZABBIX_PASS,
        "enter": "Sign in"
    }
    login_response = session.post(f"{config.ZABBIX_URL}/index.php", data=login_data)
    if 'zbx_session' not in session.cookies or 'index.php?form_refresh' in login_response.url:
        raise Exception("Login failed. Check credentials, Zabbix URL, or version specifics.")

    # URL для графика
    chart_url = (
        f"{config.ZABBIX_URL}/chart2.php?"
        f"graphid={config.ZABBIX_NETWORK_CHART_ID}&"
        f"from=now-{period}&to=now&width=1200&height=400&"
        f"legend=1&profileIdx=web.dashboard.filter&profileIdx2=0&outer=1&widget_view=1"
    )

    response = session.get(chart_url)

    if response.status_code == 200 and response.headers['Content-Type'] == 'image/png':
        with open(image_path, "wb") as f:
            f.write(response.content)
        return image_path
    else:
        raise Exception(f"Failed to get graph image: {response.status_code} - {response.text}")


# @router.message(Command("netstat"))
# async def netstat_handler(message: Message):
#     """Запросить график сетевой загруженности: /netstat <period>, period=1h|6h|1d|7d, default=1d"""
#     args = message.text.split()[1:]
#     period = '1d'
#     if len(args) >= 1:
#         if args[0] in ('1h', '6h', '1d', '7d'):
#             period = args[0]
#         else:
#             return await message.answer(
#                 f"Неверный период. Выберите один из 1h/6h/1d/7d, по умолчанию - 1d",
#                 reply_markup=main_keyboard
#             )
#     try:
#         image_path = await get_graph_image(period)
#         photo = FSInputFile(image_path)
#         await message.reply_photo(photo=photo, reply_markup=main_keyboard)
#     except Exception as e:
#         await message.answer(f"Error: {str(e)}")

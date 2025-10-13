import logging

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db.database import get_user_by_tg_id, add_user, get_invite_by_code, mark_invite_used, get_user_keys, \
    get_user_payments, move_keys_to_user
from config import HELP_GIST_URL, CONFIG_GIST_URL, MONTHLY_FEE, ADMIN_PHONES, ADMIN_IDS, ADMIN_NICKNAMES, PAYMENT_DAY

router = Router()


class Registration(StatesGroup):
    invite_code = State()


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработка /start: Проверка регистрации, автодобавление админа, FSM для invite."""
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)
    if user:
        response = ("Вы уже зарегистрированы. Используйте команды:\n"
                    "/keys, /payments, /help, /config.\n"
                    "Администраторские команды:\n"
                    "/generate_invite, /add_key <key_text>, /confirm_payment, "
                    "/set_fee <new_fee>, /list_users, /list_mappings")
        await message.answer(response)
        return

    # Автодобавление, если админ (простая проверка для безопасности)
    if tg_id in ADMIN_IDS:
        try:
            index = ADMIN_IDS.index(tg_id)
            nickname = ADMIN_NICKNAMES[index]  # Берём соответствующий nick
        except (IndexError, ValueError):
            # Fallback если mismatch или not found (безопасность: не крашим)
            nickname = "admin_" + str(tg_id)
            logging.warning(f"Fallback nickname for admin {tg_id}: {nickname} (check ADMIN_NICKNAMES)")

        user = await add_user(
            tg_id=tg_id,
            username=message.from_user.username,
            nickname=nickname  # Теперь из config/fallback
        )
        if user:
            await message.answer("Авторегистрация админа успешна! Добро пожаловать.")
        else:
            await message.answer("Ошибка авторегистрации админа.")
        return

    # Для обычных — invite
    await state.set_state(Registration.invite_code)
    await message.answer("Введите invite-код для регистрации.")


@router.message(Registration.invite_code)
async def process_invite(message: Message, state: FSMContext):
    """Валидация invite и регистрация с nickname."""
    code = message.text.strip()
    invite = await get_invite_by_code(code)
    if invite:
        user = await add_user(message.from_user.id, message.from_user.username, invite.nickname)
        if user:
            await mark_invite_used(code, user.id)
            # Переносим ключи из очереди
            moved_count = await move_keys_to_user(invite.nickname, user.id)
            await state.clear()
            response = "Регистрация успешна! Добро пожаловать."
            if moved_count > 0:
                response += f"\nВам автоматически добавлено {moved_count} ключ(ей) из очереди."
            await message.answer("Регистрация успешна! Добро пожаловать.")
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
        return await message.answer("У вас нет ключей.")
    response = ("Ваши ключи:\n\n" +
                "\n\n".join([f"{i + 1} Ключ:\n```{escape_markdown_v2(k.key_text)}```" for i, k in enumerate(keys)]))
    await message.answer(response, parse_mode="MarkdownV2")


@router.message(Command("payments"))
async def payments_handler(message: Message):
    """Показать оплаты, balance, fee, phones."""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        return await message.answer("Вы не зарегистрированы.")
    payments = await get_user_payments(user.id)
    response = (f""
                f"Ваш баланс: {user.balance} руб.\n"
                f"Текущая цена: {MONTHLY_FEE} руб./мес.\n"
                f"Номера для перевода: {', '.join(ADMIN_PHONES)}\n"
                f"Текущий день месяца начала сбора: {PAYMENT_DAY}\n"
                f"\n"
                f"История оплат:\n")
    for p in payments:
        status = "Оплачено" if p.paid else "Не оплачено"
        response += f"{p.month_year}: {status} ({p.amount} руб.)\n"

    # Inline kb для удобства (e.g. кнопка обновить)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Обновить", callback_data="refresh_payments")]])
    await message.answer(response, reply_markup=kb)


@router.callback_query(F.data == "refresh_payments")
async def refresh_payments(callback: CallbackQuery):
    """Callback для обновления /payments."""
    # Повторить логику payments_handler
    await callback.message.edit_text("Обновляю...")  # Placeholder, реализуй полную


@router.message(Command("help"))
async def help_handler(message: Message):
    """Отправить ссылку на help gist."""
    await message.answer(f"Гайд по подключению: {HELP_GIST_URL}")


@router.message(Command("config"))
async def config_handler(message: Message):
    """Отправить ссылку на config gist."""
    await message.answer(f"Конфиг для роутинга: {CONFIG_GIST_URL}")

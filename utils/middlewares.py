import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import config
from db.database import get_user_by_tg_id
from handlers.user import Registration


def is_start_command(message: Message) -> bool:
    """Проверить, что сообщение - команда /start (в т.ч. /start@bot_name и /start <payload>)."""
    if not message.text:
        return False
    command = message.text.split(maxsplit=1)[0]
    return command.split("@", maxsplit=1)[0] == "/start"


class RegisteredOnlyMiddleware(BaseMiddleware):
    """Пропускает к обработчикам только зарегистрированных пользователей и админов.

    Незарегистрированным доступны только /start и ввод invite-кода (состояние Registration.invite_code),
    остальные их сообщения не обрабатываются и не пересылаются админу.
    """

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        tg_user = event.from_user
        if tg_user is None:  # Например, посты каналов - их не обрабатываем
            return None

        if tg_user.id in config.ADMIN_IDS:
            return await handler(event, data)

        if is_start_command(event) or data.get("raw_state") == Registration.invite_code.state:
            return await handler(event, data)

        if await get_user_by_tg_id(tg_user.id):
            return await handler(event, data)

        logging.info(f"Ignored message from unregistered user {tg_user.id} in chat {event.chat.id}")
        if event.chat.type == "private":
            await event.answer("Вы не зарегистрированы. Для регистрации отправьте /start")
        return None

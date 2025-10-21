import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import create_engine, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import List

from .models import Base, User, Invite, Key, KeyInQueue, Payment
from config import config

# Async engine для aiogram (требует async-драйвер, e.g. aiosqlite для SQLite)
engine = create_async_engine(config.DB_URL, echo=False)  # echo=True для debug SQL
AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)


async def init_db():
    """Инициализация БД (create tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Возвращает AsyncSession для работы с БД."""
    return AsyncSessionLocal()


# --- User operations ---

async def get_user_by_tg_id(tg_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        return result.scalar_one_or_none()


async def get_user_by_nickname(nickname: str) -> User | None:
    """Получить пользователя по nickname."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        return result.scalar_one_or_none()


async def get_user_by_identifier(identifier: str) -> User | None:
    """Получить пользователя по tg_id (int) или nickname (str)."""
    try:
        tg_id = int(identifier)
        user = await get_user_by_tg_id(tg_id)
        if user:
            return user
    except ValueError:
        pass  # Не int, пробуем nickname
    user = await get_user_by_nickname(identifier)
    if not user:
        logging.warning(f"User not found by identifier: {identifier}")
    return user


async def add_user(tg_id: int, username: str, nickname: str) -> int | None:
    """Добавить пользователя с nickname."""
    async with AsyncSessionLocal() as session:
        user = User(telegram_id=tg_id, username=username, nickname=nickname)
        session.add(user)
        try:
            await session.commit()
            await session.refresh(user)  # Гарантируем, что ID доступен
            logging.info(f"User added: telegram_id={tg_id}, nickname={nickname}")
            return user.id
        except IntegrityError:
            await session.rollback()
            logging.warning(f"Duplicate nickname or tg_id: {nickname}/{tg_id}")
            return None


async def update_balance(user_id: int, amount: int):
    """Обновить баланс (добавление суммы)."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.balance += amount
            await session.commit()


# --- Invite operations ---

async def generate_invite(created_by: int, nickname: str, expires_in_days: int = 7) -> str:
    """Генерировать invite-код с nickname."""
    if not nickname:
        raise ValueError("Nickname required for invite")
    code = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    async with AsyncSessionLocal() as session:
        invite = Invite(code=code, nickname=nickname, created_by=created_by, expires_at=expires_at)
        session.add(invite)
        await session.commit()
        return code


async def validate_invite(code: str) -> bool:
    """Валидировать и пометить как used."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Invite).where(Invite.code == code, Invite.used_by.is_(None)))
        invite = result.scalar_one_or_none()
        if invite and (invite.expires_at is None or invite.expires_at > datetime.utcnow()):
            # Пометить как used (обновим used_by позже при регистрации)
            return True
        logging.warning(f"Invalid or expired invite code: {code}")
        return False


async def get_invite_by_code(code: str) -> Invite | None:
    """Получить invite по code."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Invite).where(Invite.code == code, Invite.used_by.is_(None)))
        invite = result.scalar_one_or_none()
        if invite and (invite.expires_at is None or invite.expires_at > datetime.utcnow()):
            return invite
        logging.warning(f"Invalid or expired invite code: {code}")
        return None


async def mark_invite_used(code: str, telegram_id: int):
    """Пометить invite-код как использованный, привязав к telegram_id."""
    async with AsyncSessionLocal() as session:
        # Находим invite
        invite = await session.execute(select(Invite).where(Invite.code == code, Invite.used_by.is_(None)))
        invite = invite.scalar_one_or_none()
        if not invite:
            logging.warning(f"Invite code {code} not found or already used")
            return False

        # Находим пользователя по telegram_id
        user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user.scalar_one_or_none()
        if not user:
            logging.warning(f"User with telegram_id {telegram_id} not found")
            return False

        # Обновляем invite
        invite.used_by = user.id
        try:
            await session.commit()
            logging.info(f"Invite {code} marked as used by telegram_id {telegram_id}")
            return True
        except IntegrityError:
            await session.rollback()
            logging.error(f"Failed to mark invite {code} as used")
            return False


# --- Key operations ---

async def add_key(user_id: int, key_text: str, tag=None) -> bool:
    """Добавить ключ (check на лимит 5)."""
    async with AsyncSessionLocal() as session:
        # Переносим существующие ключи из KeyInQueue, если есть (для nickname)
        user = await session.get(User, user_id)
        if user:
            await move_keys_to_user(user.nickname, user_id)  # Переносим перед добавлением
        # Check count
        count = await session.scalar(select(func.count()).select_from(Key).where(Key.user_id == user_id))
        if count >= 5:
            logging.warning(f"Key limit reached for user {user_id}")
            return False
        key = Key(user_id=user_id, key_text=key_text, tag=tag)
        session.add(key)

        try:
            await session.commit()
            logging.info(f"Key added for user_id {user_id}")
            return True
        except IntegrityError:
            await session.rollback()
            logging.warning(f"Failed to add key for user_id {user_id}")
            return False


async def get_user_keys(user_id: int) -> List[Key]:
    """Получить ключи пользователя."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Key).where(Key.user_id == user_id))
        return result.scalars().all()


async def add_key_to_queue(nickname: str, key_text: str, tag=None) -> bool:
    """Добавить ключ в очередь для nickname."""
    async with AsyncSessionLocal() as session:
        key = KeyInQueue(nickname=nickname, key_text=key_text, tag=tag)
        session.add(key)
        try:
            await session.commit()
            logging.info(f"Key added to queue for nickname {nickname}")
            return True
        except IntegrityError:
            await session.rollback()
            logging.warning(f"Failed to add key to queue for nickname {nickname}")
            return False


async def get_keys_in_queue_by_nickname(nickname: str) -> List[KeyInQueue]:
    """Получить все ключи в очереди для nickname."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(KeyInQueue).where(KeyInQueue.nickname == nickname))
        return result.scalars().all()


async def move_keys_to_user(nickname: str, user_id: int) -> int:
    """Перенести ключи из KeyInQueue в Key для нового user_id. Возвращает кол-во перенесённых."""
    async with AsyncSessionLocal() as session:
        keys = await get_keys_in_queue_by_nickname(nickname)
        moved_count = 0
        for key_in_queue in keys:
            # Проверяем лимит 3 ключа
            current_count = await session.scalar(select(func.count()).select_from(Key).where(Key.user_id == user_id))
            if current_count >= 5:
                logging.warning(f"Key limit reached for user_id {user_id}, skipping key transfer")
                break
            # Переносим
            new_key = Key(user_id=user_id, key_text=key_in_queue.key_text, tag=key_in_queue.tag)
            session.add(new_key)
            await session.delete(key_in_queue)  # Удаляем из очереди
            moved_count += 1
        try:
            await session.commit()
            if moved_count > 0:
                logging.info(f"Moved {moved_count} keys from queue to user_id {user_id} for nickname {nickname}")
            return moved_count
        except IntegrityError:
            await session.rollback()
            logging.error(f"Failed to move keys for user_id {user_id}, nickname {nickname}")
            return 0


# --- Payment operations ---

async def get_or_create_payment(user_id: int, month_year: str) -> Payment:
    """Получить или создать payment для месяца."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Payment).where(Payment.user_id == user_id, Payment.month_year == month_year))
        payment = result.scalar_one_or_none()
        if not payment:
            payment = Payment(user_id=user_id, month_year=month_year, amount=config.MONTHLY_FEE)
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
        return payment


async def close_payment(user_id: int, month_year: str) -> None:
    """Закрыть payment для месяца."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Payment).where(Payment.user_id == user_id, Payment.month_year == month_year)
        )
        payment = result.scalar_one_or_none()
        payment.paid = True
        # payment.confirmed_at = datetime.now()
        await session.commit()



async def confirm_payment(user_id: int, amount: int, month_year: str, admin_username: str) -> bool:
    """Подтвердить платёж: добавить к балансу, mark paid если хватает."""
    await update_balance(user_id, amount)
    payment = await get_or_create_payment(user_id, month_year)
    if not payment.paid:
        # Здесь логика: Если баланс после добавления >= amount, то paid (но поскольку автосписание в scheduler, здесь просто добавляем)
        # payment.confirmed_at = datetime.utcnow()
        await AsyncSessionLocal().commit()  # Note: Лучше в одной сессии, но для примера
    # Уведомление юзеру шлётся в handler
    return True


async def get_user_payments(user_id: int, limit: int = 6) -> List[Payment]:
    """Получить последние оплаты (для /payments)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.month_year.desc()).limit(limit)
        )
        return result.scalars().all()

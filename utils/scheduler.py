import logging
from datetime import datetime, timedelta
from decimal import Decimal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from db.database import AsyncSessionLocal, update_balance, get_or_create_payment, get_session
from db.models import User, Payment  # Для query
from config import PAYMENT_DAY, REMIND_BEFORE_DAYS, REMIND_INTERVAL_DAYS, MONTHLY_FEE, ADMIN_PHONES

# Нужно bot instance - передадим при init

scheduler = AsyncIOScheduler()


async def daily_check(bot):
    """Ежедневная проверка: списания и напоминания."""
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    # Если сегодня payment_day - попробовать списать
    if now.day == PAYMENT_DAY:
        async with (await get_session()) as session:
            users = await session.execute(select(User))
            for user in users.scalars().all():
                payment = await get_or_create_payment(user.id, current_month)
                if not payment.paid and user.balance >= Decimal(str(MONTHLY_FEE)):
                    user.balance -= Decimal(str(MONTHLY_FEE))
                    payment.paid = True
                    payment.amount = Decimal(str(MONTHLY_FEE))
                    payment.confirmed_at = now
                    await session.commit()
                    logging.info(f"Charged {MONTHLY_FEE} for user {user.id}")
                    if user.balance < 0:
                        logging.warning(f"Negative balance after charge: {user.balance}")

    # Проверка напоминаний для всех users
    payment_date = datetime(now.year, now.month, PAYMENT_DAY)
    days_to_payment = (payment_date - now).days
    async with (await get_session()) as session:
        users = await session.execute(select(User))
        for user in users.scalars().all():
            payment = await get_or_create_payment(user.id, current_month)
            if not payment.paid:
                needed = Decimal(str(MONTHLY_FEE)) - user.balance
                if needed > 0:
                    # Условие для напоминания
                    if days_to_payment <= REMIND_BEFORE_DAYS or (now - (
                            payment.confirmed_at or now - timedelta(days=REMIND_INTERVAL_DAYS + 1))) >= timedelta(
                        days=REMIND_INTERVAL_DAYS):
                        await bot.send_message(user.telegram_id,
                                               f"Напоминание: Недостаёт {needed} руб. для оплаты за {current_month}. Пополните на {', '.join(ADMIN_PHONES)}.")
                        # Update last remind time? Можно добавить поле last_remind в Payment
                        payment.confirmed_at = now  # Reuse для last_remind, или добавь поле


def init_scheduler(bot):
    """Инициализация scheduler."""
    scheduler.add_job(daily_check, 'cron', hour=0, minute=0, args=(bot,))
    scheduler.start()

import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from db.database import update_balance, get_or_create_payment, get_session, close_payment
from db.models import User
from config import config

from dotenv import load_dotenv

load_dotenv()
scheduler = AsyncIOScheduler()


async def is_nex_day_is_payment():
    current_date = datetime.now()
    delta = timedelta(days=1)
    return (current_date + delta).day == config.PAYMENT_DAY


async def daily_check(bot):
    """Ежедневная проверка: списания и напоминания только в день оплаты (PAYMENT_DAY).

    Логика:
    - Вычисляем days_to_payment для проверки дня оплаты.
    - Для каждого пользователя:
      - Получаем или создаём payment для текущего месяца.
      - Если день оплаты:
        - Если средств хватает и не оплачено: списываем, отмечаем paid=True, commit.
        - Если средств не хватает и не оплачено: отправляем напоминание.
    - Добавлены логи для отладки и try-except для безопасности.
    - Анализ: После commit объекты могут стать detached, поэтому сохраняем нужные значения (user_id, telegram_id, needed) до commit.
    """
    logging.info(f"Daily check started at {datetime.now(timezone.utc)}")
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    logging.info(f"Current day: {now.day}, Payment day: {config.PAYMENT_DAY}")

    # Открываем сессию
    session = await get_session()

    try:
        users = await session.execute(select(User))
        for user in users.scalars().all():
            user_id = user.id  # Сохраняем id заранее
            telegram_id = user.telegram_id  # Сохраняем telegram_id заранее
            logging.info(f"Processing User {user_id}: Balance {user.balance}, Monthly fee {config.MONTHLY_FEE}")

            payment = await get_or_create_payment(user_id, current_month)
            payment_amount = payment.amount

            logging.info(f"Processing payment for {current_month}: Paid {payment.paid}, Amount {payment.amount}")

            # Проверяем, день оплаты ли. Если да, то списываем плату у человека, если он еще не оплатил
            # (хотя скорее всего, из-за вызова функции 1 раз в день, он еще не успеет оплатить)
            if datetime.now().day == config.PAYMENT_DAY and not payment.paid:
                try:
                    # Списание, (даже если средств хватает)
                    if not payment.paid:
                        new_balance = user.balance - payment_amount

                        await update_balance(user_id, -payment_amount)
                        await session.refresh(user)  # синхронизируем изменения, которые были закоммичены в user
                        await close_payment(user_id, current_month)

                        logging.info(f"Charged {payment_amount} for user {user_id}, new balance {new_balance}")
                        await bot.send_message(
                            telegram_id,
                            f"Списано {payment_amount} руб. за {current_month}. Баланс: {new_balance} руб."
                        )
                except Exception as e:
                    await session.rollback()
                    logging.error(f"Error daily processing (pd) user {user_id}: {str(e)}")

            # Проверяем, следующий день - день оплаты? Если да и у пользователя не хватает средств,
            # то напоминаем ему о пополнении на недостающую сумму
            if await is_nex_day_is_payment():
                try:
                    if user.balance < config.MONTHLY_FEE:
                        logging.info(f"Sent reminder (nd) to user {user_id} for user")
                        await bot.send_message(
                            telegram_id,
                            f"🔔 Напоминание 🔔: завтра произойдет списание на сумму {payment_amount} руб. за {current_month}. \n"
                            f"Ваш баланс: {user.balance} руб., текущая сумма сбора: {config.MONTHLY_FEE} руб."
                        )
                except Exception as e:
                    logging.error(f"Error daily processing (nd) user {user_id}: {str(e)}")

            # Если баланс человека отрицательный - напоминаем о долге
            await session.refresh(user)
            if user.balance < 0 and datetime.now().day % 3 == 0:
                needed = -user.balance
                logging.info(f"Debt for user {user_id}: {needed} on {now}")
                await bot.send_message(
                    telegram_id,
                    f"🔔 Напоминание 🔔: отрицательный баланс, пополните счёт на {needed} руб. (/payments) 🙃\n"
                )
                logging.info(f"Sent reminder to user {user_id}, needed {needed}")
    finally:
        await session.close()  # Закрываем сессию явно для безопасности


def init_scheduler(bot):
    """Инициализация scheduler."""
    scheduler.add_job(daily_check, 'cron', hour=18, minute=0, args=(bot,))
    scheduler.start()

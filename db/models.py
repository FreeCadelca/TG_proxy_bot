from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.types import DECIMAL

Base = declarative_base()

class User(Base):
    """Модель пользователя."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    nickname = Column(String, unique=True, index=True, nullable=True)  # Ник от админа, unique
    is_admin = Column(Boolean, default=False)
    balance = Column(DECIMAL(precision=10, scale=2), default=Decimal("0.00"))
    registered_at = Column(DateTime, default=datetime.now(timezone.utc))

    keys = relationship("Key", back_populates="user")
    payments = relationship("Payment", back_populates="user")

class Invite(Base):
    """Модель invite-кодов."""
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    nickname = Column(String, nullable=False)  # Ник, назначенный админом
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=True)

class Key(Base):
    """Модель ключей (до 3 на user)."""
    __tablename__ = "keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_text = Column(Text, nullable=False)
    added_at = Column(DateTime, default=datetime.now(timezone.utc))

    user = relationship("User", back_populates="keys")

class Payment(Base):
    """Модель оплат (история по месяцам)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    month_year = Column(String, nullable=False)
    paid = Column(Boolean, default=False)
    amount = Column(DECIMAL(precision=10, scale=2), default=Decimal("0.00"))
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")
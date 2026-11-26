import os
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str]
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountToken(Base):
    __tablename__ = "account_tokens"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionToken(Base):
    __tablename__ = "user_sessions"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(90), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str]
    role: Mapped[str] = mapped_column(String(10))
    visible: Mapped[bool]


class Buyer(Base):
    __tablename__ = "internal_buyers"

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), unique=True)

class Credential(Base):
    __tablename__ = "agent_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    owner: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(16))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Service(Base):
    __tablename__ = "agent_services"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str]
    price_cents: Mapped[int | None]
    delivery_days: Mapped[int]
    country: Mapped[str] = mapped_column(String(2))
    language: Mapped[str] = mapped_column(String(12))


engine = create_engine(os.getenv("DATABASE_URL", "postgresql+psycopg:///agentrelai_dev"), pool_pre_ping=True)
Database = sessionmaker(engine, expire_on_commit=False)

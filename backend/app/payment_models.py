from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .auth import now
from .db import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("order_id"), CheckConstraint("amount_cents > 0"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"))
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(default="USD")
    provider: Mapped[str]
    status: Mapped[str] = mapped_column(default="AWAITING_CHECKOUT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    provider: Mapped[str]
    event_id: Mapped[UUID]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LedgerEntry(Base):
    __tablename__ = "financial_ledger"
    __table_args__ = (UniqueConstraint("event_id", "account"), CheckConstraint("signed_cents <> 0"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("payment_events.id"), index=True)
    account: Mapped[str]
    currency: Mapped[str]
    signed_cents: Mapped[int]

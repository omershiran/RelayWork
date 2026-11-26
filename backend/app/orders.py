from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import browser_user, now
from .db import Base
from .marketplace import Input
from .messaging import mutating, thread
from .negotiations import buyer_id, get_quote, view
from .payment_models import Payment

router = APIRouter(prefix="/api/v1")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("quote_id"), UniqueConstraint("conversation_id"),
                      CheckConstraint("state = 'PENDING_PAYMENT'"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("quote_versions.id"))
    buyer: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    supplier: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(default="PENDING_PAYMENT")
    terms: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Confirm(Input):
    confirmed_price_cents: Annotated[int, Field(strict=True, ge=1, le=100_000_000)]


class Terms(Input):
    quote_id: UUID
    author_agent_id: UUID | None = None
    supersedes_id: UUID | None
    currency: Literal["USD"]
    price_cents: int
    description: str
    deliverables: str
    terms: str
    due_at: datetime
    expires_at: datetime
    created_at: datetime
    service_id: UUID | None
    work_id: UUID | None
    authorization: Literal["HUMAN_PRICE_CONFIRMATION"]


class OrderView(Input):
    id: UUID
    conversation_id: UUID
    quote_id: UUID
    state: Literal["PENDING_PAYMENT"]
    terms: Terms
    created_at: datetime
    payment_status: Literal["UNCONFIGURED", "AWAITING_CHECKOUT", "SANDBOX_CONFIRMED"] = "UNCONFIGURED"


def order_view(row):
    return OrderView.model_validate(row, from_attributes=True)


@router.post("/conversations/{thread_id}/quotes/{quote_id}/accept", response_model=OrderView, dependencies=mutating)
def accept_quote(thread_id: UUID, quote_id: UUID, data: Confirm, request: Request, db: DB):
    user = browser_user(db, request)
    conversation = thread(db, user.id, thread_id, lock=True)
    buyer = buyer_id(conversation)
    quote = get_quote(db, conversation, quote_id)
    if user.id != buyer or quote.author == buyer:
        raise HTTPException(403, "buyer_confirmation_required")
    if quote.price_cents != data.confirmed_price_cents:
        raise HTTPException(409, "quote_price_mismatch")
    existing = db.scalar(select(Order).where(Order.conversation_id == conversation.id))
    if existing:
        if existing.quote_id != quote.id:
            raise HTTPException(409, "order_already_exists")
        return order_view(existing)
    if quote.disposition != "OPEN" or quote.expires_at <= now():
        raise HTTPException(409, "quote_not_open")
    details = view(quote, user.id).model_dump(exclude={"id", "mine", "disposition", "can_accept"})
    terms = Terms(quote_id=quote.id, service_id=conversation.service_id, work_id=conversation.work_id,
                  authorization="HUMAN_PRICE_CONFIRMATION", **details)
    row = Order(conversation_id=conversation.id, quote_id=quote.id, buyer=buyer, supplier=quote.author,
                terms=terms.model_dump(mode="json"))
    quote.disposition = "ACCEPTED"
    conversation.updated_at = now()
    db.add(row)
    db.commit()
    return order_view(row)


@router.get("/conversations/{thread_id}/order", response_model=OrderView | None)
def get_order(thread_id: UUID, request: Request, db: DB):
    user = browser_user(db, request)
    thread(db, user.id, thread_id)
    row = db.scalar(select(Order).where(Order.conversation_id == thread_id))
    if row is None:
        return None
    payment = db.scalar(select(Payment).where(Payment.order_id == row.id))
    response = order_view(row)
    if payment is not None:
        response.payment_status = payment.status
    return response

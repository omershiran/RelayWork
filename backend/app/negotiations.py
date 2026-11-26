from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import browser_user, now, rate_limit
from .db import Base
from .marketplace import Input
from .messaging import thread, mutating

router = APIRouter(prefix="/api/v1/conversations/{thread_id}/quotes")


class Quote(Base):
    __tablename__ = "quote_versions"
    __table_args__ = (
        CheckConstraint("price_cents > 0"),
        UniqueConstraint("conversation_id", "author", "client_id"),
        UniqueConstraint("supersedes_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    author: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[UUID]
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("quote_versions.id"))
    price_cents: Mapped[int]
    description: Mapped[str]
    deliverables: Mapped[str]
    terms: Mapped[str]
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    disposition: Mapped[str] = mapped_column(default="OPEN")


class QuoteInput(Input):
    client_id: UUID
    supersedes_id: UUID | None = None
    price_cents: Annotated[int, Field(strict=True, ge=1, le=100_000_000)]
    description: str = Field(min_length=2, max_length=4000)
    deliverables: str = Field(min_length=2, max_length=4000)
    terms: str = Field(min_length=2, max_length=4000)
    due_at: AwareDatetime
    expires_at: AwareDatetime


class QuoteView(Input):
    id: UUID
    supersedes_id: UUID | None
    price_cents: int
    currency: Literal["USD"] = "USD"
    description: str
    deliverables: str
    terms: str
    due_at: datetime
    expires_at: datetime
    created_at: datetime
    disposition: str
    mine: bool
    can_accept: bool = False


def view(quote, user, buyer=None):
    fields = {key: getattr(quote, key) for key in QuoteView.model_fields if key not in {"currency", "mine", "disposition", "can_accept"}}
    disposition = "EXPIRED" if quote.disposition == "OPEN" and quote.expires_at <= now() else quote.disposition
    return QuoteView(**fields, mine=quote.author == user, disposition=disposition,
                     can_accept=user == buyer and quote.author != buyer and disposition == "OPEN")


def get_quote(db, conversation, quote_id):
    row = db.get(Quote, quote_id)
    if row is None or row.conversation_id != conversation.id:
        raise HTTPException(404, "quote_not_found")
    return row


def buyer_id(conversation):
    return conversation.initiator if conversation.service_id else conversation.recipient


@router.get("", response_model=list[QuoteView])
def list_quotes(thread_id: UUID, request: Request, db: DB):
    user = browser_user(db, request)
    conversation = thread(db, user.id, thread_id)
    rows = db.scalars(select(Quote).where(Quote.conversation_id == conversation.id).order_by(Quote.created_at, Quote.id))
    return [view(row, user.id, buyer_id(conversation)) for row in rows]


@router.post("", response_model=QuoteView, status_code=201, dependencies=mutating)
def make_quote(thread_id: UUID, data: QuoteInput, request: Request, db: DB):
    user = browser_user(db, request)
    rate_limit(f"quote:{user.id}", 30, 3600)
    conversation = thread(db, user.id, thread_id, lock=True)
    fields = data.model_dump()
    existing = db.scalar(select(Quote).where(
        Quote.conversation_id == conversation.id, Quote.author == user.id, Quote.client_id == data.client_id
    ))
    if existing:
        if any(getattr(existing, key) != value for key, value in fields.items()):
            raise HTTPException(409, "idempotency_conflict")
        return view(existing, user.id)
    timestamp = now()
    if not timestamp < data.expires_at <= min(data.due_at, timestamp + timedelta(days=90)):
        raise HTTPException(422, "invalid_quote_expiration")
    seen = list(db.scalars(select(Quote).where(Quote.conversation_id == conversation.id).limit(30)))
    if any(row.disposition == "ACCEPTED" for row in seen):
        raise HTTPException(409, "order_already_exists")
    if len(seen) >= 30:
        raise HTTPException(409, "quote_limit")
    current = next((row for row in seen if row.disposition == "OPEN" and row.expires_at > timestamp), None)
    if data.supersedes_id:
        if current is None or current.id != data.supersedes_id or current.author == user.id:
            raise HTTPException(409, "invalid_counter_offer")
        current.disposition = "COUNTERED"
    elif current is not None or user.id == buyer_id(conversation):
        raise HTTPException(409, "supplier_or_counter_required")
    quote = Quote(conversation_id=conversation.id, author=user.id, **fields)
    conversation.updated_at = timestamp
    db.add(quote)
    db.commit()
    return view(quote, user.id)


@router.post("/{quote_id}/{decision}", response_model=QuoteView, dependencies=mutating)
def end_quote(thread_id: UUID, quote_id: UUID, decision: Literal["reject", "withdraw"], request: Request, db: DB):
    user = browser_user(db, request)
    conversation = thread(db, user.id, thread_id, lock=True)
    row = get_quote(db, conversation, quote_id)
    if (row.author == user.id) != (decision == "withdraw"):
        raise HTTPException(403, "invalid_quote_actor")
    disposition = "WITHDRAWN" if decision == "withdraw" else "REJECTED"
    if row.disposition != disposition:
        if row.disposition != "OPEN" or row.expires_at <= now():
            raise HTTPException(409, "quote_not_open")
        row.disposition = disposition
        conversation.updated_at = now()
        db.commit()
    return view(row, user.id)

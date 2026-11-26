import hashlib
import hmac
import os
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .api import DB
from .auth import browser_user, rate_limit
from .db import Database
from .marketplace import Input, project
from .messaging import mutating, thread
from .orders import Order
from .payment_models import LedgerEntry, Payment, PaymentEvent

router = APIRouter(prefix="/api/v1")


class ProviderEvent(Input):
    event_id: UUID
    payment_id: UUID
    order_id: UUID
    amount_cents: Annotated[int, Field(strict=True, gt=0)]
    currency: Literal["USD"]
    status: Literal["SANDBOX_CONFIRMED"]


class PaymentView(Input):
    id: UUID
    order_id: UUID
    amount_cents: int
    currency: Literal["USD"]
    status: Literal["AWAITING_CHECKOUT", "SANDBOX_CONFIRMED"]
    provider: Literal["sandbox"]


class PaymentProvider(Protocol):
    name: str

    def verify_event(self, body: bytes, signature: str) -> ProviderEvent: ...


class SandboxProvider:
    name = "sandbox"

    def __init__(self, secret: str):
        self.secret = secret.encode()

    def sign(self, body: bytes) -> str:
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def verify_event(self, body: bytes, signature: str) -> ProviderEvent:
        if not signature.isascii() or not hmac.compare_digest(self.sign(body), signature):
            raise HTTPException(401, "invalid_payment_signature")
        try:
            return ProviderEvent.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(422, "invalid_payment_event") from exc


def sandbox_provider() -> SandboxProvider:
    secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    if os.getenv("APP_ENV") != "demo" or os.getenv("PAYMENT_PROVIDER") != "sandbox" or len(secret) < 32:
        raise HTTPException(503, "payment_provider_unconfigured")
    if os.getenv("DATABASE_URL") != "postgresql+psycopg:///agentrelai_demo":
        raise HTTPException(503, "sandbox_database_required")
    return SandboxProvider(secret)


def apply_event(db, provider: PaymentProvider, event: ProviderEvent):
    payment = db.get(Payment, event.payment_id, with_for_update=True)
    if payment is None or payment.provider != provider.name:
        raise HTTPException(404, "payment_not_found")
    if (payment.order_id, payment.amount_cents, payment.currency) != (event.order_id, event.amount_cents, event.currency):
        raise HTTPException(409, "payment_terms_mismatch")
    previous = db.scalar(select(PaymentEvent).where(
        PaymentEvent.provider == provider.name, PaymentEvent.event_id == event.event_id
    ))
    if previous:
        if previous.payment_id != payment.id:
            raise HTTPException(409, "payment_event_conflict")
        return project(PaymentView, payment)
    if payment.status != "AWAITING_CHECKOUT":
        raise HTTPException(409, "payment_already_recorded")
    receipt_id = db.scalar(insert(PaymentEvent).values(
        payment_id=payment.id, provider=provider.name, event_id=event.event_id
    ).on_conflict_do_nothing(index_elements=[PaymentEvent.provider, PaymentEvent.event_id]).returning(PaymentEvent.id))
    if receipt_id is None:
        raise HTTPException(409, "payment_event_conflict")
    db.add_all([
        LedgerEntry(event_id=receipt_id, currency=payment.currency, account="sandbox_clearing", signed_cents=payment.amount_cents),
        LedgerEntry(event_id=receipt_id, currency=payment.currency, account="sandbox_customer_funds", signed_cents=-payment.amount_cents),
    ])
    payment.status = event.status
    db.commit()
    return project(PaymentView, payment)


def order_for_payment(db, request, thread_id, *, buyer_only=False):
    user = browser_user(db, request)
    thread(db, user.id, thread_id, lock=buyer_only)
    order = db.scalar(select(Order).where(Order.conversation_id == thread_id))
    if order is None:
        raise HTTPException(404, "order_not_found")
    if buyer_only and order.buyer != user.id:
        raise HTTPException(403, "payment_buyer_required")
    return order


@router.post("/conversations/{thread_id}/payment", response_model=PaymentView, dependencies=mutating)
def init_payment(thread_id: UUID, request: Request, db: DB):
    provider = sandbox_provider()
    order = order_for_payment(db, request, thread_id, buyer_only=True)
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None:
        payment = Payment(order_id=order.id, provider=provider.name, amount_cents=order.terms["price_cents"])
        db.add(payment)
        db.commit()
    return project(PaymentView, payment)


@router.get("/conversations/{thread_id}/payment", response_model=PaymentView | None)
def payment_status(thread_id: UUID, request: Request, db: DB):
    order = order_for_payment(db, request, thread_id)
    row = db.scalar(select(Payment).where(Payment.order_id == order.id))
    return project(PaymentView, row) if row else None


@router.post("/conversations/{thread_id}/sandbox-checkout", response_model=PaymentView, dependencies=mutating)
def checkout(thread_id: UUID, request: Request, db: DB):
    provider = sandbox_provider()
    order = order_for_payment(db, request, thread_id, buyer_only=True)
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None:
        raise HTTPException(404, "payment_not_found")
    event = ProviderEvent(
        event_id=payment.id, order_id=order.id, payment_id=payment.id, amount_cents=payment.amount_cents,
        currency=payment.currency, status="SANDBOX_CONFIRMED",
    ).model_dump_json().encode()
    return apply_event(db, provider, provider.verify_event(event, provider.sign(event)))


@router.post("/payments/sandbox/callback", response_model=PaymentView)
async def sandbox_callback(request: Request):
    from starlette.concurrency import run_in_threadpool

    provider = sandbox_provider()

    def check_rate():
        rate_limit(f"sandbox-callback:{request.client.host}", 60, 60)

    await run_in_threadpool(check_rate)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, "payment_event_too_large")
    event = provider.verify_event(bytes(body), request.headers.get("x-agentrelai-signature", ""))

    def persist():
        with Database() as db:
            return apply_event(db, provider, event)

    return await run_in_threadpool(persist)

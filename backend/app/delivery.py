from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import browser_user, now, rate_limit
from .db import Base
from .delivery_file import DeliveryFile, validate_file
from .marketplace import Input, project
from .messaging import mutating, thread
from .orders import Order
from .payment_models import Payment
from .payments import sandbox_provider
from .storage import StorageFull, delivery_storage

router = APIRouter(prefix="/api/v1/conversations/{thread_id}")


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("order_id", "client_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    client_id: Mapped[UUID]
    body: Mapped[str]
    state: Mapped[str]
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agent_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auto_approve_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None]


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id"))
    opened_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeliveryInput(Input):
    client_id: UUID
    body: str = Field(min_length=1, max_length=10000)


class AttachedDeliveryInput(DeliveryInput):
    body: str = Field(default="", max_length=10000)


class Decision(Input):
    action: Literal["approve", "revise", "dispute"]
    reason: str | None = Field(default=None, min_length=3, max_length=4000)


class AttachmentView(Input):
    id: UUID
    name: str
    size_bytes: int


class DeliveryView(Input):
    id: UUID
    body: str
    state: Literal["DELIVERED", "APPROVED", "AUTO_APPROVED", "REVISION_REQUESTED", "DISPUTED"]
    delivered_at: datetime
    agent_review_at: datetime
    auto_approve_at: datetime
    decided_at: datetime | None
    reason: str | None
    attachment: AttachmentView | None = None


def scope(db, request, thread_id, *, lock=False):
    sandbox_provider()
    user = browser_user(db, request)
    thread(db, user.id, thread_id, lock=lock)
    order = db.scalar(select(Order).where(Order.conversation_id == thread_id))
    if order is None:
        raise HTTPException(404, "order_not_found")
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None or payment.status != "SANDBOX_CONFIRMED":
        raise HTTPException(409, "sandbox_payment_required")
    return user, order


def latest(db, order_id, *, lock=False):
    query = select(Delivery).where(Delivery.order_id == order_id).order_by(
        Delivery.delivered_at.desc(), Delivery.id.desc()
    ).limit(1)
    return db.scalar(query.with_for_update() if lock else query)


def delivery_view(row, attachment=None):
    view = project(DeliveryView, row)
    if attachment is not None:
        view.attachment = project(AttachmentView, attachment)
    return view


def stored_attachment(db, delivery_id):
    return db.scalar(select(DeliveryFile).where(DeliveryFile.delivery_id == delivery_id))


@router.get("/deliveries", response_model=list[DeliveryView])
def read_deliveries(thread_id: UUID, request: Request, db: DB):
    _, order = scope(db, request, thread_id)
    rows = db.execute(select(Delivery, DeliveryFile).outerjoin(
        DeliveryFile, DeliveryFile.delivery_id == Delivery.id
    ).where(Delivery.order_id == order.id).order_by(Delivery.delivered_at, Delivery.id))
    return [delivery_view(row, attachment) for row, attachment in rows]


def supplier_order(db, request, thread_id):
    user, order = scope(db, request, thread_id, lock=True)
    if user.id != order.supplier:
        raise HTTPException(403, "delivery_supplier_required")
    rate_limit(f"delivery:{user.id}", 30, 3600)
    return order


def submit_delivery(db, order, data, uploaded=None):
    previous = db.scalar(select(Delivery).where(Delivery.order_id == order.id, Delivery.client_id == data.client_id))
    if previous:
        attachment = stored_attachment(db, previous.id)
        stored = (attachment.name, attachment.digest) if attachment else None
        incoming = (uploaded[0], uploaded[2]) if uploaded else None
        if previous.body != data.body or stored != incoming:
            raise HTTPException(409, "idempotency_conflict")
        return delivery_view(previous, attachment)
    current = latest(db, order.id, lock=True)
    if current and current.state != "REVISION_REQUESTED":
        raise HTTPException(409, "delivery_state_conflict")
    timestamp = now()
    row = Delivery(order_id=order.id, body=data.body, client_id=data.client_id, state="DELIVERED",
                   delivered_at=timestamp, agent_review_at=timestamp + timedelta(days=7),
                   auto_approve_at=timestamp + timedelta(days=14))
    db.add(row)
    attachment = None
    if uploaded:
        name, content, digest = uploaded
        db.flush()
        attachment = DeliveryFile(delivery_id=row.id, name=name, digest=digest, size_bytes=len(content))
        db.add(attachment)
        db.flush()
        try:
            delivery_storage().store(attachment.id, content)
        except (StorageFull, OSError):
            raise HTTPException(503, "delivery_storage_unavailable") from None
    # Keep the file if the database commit fails ambiguously. An unreferenced file has no download route.
    db.commit()
    return delivery_view(row, attachment)


@router.post("/deliveries", status_code=201, response_model=DeliveryView, dependencies=mutating)
def deliver(thread_id: UUID, data: DeliveryInput, request: Request, db: DB):
    return submit_delivery(db, supplier_order(db, request, thread_id), data)


@router.post("/deliveries/upload", status_code=201, response_model=DeliveryView, dependencies=mutating)
def upload_delivery(thread_id: UUID, request: Request, db: DB,
                    client_id: Annotated[UUID, Form()], attachment: Annotated[UploadFile, File()],
                    body: Annotated[str, Form(max_length=10000)] = ""):
    order = supplier_order(db, request, thread_id)
    return submit_delivery(db, order, AttachedDeliveryInput(client_id=client_id, body=body), validate_file(attachment))


@router.get("/deliveries/{delivery_id}/attachment", response_class=FileResponse)
def download_attachment(thread_id: UUID, delivery_id: UUID, request: Request, db: DB):
    _, order = scope(db, request, thread_id)
    attachment = db.scalar(select(DeliveryFile).join(Delivery, Delivery.id == DeliveryFile.delivery_id).where(
        DeliveryFile.delivery_id == delivery_id, Delivery.order_id == order.id
    ))
    if attachment is None:
        raise HTTPException(404, "delivery_file_not_found")
    path = delivery_storage().path(attachment.id)
    if not path.is_file():
        raise HTTPException(503, "delivery_storage_unavailable")
    return FileResponse(path, media_type="application/octet-stream", filename=attachment.name, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/deliveries/{delivery_id}/decision", response_model=DeliveryView, dependencies=mutating)
def decide(thread_id: UUID, delivery_id: UUID, data: Decision, request: Request, db: DB):
    user, order = scope(db, request, thread_id, lock=True)
    if data.action != "dispute" and user.id != order.buyer:
        raise HTTPException(403, "delivery_buyer_required")
    row = latest(db, order.id, lock=True)
    if row is None or row.id != delivery_id:
        raise HTTPException(404, "delivery_not_found")
    state = {"approve": "APPROVED", "revise": "REVISION_REQUESTED", "dispute": "DISPUTED"}[data.action]
    if row.state == state and row.reason == data.reason:
        return delivery_view(row, stored_attachment(db, row.id))
    allowed = {"DELIVERED", "REVISION_REQUESTED"} if data.action == "dispute" else {"DELIVERED"}
    if row.state not in allowed:
        raise HTTPException(409, "delivery_state_conflict")
    if data.action != "approve" and data.reason is None:
        raise HTTPException(422, "delivery_reason_required")
    timestamp = now()
    if data.action == "dispute":
        db.add(Dispute(order_id=order.id, delivery_id=row.id, opened_by=user.id, reason=data.reason, opened_at=timestamp))
    row.state = state
    row.decided_at = timestamp
    row.reason = data.reason
    db.commit()
    return delivery_view(row, stored_attachment(db, row.id))


def auto_approve(db, timestamp):
    rows = list(db.scalars(select(Delivery).where(
        Delivery.state == "DELIVERED", Delivery.auto_approve_at <= timestamp
    ).order_by(Delivery.auto_approve_at, Delivery.id).limit(100).with_for_update(skip_locked=True)))
    for row in rows:
        row.state = "AUTO_APPROVED"
        row.decided_at = timestamp
    db.commit()
    return len(rows)

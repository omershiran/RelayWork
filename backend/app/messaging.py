from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import browser_user, now, rate_limit, same_origin
from .db import Agent, Base, Service, User
from .marketplace import Input, project, public_agents
from .work import WorkRequest

router = APIRouter(prefix="/api/v1/conversations")
mutating = [Depends(same_origin)]


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (CheckConstraint("initiator <> recipient"),
                      CheckConstraint("num_nonnulls(service_id, work_id) = 1"),
                      UniqueConstraint("initiator", "client_id"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    initiator: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    recipient: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_services.id"))
    work_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_requests.id"))
    client_id: Mapped[UUID]
    subject: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    next_sequence: Mapped[int] = mapped_column(default=1)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence"),
                      UniqueConstraint("conversation_id", "sender", "client_id"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    sender: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[UUID]
    sequence: Mapped[int]
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MessageInput(Input):
    client_id: UUID
    body: str = Field(min_length=1, max_length=6000)


class StartConversation(MessageInput):
    kind: Annotated[str, Field(pattern="^(service|work)$")]
    resource_id: UUID


class ConversationView(Input):
    id: UUID
    subject: str
    service_id: UUID | None
    work_id: UUID | None
    created_at: datetime
    updated_at: datetime


def membership(owner):
    return or_(Conversation.initiator == owner, Conversation.recipient == owner)


def thread(db, owner, thread_id, *, lock=False):
    query = select(Conversation).where(Conversation.id == thread_id, membership(owner))
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "conversation_not_found")
    return row


def target(db, data):
    if data.kind == "service":
        suppliers = public_agents().subquery()
        entry = db.execute(select(Service.title, Agent.owner).join(
            Agent, Agent.id == Service.agent_id
        ).join(suppliers, suppliers.c.id == Agent.id).where(Service.id == data.resource_id)).one_or_none()
    else:
        entry = db.execute(select(WorkRequest.title, WorkRequest.owner).where(
            WorkRequest.id == data.resource_id, WorkRequest.closed_at.is_(None), WorkRequest.expires_at > now()
        )).one_or_none()
    if entry is None:
        raise HTTPException(404, "conversation_resource_not_found")
    return entry.title, entry.owner


def append_message(db, conversation, sender, data):
    row = db.scalar(select(Message).where(
        Message.conversation_id == conversation.id, Message.sender == sender, Message.client_id == data.client_id,
    ))
    if row:
        if row.body != data.body:
            raise HTTPException(409, "idempotency_conflict")
        return row
    row = Message(conversation_id=conversation.id, sender=sender, client_id=data.client_id,
                  body=data.body, sequence=conversation.next_sequence)
    conversation.next_sequence += 1
    conversation.updated_at = now()
    db.add(row)
    db.flush()
    return row


def message_view(row, owner):
    return {"id": row.id, "sequence": row.sequence, "body": row.body, "created_at": row.created_at,
            "mine": row.sender == owner, "sender_type": "human", "type": "MESSAGE"}


@router.post("", response_model=ConversationView, status_code=201, dependencies=mutating)
def start(data: StartConversation, request: Request, db: DB):
    user = browser_user(db, request)
    rate_limit(f"open-thread:{user.id}", 20, 3600)
    db.get(User, user.id, with_for_update=True)
    initial = {"service_id": data.resource_id} if data.kind == "service" else {"work_id": data.resource_id}
    row = db.scalar(select(Conversation).where(
        Conversation.initiator == user.id, Conversation.client_id == data.client_id,
    ).with_for_update())
    if row:
        field, resource = next(iter(initial.items()))
        if getattr(row, field) != resource:
            raise HTTPException(409, "idempotency_conflict")
    else:
        title, recipient = target(db, data)
        if recipient == user.id:
            raise HTTPException(409, "cannot_contact_yourself")
        row = Conversation(initiator=user.id, recipient=recipient, subject=title, client_id=data.client_id, **initial)
        db.add(row)
        db.flush()
    append_message(db, row, user.id, data)
    db.commit()
    return project(ConversationView, row)


@router.get("", response_model=list[ConversationView])
def list_threads(request: Request, db: DB, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    user = browser_user(db, request)
    return [project(ConversationView, row) for row in db.scalars(select(Conversation).where(
        membership(user.id)
    ).order_by(Conversation.updated_at.desc(), Conversation.id).offset(offset).limit(50))]


@router.get("/{thread_id}/messages")
def read_messages(thread_id: UUID, request: Request, db: DB, after: Annotated[int, Query(ge=0)] = 0):
    user = browser_user(db, request)
    thread(db, user.id, thread_id)
    rows = db.scalars(select(Message).where(
        Message.conversation_id == thread_id, Message.sequence > after
    ).order_by(Message.sequence).limit(100))
    return [message_view(row, user.id) for row in rows]


@router.post("/{thread_id}/messages", status_code=201, dependencies=mutating)
def send_message(thread_id: UUID, data: MessageInput, request: Request, db: DB):
    user = browser_user(db, request)
    rate_limit(f"message-send:{user.id}", 60, 60)
    row = append_message(db, thread(db, user.id, thread_id, lock=True), user.id, data)
    db.commit()
    return message_view(row, user.id)

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import bearer, browser_user, now, rate_limit, same_origin
from .db import Agent, Base, Service, User
from .marketplace import Input, project, public_agents
from .work import WorkRequest

router = APIRouter(prefix="/api/v1/conversations")
mutating = [Depends(same_origin)]


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (CheckConstraint("initiator <> recipient"),
                      CheckConstraint("num_nonnulls(service_id, work_id) = 1"),
                      UniqueConstraint("initiator", "client_id"),
                      CheckConstraint("(initiator_agent_id IS NULL) = (recipient_agent_id IS NULL)",
                                      name="conversation_agents_paired"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    initiator: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    recipient: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    initiator_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"), index=True)
    recipient_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"), index=True)
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
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
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
    initiator_agent_id: UUID | None
    recipient_agent_id: UUID | None
    work_id: UUID | None
    created_at: datetime
    updated_at: datetime


class MessageView(Input):
    id: UUID
    sequence: int
    body: str
    created_at: datetime
    mine: bool
    sender_type: Literal["human", "agent"]
    agent_id: UUID | None
    type: Literal["MESSAGE"] = "MESSAGE"


class AgentContact(MessageInput):
    service_id: UUID


def membership(owner, agent_id=None):
    if agent_id is not None:
        return or_(
            (Conversation.initiator == owner) & (Conversation.initiator_agent_id == agent_id),
            (Conversation.recipient == owner) & (Conversation.recipient_agent_id == agent_id),
        )
    return or_(Conversation.initiator == owner, Conversation.recipient == owner)


def thread(db, owner, thread_id, *, lock=False, agent_id=None):
    query = select(Conversation).where(Conversation.id == thread_id, membership(owner, agent_id))
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "conversation_not_found")
    return row


def target(db, data):
    if data.kind == "service":
        suppliers = public_agents().subquery()
        entry = db.execute(select(Service.title, Agent.owner, Agent.id.label("agent_id")).join(
            Agent, Agent.id == Service.agent_id
        ).join(suppliers, suppliers.c.id == Agent.id).where(Service.id == data.resource_id)).one_or_none()
    else:
        entry = db.execute(select(WorkRequest.title, WorkRequest.owner).where(
            WorkRequest.id == data.resource_id, WorkRequest.closed_at.is_(None), WorkRequest.expires_at > now()
        )).one_or_none()
    if entry is None:
        raise HTTPException(404, "conversation_resource_not_found")
    return entry.title, entry.owner, getattr(entry, "agent_id", None)


def append_message(db, conversation, sender, data, agent_id=None):
    row = db.scalar(select(Message).where(
        Message.conversation_id == conversation.id, Message.sender == sender, Message.client_id == data.client_id,
    ))
    if row:
        if row.body != data.body or row.agent_id != agent_id:
            raise HTTPException(409, "idempotency_conflict")
        return row
    row = Message(conversation_id=conversation.id, sender=sender, agent_id=agent_id, client_id=data.client_id,
                  body=data.body, sequence=conversation.next_sequence)
    conversation.next_sequence += 1
    conversation.updated_at = now()
    db.add(row)
    db.flush()
    return row


def message_view(row, owner):
    return MessageView(id=row.id, sequence=row.sequence, body=row.body, created_at=row.created_at,
                       mine=row.sender == owner, sender_type="agent" if row.agent_id else "human", agent_id=row.agent_id)


def open_thread(db, owner, data, agent_id=None):
    rate_limit(f"open-thread:{owner}", 20, 3600)
    db.get(User, owner, with_for_update=True)
    initial = {"service_id": data.resource_id} if data.kind == "service" else {"work_id": data.resource_id}
    row = db.scalar(select(Conversation).where(
        Conversation.initiator == owner, Conversation.client_id == data.client_id,
    ).with_for_update())
    if row:
        field, resource = next(iter(initial.items()))
        if getattr(row, field) != resource or row.initiator_agent_id != agent_id:
            raise HTTPException(409, "idempotency_conflict")
    else:
        title, recipient, recipient_agent = target(db, data)
        if recipient == owner:
            raise HTTPException(409, "cannot_contact_yourself")
        row = Conversation(initiator=owner, recipient=recipient, subject=title, client_id=data.client_id,
                           initiator_agent_id=agent_id, recipient_agent_id=recipient_agent if agent_id else None, **initial)
        db.add(row)
        db.flush()
    append_message(db, row, owner, data, agent_id)
    db.commit()
    return project(ConversationView, row)


@router.post("", response_model=ConversationView, status_code=201, dependencies=mutating)
def start(data: StartConversation, request: Request, db: DB):
    return open_thread(db, browser_user(db, request).id, data)


@router.get("", response_model=list[ConversationView])
def list_threads(request: Request, db: DB, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    user = browser_user(db, request)
    return conversations(db, user.id, offset)


def conversations(db, owner, offset=0, agent_id=None):
    return [project(ConversationView, row) for row in db.scalars(select(Conversation).where(
        membership(owner, agent_id)
    ).order_by(Conversation.updated_at.desc(), Conversation.id).offset(offset).limit(50))]


@router.get("/{thread_id}/messages", response_model=list[MessageView])
def read_messages(thread_id: UUID, request: Request, db: DB, after: Annotated[int, Query(ge=0)] = 0):
    user = browser_user(db, request)
    return messages(db, user.id, thread_id, after)


def messages(db, owner, thread_id, after=0, agent_id=None):
    thread(db, owner, thread_id, agent_id=agent_id)
    rows = db.scalars(select(Message).where(
        Message.conversation_id == thread_id, Message.sequence > after
    ).order_by(Message.sequence).limit(100))
    return [message_view(row, owner) for row in rows]


@router.post("/{thread_id}/messages", status_code=201, response_model=MessageView, dependencies=mutating)
def send_message(thread_id: UUID, data: MessageInput, request: Request, db: DB):
    user = browser_user(db, request)
    return write_message(db, user.id, thread_id, data)


def write_message(db, owner, thread_id, data, agent_id=None):
    rate_limit(f"message-send:{owner}", 60, 60)
    row = append_message(db, thread(db, owner, thread_id, lock=True, agent_id=agent_id), owner, data, agent_id)
    db.commit()
    return message_view(row, owner)


agent_router = APIRouter(prefix="/api/v1/agent-conversations")


def messaging_actor(db, authorization):
    key = bearer(db, authorization)
    if key.scope != "messaging" or key.agent_id is None:
        raise HTTPException(403, "scope_required")
    agent = db.get(Agent, key.agent_id)
    if agent is None or agent.owner != key.owner:
        raise HTTPException(403, "scope_required")
    return agent


def contact_supplier(db, agent, data):
    if agent.role not in {"buyer", "both"}:
        raise HTTPException(403, "buyer_agent_required")
    request = StartConversation(kind="service", resource_id=data.service_id, body=data.body, client_id=data.client_id)
    return open_thread(db, agent.owner, request, agent.id)


@agent_router.post("", status_code=201, response_model=ConversationView)
def agent_start(data: AgentContact, request: Request, db: DB):
    return contact_supplier(db, messaging_actor(db, request.headers.get("authorization")), data)


@agent_router.get("", response_model=list[ConversationView])
def agent_list(request: Request, db: DB, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    agent = messaging_actor(db, request.headers.get("authorization"))
    return conversations(db, agent.owner, offset, agent.id)


@agent_router.get("/{thread_id}/messages", response_model=list[MessageView])
def agent_read(thread_id: UUID, request: Request, db: DB, after: Annotated[int, Query(ge=0)] = 0):
    agent = messaging_actor(db, request.headers.get("authorization"))
    return messages(db, agent.owner, thread_id, after, agent.id)


@agent_router.post("/{thread_id}/messages", status_code=201, response_model=MessageView)
def agent_reply(thread_id: UUID, data: MessageInput, request: Request, db: DB):
    agent = messaging_actor(db, request.headers.get("authorization"))
    return write_message(db, agent.owner, thread_id, data, agent.id)

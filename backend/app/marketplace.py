import re
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from .db import Agent, Buyer, Service, User


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentInput(Input):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=4000)
    role: Literal["buyer", "supplier", "both"]
    visible: bool = True


class AgentView(AgentInput):
    id: UUID
    slug: str


class ServiceInput(Input):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=4000)
    price_cents: Annotated[int, Field(strict=True, ge=0, le=100_000_000)] | None = None
    delivery_days: int = Field(ge=1, le=365)
    country: str = Field(pattern=r"^([A-Z]{2})?$", default="")
    language: str = Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")


class ServiceView(ServiceInput):
    id: UUID
    agent_id: UUID


class Search(Input):
    query: str = Field(max_length=200, default="")
    category: str = Field(max_length=80, default="")
    country: str = Field(pattern=r"^([A-Z]{2})?$", default="")
    language: str = Field(max_length=12, default="")
    max_price_cents: int | None = Field(default=None, ge=0)
    max_delivery_days: int | None = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0, le=10000)


class Listing(Input):
    agent: AgentView
    service: ServiceView


def project(schema, row):
    return schema.model_validate(row, from_attributes=True)


def owned_agent(db, owner, agent_id):
    row = db.get(Agent, agent_id)
    if row is None or row.owner != owner:
        raise HTTPException(404, "agent_not_found")
    return row


def save_agent(db, owner, data, agent_id=None):
    if agent_id:
        row = owned_agent(db, owner, agent_id)
        internal = db.get(Buyer, owner)
        if internal and internal.agent_id == agent_id:
            raise HTTPException(403, "internal_agent_profile_managed")
        for field, value in data.model_dump().items():
            setattr(row, field, value)
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", data.name.lower()).strip("-")[:65] or "agent"
        row = Agent(owner=owner, slug=f"{slug}-{uuid4().hex[:16]}", **data.model_dump())
        db.add(row)
    db.flush()
    return project(AgentView, row)


def save_service(db, owner, agent_id, data, service_id=None):
    agent = owned_agent(db, owner, agent_id)
    if agent.role == "buyer":
        raise HTTPException(409, "supplier_role_required")
    if service_id:
        row = db.get(Service, service_id)
        if row is None or row.agent_id != agent.id:
            raise HTTPException(404, "service_not_found")
        for field, value in data.model_dump().items():
            setattr(row, field, value)
    else:
        row = Service(agent_id=agent.id, **data.model_dump())
        db.add(row)
    db.flush()
    return project(ServiceView, row)


def public_agents():
    return select(Agent).join(User, Agent.owner == User.id).where(
        Agent.visible.is_(True), Agent.role.in_(["supplier", "both"]), User.verified.is_(True)
    )


def public_profile(db, slug):
    agent = db.scalar(public_agents().where(Agent.slug == slug))
    if agent is None:
        raise HTTPException(404, "agent_not_found")
    services = db.scalars(select(Service).where(Service.agent_id == agent.id).order_by(Service.id))
    return {"agent": project(AgentView, agent), "services": [project(ServiceView, row) for row in services]}


def search_services(db, filters, *, exclude_owner=None):
    agents = public_agents().subquery()
    query = select(Service, Agent).join(Agent, Service.agent_id == Agent.id).join(agents, agents.c.id == Agent.id)
    if exclude_owner is not None:
        query = query.where(Agent.owner != exclude_owner)
    for word in filters.query.split():
        query = query.where(or_(*(column.icontains(word, autoescape=True) for column in (
            Agent.name, Agent.description, Service.title, Service.description, Service.category
        ))))
    for field in ("category", "country", "language"):
        if value := getattr(filters, field):
            query = query.where(getattr(Service, field) == value)
    if filters.max_price_cents is not None:
        query = query.where(Service.price_cents <= filters.max_price_cents)
    if filters.max_delivery_days is not None:
        query = query.where(Service.delivery_days <= filters.max_delivery_days)
    return [
        Listing(agent=project(AgentView, agent), service=project(ServiceView, service))
        for service, agent in db.execute(query.order_by(Service.id).offset(filters.offset).limit(50))
    ]

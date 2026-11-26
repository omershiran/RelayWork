from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .api import DB
from .auth import browser_user, now, rate_limit, same_origin
from .db import Base
from .marketplace import Input, project

router = APIRouter(prefix="/api/v1/work-requests")

Cents = Annotated[int, Field(strict=True, ge=0, le=100_000_000)]


class WorkRequest(Base):
    __tablename__ = "work_requests"
    __table_args__ = (
        CheckConstraint("min_price_cents is null or max_price_cents is null or min_price_cents <= max_price_cents"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str]
    deliverable: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))
    min_price_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_price_cents: Mapped[int | None] = mapped_column(BigInteger)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkInput(Input):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=6000)
    deliverable: str = Field(min_length=2, max_length=120)
    country: str = Field(pattern=r"^([A-Z]{2})?$", default="")
    min_price_cents: Cents | None = None
    max_price_cents: Cents | None = None
    due_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_terms(self):
        if self.min_price_cents is not None and self.max_price_cents is not None and self.min_price_cents > self.max_price_cents:
            raise ValueError("Minimum price exceeds maximum price")
        if self.expires_at > self.due_at:
            raise ValueError("Listing expiration exceeds delivery deadline")
        return self


class WorkView(WorkInput):
    id: UUID
    created_at: datetime
    closed_at: datetime | None


def list_open_work(db, category="", offset=0):
    query = select(WorkRequest).where(WorkRequest.closed_at.is_(None), WorkRequest.expires_at > now())
    if category:
        query = query.where(WorkRequest.category == category)
    return [project(WorkView, row) for row in db.scalars(
        query.order_by(WorkRequest.created_at.desc(), WorkRequest.id).offset(offset).limit(50)
    )]


@router.get("", response_model=list[WorkView])
def public_work(db: DB, category: Annotated[str, Query(max_length=80)] = "",
                offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    return list_open_work(db, category, offset)


@router.get("/mine", response_model=list[WorkView])
def own_work(request: Request, db: DB):
    user = browser_user(db, request)
    return [project(WorkView, row) for row in db.scalars(
        select(WorkRequest).where(WorkRequest.owner == user.id).order_by(WorkRequest.created_at.desc()).limit(100)
    )]


@router.post("", response_model=WorkView, status_code=201, dependencies=[Depends(same_origin)])
def publish_work(data: WorkInput, request: Request, db: DB):
    user = browser_user(db, request)
    rate_limit(f"work-publish:{user.id}", 12, 3600)
    timestamp = now()
    if not timestamp < data.expires_at <= timestamp + timedelta(days=90):
        raise HTTPException(422, "invalid_work_expiration")
    row = WorkRequest(owner=user.id, **data.model_dump())
    db.add(row)
    db.commit()
    return project(WorkView, row)


@router.post("/{work_id}/close", response_model=WorkView, dependencies=[Depends(same_origin)])
def close_work(work_id: UUID, request: Request, db: DB):
    user = browser_user(db, request)
    row = db.scalar(select(WorkRequest).where(WorkRequest.id == work_id, WorkRequest.owner == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "work_not_found")
    if row.closed_at is None:
        row.closed_at = now()
    db.commit()
    return project(WorkView, row)

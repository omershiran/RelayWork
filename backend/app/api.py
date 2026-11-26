from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from .auth import (
    APP_URL, COOKIE, bearer, browser_user, check_password, digest, issue_token, now,
    passwords, rate_limit, same_origin, send_account_link,
)
from .db import AccountToken, Agent, Credential, Database, SessionToken, User
from .marketplace import (
    AgentInput, AgentView, Input, Listing, Search, ServiceInput, ServiceView,
    owned_agent, project, public_profile, save_agent, save_service, search_services,
)

api = APIRouter(prefix="/api/v1")


def transaction():
    with Database() as db:
        yield db


DB = Annotated[object, Depends(transaction)]
origin = [Depends(same_origin)]


class Email(Input):
    email: EmailStr


class Login(Email):
    model_config = ConfigDict(str_strip_whitespace=False)
    password: str = Field(min_length=12, max_length=128)


class Action(Input):
    model_config = ConfigDict(str_strip_whitespace=False)
    token: str = Field(min_length=43, max_length=43)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class KeyInput(Input):
    agent_id: UUID | None = None


def limit_email(request, address):
    rate_limit(f"auth:ip:{request.client.host}", 20, 300)
    rate_limit(f"auth:email:{digest(address)}", 6, 300)


def new_account_link(db, user, purpose):
    token, _ = issue_token(db, user, purpose, AccountToken, timedelta(minutes=45))
    db.commit()
    send_account_link(user.email, token, purpose)


@api.post("/auth/register", status_code=202, dependencies=origin)
def register(data: Login, request: Request, db: DB):
    email = data.email.lower()
    limit_email(request, email)
    user = db.scalar(insert(User).values(email=email, password_hash=passwords.hash(data.password))
                     .on_conflict_do_nothing(index_elements=[User.email]).returning(User))
    if user:
        new_account_link(db, user, "verify")
    return {"accepted": True}


@api.post("/auth/resend", status_code=202, dependencies=origin)
@api.post("/auth/reset", status_code=202, dependencies=origin)
def request_account_link(data: Email, request: Request, db: DB):
    email = data.email.lower()
    limit_email(request, email)
    purpose = "reset" if request.url.path.endswith("/reset") else "verify"
    user = db.scalar(select(User).where(User.email == email))
    if user and user.verified == (purpose == "reset"):
        new_account_link(db, user, purpose)
    return {"accepted": True}


@api.post("/auth/verify", dependencies=origin)
@api.post("/auth/set-password", dependencies=origin)
def complete_account_action(data: Action, request: Request, db: DB):
    rate_limit(f"action:{request.client.host}", 20, 300)
    purpose = "verify" if request.url.path.endswith("/verify") else "reset"
    token = db.get(AccountToken, digest(data.token))
    if not token or token.purpose != purpose or token.expires <= now():
        raise HTTPException(400, "invalid_account_link")
    user = db.get(User, token.owner, with_for_update=True)
    if purpose == "verify" and (data.password is None or not check_password(user, data.password)):
        raise HTTPException(400, "invalid_account_link")
    consumed = db.execute(delete(AccountToken).where(
        AccountToken.digest == token.digest, AccountToken.expires > now()
    ))
    if consumed.rowcount != 1:
        raise HTTPException(400, "invalid_account_link")
    if purpose == "verify":
        user.verified = True
    else:
        if data.password is None:
            raise HTTPException(422, "password_required")
        user.password_hash = passwords.hash(data.password)
        db.execute(delete(SessionToken).where(SessionToken.owner == user.id))
        db.execute(delete(Credential).where(Credential.owner == user.id))
    db.execute(delete(AccountToken).where(AccountToken.owner == user.id, AccountToken.purpose == purpose))
    db.commit()
    return {"accepted": True}


@api.post("/auth/login", dependencies=origin)
def login(data: Login, request: Request, response: Response, db: DB):
    email = data.email.lower()
    limit_email(request, email)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if not check_password(user, data.password):
        raise HTTPException(401, "invalid_login")
    raw, _ = issue_token(db, user, None, SessionToken, timedelta(hours=12))
    db.commit()
    response.set_cookie(COOKIE, raw, httponly=True, secure=APP_URL.startswith("https://"),
                        samesite="lax", max_age=43200)
    return {"email": user.email, "verified": user.verified}


@api.post("/auth/logout", dependencies=origin)
def logout(request: Request, response: Response, db: DB):
    if raw := request.cookies.get(COOKIE):
        db.execute(delete(SessionToken).where(SessionToken.digest == digest(raw)))
        db.commit()
    response.delete_cookie(COOKIE, secure=APP_URL.startswith("https://"), httponly=True)
    return {"accepted": True}


@api.get("/auth/me")
def me(request: Request, db: DB):
    user = browser_user(db, request, verified=False)
    return {"email": user.email, "verified": user.verified}


@api.get("/me/agents", response_model=list[AgentView])
def my_agents(request: Request, db: DB):
    user = browser_user(db, request, verified=False)
    return [project(AgentView, row) for row in db.scalars(
        select(Agent).where(Agent.owner == user.id).order_by(Agent.name)
    )]


@api.get("/me/credentials")
def list_credentials(request: Request, db: DB):
    user = browser_user(db, request)
    return [{"id": row.id, "agent_id": row.agent_id, "scope": row.scope, "expires": row.expires}
            for row in db.scalars(select(Credential).where(Credential.owner == user.id, Credential.expires > now()))]


@api.post("/me/credentials", status_code=201, dependencies=origin)
def create_key(data: KeyInput, request: Request, response: Response, db: DB):
    user = browser_user(db, request)
    rate_limit(f"new-key:{user.id}", 12, 3600)
    if data.agent_id:
        owned_agent(db, user.id, data.agent_id)
    raw, key = issue_token(db, user, None, Credential, timedelta(days=30 if data.agent_id else 1),
                           agent_id=data.agent_id, scope="catalog" if data.agent_id else "register")
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"id": key.id, "token": raw, "expires": key.expires}


@api.delete("/me/credentials/{key_id}", dependencies=origin)
def revoke_key(key_id: UUID, request: Request, db: DB):
    user = browser_user(db, request)
    db.execute(delete(Credential).where(Credential.id == key_id, Credential.owner == user.id))
    db.commit()
    return {"accepted": True}


def catalog_owner(db, request, scope, agent_id=None):
    if request.headers.get("authorization"):
        return bearer(db, request.headers["authorization"], scope, agent_id).owner
    same_origin(request)
    return browser_user(db, request).id


@api.post("/agents", status_code=201, response_model=AgentView)
def create_agent(data: AgentInput, request: Request, db: DB):
    owner = catalog_owner(db, request, "register")
    rate_limit(f"agent-create:{owner}", 20, 3600)
    result = save_agent(db, owner, data)
    db.commit()
    return result


@api.put("/agents/{agent_id}", response_model=AgentView)
def update_agent(agent_id: UUID, data: AgentInput, request: Request, db: DB):
    result = save_agent(db, catalog_owner(db, request, "catalog", agent_id), data, agent_id)
    db.commit()
    return result


@api.post("/agents/{agent_id}/services", status_code=201, response_model=ServiceView)
@api.put("/agents/{agent_id}/services/{service_id}", response_model=ServiceView)
def write_service(agent_id: UUID, data: ServiceInput, request: Request, db: DB, service_id: UUID | None = None):
    owner = catalog_owner(db, request, "catalog", agent_id)
    rate_limit(f"service-write:{owner}", 60, 3600)
    result = save_service(db, owner, agent_id, data, service_id)
    db.commit()
    return result


@api.get("/agents/{slug}")
def profile(slug: str, db: DB):
    return public_profile(db, slug)


@api.get("/services", response_model=list[Listing])
def marketplace(filters: Annotated[Search, Query()], db: DB):
    return search_services(db, filters)

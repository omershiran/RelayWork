import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from .db import AccountToken, Credential, SessionToken, User

APP_URL = os.getenv("APP_URL", "http://127.0.0.1:8090").rstrip("/")
RATE_NAMESPACE = os.getenv("TEST_RATE_NAMESPACE", "test") if os.getenv("APP_ENV") == "test" else "app"
COOKIE = "__Host-agentrelai" if APP_URL.startswith("https://") else "agentrelai-dev"
passwords = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
dummy_password = passwords.hash(secrets.token_urlsafe(32))
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"), socket_timeout=2)


def now():
    return datetime.now(UTC)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def rate_limit(bucket, limit, window):
    try:
        key = f"agentrelai:{RATE_NAMESPACE}:limit:{bucket}:{int(now().timestamp()) // window}"
        with redis.pipeline() as pipe:
            count, _ = pipe.incr(key).expire(key, window + 1).execute()
    except RedisError as exc:
        raise HTTPException(503, "rate_limit_unavailable") from exc
    if count > limit:
        raise HTTPException(429, "rate_limited")


def same_origin(request: Request):
    if request.headers.get("origin") != APP_URL:
        raise HTTPException(403, "origin_required")


def browser_user(db, request, verified=True):
    value = request.cookies.get(COOKIE)
    session = db.get(SessionToken, digest(value)) if value else None
    if session is None or session.expires <= now():
        raise HTTPException(401, "login_required")
    user = db.get(User, session.owner)
    if verified and not user.verified:
        raise HTTPException(403, "email_verification_required")
    return user


def check_password(user, value):
    try:
        return passwords.verify(user.password_hash if user else dummy_password, value) and user is not None
    except VerifyMismatchError:
        return False


def issue_token(db, user, purpose, model, duration, **fields):
    raw = secrets.token_urlsafe(32)
    row = model(digest=digest(raw), owner=user.id, expires=now() + duration, **fields)
    if model is AccountToken:
        row.purpose = purpose
    db.add(row)
    db.flush()
    return raw, row


def bearer(db, authorization, scope=None, agent_id: UUID | None = None):
    prefix, _, value = (authorization or "").partition(" ")
    if prefix.lower() != "bearer" or not value:
        raise HTTPException(401, "bearer_required")
    key = db.scalar(select(Credential).where(Credential.digest == digest(value)))
    if key is None or key.expires <= now() or not db.get(User, key.owner).verified:
        raise HTTPException(401, "invalid_credential")
    rate_limit(f"credential:{key.id}", 120, 60)
    if scope and (key.scope != scope or key.agent_id != agent_id):
        raise HTTPException(403, "scope_required")
    return key


def require_account_mail():
    provider = os.getenv("SENDGRID_API_KEY") and os.getenv("EMAIL_FROM")
    local = os.getenv("APP_ENV", "development") in {"development", "test", "demo"} and os.getenv("DEV_MAIL_DIR")
    if not provider and not local:
        raise HTTPException(503, "email_unavailable")


def send_account_link(email, token, purpose):
    link = f"{APP_URL}/account-action#{purpose}:{token}"
    key = os.getenv("SENDGRID_API_KEY")
    sender = os.getenv("EMAIL_FROM")
    spool = os.getenv("DEV_MAIL_DIR")
    if key and sender:
        try:
            response = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "personalizations": [{"to": [{"email": email}]}],
                    "from": {"email": sender},
                    "subject": "agentrelai account verification" if purpose == "verify" else "agentrelai password reset",
                    "content": [{"type": "text/plain", "value": f"Open this account link: {link}"}],
                },
                timeout=8,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(503, "email_unavailable") from exc
    elif spool and os.getenv("APP_ENV", "development") in {"development", "test", "demo"}:
        path = Path(spool) / f"{secrets.token_hex(16)}.mail"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as message:
            message.write(f"To: {email}\n\n{link}\n")
    else:
        raise HTTPException(503, "email_unavailable")

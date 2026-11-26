from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.payments import ProviderEvent, SandboxProvider, sandbox_provider


def test_provider_authenticates_raw_event_bytes():
    provider = SandboxProvider("integration-only-signature-secret")
    event = ProviderEvent(
        event_id=uuid4(), payment_id=uuid4(), order_id=uuid4(), amount_cents=1250,
        currency="USD", status="SANDBOX_CONFIRMED",
    )
    body = event.model_dump_json().encode()
    signature = provider.sign(body)
    assert provider.verify_event(body, signature) == event
    altered = body.replace(b"1250", b"1251")
    with pytest.raises(HTTPException) as exc:
        provider.verify_event(altered, signature)
    assert exc.value.status_code == 401


def test_sandbox_requires_demo_environment_and_database(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "sandbox")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "x" * 32)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///agentrelai_demo")
    with pytest.raises(HTTPException, match="payment_provider_unconfigured"):
        sandbox_provider()
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///agentrelai_prod")
    with pytest.raises(HTTPException, match="sandbox_database_required"):
        sandbox_provider()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///agentrelai_demo")
    assert sandbox_provider().name == "sandbox"

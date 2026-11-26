import asyncio
import os
import subprocess
import socket
from collections import namedtuple
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

LocalServer = namedtuple("LocalServer", ["origin", "mail"])
PASSWORD = " local integration password "


@pytest.fixture
def server(tmp_path_factory):
    mail = tmp_path_factory.mktemp("private-mail")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = dict(os.environ, APP_ENV="test", APP_URL=origin, DEV_MAIL_DIR=str(mail),
               SENDGRID_API_KEY="", DATABASE_URL="postgresql+psycopg:///agentrelai_test",
               REDIS_URL="redis://127.0.0.1:6379/14", TEST_RATE_NAMESPACE=uuid4().hex)
    with listener:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--fd", str(listener.fileno()), "--no-access-log"],
            env=env,
            pass_fds=(listener.fileno(),),
        )
    try:
        for _ in range(80):
            if process.poll() is not None:
                pytest.fail("Test API exited")
            try:
                if httpx.get(f"{origin}/api/health", timeout=1).is_success:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Test API did not become healthy")
        yield LocalServer(origin, mail)
    finally:
        process.terminate()
        process.wait(timeout=10)


def signup(client, server):
    email = f"{uuid4().hex}@example.com"
    data = {"email": email, "password": PASSWORD}
    assert client.post("/auth/register", json=data).status_code == 202
    token = account_token(server.mail, email, "verify")
    assert client.post("/auth/login", json=data).json()["verified"] is False
    assert client.post("/me/credentials", json={}).status_code == 403
    assert client.post("/auth/verify", json={"token": token, "password": "incorrect password"}).status_code == 400
    verify = {"token": token, "password": PASSWORD}
    assert client.post("/auth/verify", json=verify).status_code == 200
    assert client.post("/auth/verify", json=verify).status_code == 400
    assert client.get("/auth/me").json()["verified"] is True
    return email


def account_token(mail: Path, email, purpose):
    for path in mail.glob("*.mail"):
        message = path.read_text()
        if message.startswith(f"To: {email}\n") and f"#{purpose}:" in message:
            return message.strip().split(f"#{purpose}:")[1]
    pytest.fail(f"No {purpose} email")


def client(server):
    return httpx.Client(base_url=server.origin + "/api/v1", headers={"Origin": server.origin})


async def call_tool(server, token, name, arguments):
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
        async with streamable_http_client(server.origin + "/mcp/", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert name in {tool.name for tool in tools.tools}
                return await session.call_tool(name, arguments)


def test_mcp_supplier_onboarding_and_revocation(server):
    with client(server) as owner, client(server) as other:
        signup(owner, server)
        signup(other, server)
        key = owner.post("/me/credentials", json={}).json()["token"]
        profile = {"name": f"Print {uuid4().hex}", "description": "Catalog printing supplier", "role": "supplier"}
        result = asyncio.run(call_tool(server, key, "register_agent", {"profile": profile}))
        assert not result.isError, result
        agent = result.structuredContent
        assert other.post("/me/credentials", json={"agent_id": agent["id"]}).status_code == 404
        assert other.put("/agents/" + agent["id"], json=profile).status_code == 404
        credential = owner.post("/me/credentials", json={"agent_id":agent["id"]}).json()
        service = {"title":"Catalog printing", "description":"Print a booklet", "category":"printing",
                   "delivery_days":3, "country":"US", "language":"en", "price_cents":1599}
        args = {"agent_id":agent["id"], "service":service}
        assert asyncio.run(call_tool(server, key, "publish_service", args)).isError
        published = asyncio.run(call_tool(server, credential["token"], "publish_service", args))
        assert not published.isError, published
        assert other.get("/agents/" + agent["slug"]).json()["services"][0]["price_cents"] == 1599
        filters = {"query": profile["name"], "country":"US", "max_delivery_days":3, "max_price_cents":1599}
        response = asyncio.run(call_tool(server, key, "search_services", {"filters":filters}))
        assert not response.isError, response
        assert response.structuredContent["result"][0]["agent"]["id"] == agent["id"]
        assert other.get("/services", params={**filters, "max_delivery_days":2}).json() == []
        assert other.get("/services", params={**filters, "max_price_cents":1598}).json() == []
        assert owner.put("/agents/" + agent["id"], json={**profile, "visible":False}).status_code == 200
        assert other.get("/agents/" + agent["slug"]).status_code == 404
        assert other.get("/services", params=filters).json() == []
        assert owner.delete("/me/credentials/" + credential["id"]).status_code == 200
        assert asyncio.run(call_tool(server, credential["token"], "publish_service", args)).isError


def test_password_reset_and_origin(server):
    with client(server) as owner:
        email = signup(owner, server)
        assert owner.post("/me/credentials", headers={"Origin": "https://outside.example"}, json={}).status_code == 403
        key = owner.post("/me/credentials", json={}).json()["token"]
        assert owner.post("/auth/reset", json={"email":email}).status_code == 202
        token = account_token(server.mail, email, "reset")
        new_password = "updated integration password"
        assert owner.post("/auth/set-password", json={"token":token,"password":new_password}).status_code == 200
        assert owner.get("/auth/me").status_code == 401
        assert owner.post("/agents", headers={"Authorization":f"Bearer {key}"},
                          json={"name":"Attempt", "description":"Supplier", "role":"supplier"}).status_code == 401
        assert owner.post("/auth/login", json={"email":email,"password":PASSWORD}).status_code == 401
        assert owner.post("/auth/login", json={"email":email,"password":new_password}).status_code == 200


def test_work_request_and_private_polling(server):
    from datetime import UTC, datetime, timedelta

    with client(server) as buyer, client(server) as supplier, client(server) as stranger:
        signup(buyer, server)
        signup(supplier, server)
        signup(stranger, server)
        stamp = datetime.now(UTC)
        data = {"title":"Print a book", "category":"printing", "description":"Print a booklet for an event",
                "deliverable":"One booklet", "due_at":(stamp + timedelta(days=4)).isoformat(),
                "expires_at":(stamp + timedelta(days=2)).isoformat()}
        assert buyer.post("/work-requests", json={**data, "private_budget": 50}).status_code == 422
        response = buyer.post("/work-requests", json=data)
        assert response.status_code == 201, response.text
        work = response.json()
        assert not {"owner", "email"}.intersection(work)
        assert work["min_price_cents"] is None and work["max_price_cents"] is None
        key = supplier.post("/me/credentials", json={}).json()["token"]
        listed = asyncio.run(call_tool(server, key, "get_work_requests", {"category":"printing"}))
        assert not listed.isError, listed
        assert work["id"] in {row["id"] for row in listed.structuredContent["result"]}
        path = "/work-requests/" + work["id"] + "/close"
        assert stranger.post(path).status_code == 404
        first = {"client_id":str(uuid4()), "kind":"work", "resource_id":work["id"], "body":"I can print this."}
        assert buyer.post("/conversations", json=first).status_code == 409
        opened = supplier.post("/conversations", json=first)
        assert opened.status_code == 201, opened.text
        conversation_id = opened.json()["id"]
        assert supplier.post("/conversations", json=first).json()["id"] == conversation_id
        assert supplier.post("/conversations", json={**first, "body":"Different"}).status_code == 409
        messages = "/conversations/" + conversation_id + "/messages"
        assert stranger.get(messages).status_code == 404
        assert stranger.post(messages, json={"body":"Blocked", "client_id":str(uuid4())}).status_code == 404
        initial = buyer.get(messages).json()
        assert len(initial) == 1 and initial[0]["mine"] is False
        reply = {"client_id":str(uuid4()), "body":"Can you deliver in two days?"}
        sent = buyer.post(messages, json=reply).json()
        assert buyer.post(messages, json=reply).json()["id"] == sent["id"]
        polled = supplier.get(messages, params={"after":initial[0]["sequence"]}).json()
        assert [row["id"] for row in polled] == [sent["id"]]
        assert buyer.post(path).status_code == 200
        assert stranger.post("/conversations", json={**first, "client_id": str(uuid4())}).status_code == 404
        assert buyer.get(messages).status_code == 200


def test_validation_does_not_echo_secret_input(server):
    with client(server) as browser:
        password = uuid4().hex * 8
        response = browser.post("/auth/register", json={"email":"invalid", "password":password})
        assert response.status_code == 422
        assert password not in response.text


def test_counter_and_human_order_snapshot(server):
    from datetime import UTC, datetime, timedelta

    with client(server) as buyer, client(server) as supplier, client(server) as stranger:
        signup(buyer, server)
        signup(supplier, server)
        signup(stranger, server)
        stamp = datetime.now(UTC)
        expires = (stamp + timedelta(days=2)).isoformat()
        due = (stamp + timedelta(days=4)).isoformat()
        data = {"title":"Print posters", "category":"printing", "description":"Artwork will be supplied.",
                "deliverable":"Printed posters", "due_at":due, "expires_at":expires}
        work = buyer.post("/work-requests", json=data).json()
        opening = {"client_id":str(uuid4()), "kind":"work", "resource_id":work["id"], "body":"We can print posters."}
        thread_id = supplier.post("/conversations", json=opening).json()["id"]
        thread = "/conversations/" + thread_id
        path = thread + "/quotes"
        quote = {"client_id":str(uuid4()), "price_cents":1734, "description":"Printing",
                 "deliverables":"Fifty posters", "terms":"One proof revision", "due_at":due, "expires_at":expires}
        assert buyer.post(path, json=quote).status_code == 409
        original = supplier.post(path, json=quote)
        assert original.status_code == 201, original.text
        original = original.json()
        assert supplier.post(path, json=quote).json()["id"] == original["id"]
        counter = {**quote, "client_id":str(uuid4()), "price_cents":1500, "supersedes_id":original["id"]}
        counter_result = buyer.post(path, json=counter)
        assert counter_result.status_code == 201, counter_result.text
        mod = {**quote, "client_id":str(uuid4()), "price_cents":1600, "supersedes_id":counter_result.json()["id"]}
        final = supplier.post(path, json=mod).json()
        assert buyer.get(path).json()[-1]["can_accept"]
        assert stranger.get(path).status_code == 404
        endpoint = path + "/" + final["id"] + "/accept"
        assert supplier.post(endpoint, json={"confirmed_price_cents":1600}).status_code == 403
        assert buyer.post(endpoint, json={"confirmed_price_cents":1500}).status_code == 409
        assert buyer.post(path + "/" + original["id"] + "/accept", json={"confirmed_price_cents":1734}).status_code == 409
        confirmation = buyer.post(endpoint, json={"confirmed_price_cents":1600})
        assert confirmation.status_code == 200, confirmation.text
        order = confirmation.json()
        assert order["payment_status"] == "UNCONFIGURED"
        assert order["terms"]["price_cents"] == 1600
        assert order["terms"]["deliverables"] == "Fifty posters"
        assert buyer.post(endpoint, json={"confirmed_price_cents":1600}).json()["id"] == order["id"]
        assert supplier.get(thread + "/order").json() == order
        assert stranger.get(thread + "/order").status_code == 404
        assert supplier.post(path, json={**quote, "client_id":str(uuid4())}).status_code == 409

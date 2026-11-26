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


def test_scoped_agent_to_agent_contact_and_reply(server):
    from uuid import UUID

    with client(server) as buyer, client(server) as seller:
        signup(buyer, server)
        signup(seller, server)

        def create(owner, role, scope="messaging"):
            agent = owner.post("/agents", json={
                "name": f"Agent {uuid4().hex}", "description": "Agent test fixture", "role":role,
            }).raise_for_status().json()
            key = owner.post("/me/credentials", json={"agent_id":agent["id"], "scope":scope}).raise_for_status().json()
            return agent, key

        buyer_agent, buyer_key = create(buyer, "buyer")
        seller_agent, seller_key = create(seller, "supplier")
        _, isolated_key = create(seller, "supplier")
        _, catalog_key = create(buyer, "buyer", "catalog")
        service = seller.post(f"/agents/{seller_agent['id']}/services", json={
            "title":"Agent printing", "category":"printing", "description":"Print on demand",
            "delivery_days":2, "language":"en",
        }).raise_for_status().json()
        contact = {"service_id":service["id"], "body":"Please describe your printing options.", "client_id":str(uuid4())}
        assert asyncio.run(call_tool(server, catalog_key["token"], "start_conversation", {"contact":contact})).isError
        started = asyncio.run(call_tool(server, buyer_key["token"], "start_conversation", {"contact":contact}))
        assert not started.isError, started
        thread = started.structuredContent
        assert thread["initiator_agent_id"] == buyer_agent["id"]
        assert thread["recipient_agent_id"] == seller_agent["id"]
        UUID(thread["id"])
        base = "/agent-conversations"
        path = base + "/" + thread["id"] + "/messages"
        seller_headers = {"Authorization":f"Bearer {seller_key['token']}"}
        isolated_headers = {"Authorization":f"Bearer {isolated_key['token']}"}
        assert seller.get(path, headers=isolated_headers).status_code == 404
        assert seller.get(base, headers=isolated_headers).json() == []
        assert seller.get(base, headers=seller_headers).json()[0]["id"] == thread["id"]
        first = seller.get(path, headers=seller_headers).raise_for_status().json()[0]
        assert first["sender_type"] == "agent" and first["agent_id"] == buyer_agent["id"]
        message = {"body":"We print booklets.", "client_id":str(uuid4())}
        reply = {"thread_id":thread["id"], "message":message}
        assert not asyncio.run(call_tool(server, seller_key["token"], "send_message", reply)).isError
        assert not asyncio.run(call_tool(server, seller_key["token"], "send_message", reply)).isError
        polled = asyncio.run(call_tool(server, buyer_key["token"], "get_messages", {
            "thread_id":thread["id"], "after": first["sequence"],
        }))
        rows = polled.structuredContent["result"]
        assert len(rows) == 1 and rows[0]["agent_id"] == seller_agent["id"]
        human = seller.get("/conversations/" + thread["id"] + "/messages").raise_for_status().json()
        assert len(human) == 2
        assert seller.delete("/me/credentials/" + seller_key["id"]).status_code == 200
        assert seller.get(path, headers=seller_headers).status_code == 401

        from datetime import UTC, datetime, timedelta

        def negotiation_key(account, agent):
            return account.post("/me/credentials", json={
                "agent_id":agent["id"], "scope":"negotiation",
            }).raise_for_status().json()

        customer_quote_key = negotiation_key(buyer, buyer_agent)["token"]
        business_quote_key = negotiation_key(seller, seller_agent)["token"]
        sibling = seller.post("/agents", json={
            "name":"Unrelated seller", "description":"Independent supplier fixture", "role":"supplier",
        }).raise_for_status().json()
        unrelated = negotiation_key(seller, sibling)["token"]
        quote_path = base + "/" + thread["id"] + "/quotes"
        assert seller.get(quote_path, headers={"Authorization":f"Bearer {unrelated}"}).status_code == 404
        assert buyer.get(quote_path, headers={"Authorization":f"Bearer {buyer_key['token']}"}).status_code == 403
        timestamp = datetime.now(UTC)
        terms = {
            "client_id":str(uuid4()), "price_cents":3400, "description":"Print booklets",
            "deliverables":"10 bound copies", "terms":"One proof revision",
            "due_at":(timestamp + timedelta(days=3)).isoformat(),
            "expires_at":(timestamp + timedelta(days=1)).isoformat(),
        }
        args = {"thread_id":thread["id"], "quote":terms}
        open_quote = asyncio.run(call_tool(server, business_quote_key, "send_quote", args))
        assert not open_quote.isError, open_quote
        proposal = open_quote.structuredContent
        assert proposal["author_agent_id"] == seller_agent["id"]
        replay = asyncio.run(call_tool(server, business_quote_key, "send_quote", args))
        assert replay.structuredContent["id"] == proposal["id"]
        counter = {**terms, "client_id":str(uuid4()), "price_cents":3000, "supersedes_id":proposal["id"]}
        response = buyer.post(quote_path, json=counter, headers={"Authorization":f"Bearer {customer_quote_key}"})
        assert response.status_code == 201, response.text
        assert response.json()["author_agent_id"] == buyer_agent["id"]
        final = {**terms, "client_id":str(uuid4()), "price_cents":3200, "supersedes_id":response.json()["id"]}
        offered = asyncio.run(call_tool(server, business_quote_key, "send_quote", {"thread_id":thread["id"], "quote":final}))
        assert not offered.isError, offered
        accepted = offered.structuredContent
        history = asyncio.run(call_tool(server, customer_quote_key, "get_quotes", {"thread_id":thread["id"]}))
        assert [quote["disposition"] for quote in history.structuredContent["result"]] == ["COUNTERED", "COUNTERED", "OPEN"]
        assert not any(quote["can_accept"] for quote in history.structuredContent["result"])
        decision = {"thread_id":thread["id"], "quote_id":accepted["id"], "decision":"withdraw"}
        assert asyncio.run(call_tool(server, customer_quote_key, "respond_to_quote", decision)).isError
        assert asyncio.run(call_tool(server, business_quote_key, "respond_to_quote", {**decision, "decision":"reject"})).isError
        human = "/conversations/" + thread["id"] + "/quotes/" + accepted["id"] + "/accept"
        with httpx.Client(base_url=server.origin + "/api/v1", headers={"Origin":server.origin}) as agent:
            assert agent.post(human, json={"confirmed_price_cents":3200},
                              headers={"Authorization":f"Bearer {customer_quote_key}"}).status_code == 401
        order = buyer.post(human, json={"confirmed_price_cents":3200}).raise_for_status().json()
        assert order["terms"]["price_cents"] == 3200
        assert order["terms"]["author_agent_id"] == seller_agent["id"]
        assert order["payment_status"] == "UNCONFIGURED"


def test_one_click_internal_buyer_chat_and_supplier_contact(server):
    with client(server) as buyer, client(server) as supplier:
        signup(buyer, server)
        signup(supplier, server)
        agent = buyer.post("/buyer").raise_for_status().json()
        assert buyer.post("/buyer").raise_for_status().json()["id"] == agent["id"]
        assert agent["role"] == "buyer" and not agent["visible"]
        assert buyer.get("/me/agents").raise_for_status().json() == []
        assert buyer.post("/me/credentials", json={"agent_id":agent["id"], "scope":"messaging"}).status_code == 403
        path = "/buyer/" + agent["id"] + "/chat"
        assert supplier.get(path).status_code == 404
        assert buyer.post(path, headers={"Origin":"https://unrelated.example"}, json={}).status_code == 403
        arithmetic = {"client_id":str(uuid4()), "prompt":"Calculate 8 × 7"}
        answer = buyer.post(path, json=arithmetic).raise_for_status().json()
        assert answer["response"] == "56" and answer["kind"] == "answer"
        assert buyer.post(path, json=arithmetic).raise_for_status().json()["id"] == answer["id"]
        assert buyer.post(path, json={**arithmetic, "prompt":"1+1"}).status_code == 409
        business = supplier.post("/agents", json={
            "name":"TimbrelTech", "description":"Specialized service provider", "role":"supplier",
        }).raise_for_status().json()
        service = supplier.post("/agents/" + business["id"] + "/services", json={
            "title":"TimbrelTech printing", "category":"printing", "description":"Printing for small booklets",
            "delivery_days":3, "language":"en",
        }).raise_for_status().json()
        search = {"client_id":str(uuid4()), "prompt":"Find me TimbrelTech"}
        found = buyer.post(path, json=search).raise_for_status().json()
        assert found["kind"] == "services"
        assert found["recommendations"][0]["service"]["id"] == service["id"]
        assert supplier.get("/conversations").raise_for_status().json() == []
        contact = path + "/" + found["id"] + "/contact"
        details = {"client_id":str(uuid4()), "service_id":service["id"], "brief":"Can you print 20 booklets?"}
        assert buyer.post(contact, json={**details, "service_id":str(uuid4())}).status_code == 404
        thread = buyer.post(contact, json=details).raise_for_status().json()
        assert thread["initiator_agent_id"] == agent["id"]
        assert thread["recipient_agent_id"] == business["id"]
        assert buyer.post(contact, json=details).raise_for_status().json()["id"] == thread["id"]
        assert len(buyer.get(path).raise_for_status().json()) == 2
        inbox = supplier.get("/conversations/" + thread["id"] + "/messages").raise_for_status().json()
        assert inbox[0]["body"] == details["brief"] and inbox[0]["sender_type"] == "agent"

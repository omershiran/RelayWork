from typing import Annotated, Literal
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .auth import APP_URL, bearer, rate_limit
from .db import Database
from .marketplace import AgentInput, AgentView, Listing, Search, ServiceInput, ServiceView, save_agent, save_service, search_services as search_listings

from .messaging import (
    AgentContact, ConversationView, MessageInput, MessageView, contact_supplier, conversations, credential_agent,
    messages, write_message,
)
from .negotiations import QuoteInput, QuoteView, decide_quote, quote_history, submit_quote
from .work import WorkView, list_open_work

host = APP_URL.split("://", 1)[1]
server = FastMCP(
    "agentrelai",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host],
        allowed_origins=[APP_URL],
    ),
)


async def call(ctx, action, scope=None, agent_id=None):
    headers = ctx.request_context.request.headers

    def execute():
        with Database() as db:
            key = bearer(db, headers.get("authorization"), scope, agent_id)
            result = action(db, key.owner)
            db.commit()
            return result

    return await run_in_threadpool(execute)


@server.tool()
async def search_services(filters: Search, ctx: Context) -> list[Listing]:
    """Find public supplier services using keywords and strict catalog filters."""
    return await call(ctx, lambda db, _: search_listings(db, filters))


@server.tool()
async def register_agent(profile: AgentInput, ctx: Context) -> AgentView:
    """Create an external agent profile with a short-lived registration credential."""
    def create(db, owner):
        rate_limit(f"agent-create:{owner}", 20, 3600)
        return save_agent(db, owner, profile)

    return await call(ctx, create, "register")


@server.tool()
async def update_agent(agent_id: UUID, profile: AgentInput, ctx: Context) -> AgentView:
    """Replace the public-facing profile for the agent authorized by the credential."""
    return await call(ctx, lambda db, owner: save_agent(db, owner, profile, agent_id), "catalog", agent_id)


@server.tool()
async def publish_service(agent_id: UUID, service: ServiceInput, ctx: Context) -> ServiceView:
    """Publish a service for the specified supplier. Price, when present, is in USD cents."""
    def publish(db, owner):
        rate_limit(f"service-write:{owner}", 60, 3600)
        return save_service(db, owner, agent_id, service)

    return await call(ctx, publish, "catalog", agent_id)


@server.tool()
async def get_work_requests(
    ctx: Context,
    category: Annotated[str, Field(max_length=80)] = "",
    offset: Annotated[int, Field(ge=0, le=10000)] = 0,
) -> list[WorkView]:
    """Find active public work requests. Only explicitly public price fields are returned."""
    return await call(ctx, lambda db, _: list_open_work(db, category, offset))


async def call_agent(ctx, scope, action):
    authorization = ctx.request_context.request.headers.get("authorization")

    def execute():
        with Database() as db:
            return action(db, credential_agent(db, authorization, scope))

    return await run_in_threadpool(execute)


@server.tool()
async def start_conversation(contact: AgentContact, ctx: Context) -> ConversationView:
    """Contact the business agent for a listed service using a customer agent messaging key."""
    return await call_agent(ctx, "messaging", lambda db, agent: contact_supplier(db, agent, contact))


@server.tool()
async def list_conversations(ctx: Context, offset: Annotated[int, Field(ge=0, le=10000)] = 0) -> list[ConversationView]:
    """List conversations for the agent bound to this messaging key."""
    return await call_agent(ctx, "messaging", lambda db, agent: conversations(db, agent.owner, offset, agent.id))


@server.tool()
async def get_messages(thread_id: UUID, ctx: Context, after: Annotated[int, Field(ge=0)] = 0) -> list[MessageView]:
    """Read messages after a sequence number in one of this agent's conversations."""
    return await call_agent(ctx, "messaging", lambda db, agent: messages(db, agent.owner, thread_id, after, agent.id))


@server.tool()
async def send_message(thread_id: UUID, message: MessageInput, ctx: Context) -> MessageView:
    """Send a message from this agent. Reuse the client ID when retrying the same message."""
    return await call_agent(ctx, "messaging", lambda db, agent: write_message(db, agent.owner, thread_id, message, agent.id))


@server.tool()
async def get_quotes(thread_id: UUID, ctx: Context) -> list[QuoteView]:
    """Read structured quotes for this agent's conversation using a negotiation key."""
    return await call_agent(ctx, "negotiation", lambda db, agent: quote_history(db, agent.owner, thread_id, agent.id))


@server.tool()
async def send_quote(thread_id: UUID, quote: QuoteInput, ctx: Context) -> QuoteView:
    """Propose a quote in USD cents. Set supersedes_id to counter an open quote. Orders require human approval."""
    return await call_agent(ctx, "negotiation", lambda db, agent: submit_quote(db, agent.owner, thread_id, quote, agent.id))


@server.tool()
async def respond_to_quote(thread_id: UUID, quote_id: UUID, decision: Literal["reject", "withdraw"], ctx: Context) -> QuoteView:
    """Reject a counterparty's quote or withdraw a quote sent by this agent."""
    return await call_agent(ctx, "negotiation", lambda db, agent: decide_quote(
        db, agent.owner, thread_id, quote_id, decision, agent.id
    ))

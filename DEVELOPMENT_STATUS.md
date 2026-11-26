# Development status

Development is deployed on the existing AWS EC2 instance at `http://127.0.0.1:8090`. The public domain and payment processing are pending. The current milestone ends at a human-confirmed order with payment status `UNCONFIGURED`.

## Completed and deployed

- Audited Ubuntu 24.04, one vCPU, approximately 2 GiB RAM, disk, sudo, service ports, host firewall and DNS. No product checkout was found. Created a local Git repository. Installed PostgreSQL 16, pgvector, Redis, Nginx, Python virtual environment and frontend build tooling without Docker.
- Created dedicated PostgreSQL databases for development, automated tests, production and demo. Development and test use the Ubuntu peer role. Production and demo have dedicated database owners and await runtime wiring. PostgreSQL, Redis, Nginx development and Uvicorn are bound to loopback. The development API runs under systemd.
- Implemented password signup, single-use email verification and password reset, session cookies, Argon2id, same-origin protection, Redis rate limits and revocable hashed credentials. A password is required to consume a verification link. Development email uses a private spool. The SendGrid adapter is implemented for account messages and awaits real credentials and sender verification.
- Implemented supplier profiles, publish/hide, catalog writes, keyword search and numeric/language/country/category hard filters. pgvector is installed. Semantic ranking has no runtime implementation yet.
- The bilingual React app displays the marketplace, agent profiles, Connect page, account forms, credentials, work requests and conversations. The API supports service edits, and the browser currently supports publication and agent profile editing.
- Human buyers can publish and close work requests without creating an agent. Verified marketplace users can contact the owner of a public service or work request. Private threads support polling with a sequence cursor and idempotent writes.
- Human negotiation supports structured USD quotes, counteroffers, rejection, withdrawal and explicit buyer confirmation. Acceptance serializes changes per conversation, deduplicates orders and stores a snapshot. Payment status remains `UNCONFIGURED`.
- The MCP Python SDK server uses Streamable HTTP and shares service functions with REST for agent registration, profile changes, service publication and search. It also exposes public work requests. The downloadable Skill documents how to provision keys and connect compatible clients.

## Verification

- Real local services: PostgreSQL migrations and Alembic consistency, Redis health, Nginx configuration, systemd health and a pg_dump/pg_restore exercise into a temporary database.
- Pytest integration uses real isolated PostgreSQL, Redis, Uvicorn and a real MCP SDK client. The mail spool is a development transport. Coverage includes account verification and reset, invalid input redaction, ownership and revocation, MCP onboarding, filtering, work request visibility, private polling, idempotency, structured counteroffers and order snapshot checks.
- Playwright Chromium covers the live search page, English/Hebrew direction, Skill download and Swagger schema. Browser dependencies and a Node 22 runtime were installed after the initial environment failed to launch Chromium.
- The initial restore attempt failed when the dump tried to comment on the preinstalled pgvector extension. The verified dump omits comments. The initial frontend audit found React Router advisories. The lockfile was upgraded and the follow-up audit reported zero advisories.
- Repeated integration runs initially shared Redis IP limit counters. The test API now uses an isolated namespace per scenario. Production limits remain enabled.
- No payment sandbox, cloud AI client, Google OAuth, SendGrid or OpenAI provider was used in these tests.

## Open work

1. Add dynamic agent policy enforcement, transaction-safe budget reservations, per-action human approval, audit events and provider-neutral payment, payout and ledger services. Run a separate, explicitly labelled sandbox through payment, delivery and dispute resolution.
2. Add authenticated private storage, durable 7/14-day processing, notifications, dispute administration and reputation.
3. Add semantic ranking, the internal No-Code agent runtime, OpenAI adapter, usage caps, RAG and approved outbound API connections.
4. Complete versioned REST/MCP coverage, OAuth-compatible onboarding, A2A, webhooks and WebSocket. Validate and time onboarding in real client environments.
5. Add admin roles and MFA, metrics, invite-only signup, full localization, Google OAuth, and complete browser and performance coverage. A human supplier still needs an agent profile to list services.
6. Finish the production and demo runtime isolation, TLS, backups and recovery policy. Confirm public DNS and security group configuration with the account owner. Current DNS and the instance public address differ.

See the deployment scripts, architecture, ERD and task plan for continuation. Real payment requires processor details and approved collection/payout arrangements.

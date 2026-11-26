# Development status

Development is deployed on the existing AWS EC2 instance at `http://127.0.0.1:8090`. A separate public preview is live at https://agentrelai.com. Commercial payment processing is pending. The current milestone ends at a human-confirmed order with payment status `UNCONFIGURED`.

## Completed and deployed

- Audited Ubuntu 24.04, one vCPU, approximately 2 GiB RAM, disk, sudo, service ports, host firewall and DNS. No product checkout was found. Created a local Git repository. Installed PostgreSQL 16, pgvector, Redis, Nginx, Python virtual environment and frontend build tooling without Docker.
- Created dedicated PostgreSQL databases for development, automated tests, production and demo. Development and test use the Ubuntu peer role. Production and demo run as dedicated OS and PostgreSQL roles with separate databases and Redis indexes. PostgreSQL, Redis, Nginx development and Uvicorn are bound to loopback. The development API runs under systemd.
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
- No external payment provider, cloud AI client, Google OAuth, SendGrid or OpenAI provider was used in these tests.

## Open work

1. Add dynamic agent policy enforcement, transaction-safe budget reservations, per-action human approval, audit events and provider-neutral payment, payout and ledger services. Extend the isolated payment sandbox through delivery and dispute resolution.
2. Add authenticated private storage, durable 7/14-day processing, notifications, dispute administration and reputation.
3. Add semantic ranking, the internal No-Code agent runtime, OpenAI adapter, usage caps, RAG and approved outbound API connections.
4. Complete versioned REST/MCP coverage, OAuth-compatible onboarding, A2A, webhooks and WebSocket. Validate and time onboarding in real client environments.
5. Add admin roles and MFA, metrics, invite-only signup, full localization, Google OAuth, and complete browser and performance coverage. A human supplier still needs an agent profile to list services.
6. Finish the production and demo runtime isolation, TLS, backups and recovery policy. Confirm public DNS and security group configuration with the account owner. Public DNS now matches the EC2 public IPv4 address and TLS is active.

See the deployment scripts, architecture, ERD and task plan for continuation. Real payment requires processor details and approved collection/payout arrangements.

## Public deployment and sandbox payment milestone

- Verified that public DNS and EC2 metadata both report 63.182.147.203. Issued a Let's Encrypt certificate with HTTP-01 and installed the Nginx renewal hook.
- Deployed the public preview with separate static assets, runtime user, PostgreSQL and Redis configuration. Signup and account-link delivery return 503 until a SendGrid sender and key are configured.
- Deployed an explicitly labelled, loopback-only demo. Only the demo runtime and its dedicated database can activate the sandbox provider. The buyer can initialize checkout and confirm a synthetic payment. HMAC verification, amount/currency/order reconciliation, event deduplication and paired ledger entries run on the server.
- Commercial settlement, refunds, disputes, delivery and 7/14-day processing remain open. The sandbox form is hosted internally. A real hosted checkout and its webhook contract depend on the selected provider.

Validation for this milestone passed seven pytest cases, two Playwright cases against the public HTTPS URL, Alembic schema reconciliation, and an end-to-end sandbox flow. The latter verified buyer authorization, idempotent initiation and confirmation, forged callback rejection, a balanced journal and the disabled sandbox callback on production. A parallel pytest run originally collided on its fixed Uvicorn port. The fixture now reserves an ephemeral port and passes the socket to Uvicorn.

The Certbot HTTP-01 renewal dry run passed. The renewal hook validated and reloaded Nginx.

## Provider and sandbox delivery milestone

- The supplied provider keys were found in the protected development environment file and copied to the protected production file without displaying values. Production account mail is configured with no-reply@agentrelai.com, selected from the configured sending domain. SendGrid DKIM CNAMEs resolve. SendGrid Mail Send Sandbox returned 200. Sender-management endpoints returned 403 under the restricted key. A real verification email has not been sent as part of this deployment check.
- The OpenAI models metadata request returned 200. A Responses API adapter reports input and output token counts and has mocked tests. Generation remains disabled. The public runtime has no model-generation route and awaits a configured model, usage accounting and approved cost limit.
- After sandbox payment, suppliers can submit text deliverables. Buyers can request revisions or approve, and both participants can open disputes on eligible deliveries. The next delivery after a revision receives a new review window. The persistent systemd timer checks stored deadlines and skips disputed or revision-blocked deliveries. The 7-day date is stored, and agent approval, notifications, files, resolution and payouts remain open.

Validation passed nine pytest cases and Alembic schema reconciliation. The isolated sandbox verification exercised payment, supplier-only submission, buyer revision requests, resubmission, dispute hold, manual approval and the scheduled approval worker. To verify the worker without waiting fourteen days, the test moved only its own demo delivery deadlines into the past.

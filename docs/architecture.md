# Architecture

Run a modular FastAPI monolith behind Nginx. Serve the React application from the same origin. PostgreSQL owns durable state and invariants. Redis handles ephemeral limits and later Celery dispatch. REST and MCP call the same onboarding services. A2A will reuse the same messaging and order services when those exist.

Separate development, production and demo by database, PostgreSQL role, Redis instance/database, storage root and credentials. Start with a loopback-only development deployment. Deploy the public vhost after network ownership and DNS are verified.

Browser sessions use opaque cookies with server-side expiry and same-origin mutation checks. External agents use separately scoped, revocable opaque credentials. Only digests are stored. PostgreSQL is the authority for tenant ownership. Verified owners may publish. Marketplace views use explicit public projections.

Transactions will lock the customer policy record when accepting a quote and reserve funds atomically. Accepted terms will be copied into an immutable snapshot. Payment and delivery states will remain separate. Ledger entries will be balanced per journal and use integer cents. Real payment transitions require an authenticated provider event. Use a database outbox for retriable delivery and approval work.

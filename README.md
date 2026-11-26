# agentrelai

An agent services marketplace built with FastAPI, PostgreSQL, Redis and React. The current development release supports account verification, external agent onboarding, catalog search, work requests, private conversations, structured negotiation and human-confirmed orders. Orders show checkout as unavailable until a provider is connected.

## Use the development deployment

On the EC2 host, the site is served at `http://127.0.0.1:8090`. The API health check is `/api/health`, Swagger is `/api/docs`, and MCP Streamable HTTP is `/mcp/`. To browse from another device, use an SSH tunnel with local port 8090. Keep that port and numeric loopback origin to match server-side browser origin and MCP host validation.

Development account messages are written to `/var/lib/agentrelai-dev/mail` with owner-only permissions. The mail spool is a development transport. Keep its contents out of logs, Git and support messages.

To onboard an external agent, verify the account, create a registration key, register via MCP or REST, then create a catalog key tied to that agent. The Connect page serves the versioned Skill archive. The browser can also register agents and publish services directly.

## Install and update

Prerequisites are Ubuntu 24.04, PostgreSQL 16 with pgvector, Redis, Nginx, Python 3.12 with venv, npm and Node 22 for frontend tooling. On this server the build script uses a Node 22 runtime from the npm package cache and Ubuntu's npm launcher.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
deployment/scripts/init-db.sh
deployment/scripts/build-frontend.sh
deployment/scripts/deploy-dev.sh
```

Run the scripts from the checkout. The systemd development unit is configured for this EC2 checkout at `/home/ubuntu/agentrelai`. In a different environment, adjust its paths and service account. Re-run build and deployment scripts to update. Alembic upgrades the development schema before restarting the API. Use the previous Git revision and its assets to roll back application code. Review migration reversibility separately before any database rollback.

Set runtime options through `/etc/agentrelai/dev.env` or process environment. See `.env.example` for names. Use a restricted environment file for real secrets. A configured SendGrid API key and sender switch account mail from the development spool to the provider. No external mail service has been exercised.

## Verify

```sh
cd backend
DATABASE_URL=postgresql+psycopg:///agentrelai_test ../.venv/bin/alembic upgrade head
../.venv/bin/python -m pytest -q
cd ../frontend
npm exec --yes --package=node@22 -- node node_modules/@playwright/test/cli.js install chromium
npm exec --yes --package=node@22 -- node node_modules/@playwright/test/cli.js test
```

Pytest uses an isolated PostgreSQL database, Redis database index 14, a private temporary mail spool and a real local MCP SDK client. Playwright smoke tests target the running development vhost. Chromium needs its OS libraries, which can be installed with the Playwright CLI's `install-deps chromium`.

Run `deployment/scripts/verify-restore.sh` for a real development database dump and isolated local restore. The script removes the scratch database on exit. A durable backup schedule and a separate backup destination remain production work.

For troubleshooting, inspect `sudo journalctl -u agentrelai-dev -n 60`, `sudo nginx -t`, and the health endpoint. Verify PostgreSQL and Redis are up if health returns 503. Keep account tokens, passwords and authorization headers out of diagnostic output.

See [architecture](docs/architecture.md), [data model](docs/data-model.md), [plan](docs/plan.md), [development status](DEVELOPMENT_STATUS.md) and [owner actions](USER_ACTION_REQUIRED.md).

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(cat frontend/.build-target)" = sandbox
if ! getent passwd agentrelai_demo >/dev/null; then
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin agentrelai_demo
fi
sudo install -d -m 0750 /etc/agentrelai
if ! sudo test -s /etc/agentrelai/demo.env; then
  sudo python3 - <<'PY'
import os
import secrets
fd = os.open("/etc/agentrelai/demo.env", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("PAYMENT_WEBHOOK_SECRET=" + secrets.token_hex(32) + "\n")
PY
fi
sudo install -d -m 0700 -o agentrelai_demo -g agentrelai_demo /var/lib/agentrelai-demo/mail
sudo -u agentrelai_demo bash -c 'cd /opt/agentrelai-prod/backend && DATABASE_URL=postgresql+psycopg:///agentrelai_demo ../.venv/bin/python -m alembic upgrade head'
sudo install -d -m 0755 /var/www/agentrelai-demo
sudo cp -a frontend/dist/. /var/www/agentrelai-demo/
sudo install -m 0644 deployment/systemd/agentrelai-demo.service /etc/systemd/system/
sudo install -m 0644 deployment/systemd/agentrelai-demo-approvals.{service,timer} /etc/systemd/system/
sudo install -m 0644 deployment/nginx/agentrelai-demo.conf /etc/nginx/sites-available/
sudo ln -sfn /etc/nginx/sites-available/agentrelai-demo.conf /etc/nginx/sites-enabled/agentrelai-demo.conf
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable agentrelai-demo
sudo systemctl enable --now agentrelai-demo-approvals.timer
sudo systemctl restart agentrelai-demo
sudo systemctl reload nginx
curl -fsS --retry 8 --retry-all-errors --retry-delay 1 http://127.0.0.1:8093/api/health

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(cat frontend/.build-target)" = development
test -f frontend/dist/index.html
test -f frontend/dist/downloads/agentrelai-skill.zip
(cd backend && DATABASE_URL=postgresql+psycopg:///agentrelai_dev ../.venv/bin/alembic upgrade head)
sudo install -d -m 0700 -o ubuntu -g ubuntu /var/lib/agentrelai-dev/mail
sudo install -d -m 0755 /var/www/agentrelai-dev
sudo cp -a frontend/dist/. /var/www/agentrelai-dev/
sudo install -m 0644 deployment/systemd/agentrelai-dev.service /etc/systemd/system/
sudo install -m 0644 deployment/nginx/agentrelai-dev.conf /etc/nginx/sites-available/
sudo ln -sfn /etc/nginx/sites-available/agentrelai-dev.conf /etc/nginx/sites-enabled/agentrelai-dev.conf
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable agentrelai-dev
sudo systemctl restart agentrelai-dev
sudo systemctl reload nginx
curl -fsS --retry 8 --retry-all-errors --retry-delay 1 http://127.0.0.1:8090/api/health

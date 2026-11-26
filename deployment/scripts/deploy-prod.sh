#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(cat frontend/.build-target)" = public
test -f frontend/dist/index.html
test -f frontend/dist/downloads/agentrelai-skill.zip
sudo test -s /etc/letsencrypt/live/agentrelai.com/fullchain.pem
if ! getent passwd agentrelai >/dev/null; then
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin agentrelai
fi
sudo install -d -m 0755 /opt/agentrelai-prod/backend /var/www/agentrelai-prod
sudo install -d -m 0750 /etc/agentrelai
sudo cp -a backend/app backend/migrations backend/alembic.ini /opt/agentrelai-prod/backend/
sudo chown -R root:root /opt/agentrelai-prod/backend
sudo python3 -m venv /opt/agentrelai-prod/.venv
sudo /opt/agentrelai-prod/.venv/bin/pip install --disable-pip-version-check --no-cache-dir -r backend/requirements.txt
sudo -u agentrelai bash -c 'cd /opt/agentrelai-prod/backend && DATABASE_URL=postgresql+psycopg:///agentrelai_prod ../.venv/bin/python -m alembic upgrade head'
sudo cp -a frontend/dist/. /var/www/agentrelai-prod/
sudo chown -R root:root /var/www/agentrelai-prod
sudo install -m 0644 deployment/systemd/agentrelai-prod.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agentrelai-prod
sudo systemctl restart agentrelai-prod
curl -fsS --retry 8 --retry-all-errors --retry-delay 1 http://127.0.0.1:8092/api/health
sudo install -m 0644 deployment/nginx/agentrelai-prod.conf /etc/nginx/sites-available/
sudo ln -sfn /etc/nginx/sites-available/agentrelai-prod.conf /etc/nginx/sites-enabled/agentrelai-prod.conf
sudo nginx -t
sudo systemctl reload nginx
curl -fsS --resolve agentrelai.com:443:127.0.0.1 https://agentrelai.com/api/health

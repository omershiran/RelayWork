#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
checkout=/home/ubuntu/agentrelai-deploy
if [[ ! -d "$checkout/.git" ]]; then
  GIT_SSH_COMMAND="$(git config --local --get core.sshCommand)" \
    git clone --no-checkout "$(git remote get-url origin)" "$checkout"
fi
git -C "$checkout" config --local core.sshCommand "$(git config --local --get core.sshCommand)"
sudo install -d /usr/local/libexec
sudo install -m 0755 deployment/scripts/sync-main.sh /usr/local/libexec/agentrelai-sync-main
sudo install -m 0644 deployment/systemd/agentrelai-main-deploy.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agentrelai-main-deploy.timer

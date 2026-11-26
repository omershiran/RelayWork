#!/usr/bin/env bash
set -euo pipefail

checkout=/home/ubuntu/agentrelai-deploy
state=/home/ubuntu/.local/state/agentrelai
mkdir -p "$state"
exec 9>"$state/deploy.lock"
flock -n 9 || exit 0

git -C "$checkout" fetch --quiet origin refs/heads/main
revision="$(git -C "$checkout" rev-parse FETCH_HEAD)"
if [[ -f "$state/deployed-main" && "$(cat "$state/deployed-main")" == "$revision" ]]; then
  exit 0
fi
git -C "$checkout" switch --quiet --detach "$revision"
cd "$checkout"
VITE_DEPLOYMENT=public deployment/scripts/build-frontend.sh
deployment/scripts/deploy-prod.sh
printf '%s\n' "$revision" > "$state/deployed-main.next"
mv "$state/deployed-main.next" "$state/deployed-main"
echo "Deployed agentrelai main $revision"

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
npm exec --yes --package=node@22 -- node /usr/share/nodejs/npm/bin/npm-cli.js --prefix frontend ci
npm exec --yes --package=node@22 -- node frontend/node_modules/vite/bin/vite.js build frontend
frontend_dist="$(realpath frontend/dist)"
mkdir -p "$frontend_dist/downloads"
python3 -m zipfile -c "$frontend_dist/downloads/agentrelai-skill.zip" skills/agentrelai

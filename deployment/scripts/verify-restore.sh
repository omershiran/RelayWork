#!/usr/bin/env bash
set -euo pipefail
umask 077
scratch="$(mktemp -d)"
database="agentrelai_restore_${scratch##*.}"
cleanup() {
  sudo -u postgres dropdb --if-exists "$database"
  rm -rf -- "$scratch"
}
trap cleanup EXIT
pg_dump --format=custom --no-owner --no-acl --no-comments agentrelai_dev > "$scratch/agentrelai.dump"
sudo -u postgres createdb --owner=ubuntu "$database"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$database" -qc 'create extension vector;'
pg_restore --exit-on-error --no-owner --no-acl --dbname="$database" "$scratch/agentrelai.dump"
check='select version_num from alembic_version; select count(*) from users; select count(*) from agent_services; select count(*) from orders;'
diff <(psql -Atq -d agentrelai_dev -c "$check") <(psql -Atq -d "$database" -c "$check")
echo "Development backup restored and checked."

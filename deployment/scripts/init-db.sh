#!/usr/bin/env bash
set -euo pipefail
for pair in "ubuntu agentrelai_dev" "ubuntu agentrelai_test" "agentrelai agentrelai_prod" "agentrelai_demo agentrelai_demo"; do
  read -r role database <<< "$pair"
  if ! sudo -u postgres psql -Atqc "select rolname from pg_roles where rolname = '$role'" | grep -qx "$role"; then
    sudo -u postgres createuser "$role"
  fi
  if ! sudo -u postgres psql -Atqc "select datname from pg_database where datname = '$database'" | grep -qx "$database"; then
    sudo -u postgres createdb --owner="$role" "$database"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$database" -qc 'create extension vector; revoke connect on database '"$database"' from public;'
  fi
done

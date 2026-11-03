#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# Schema changes on an existing installation require a validated backup first.
if docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
  "$ROOT/ops/backup/backup.sh" "$ROOT/backups"
fi
docker compose run --rm backend alembic -c alembic.ini upgrade head

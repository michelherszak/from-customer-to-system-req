#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
SOURCE="${1:-}"
[[ -n "$SOURCE" && -d "$SOURCE" ]] || { echo "usage: $0 <backup-directory> [--no-prebackup]" >&2; exit 2; }
SOURCE="$(cd "$SOURCE" && pwd)"
NO_PREBACKUP="${2:-}"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
[[ -f "$SOURCE/MANIFEST.sha256" ]] || { echo "missing MANIFEST.sha256" >&2; exit 3; }
(cd "$SOURCE" && sha256sum -c MANIFEST.sha256)
[[ -f "$SOURCE/postgresql.dump" && -f "$SOURCE/artifacts.tar.gz" ]] || { echo "incomplete backup" >&2; exit 3; }

if [[ "$NO_PREBACKUP" != "--no-prebackup" ]]; then
  echo "Creating safety backup of current installation..."
  "$ROOT/ops/backup/backup.sh" "$ROOT/backups" >/dev/null
fi

echo "Stopping application services..."
docker compose stop frontend scheduler worker backend || true
docker compose up -d postgres redis

echo "Restoring PostgreSQL..."
docker compose exec -T postgres dropdb -U kusys --if-exists kusys
docker compose exec -T postgres createdb -U kusys kusys
cat "$SOURCE/postgresql.dump" | docker compose exec -T postgres pg_restore -U kusys -d kusys --no-owner --no-privileges

echo "Restoring artifact storage..."
cat "$SOURCE/artifacts.tar.gz" | docker compose run --rm --no-deps -T backend sh -c 'rm -rf /data/artifacts/* /data/artifacts/.[!.]* /data/artifacts/..?* 2>/dev/null || true; tar -xzf - -C /data/artifacts'

echo "Checking migration compatibility..."
docker compose run --rm backend alembic -c alembic.ini upgrade head

echo "Starting application..."
docker compose up -d backend worker scheduler frontend

echo "Running health check..."
for _ in $(seq 1 30); do
  if docker compose exec -T backend python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).read()
PY
  then
    echo "Restore successful: $SOURCE"
    exit 0
  fi
  sleep 2
done

echo "restore completed but health check failed" >&2
exit 4

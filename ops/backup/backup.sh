#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
BACKUP_ROOT="${1:-$ROOT/backups}"
KEEP="${KUSYS_BACKUP_RETENTION:-20}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/kusys-$STAMP"
mkdir -p "$TARGET"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
docker compose version >/dev/null

echo "[1/6] PostgreSQL dump"
docker compose exec -T postgres pg_dump -U kusys -d kusys -Fc > "$TARGET/postgresql.dump"

echo "[2/6] Artifact storage"
docker compose run --rm --no-deps -T backend sh -c 'tar -czf - -C /data/artifacts .' > "$TARGET/artifacts.tar.gz"

echo "[3/6] Configuration snapshot (without plaintext secrets)"
mkdir -p "$TARGET/config"
cp config/kusys.example.yaml "$TARGET/config/kusys.example.yaml"
if [[ -f config/kusys.yaml ]]; then cp config/kusys.yaml "$TARGET/config/kusys.yaml"; fi
cp kusys-environment.yaml "$TARGET/kusys-environment.yaml"
cp VERSIONS.md "$TARGET/VERSIONS.md"

MIGRATION_HEAD="$(docker compose exec -T backend alembic -c alembic.ini current 2>/dev/null | tail -n 1 || true)"
cat > "$TARGET/backup.json" <<JSON
{
  "format": 1,
  "created_at_utc": "$STAMP",
  "application_version": "1.0.0",
  "migration_head": "${MIGRATION_HEAD//\"/}",
  "database": "postgresql",
  "artifact_backend": "local-filesystem"
}
JSON

echo "[4/6] Checksums"
(
  cd "$TARGET"
  find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256
)

echo "[5/6] Validate backup"
(cd "$TARGET" && sha256sum -c MANIFEST.sha256 >/dev/null)
[[ -s "$TARGET/postgresql.dump" ]] || { echo "database dump is empty" >&2; exit 3; }
[[ -s "$TARGET/artifacts.tar.gz" ]] || { echo "artifact archive is empty" >&2; exit 3; }

echo "[6/6] Rotate backups (keep $KEEP)"
mapfile -t OLD < <(find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -name 'kusys-*' -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
if (( ${#OLD[@]} > KEEP )); then
  for ((i=KEEP; i<${#OLD[@]}; i++)); do rm -rf -- "${OLD[$i]}"; done
fi

echo "$TARGET"

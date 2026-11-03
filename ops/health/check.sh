#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
docker compose ps
if docker compose exec -T backend python - <<'PY'
import json, urllib.request
print(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3).read()))
PY
then exit 0; else exit 1; fi

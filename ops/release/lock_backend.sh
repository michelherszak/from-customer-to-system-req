#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/backend"
command -v uv >/dev/null 2>&1 || { echo "uv is required to generate the fully resolved backend lock" >&2; exit 2; }
PYTHON_BIN="${PYTHON_BIN:-python3.14}"
uv lock --python "$PYTHON_BIN"
uv lock --check --python "$PYTHON_BIN"
echo "Generated backend/uv.lock"

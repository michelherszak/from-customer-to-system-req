#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/apps/frontend"
command -v npm >/dev/null 2>&1 || { echo "npm is required" >&2; exit 2; }
rm -f package-lock.json
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck
npm run build
echo "Generated and verified apps/frontend/package-lock.json"

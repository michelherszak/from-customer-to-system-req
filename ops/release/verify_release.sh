#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

! grep -R --include='docker-compose*.yml' -nE 'image:\s*[^[:space:]]+:latest([[:space:]]|$)' .
python -m compileall -q backend/kusys backend/tests
(cd backend && pytest -q)
python ops/release/generate_sbom.py
python - <<'PY'
import yaml
for f in ('docker-compose.yml','docker-compose.dev.yml','kusys-environment.yaml','config/kusys.example.yaml'):
    with open(f,encoding='utf-8') as h: yaml.safe_load(h)
print('YAML parse: OK')
PY

if command -v node >/dev/null 2>&1 && node -e "require('typescript')" >/dev/null 2>&1; then
  node - <<'JS'
const fs=require('fs'),ts=require('typescript');
const files=['apps/frontend/src/main.tsx','apps/frontend/src/api.ts','apps/frontend/playwright.config.ts','apps/frontend/e2e/full-flow.spec.ts'];
let bad=false;
for(const f of files){const d=ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX},reportDiagnostics:true,fileName:f}).diagnostics||[];if(d.some(x=>x.category===ts.DiagnosticCategory.Error)){bad=true;console.error('TypeScript syntax failed:',f)}}
if(bad)process.exit(1);console.log('TypeScript syntax transpilation: OK')
JS
fi

if [[ -f apps/frontend/package-lock.json ]]; then
  (cd apps/frontend && npm ci --ignore-scripts --no-audit --no-fund && npm run typecheck && npm run build)
else
  echo 'WARNING: apps/frontend/package-lock.json not present; run ./ops/release/lock_frontend.sh on a registry-connected release host.' >&2
fi
if [[ -f backend/uv.lock ]]; then
  (cd backend && uv lock --check)
else
  echo 'WARNING: backend/uv.lock not present; run ./ops/release/lock_backend.sh with Python 3.14 on a registry-connected release host.' >&2
fi

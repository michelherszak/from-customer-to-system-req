#!/usr/bin/env bash
set -euo pipefail
# Resolve the two public ports before docker compose starts. Up to twenty successors are tried,
# as required by the rebuild specification. Existing explicit non-numeric values are rejected.
strict="${KUSYS_PORT_STRICT:-false}"
find_port() {
  local requested="$1" name="$2" p
  [[ "$requested" =~ ^[0-9]+$ ]] || { echo "$name port must be numeric" >&2; return 2; }
  for ((p=requested; p<=requested+20; p++)); do
    if python3 - "$p" <<'PY'
import socket,sys
p=int(sys.argv[1]); s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
try: s.bind(("0.0.0.0",p))
except OSError: raise SystemExit(1)
finally: s.close()
PY
    then printf '%s' "$p"; return 0; fi
    if [[ "$strict" == "true" ]]; then echo "$name port $requested is occupied (strict mode)" >&2; return 1; fi
  done
  echo "No free $name port in range $requested-$((requested+20))" >&2; return 1
}
front="$(find_port "${KUSYS_FRONTEND_PORT:-5173}" frontend)"
back="$(find_port "${KUSYS_BACKEND_PORT:-8000}" backend)"
export KUSYS_FRONTEND_PORT="$front" KUSYS_BACKEND_PORT="$back"
# The browser talks to the frontend and nginx proxies /api to backend inside compose. This origin
# therefore follows the selected frontend port automatically.
export KUSYS_FRONTEND_ORIGIN="${KUSYS_FRONTEND_ORIGIN:-http://localhost:$front}"
printf 'KUSYS_FRONTEND_PORT=%s\nKUSYS_BACKEND_PORT=%s\nKUSYS_FRONTEND_ORIGIN=%s\n' "$front" "$back" "$KUSYS_FRONTEND_ORIGIN"

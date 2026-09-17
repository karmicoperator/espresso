#!/bin/bash
# MedScroll: double-click to start, or run from Terminal.
#
# Brings up the API and the web app, then opens a browser. Reuses our own instances if
# they are already running, and steps past a port held by somebody else's dev server
# rather than adopting it. Ctrl-C stops whatever this invocation started; anything it
# found already running is left alone.

set -u
cd "$(dirname "$0")"
mkdir -p logs
# shellcheck source=scripts/launch-lib.sh
. scripts/launch-lib.sh

STARTED=()

echo "MedScroll"
echo

API=$(resolve_port api) || { echo "  All ports $API_PORT_BASE-$((API_PORT_BASE + PORT_SPAN)) are taken. Nothing free for the API."; exit 1; }
WEB=$(resolve_port web) || { echo "  All ports $WEB_PORT_BASE-$((WEB_PORT_BASE + PORT_SPAN)) are taken. Nothing free for the web app."; exit 1; }
API_PORT=${API%% *}; API_ACTION=${API##* }
WEB_PORT=${WEB%% *}; WEB_ACTION=${WEB##* }

if [ "$API_ACTION" = reuse ]; then
  echo "  api   already running on :$API_PORT"
else
  if [ ! -x backend/.venv/bin/python ]; then
    echo "  api   no virtualenv at backend/.venv. Run:  cd backend && uv sync"
    exit 1
  fi
  ( cd backend && API_PORT="$API_PORT" nohup .venv/bin/python main.py > ../logs/api.log 2>&1 & )
  if wait_for_service api "$API_PORT" 45; then
    STARTED+=("api:$API_PORT")
    echo "  api   started on :$API_PORT"
  else
    echo "  api   did not come up. See logs/api.log"
    exit 1
  fi
fi

if [ "$WEB_ACTION" = reuse ]; then
  echo "  web   already running on :$WEB_PORT"
else
  if [ ! -d frontend/node_modules ]; then
    echo "  web   installing dependencies (first run only)"
    ( cd frontend && npm install >/dev/null 2>&1 )
  fi
  # The API origin is compiled into the page, so it has to be set before Next starts.
  ( cd frontend && NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" \
      nohup npm run dev -- -p "$WEB_PORT" > ../logs/web.log 2>&1 & )
  if wait_for_service web "$WEB_PORT" 90; then
    STARTED+=("web:$WEB_PORT")
    echo "  web   started on :$WEB_PORT"
  else
    echo "  web   did not come up. See logs/web.log"
    exit 1
  fi
fi

echo
PROVIDER=$(curl -s --max-time 8 "http://127.0.0.1:$API_PORT/api/health" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["services"]["llm_provider"])' 2>/dev/null)
echo "  model provider: ${PROVIDER:-unknown}"
case "${PROVIDER:-}" in
  claude_cli)    echo "  (headless Claude Code, no API key needed)" ;;
  unconfigured*) echo "  Papers already built will open, but new ones cannot be built." ;;
esac
echo
echo "  open http://localhost:$WEB_PORT"
open "http://localhost:$WEB_PORT" 2>/dev/null

if [ ${#STARTED[@]} -eq 0 ]; then
  echo
  echo "  Both were already running, so nothing to stop here. Close this window."
  exit 0
fi

stop_started() {
  echo
  for entry in "${STARTED[@]}"; do
    name=${entry%%:*}
    port=${entry##*:}
    kill $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null) 2>/dev/null
    echo "  stopped $name"
  done
  exit 0
}

echo
echo "  Ctrl-C to stop."
trap stop_started INT TERM
while true; do sleep 3600; done

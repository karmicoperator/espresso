#!/bin/bash
# Paper in Five: double-click to start, or run from Terminal.
#
# Installs what is missing on first run, brings up the API and the web app, then opens a
# browser. Reuses our own instances if they are already running, and steps past a port
# held by somebody else's dev server rather than adopting it. Ctrl-C stops whatever this
# invocation started; anything it found already running is left alone.
#
#   PAPERINFIVE_DEV=1 ./start.command     runs the web app's dev server instead of a build

set -u
cd "$(dirname "$0")"

say()  { echo "  $1"; }
fail() { echo; echo "  $1" | sed '2,$s/^/  /'; echo; exit 1; }

# shellcheck source=scripts/launch-lib.sh
. scripts/launch-lib.sh

echo "Paper in Five"
echo

setup_backend
setup_frontend

API=$(resolve_port api) || fail "All ports $API_PORT_BASE-$((API_PORT_BASE + PORT_SPAN)) are taken. Nothing free for the API."
WEB=$(resolve_port web) || fail "All ports $WEB_PORT_BASE-$((WEB_PORT_BASE + PORT_SPAN)) are taken. Nothing free for the web app."
API_PORT=${API%% *}; API_ACTION=${API##* }
WEB_PORT=${WEB%% *}; WEB_ACTION=$(web_action "${WEB%% *}" "${WEB##* }")

STARTED=()

if [ "$API_ACTION" = reuse ]; then
  say "api   already running on :$API_PORT"
else
  start_api "$API_PORT"
  STARTED+=("api:$API_PORT")
  say "api   started on :$API_PORT"
fi

if [ "$WEB_ACTION" = reuse ]; then
  say "web   already running on :$WEB_PORT"
else
  start_web "$WEB_PORT" "$API_PORT"
  STARTED+=("web:$WEB_PORT")
  say "web   started on :$WEB_PORT"
fi

echo
PROVIDER=$(llm_status "$API_PORT")
say "model provider: ${PROVIDER:-unknown}"
ADVICE=$(llm_advice "${PROVIDER:-unconfigured}")
if [ -n "$ADVICE" ]; then
  echo
  echo "$ADVICE" | sed 's/^/  /'
elif [ "$PROVIDER" = claude_cli ]; then
  say "(headless Claude Code, no API key needed)"
fi
echo
say "open http://localhost:$WEB_PORT"
open "http://localhost:$WEB_PORT" 2>/dev/null

if [ ${#STARTED[@]} -eq 0 ]; then
  echo
  say "Both were already running, so nothing to stop here. Close this window."
  exit 0
fi

stop_started() {
  echo
  for entry in "${STARTED[@]}"; do
    stop_port "${entry##*:}"
    say "stopped ${entry%%:*}"
  done
  # Reap the servers quietly: bash would otherwise print a "Terminated" line for each.
  wait 2>/dev/null
  exit 0
}

echo
say "Ctrl-C to stop."
trap stop_started INT TERM
# `sleep & wait` rather than a plain sleep: bash runs a trap only once the foreground
# command returns, so a plain sleep would hold a Ctrl-C from anything but the terminal
# itself for up to an hour. `wait` returns the moment the signal arrives.
while true; do sleep 3600 & wait $!; done

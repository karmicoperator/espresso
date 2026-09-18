# Shared by espresso.app and start.command: first-run setup, port resolution, starting.
#
# The caller defines two functions before sourcing this:
#   say  <text>   progress, non-fatal        (terminal line, or a notification)
#   fail <text>   stop with an explanation   (terminal line + exit, or a dialog)
#
# Written for the bash macOS ships (3.2): no associative arrays, no mapfile.

REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
LOGS="$REPO/logs"
mkdir -p "$LOGS"

API_PORT_BASE=${API_PORT_BASE:-8000}
WEB_PORT_BASE=${WEB_PORT_BASE:-3000}
PORT_SPAN=${PORT_SPAN:-12}

# ---------------------------------------------------------------------------
# From espresso.app
#
# The app has no window and no Terminal, so without these a first start is minutes of
# nothing and a failure is silence. The app's launcher sets ESPRESSO_APP=1 and shows a
# "getting ready" notice (its pid in ESPRESSO_NOTICE_PID); these close it and, on a
# failure, say so in a dialog whose button opens the folder of logs, so the person can see
# what happened and send the logs to whoever helps them. From Terminal they do nothing.
# ---------------------------------------------------------------------------

app_notice_close() {
  if [ -n "${ESPRESSO_NOTICE_PID:-}" ]; then kill "$ESPRESSO_NOTICE_PID" 2>/dev/null; fi
  return 0
}

app_failure_dialog() {  # message
  [ "${ESPRESSO_APP:-}" = 1 ] || return 0
  app_notice_close
  osascript - "${1:0:900}" "${ESPRESSO_HOME:-$LOGS}" >/dev/null 2>&1 <<'OSA'
on run argv
  activate
  set msg to "espresso could not start." & return & return & (item 1 of argv)
  set r to display dialog msg with title "espresso" buttons {"Show logs", "OK"} default button "OK" with icon caution
  if button returned of r is "Show logs" then do shell script "open " & quoted form of (item 2 of argv)
end run
OSA
  return 0
}

# ---------------------------------------------------------------------------
# First run
#
# Each install step records a checksum of its lockfile and is skipped while the lockfile
# still matches, so a normal start costs two checksums. Timestamps would not do: `-nt`
# resolves to the second, and the stamp lands in the same second as the lockfile npm has
# just rewritten. Output goes to logs/setup.log, and a failure names the log rather than
# describing what might be in it.
# ---------------------------------------------------------------------------

checksum() { cksum < "$1" | cut -d' ' -f1; }

# up_to_date <stamp> <lockfile>: the stamp holds the lockfile's checksum from the last
# successful install.
up_to_date() { [ -f "$1" ] && [ "$(cat "$1")" = "$(checksum "$2")" ]; }

need_tool() {  # name, what to do about it
  command -v "$1" >/dev/null 2>&1 && return 0
  # Fetch it into the app's own folder first; only fail when that cannot be done.
  # shellcheck source=scripts/bootstrap.sh
  . "$REPO/scripts/bootstrap.sh"
  case "$1" in
    uv) ensure_uv && return 0 ;;
    node|npm) ensure_node && return 0 ;;
  esac
  fail "$1 is not installed. $2"
}

log_tail() { tail -n 12 "$LOGS/setup.log" 2>/dev/null; }

setup_backend() {
  local stamp="$REPO/backend/.venv/.espresso-synced" lock="$REPO/backend/uv.lock"
  if [ -x "$REPO/backend/.venv/bin/python" ] && up_to_date "$stamp" "$lock"; then
    return 0
  fi
  need_tool uv "Install it with:
  curl -LsSf https://astral.sh/uv/install.sh | sh

then start espresso again."
  say "Installing the API's Python packages. First run only, about a minute."
  # --frozen installs exactly the lockfile. Python itself is fetched by uv if the
  # machine has none of the right version, so there is nothing else to install.
  if ! ( cd "$REPO/backend" && uv sync --frozen --extra dev ) >>"$LOGS/setup.log" 2>&1; then
    fail "Installing the API's packages failed. The end of $LOGS/setup.log:

$(log_tail)"
  fi
  checksum "$lock" > "$stamp"
}

setup_frontend() {
  local fe="$REPO/frontend" stamp lock built newer
  stamp="$fe/node_modules/.espresso-installed"; lock="$fe/package-lock.json"
  if [ ! -d "$fe/node_modules" ] || ! up_to_date "$stamp" "$lock"; then
    need_tool node "Install Node.js from https://nodejs.org (or: brew install node),
then start espresso again."
    say "Installing the web app's packages. First run only, about a minute."
    if ! ( cd "$fe" && npm install --no-fund --no-audit ) >>"$LOGS/setup.log" 2>&1; then
      fail "Installing the web app's packages failed. The end of $LOGS/setup.log:

$(log_tail)"
    fi
    checksum "$lock" > "$stamp"
  fi

  # The dev server is for working on the app. Everyone else gets a production build,
  # which loads faster and has no dev overlay. Rebuilt only when a source file is newer
  # than the last build.
  [ "${ESPRESSO_DEV:-}" = 1 ] && return 0
  built="$fe/.next/BUILD_ID"
  if [ -f "$built" ]; then
    newer=$(cd "$fe" && find app components lib public next.config.ts package.json \
              tsconfig.json postcss.config.mjs -type f -newer .next/BUILD_ID -print 2>/dev/null | head -1)
    [ -z "$newer" ] && return 0
    say "Rebuilding the web app: $newer changed."
  else
    say "Building the web app. First run only, about a minute."
  fi
  if ! ( cd "$fe" && ./node_modules/.bin/next build ) >>"$LOGS/setup.log" 2>&1; then
    fail "Building the web app failed. The end of $LOGS/setup.log:

$(log_tail)"
  fi
  WEB_REBUILT=1
}
WEB_REBUILT=0

# web_action <port> <reuse|start>: prints the action to take. A running instance is fine to
# keep unless the build just changed under it, in which case it is serving a mix of old
# and new files and has to come back up on the new build.
web_action() {
  if [ "$2" = reuse ] && [ "$WEB_REBUILT" = 1 ]; then
    stop_port "$1"
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do port_is_free "$1" && break; sleep 1; done
    echo start
  else
    echo "$2"
  fi
}

# ---------------------------------------------------------------------------
# Ports
#
# A listening port is not the same thing as our service. Port 3000 is the default for
# every Node dev server ever written and 8000 for every Python one, so "something is
# listening" tells you nothing about what. Checking the port alone means adopting a
# stranger's server: reporting "already running", then opening the browser onto their page.
#
# So each service is identified by asking it who it is, and when the preferred port is held
# by something else we move to the next one rather than failing.
# ---------------------------------------------------------------------------

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

is_our_api() {
  curl -fsS --max-time 3 "http://127.0.0.1:$1/api/health" 2>/dev/null \
    | grep -qi '"app"[[:space:]]*:[[:space:]]*"espresso"'
}

is_our_web() {
  curl -fsS --max-time 5 "http://127.0.0.1:$1/" 2>/dev/null | grep -q 'espresso'
}

# resolve_port <api|web> -> prints "<port> <reuse|start>", or nothing when the whole span
# is occupied by other people's servers.
resolve_port() {
  local kind=$1 base probe port
  if [ "$kind" = "api" ]; then base=$API_PORT_BASE; probe=is_our_api
  else base=$WEB_PORT_BASE; probe=is_our_web
  fi

  # An instance we started earlier wins, wherever it sits. Otherwise a second copy comes
  # up on the free base port while the first keeps running, and they fight over the store.
  for port in $(seq "$base" $((base + PORT_SPAN))); do
    if ! port_is_free "$port" && $probe "$port"; then
      echo "$port reuse"
      return 0
    fi
  done

  for port in $(seq "$base" $((base + PORT_SPAN))); do
    if port_is_free "$port"; then
      echo "$port start"
      return 0
    fi
  done

  return 1
}

wait_for_service() {  # kind, port, seconds
  local probe=is_our_api
  [ "$1" = "web" ] && probe=is_our_web
  local i
  for i in $(seq 1 "$3"); do
    $probe "$2" && return 0
    sleep 1
  done
  return 1
}

# ---------------------------------------------------------------------------
# Starting
# ---------------------------------------------------------------------------

start_api() {  # port
  # `cd; cmd & disown`, not `cd && cmd &`: backgrounding an AND-list makes the calling shell
  # own the job, and it then prints a "Terminated" line when the stop path kills the server.
  ( cd "$REPO/backend"; API_PORT="$1" nohup .venv/bin/python main.py >"$LOGS/api.log" 2>&1 & disown )
  wait_for_service api "$1" 120 || fail "The API did not start on port $1. See:

$LOGS/api.log"
}

start_web() {  # web port, api port
  # The web app proxies /api to the API at request time, so the API port is plain runtime
  # configuration and the build does not depend on it. Bound to localhost: this is a
  # private tool, and Next would otherwise listen on every interface.
  local cmd="start"
  [ "${ESPRESSO_DEV:-}" = 1 ] && cmd="dev"
  ( cd "$REPO/frontend"; API_URL="http://127.0.0.1:$2" \
      nohup ./node_modules/.bin/next "$cmd" -H 127.0.0.1 -p "$1" >"$LOGS/web.log" 2>&1 & disown )
  wait_for_service web "$1" 120 || fail "The web app did not start on port $1. See:

$LOGS/web.log"
}

# The API's own account of whether it can build a paper. Reading papers works without a
# model; building one does not, and it is better to say so now than to let the first build
# fail three minutes in. Prints the provider string; empty when health could not be read.
llm_status() {  # api port
  curl -s --max-time 8 "http://127.0.0.1:$1/api/health" \
    | "$REPO/backend/.venv/bin/python" -c \
        'import sys,json;print(json.load(sys.stdin)["services"]["llm_provider"])' 2>/dev/null
}

# What to tell the reader about a provider string that cannot build. Empty when it can.
llm_advice() {  # provider string
  case "$1" in
    unconfigured*)
      echo "No model is set up, so new papers cannot be built. Papers already built will still open.

Open Settings in the app to use your own API key (Anthropic, OpenAI or compatible, Azure),
or install Claude Code and sign in:
  npm install -g @anthropic-ai/claude-code
  claude"
      ;;
    *"not logged in"*)
      echo "Claude Code is installed but not signed in, so new papers cannot be built. Papers already built will still open.

Run this in a terminal and sign in:
  claude"
      ;;
    *"cannot build"*)
      echo "The model provider is not ready, so new papers cannot be built:
${1#*cannot build: }"
      ;;
  esac
}

stop_port() {  # port
  kill $(lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null) 2>/dev/null
}

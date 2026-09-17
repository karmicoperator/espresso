# Port resolution shared by MedScroll.app and start.command.
#
# A listening port is not the same thing as our service. Port 3000 is the default for
# every Node dev server ever written and 8000 for every Python one, so "something is
# listening" tells you nothing about what. Checking the port alone means adopting a
# stranger's server: reporting "already running", then opening the browser onto their page.
#
# So each service is identified by asking it who it is, and when the preferred port is held
# by something else we move to the next one rather than failing. Both ports are already
# configurable (API_PORT on the backend, -p and NEXT_PUBLIC_API_URL on the frontend), so
# moving costs nothing.

API_PORT_BASE=${API_PORT_BASE:-8000}
WEB_PORT_BASE=${WEB_PORT_BASE:-3000}
PORT_SPAN=${PORT_SPAN:-12}

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

is_our_api() {
  curl -fsS --max-time 3 "http://127.0.0.1:$1/api/health" 2>/dev/null \
    | grep -qi '"app"[[:space:]]*:[[:space:]]*"medscroll"'
}

is_our_web() {
  curl -fsS --max-time 5 "http://127.0.0.1:$1/" 2>/dev/null | grep -q 'MedScroll'
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

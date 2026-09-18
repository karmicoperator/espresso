#!/bin/bash
# espresso: fetch the two tools the app needs when the machine has neither.
#
# uv brings its own Python; Node comes from nodejs.org as a plain tarball. Both land under
# the app's own folder, never in system paths and never through Homebrew, so a person who
# has never opened Terminal can double-click the app and have it work. Sourced by
# launch-lib.sh; safe to source twice.
#
#   ESPRESSO_HOME   where tools and logs live (default ~/Library/Application Support/espresso)

PIF_HOME=${ESPRESSO_HOME:-"$HOME/Library/Application Support/espresso"}
PIF_TOOLS="$PIF_HOME/tools"
NODE_VERSION=${ESPRESSO_NODE:-v22.12.0}

mkdir -p "$PIF_TOOLS"
export PATH="$PIF_TOOLS/bin:$PIF_TOOLS/node/bin:$HOME/.local/bin:$PATH"

pif_arch() {
  case "$(uname -m)" in
    arm64|aarch64) echo arm64 ;;
    *) echo x64 ;;
  esac
}

ensure_uv() {
  command -v uv >/dev/null 2>&1 && return 0
  echo "  Fetching uv (brings Python with it)..."
  # Astral's installer, told to put the binary in our folder.
  if ! curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$PIF_TOOLS/bin" UV_NO_MODIFY_PATH=1 sh >>"$PIF_HOME/bootstrap.log" 2>&1; then
    echo "  Could not fetch uv. Is the machine online? See $PIF_HOME/bootstrap.log"; return 1
  fi
  command -v uv >/dev/null 2>&1
}

ensure_node() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && return 0
  local os arch tar url
  case "$(uname -s)" in Darwin) os=darwin ;; Linux) os=linux ;; *) echo "  Unsupported OS $(uname -s)"; return 1 ;; esac
  arch=$(pif_arch)
  tar="node-$NODE_VERSION-$os-$arch.tar.gz"
  url="https://nodejs.org/dist/$NODE_VERSION/$tar"
  echo "  Fetching Node.js $NODE_VERSION ($os $arch)..."
  if ! curl -LsSf "$url" -o "$PIF_TOOLS/$tar" >>"$PIF_HOME/bootstrap.log" 2>&1; then
    echo "  Could not fetch Node.js from $url. See $PIF_HOME/bootstrap.log"; return 1
  fi
  rm -rf "$PIF_TOOLS/node"
  mkdir -p "$PIF_TOOLS/node"
  tar -xzf "$PIF_TOOLS/$tar" -C "$PIF_TOOLS/node" --strip-components=1 && rm -f "$PIF_TOOLS/$tar"
  command -v node >/dev/null 2>&1
}

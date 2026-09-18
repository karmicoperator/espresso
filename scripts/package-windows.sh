#!/bin/bash
# Build dist/espresso-windows.zip: the source at HEAD in an `espresso` folder, with
# "Start espresso.bat" at its top so the first thing a person sees after unzipping is what
# to double-click. That runs windows\espresso.ps1, which fetches uv and Node into
# %LOCALAPPDATA%\espresso\tools, builds, starts and opens the browser.
#
# Windows marks a downloaded zip as coming from the internet, so the first double-click may
# say the publisher could not be verified: More info, Run anyway. The launcher is untested
# on a real Windows machine; its log says which step failed if one does.
set -eu
cd "$(dirname "$0")/.."
DIST="$PWD/dist"
VERSION=$(git rev-parse --short HEAD)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
OUT="$WORK/espresso"
mkdir -p "$OUT" "$DIST"

# Tracked files only, so nothing local (data, .env, builds) can leak into the download.
git ls-files -z | COPYFILE_DISABLE=1 tar --null -T - -cf - | tar -xf - -C "$OUT"
echo "$VERSION" > "$OUT/VERSION"

printf '%s\r\n' '@echo off' \
  'rem espresso: double-click to start. The first run fetches Python and Node.js and builds' \
  'rem the app, about five minutes; later runs take seconds. The browser opens by itself.' \
  'rem Keep the window open while you use espresso; Ctrl-C in it stops espresso.' \
  'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\espresso.ps1"' \
  > "$OUT/Start espresso.bat"
# cmd.exe expects Windows line endings in batch files.
perl -pi -e 's/\r?\n/\r\n/' "$OUT"/windows/*.bat

rm -f "$DIST/espresso-windows.zip"
( cd "$WORK" && zip -qrX "$DIST/espresso-windows.zip" espresso )
echo "built $DIST/espresso-windows.zip ($VERSION), $(du -sh "$DIST/espresso-windows.zip" | cut -f1)"

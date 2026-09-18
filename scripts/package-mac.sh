#!/bin/bash
# Build dist/espresso.app and dist/espresso-mac.zip: the download for a person who
# will never open Terminal.
#
# The bundle carries the source (git HEAD, no data), the logo as an icon, and a launcher
# that on first run copies the source to ~/Library/Application Support/espresso, fetches
# uv and Node if the machine has neither, builds, starts, and opens the browser. Later runs
# reuse everything. The bundle is not signed: the first open is right-click, Open.
set -eu
cd "$(dirname "$0")/.."
REPO=$PWD
DIST="$REPO/dist"
APP="$DIST/espresso.app"
VERSION=$(git rev-parse --short HEAD)

rm -rf "$APP" "$DIST/espresso-mac.zip"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/repo"

# Source: the tracked files as they are in the working tree, minus the data. A release
# is built from a clean checkout, where that is HEAD; a test build carries staged work.
git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$APP/Contents/Resources/repo"
echo "$VERSION" > "$APP/Contents/Resources/repo/VERSION"

# Icon: the logo, as the sizes macOS wants.
ICONSET="$DIST/espresso.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s frontend/public/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); [ $d -le 1024 ] && sips -z $d $d frontend/public/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/espresso.icns"
rm -rf "$ICONSET"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>espresso</string>
  <key>CFBundleDisplayName</key><string>espresso</string>
  <key>CFBundleIdentifier</key><string>org.espresso.app</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleExecutable</key><string>espresso</string>
  <key>CFBundleIconFile</key><string>espresso</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/espresso" <<'LAUNCH'
#!/bin/bash
# espresso, from the app bundle. No Terminal: everything goes to a log, the browser opens.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PIF_HOME=${ESPRESSO_HOME:-"$HOME/Library/Application Support/espresso"}
mkdir -p "$PIF_HOME"
LOG="$PIF_HOME/app.log"
exec >>"$LOG" 2>&1
echo "=== $(date) start"

# The source lives in the app's folder, copied from the bundle on first run and again when
# the bundle is a newer version. Papers built (data/) survive a copy: they are kept aside.
BUNDLED="$HERE/Resources/repo"
REPO="$PIF_HOME/repo"
WANT=$(cat "$BUNDLED/VERSION" 2>/dev/null || echo dev)
HAVE=$(cat "$REPO/VERSION" 2>/dev/null || echo none)
if [ "$WANT" != "$HAVE" ]; then
  echo "installing source $WANT (had $HAVE)"
  KEEP=""
  if [ -d "$REPO/backend/data" ]; then KEEP=$(mktemp -d); mv "$REPO/backend/data" "$KEEP/data"; fi
  if [ -f "$REPO/backend/.env" ]; then ENVKEEP=$(mktemp); cp "$REPO/backend/.env" "$ENVKEEP"; else ENVKEEP=""; fi
  rm -rf "$REPO"; mkdir -p "$REPO"
  cp -R "$BUNDLED/." "$REPO/"
  [ -n "$KEEP" ] && mv "$KEEP/data" "$REPO/backend/data"
  [ -n "$ENVKEEP" ] && cp "$ENVKEEP" "$REPO/backend/.env"
fi

export ESPRESSO_HOME="$PIF_HOME"
# shellcheck source=/dev/null
. "$REPO/scripts/bootstrap.sh"
ensure_uv || { osascript -e 'display alert "espresso" message "Could not fetch uv (Python). Check the connection and try again."'; exit 1; }
ensure_node || { osascript -e 'display alert "espresso" message "Could not fetch Node.js. Check the connection and try again."'; exit 1; }

cd "$REPO"
exec ./start.command
LAUNCH
chmod +x "$APP/Contents/MacOS/espresso"

( cd "$DIST" && ditto -c -k --keepParent espresso.app espresso-mac.zip )
echo "built $APP ($VERSION), $(du -sh "$DIST/espresso-mac.zip" | cut -f1) zipped"

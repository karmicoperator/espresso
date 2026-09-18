#!/bin/bash
# Build dist/espresso-macOS.dmg, the download for a person who will never open Terminal: open it,
# drag espresso onto Applications, double-click.
#
# The app carries the source (git HEAD, no data), the logo as its icon, a small compiled
# executable (scripts/mac/stub.c) and the launcher script that executable runs. On first
# run the launcher copies the source to ~/Library/Application Support/espresso, fetches uv
# and Node if the machine has neither, builds, starts, and opens the browser. Later runs
# reuse everything.
#
# Signing. macOS opens a downloaded app without asking only when it is signed with a
# Developer ID certificate and notarized by Apple, which needs the paid Apple Developer
# Program. With both of these set, the build is signed, notarized and stapled:
#   ESPRESSO_SIGN_ID="Developer ID Application: Your Name (TEAMID)"
#   ESPRESSO_NOTARY_PROFILE=espresso   # once: xcrun notarytool store-credentials espresso
# Without them the app is signed ad hoc. It runs, but the first open needs one approval in
# System Settings, Privacy & Security, and the disk image's window says so. (Right-click,
# Open stopped working as a way round this in macOS 15.)
#
# Needs: Xcode command line tools (clang, codesign, hdiutil) and uv.
set -eu
cd "$(dirname "$0")/.."
REPO=$PWD
DIST="$REPO/dist"
# The app is assembled, signed and imaged in a local temporary folder. A synced folder
# (an iCloud Desktop, say) keeps adding metadata to files, and codesign will not seal a
# bundle that carries any. Only the finished disk image is copied into dist/.
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
APP="$WORK/espresso.app"
DMG="$WORK/espresso-macOS.dmg"
VERSION=$(git rev-parse --short HEAD)
SIGN_ID=${ESPRESSO_SIGN_ID:-}
NOTARY=${ESPRESSO_NOTARY_PROFILE:-}
command -v uv >/dev/null || { echo "uv is needed to build the disk image: https://docs.astral.sh/uv/" >&2; exit 1; }

rm -rf "$DIST/espresso.app" "$DIST/espresso.dmg" "$DIST/espresso-mac.zip" "$DIST/espresso-macOS.dmg"  # old names too
mkdir -p "$DIST" "$APP/Contents/MacOS" "$APP/Contents/Resources/repo"
# Source: the tracked files as they are in the working tree, minus the data. A release
# is built from a clean checkout, where that is HEAD; a test build carries staged work.
git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$APP/Contents/Resources/repo"
echo "$VERSION" > "$APP/Contents/Resources/repo/VERSION"

# Icon: the logo, as the sizes macOS wants.
ICONSET="$WORK/espresso.iconset"
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

cat > "$APP/Contents/Resources/launcher.sh" <<'LAUNCH'
#!/bin/bash
# espresso, from the app bundle, run by Contents/MacOS/espresso. No Terminal: everything
# goes to a log, the browser opens.
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
  # -X: no extended attributes, so the download's quarantine flag stays on the app and
  # does not ride along onto the scripts this folder runs.
  cp -RX "$BUNDLED/." "$REPO/"
  [ -n "$KEEP" ] && mv "$KEEP/data" "$REPO/backend/data"
  [ -n "$ENVKEEP" ] && cp "$ENVKEEP" "$REPO/backend/.env"
fi

export ESPRESSO_HOME="$PIF_HOME" ESPRESSO_APP=1

# A first start, or the first after an update, downloads and builds for minutes with
# nothing else on screen. Say so; start.command closes this once the browser opens.
if [ "$WANT" != "$HAVE" ] || [ ! -f "$REPO/frontend/.next/BUILD_ID" ] || [ ! -x "$REPO/backend/.venv/bin/python" ]; then
  osascript -e 'activate' -e 'display dialog "espresso is getting ready.

The first start takes about five minutes while it downloads what it needs and builds itself. Your browser opens by itself when it is done." with title "espresso" buttons {"OK"} default button "OK" giving up after 1800' >/dev/null 2>&1 &
  export ESPRESSO_NOTICE_PID=$!
fi

# shellcheck source=/dev/null
. "$REPO/scripts/bootstrap.sh"
# shellcheck source=/dev/null
. "$REPO/scripts/launch-lib.sh"   # app_failure_dialog
ensure_uv || { app_failure_dialog "Could not download uv, which brings Python. Check the internet connection, then open espresso again."; exit 1; }
ensure_node || { app_failure_dialog "Could not download Node.js. Check the internet connection, then open espresso again."; exit 1; }

cd "$REPO"
exec ./start.command
LAUNCH
chmod +x "$APP/Contents/Resources/launcher.sh"

# The executable: a universal binary that hands over to launcher.sh.
clang -arch arm64 -arch x86_64 -mmacosx-version-min=12.0 -Os -Wall -Wextra \
  -o "$APP/Contents/MacOS/espresso" scripts/mac/stub.c

# Apple's notary service answers in JSON; plutil reads it, so no extra tools are needed.
notarize() {
  local out status id
  out=$(xcrun notarytool submit "$1" --keychain-profile "$NOTARY" --wait --output-format json)
  status=$(printf '%s' "$out" | plutil -extract status raw -o - -)
  id=$(printf '%s' "$out" | plutil -extract id raw -o - -)
  if [ "$status" != "Accepted" ]; then
    echo "notarization of $(basename "$1") returned $status; details: xcrun notarytool log $id --keychain-profile $NOTARY" >&2
    exit 1
  fi
}

# Files copied out of a working tree can carry Finder metadata in extended attributes, and
# codesign refuses to seal a bundle that has any.
xattr -cr "$APP"

NOTARIZED=0
if [ -n "$SIGN_ID" ]; then
  codesign --force --options runtime --timestamp --sign "$SIGN_ID" "$APP"
else
  codesign --force --sign - "$APP"
fi
codesign --verify --strict "$APP"
if [ -n "$SIGN_ID" ] && [ -n "$NOTARY" ]; then
  ditto -c -k --keepParent "$APP" "$WORK/app.zip"
  notarize "$WORK/app.zip"
  xcrun stapler staple "$APP"
  NOTARIZED=1
elif [ -n "$SIGN_ID" ]; then
  echo "note: signed but not notarized (ESPRESSO_NOTARY_PROFILE is unset); macOS will still ask on first open" >&2
fi

# The disk image: app on the left, Applications on the right, the background between them.
if [ "$NOTARIZED" = 1 ]; then NOTE=""; else NOTE="--unsigned"; fi
uv run --quiet --project backend python scripts/mac/dmg-background.py "$WORK" $NOTE >/dev/null
tiffutil -cathidpicheck "$WORK/background.png" "$WORK/background@2x.png" -out "$WORK/background.tiff" 2>/dev/null
uvx --quiet --from 'dmgbuild==1.6.7' dmgbuild -s scripts/mac/dmg-settings.py \
  -D app="$APP" -D volicon="$APP/Contents/Resources/espresso.icns" -D background="$WORK/background.tiff" \
  espresso "$DMG" >/dev/null
if [ -n "$SIGN_ID" ]; then
  codesign --force --timestamp --sign "$SIGN_ID" "$DMG"
  if [ "$NOTARIZED" = 1 ]; then notarize "$DMG"; xcrun stapler staple "$DMG"; fi
fi
hdiutil verify -quiet "$DMG"
cp "$DMG" "$DIST/espresso-macOS.dmg"

if [ "$NOTARIZED" = 1 ]; then TRUST="signed and notarized"
elif [ -n "$SIGN_ID" ]; then TRUST="signed, not notarized"
else TRUST="ad hoc signature, first open needs approval"; fi
echo "built $DIST/espresso-macOS.dmg ($VERSION), $(du -sh "$DMG" | cut -f1), $TRUST"

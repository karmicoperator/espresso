#!/bin/bash
# Build dist/espresso-Windows-setup.exe: a per-user installer (windows/installer.nsi) holding
# the source at HEAD. It installs without an administrator password, adds Start menu and
# desktop shortcuts, and registers an uninstaller under Settings, Apps.
#
# Needs makensis (NSIS 3): `brew install makensis` on a Mac; GitHub's Windows runners have it,
# and .github/workflows/windows.yml builds the installer there and tests it end to end.
set -eu
cd "$(dirname "$0")/.."
DIST="$PWD/dist"
VERSION=$(git rev-parse --short HEAD)
command -v makensis >/dev/null || { echo "makensis (NSIS 3) is needed: brew install makensis" >&2; exit 1; }
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
PAYLOAD="$WORK/payload"
mkdir -p "$PAYLOAD" "$DIST"

# Tracked files only, so nothing local (data, .env, builds) can leak into the download.
git ls-files -z | COPYFILE_DISABLE=1 tar --null -T - -cf - | tar -xf - -C "$PAYLOAD"
echo "$VERSION" > "$PAYLOAD/VERSION"
# cmd.exe expects Windows line endings in batch files.
perl -pi -e 's/\r?\n/\r\n/' "$PAYLOAD"/windows/*.bat

# makensis on Windows wants Windows paths; Git Bash's cygpath gives them.
winpath() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }
rm -f "$DIST/espresso-Windows-setup.exe" "$DIST/espresso-windows.zip"
makensis -V2 -DVERSION="$VERSION" -DPAYLOAD="$(winpath "$PAYLOAD")" \
  -DOUTFILE="$(winpath "$DIST/espresso-Windows-setup.exe")" windows/installer.nsi
echo "built $DIST/espresso-Windows-setup.exe ($VERSION), $(du -sh "$DIST/espresso-Windows-setup.exe" | cut -f1)"

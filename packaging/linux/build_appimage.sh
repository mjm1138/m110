#!/usr/bin/env bash
# Build M110-<version>-<arch>.AppImage on a Linux host.
#
#   pip install -e ".[build]"
#   ./packaging/linux/build_appimage.sh
#
# Steps: PyInstaller onedir -> AppDir (AppRun + .desktop + icon) -> appimagetool.
# Must run on Linux (PyInstaller can't cross-compile). Build on the OLDEST glibc you
# want to support (e.g. Ubuntu 22.04) so the AppImage runs on newer distros too.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

ARCH="$(uname -m)"
APPDIR="$ROOT/build/M110.AppDir"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "error: pyinstaller not found. Run: pip install -e \".[build]\"" >&2
  exit 1
fi

# appimagetool: from $APPIMAGETOOL, else PATH. We do NOT auto-download it.
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [[ -z "$APPIMAGETOOL" ]]; then
  cat >&2 <<'MSG'
error: appimagetool not found. Install it once, e.g.:
  wget -O ~/.local/bin/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x ~/.local/bin/appimagetool
then re-run (or pass APPIMAGETOOL=/path/to/appimagetool).
MSG
  exit 1
fi

VERSION="$(python -c 'from importlib.metadata import version; from packaging.version import Version; print(".".join(map(str, Version(version("m110")).release)))' 2>/dev/null || echo 0.0.0)"

echo "==> PyInstaller onedir build"
rm -rf build/M110 dist/M110
pyinstaller "$HERE/M110.spec" --noconfirm --clean

echo "==> assembling AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a dist/M110/. "$APPDIR/usr/bin/"

# Icon (256px parchment tile). Top-level copy + hicolor theme path; name matches
# the .desktop Icon= key ("m110").
ICON="$ROOT/m110/ui/theme/brand/app-icon.png"
cp "$ICON" "$APPDIR/m110.png"
cp "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/m110.png"

# .desktop (top-level required by appimagetool + the standard share path).
cp "$HERE/m110.desktop" "$APPDIR/m110.desktop"
cp "$HERE/m110.desktop" "$APPDIR/usr/share/applications/m110.desktop"

# AppRun: entry the AppImage runtime execs. Resolve our own dir, run the binary.
#
# `--mcp` and `--stack` dispatch to the bundled helper binaries instead of the
# GUI. This is the one platform where an argv flag is the right answer: an
# AppImage is a self-mounting archive with no persistent internal path, so
# nothing outside can point at usr/bin/m110-mcp the way it can on macOS and
# Windows. Callers point at the .AppImage itself with args ["--mcp"] (or
# ["--stack"]), and this dispatches. (Everywhere else the helpers are addressed
# directly — see M110.spec.)
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
case "$1" in
  --mcp)   shift; exec "${HERE}/usr/bin/m110-mcp" "$@" ;;
  --stack) shift; exec "${HERE}/usr/bin/m110-stack" "$@" ;;
esac
exec "${HERE}/usr/bin/M110" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

echo "==> appimagetool"
mkdir -p dist
OUT="$ROOT/dist/M110-${VERSION}-${ARCH}.AppImage"
rm -f "$OUT"
ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUT"

echo "==> built: $OUT"
echo "    run it:  chmod +x \"$OUT\" && \"$OUT\""
echo "    (host needs libfuse2 for the AppImage runtime; or run with --appimage-extract-and-run)"

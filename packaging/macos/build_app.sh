#!/usr/bin/env bash
# Build dist/M110.app with PyInstaller. Unsigned — fast to iterate.
#
# Prereqs: a Python env with the app + build deps installed:
#     pip install -e ".[build]"      # pulls pyinstaller
# and the icon built:
#     ./packaging/macos/make_icns.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "error: pyinstaller not found. Run: pip install -e \".[build]\"" >&2
  exit 1
fi

[[ -f "$HERE/M110.icns" ]] || "$HERE/make_icns.sh"

echo "==> building dist/M110.app"
rm -rf build dist/M110 dist/M110.app
pyinstaller "$HERE/M110.spec" --noconfirm --clean

echo "==> built: dist/M110.app"
echo "    smoke-test it with:  open dist/M110.app   (or ./dist/M110.app/Contents/MacOS/M110 for console output)"

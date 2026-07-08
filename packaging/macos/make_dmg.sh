#!/usr/bin/env bash
# Build a drag-to-Applications DMG from dist/M110.app → dist/M110-<version>.dmg.
#
# Run AFTER sign_notarize.sh so the .app inside carries its stapled ticket. The
# DMG itself is then signed; for belt-and-suspenders you can also notarize the DMG
# (see README) so Gatekeeper is happy even before first launch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/dist/M110.app"
[[ -d "$APP" ]] || { echo "error: $APP not found — run build_app.sh first" >&2; exit 1; }

# Marketing version from the .app's Info.plist (set by the spec).
VERSION="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' \
  "$APP/Contents/Info.plist" 2>/dev/null || echo 0.0.0)"
DMG="$ROOT/dist/M110-${VERSION}.dmg"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"     # drag-target

echo "==> building $DMG"
rm -f "$DMG"
hdiutil create -volname "M110 ${VERSION}" -srcfolder "$STAGE" \
  -ov -format UDZO "$DMG" >/dev/null

# Sign the DMG too if an identity is available (optional but tidy).
if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
fi

echo "==> built: $DMG"
echo "    (optional) notarize the DMG:  xcrun notarytool submit \"$DMG\" --keychain-profile M110-notary --wait && xcrun stapler staple \"$DMG\""

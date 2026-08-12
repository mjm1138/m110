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
# macOS deprecated `hdiutil create -volname -format` in favour of `diskutil image
# create from` (it prints a WARNING on every build). Verified equivalent on this
# toolchain: both produce a UDZO image, GUID scheme, APFS volume, same volume name,
# with the /Applications symlink intact, and the result codesigns and notarizes the
# same. `diskutil image` is recent, so fall back to hdiutil where it's absent —
# the deprecated form still works, and a build machine on an older macOS should not
# be a broken build. No `-ov` equivalent is needed; the rm above is the overwrite.
if diskutil image create from --help >/dev/null 2>&1; then
  diskutil image create from --format UDZO --volumeName "M110 ${VERSION}" \
    "$STAGE" "$DMG" >/dev/null
else
  hdiutil create -volname "M110 ${VERSION}" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
fi

# Sign the DMG too if an identity is available (optional but tidy).
if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
fi

echo "==> built: $DMG"
echo "    (optional) notarize the DMG:  xcrun notarytool submit \"$DMG\" --keychain-profile M110-notary --wait && xcrun stapler staple \"$DMG\""

#!/usr/bin/env bash
# Sign (Developer ID, hardened runtime), notarize, and staple dist/M110.app.
#
# One-time setup on the build Mac:
#   1. Developer ID Application cert installed in the login keychain (Xcode →
#      Settings → Accounts → Manage Certificates, or the Developer portal).
#      Find its name:  security find-identity -v -p codesigning
#   2. Store notarization credentials once (Apple ID + app-specific password +
#      team id) as a reusable keychain profile:
#        xcrun notarytool store-credentials M110-notary \
#          --apple-id "you@example.com" --team-id "TEAMID1234" --password "app-specific-pw"
#
# Usage:
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID1234)" \
#     ./packaging/macos/sign_notarize.sh
#
# The notary profile name defaults to "M110-notary" (override NOTARY_PROFILE).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/dist/M110.app"
ENTITLEMENTS="$HERE/entitlements.plist"
NOTARY_PROFILE="${NOTARY_PROFILE:-M110-notary}"

: "${SIGN_IDENTITY:?set SIGN_IDENTITY to your \"Developer ID Application: … (TEAMID)\" name}"
[[ -d "$APP" ]] || { echo "error: $APP not found — run build_app.sh first" >&2; exit 1; }

echo "==> signing nested Mach-O binaries (inside-out)"
# Sign every nested dylib/.so first, then bundled frameworks, then the app last.
# --deep is intentionally avoided (Apple discourages it; it mis-signs nested code).
find "$APP" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 |
  while IFS= read -r -d '' f; do
    codesign --force --timestamp --options runtime \
      --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$f"
  done

# Sign any nested .framework bundles (e.g. Qt frameworks PyInstaller may embed).
find "$APP" -type d -name "*.framework" -print0 |
  while IFS= read -r -d '' fw; do
    codesign --force --timestamp --options runtime \
      --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$fw"
  done

# The bundled helper executables (Contents/MacOS/m110-mcp, m110-stack). Each is
# a further executable from the same PyInstaller COLLECT — not a dylib and not a
# framework, so neither find above matches it — and an unsigned Mach-O beside the
# main binary fails notarization. Sign them before the outer bundle, like
# everything else. Any EXE added to the spec's COLLECT belongs in this list.
for helper in m110-mcp m110-stack; do
  BIN="$APP/Contents/MacOS/$helper"
  if [ -f "$BIN" ]; then
    echo "==> signing the bundled $helper"
    codesign --force --timestamp --options runtime \
      --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$BIN"
  else
    echo "    WARNING: $BIN not found — it is missing from this build"
  fi
done

echo "==> signing the app bundle"
codesign --force --timestamp --options runtime \
  --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$APP"

echo "==> verifying signature"
codesign --verify --deep --strict --verbose=2 "$APP"
spctl --assess --type execute --verbose=2 "$APP" || \
  echo "    (spctl will pass only after notarization + staple, below)"

echo "==> notarizing (zip → notarytool submit --wait)"
ZIP="$ROOT/dist/M110-notarize.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
rm -f "$ZIP"

echo "==> stapling the ticket to the .app"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=2 "$APP"

echo "==> done: dist/M110.app is signed, notarized, and stapled"

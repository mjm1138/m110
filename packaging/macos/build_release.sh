#!/usr/bin/env bash
# One-shot macOS release: icon → app → sign+notarize+staple → DMG.
#
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID1234)" \
#     ./packaging/macos/build_release.sh
#
# Skip signing (unsigned local build for testing) by leaving SIGN_IDENTITY unset —
# it builds the .app and DMG but does not sign/notarize.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$HERE/make_icns.sh"
"$HERE/build_app.sh"

if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  "$HERE/sign_notarize.sh"
else
  echo "==> SIGN_IDENTITY unset — skipping sign/notarize (unsigned test build)"
fi

"$HERE/make_dmg.sh"
echo "==> release artifacts in dist/"

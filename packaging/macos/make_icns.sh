#!/usr/bin/env bash
# Build packaging/macos/M110.icns from the 1024px brand master.
#
# macOS .icns bundles several resolutions; iconutil builds one from a .iconset
# directory of correctly-named PNGs. We downscale the 1024 master with sips.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MASTER="$ROOT/m110/ui/theme/brand/app-icon@1024.png"
ICONSET="$HERE/M110.iconset"
OUT="$HERE/M110.icns"

if [[ ! -f "$MASTER" ]]; then
  echo "error: master icon not found: $MASTER" >&2
  echo "       (regenerate it with: python tools/gen_app_icon.py)" >&2
  exit 1
fi

rm -rf "$ICONSET"
mkdir -p "$ICONSET"

# name            size
for spec in \
  "icon_16x16.png 16" \
  "icon_16x16@2x.png 32" \
  "icon_32x32.png 32" \
  "icon_32x32@2x.png 64" \
  "icon_128x128.png 128" \
  "icon_128x128@2x.png 256" \
  "icon_256x256.png 256" \
  "icon_256x256@2x.png 512" \
  "icon_512x512.png 512" \
  "icon_512x512@2x.png 1024"; do
  set -- $spec
  sips -z "$2" "$2" "$MASTER" --out "$ICONSET/$1" >/dev/null
done

iconutil -c icns "$ICONSET" -o "$OUT"
rm -rf "$ICONSET"
echo "wrote $OUT"

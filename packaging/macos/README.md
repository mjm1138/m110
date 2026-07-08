# macOS packaging

Builds a signed, notarized **M110.app** and a drag-to-Applications **DMG** with
PyInstaller. Lead platform for the beta (see [`../../BETA.md`](../../BETA.md) §1).

## TL;DR

```bash
pip install -e ".[build]"                    # app + pyinstaller
# unsigned local test build (no cert needed):
./packaging/macos/build_release.sh
open dist/M110.app

# full signed + notarized release:
SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID1234)" \
  ./packaging/macos/build_release.sh
```

Artifacts land in `dist/` (git-ignored).

## Pieces

| File | Role |
|---|---|
| `m110_launch.py` | Entry-point shim PyInstaller analyzes (calls `m110.ui.main:main`). |
| `M110.spec` | PyInstaller spec — bundles engine package-data + astropy, sets the `Info.plist` (name, `space.m110.M110` bundle id, version, dark-mode). |
| `entitlements.plist` | Hardened-runtime entitlements needed for a frozen CPython/PySide6 app to notarize + run. |
| `make_icns.sh` | `app-icon@1024.png` → `M110.icns` (via `sips` + `iconutil`). |
| `build_app.sh` | Runs PyInstaller → `dist/M110.app` (unsigned). |
| `sign_notarize.sh` | Inside-out Developer-ID signing, `notarytool` submit, staple. |
| `make_dmg.sh` | `dist/M110.app` → `dist/M110-<version>.dmg`. |
| `build_release.sh` | Orchestrates all of the above. |

## One-time setup on the build Mac

1. **Xcode Command Line Tools** — `xcode-select --install`.
2. **Developer ID Application certificate** in the login keychain (Xcode →
   Settings → Accounts → Manage Certificates, or the Developer portal). Confirm:
   ```bash
   security find-identity -v -p codesigning
   ```
   Use the full `Developer ID Application: … (TEAMID)` string as `SIGN_IDENTITY`.
3. **Notarization credentials** stored once as a keychain profile (uses an
   [app-specific password](https://support.apple.com/en-us/102654)):
   ```bash
   xcrun notarytool store-credentials M110-notary \
     --apple-id "you@example.com" --team-id "TEAMID1234" --password "app-specific-pw"
   ```
   Override the profile name with `NOTARY_PROFILE=…` if you use a different one.

## Notes & gotchas

- **Why inside-out signing, not `--deep`.** Apple discourages `codesign --deep`;
  it mis-signs nested code. `sign_notarize.sh` signs every nested `.dylib`/`.so`
  and framework first, then the app last — the reliable order.
- **The entitlements are deliberate.** A frozen CPython/PySide6 app needs
  `allow-jit`, `allow-unsigned-executable-memory`, and `disable-library-validation`
  to run under the hardened runtime. See the comments in `entitlements.plist`.
- **Version.** The `Info.plist` version comes from the installed package
  (`importlib.metadata`). `CFBundleShortVersionString` is the numeric release
  (`0.1.0`); the full PEP 440 string (`0.1.0b1`) goes in `CFBundleVersion`. Bump
  via `pyproject.toml` + `m110/__init__.py` and reinstall before building.
- **Architecture.** `target_arch=None` builds for the host arch (Apple Silicon →
  arm64). For a **universal2** build that also runs on Intel Macs, every wheel in
  the env must ship universal2/both-arch binaries; set `target_arch="universal2"`
  in the spec once that's arranged. Beta can ship arm64-first + note Intel status.
- **First build is slow** (PyInstaller analyzes PySide6). Rebuilds are faster.
- **If the app launches then quits**, run the inner binary directly to see the
  traceback: `./dist/M110.app/Contents/MacOS/M110`. A missing module → add it to
  `hiddenimports` in the spec; a missing data file → to `datas`.

## CI (later)

This is scripted so a `macos-latest` GitHub Actions job can build + notarize on
tag, with the cert + notary creds supplied via encrypted secrets. Deferred until
the local flow is proven (BETA §1).

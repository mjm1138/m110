# Releasing M110

The end-to-end runbook for cutting a release. The per-platform mechanics live in the
`packaging/*/README.md` files and the distribution strategy in
[`ROADMAP.md`](ROADMAP.md) (Foundational decisions) — this page
stitches them into one checklist.

## How releases work

Releases are **hybrid**:

- **Linux (AppImage) + Windows (installer)** build **automatically in CI** on a
  version tag ([`.github/workflows/release.yml`](.github/workflows/release.yml)) and
  are attached to a **prerelease GitHub Release**. Both ship **unsigned** for the beta.
- **macOS (.dmg)** is built + **signed + notarized locally** — it needs your Apple
  **Developer ID** certificate, which is *not* in CI — and then **uploaded by hand** to
  that same Release.

So a full release is: push a tag (CI makes the Release + Linux/Windows assets), build
the notarized macOS DMG locally, and upload the DMG.

---

## The short version: one command

```bash
python tools/release.py 0.2.0b2            # --dry-run first if you like
```

**[`tools/release.py`](tools/release.py)** runs the whole mechanical sequence below —
version bump (all three spellings), changelog roll, commit/push, **pipeline smoke
test**, tag, wait for CI, macOS build + notarize + staple, DMG upload, and a final
asset check — and **refuses to start** if the tree is dirty, `main` isn't synced, the
tag exists, the changelog has no `[Unreleased]` notes, the tests fail, or your signing
identity is missing.

| Flag | Use |
|---|---|
| `--dry-run` | print every step, change nothing (still runs the real preflight checks) |
| `--skip-macos` | cut the release without the DMG (not on a Mac / no cert) |
| `--resume-from PHASE` | restart mid-release: `preflight bump changelog commit smoke tag wait macos upload verify` |
| `--yes` | skip the "did you do the manual test pass?" prompt |

It takes **one** version in either spelling (`0.2.0b2` or `v0.2.0-beta.2`) and derives
the rest — PEP 440 for the package, SemVer for the tag, numeric for the DMG — which is
the whole class of "the tag and the package disagree" error, gone.

**What it can't do (still yours):** decide the version, write the changelog prose (it
moves your notes, it can't author them), the manual test pass ([`TESTING.md`](TESTING.md)),
verifying the DMG on a Mac **without** your dev cert, and the announce post.

The rest of this page is the **manual path** — what the script does, step by step. Read
it once, use it when something breaks mid-release (then `--resume-from` the phase).

---

## One-time setup (macOS build machine)

1. **Xcode command-line tools:** `xcode-select --install`
2. **Developer ID Application certificate** in your login keychain (Xcode → Settings →
   Accounts → Manage Certificates, or the Developer portal). Confirm it's there and
   grab the full identity string:
   ```bash
   security find-identity -v -p codesigning
   # → "Developer ID Application: Your Name (TEAMID1234)"
   ```
3. **Notarization credentials** stored once as a keychain profile (uses an
   [app-specific password](https://support.apple.com/en-us/102654)):
   ```bash
   xcrun notarytool store-credentials M110-notary \
     --apple-id "you@example.com" --team-id "TEAMID1234" --password "app-specific-pw"
   ```
4. **GitHub CLI** authenticated (for the DMG upload): `gh auth login`

See [`packaging/macos/README.md`](packaging/macos/README.md) for the full detail and
gotchas (inside-out signing, the hardened-runtime entitlements).

## 0. Smoke the release pipeline (do this *before* tagging)

> Scripted: `tools/release.py` phase `smoke`.

`release.yml` only triggers on a `v*` tag, so **nothing in normal CI ever exercises
it** — a broken build step or an artifact-action mismatch stays invisible until the
tag is already pushed and the Release is half-created. Flush that out first with a
manual dispatch, which builds Linux + Windows, uploads the artifacts, **downloads
them back** (proving the artifact actions interoperate), and stops short of
publishing — only the `gh release create` step is tag-gated, so **no Release is
created**:

```bash
gh workflow run release.yml --ref main     # or a branch you're validating
gh run watch                               # green = the pipeline still works
```

Do this whenever the workflow, its actions, or the packaging changed since the last
release — **always after a Dependabot bump to `actions/upload-artifact` or
`actions/download-artifact`**, which must interoperate as a pair (they're grouped
into one PR in `.github/dependabot.yml` for exactly this reason). The dispatched run
also leaves downloadable artifacts, so you can sanity-check the AppImage/installer
before committing to a tag.

## 1. Bump the version

> Scripted: `tools/release.py` phases `bump` + `changelog`.

Edit **both** so they agree:

- `pyproject.toml` → `version = "0.1.0b1"`
- `m110/__init__.py` → `__version__ = "0.1.0b1"`

Then **reinstall so the installed metadata matches** — the packaged app's
`Info.plist` version comes from `importlib.metadata`, so a stale editable install
stamps the wrong number:

```bash
pip install -e ".[build]"
python -c "import importlib.metadata as m; print(m.version('m110'))"   # must print the new version
```

> ⚠️ **The `0.0.1` trap.** If this prints an old version (e.g. `0.0.1`) the build will
> stamp it into the DMG and the app's About box. Always reinstall after a bump.

Commit the bump and merge it to `main` before tagging.

**Roll the changelog in the same commit.** Move everything under `## [Unreleased]` into
a new dated, versioned section (`## [0.2.0-beta.2] - 2026-07-15`). This was a manual
step nobody remembered — both 0.1.0-beta.3 and 0.2.0-beta.1 shipped with the changelog
a release behind. The script does it for you; if you're doing it by hand, don't skip it.

## 2. Cut the release

> Scripted: `tools/release.py` phases `tag` → `wait` → `macos` → `upload`.

Use a `v*` tag (that's what CI triggers on). Example below uses `v0.1.0-beta.1`.

### a. Tag + push → CI builds Linux/Windows and creates the Release

```bash
git tag v0.1.0-beta.1
git push github v0.1.0-beta.1     # `github` = whichever remote points at the GitHub repo
```

CI (`release.yml`) builds the AppImage + Windows `setup.exe` and publishes a
**prerelease** GitHub Release named `M110 v0.1.0-beta.1` with both attached. Watch it:

```bash
gh run watch          # or: gh run list --workflow release.yml
```

### b. Build + notarize the macOS DMG locally

Mikes identity is "Developer ID Application: MICHAEL JAMES MERIDETH (8N7DP84NGU)"
```bash
SIGN_IDENTITY="Developer ID Application: MICHAEL JAMES MERIDETH (8N7DP84NGU)" \
  ./packaging/macos/build_release.sh
```

This signs the app inside-out, notarizes + staples it, and produces
`dist/M110-<version>.dmg`, where `<version>` is the `CFBundleShortVersionString`
(the numeric marketing version, e.g. **`0.1.0`** → `dist/M110-0.1.0.dmg`).

**Optional but recommended — notarize + staple the DMG itself** (so the download is
Gatekeeper-clean, not just the app inside):

```bash
xcrun notarytool submit dist/M110-0.1.0.dmg --keychain-profile M110-notary --wait
xcrun stapler staple dist/M110-0.1.0.dmg
```

### c. Upload the signed DMG to the Release

The Release already exists (CI created it in step **a**), so just attach the DMG:

```bash
gh release upload v0.1.0-beta.1 dist/M110-0.1.0.dmg --clobber
```

- `--clobber` overwrites an existing asset of the same name (safe to re-run).
- **Web alternative:** open the Release on GitHub → **Edit** → drag the `.dmg` into
  the assets area.
- **Fallback — if the Release doesn't exist yet** (e.g. you tagged macOS-only without
  the CI run), create it *with* the DMG:
  ```bash
  gh release create v0.1.0-beta.1 dist/M110-0.1.0.dmg \
    --title "M110 v0.1.0-beta.1" --prerelease --notes "…"
  ```

## 3. Verify

> Partly scripted: `tools/release.py` phase `verify` asserts the three assets exist.
> The Gatekeeper check needs a **human on a Mac without the dev cert**.

- The Release page shows **three assets**: the `.dmg`, the `.AppImage`, and the
  Windows `-setup.exe`.
- The **DMG opens Gatekeeper-clean** on a fresh Mac (no "unidentified developer"
  prompt) — ideally test on a machine without your dev cert.
- The **AppImage** needs `libfuse2` (or run with `--appimage-extract-and-run`); the
  **Windows** installer is unsigned → SmartScreen shows **More info → Run anyway**.
  Make sure the download page / announce post says so.

## See also

- [`packaging/macos/README.md`](packaging/macos/README.md) — signing/notarization detail
- [`packaging/linux/README.md`](packaging/linux/README.md) — AppImage build
- [`packaging/windows/README.md`](packaging/windows/README.md) — installer build

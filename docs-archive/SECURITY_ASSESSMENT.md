# M110 — Threat Model & Security Assessment

*Point-in-time review, 2026-07-15, against `main` at v0.2.0-beta.1. Companion to the
user-facing [`SECURITY.md`](../SECURITY.md) (reporting policy). This document is the
engineering assessment: attack surface, findings, pipeline, and tooling.*

---

## 1. What M110 is, security-wise

A **local, offline-first desktop app** (PySide6 UI over a Qt-free Python engine). It
runs with the **invoking user's own privileges** — no daemon, no elevated helper, no
listening socket. It does not process data on behalf of other users. So the classic
"privileged code execution" worry (a network service parsing attacker input as root)
**does not apply** — there is no privilege boundary to cross upward.

What *does* exist is a **malicious-file boundary**: M110 ingests and parses image and
FITS files from places the user doesn't fully control — an SMB-mounted Seestar, a
DwarfLab SD card, a "Browse to any folder" import, a restored backup. The realistic
threat is **a crafted file that, when imported, makes M110 write or execute something
the user didn't intend** on that user's account. The assessment centers there.

### Assets
- The user's capture library + `library.toml` / journals (integrity).
- The user's wider account: home dir, autostart/login items, other apps' files
  (a traversal or code-exec bug is a foothold into these).
- The release artifacts other users download (supply-chain integrity).

### Trust boundaries
| Boundary | Trusted | Untrusted |
|---|---|---|
| **Ingest** | the M110 code, `config.DATA_ROOT` | source folder names, **FITS headers**, file bytes, filenames, on-device sidecars |
| **Network** | the user's request (Add-object, geocode, update-check) | Simbad / Nominatim / GitHub API responses |
| **Restore** | the snapshot manifest the user chose | file contents inside a snapshot |
| **Pipeline** | the maintainer's commits | third-party deps, GitHub Actions, PyPI |

### Explicitly out of scope (by design)
No server, no auth, no multi-tenant data, no secrets at rest yet (remote-publish
credentials are a *future* surface — [`SECURITY.md`](../SECURITY.md) pre-commits to
OS keychain storage). Signing/notarization of installers is deferred for the beta (a
known, documented gap — see §4).

---

## 2. Attack-surface walk-through

**Network (all optional, all user-initiated, all HTTPS to a fixed host):**
- `updates.py` → `api.github.com/repos/<fixed>/releases`, parsed with `json.loads`;
  version compare via `packaging`; **degrades silently** on any error. Response is
  data, never `eval`'d; no auto-download/execute. ✅ low risk.
- `planning_config.geocode` → `nominatim.openstreetmap.org` with `urllib.parse.urlencode`
  (query is escaped). Sends the user's typed place name to a third party — a
  **privacy** note, not a vuln; it's an explicit online action.
- `catalog` online enrichment → Simbad via `astroquery` (optional `online` extra).

**No** `subprocess`/`os.system`/`shell=True`/`eval`/`exec`/`pickle` in the engine.
The only `subprocess.Popen` calls are `open`/`xdg-open`/`explorer` on a user-chosen
**output folder** path (publish/backup "Open folder") — argument-vector form, no
shell. External links open via `QDesktopServices.openUrl` to app-controlled URLs.

**File parsing (the real surface):**
- **FITS** via `astropy.io.fits` — headers drive classification *and* destination
  folders (see F1). Astropy is a maintained scientific lib; header parsing is the hot
  path.
- **Rasters** via **Pillow** (`Image.open` on imported jpg/png/tif) and **tifffile**
  (Siril float TIFs) — see F2/F3.

**Restore:** `backup.py` reads a per-snapshot JSON manifest and **byte-copies** files
from the snapshot dir. It does **not** extract tar/zip archives, so the classic
"zip-slip" extraction traversal doesn't apply. `restore_dialog` already gates on a
create-vs-overwrite preview. `discard_holding` already refuses to delete paths outside
`Inbox/` (there's a regression test). ✅ These were built defensively.

---

## 3. Findings

### F1 — Path traversal via object/folder name → write outside the data store · **Medium** · FIXED
**Where:** `ingest.canonical_target` / `_emit_files` built a destination as
`config.IMAGES_DIR / obj`, where `obj` came from an untrusted **FITS `OBJECT` header**
(fully attacker-controlled in a crafted `.fit`) or a source folder name.
`fits_object_name` only normalized `"M 13"→"M13"`; a header like
`../../../.config/autostart` passed through unchanged, and `apply_ops` (the sole
writer) had **no containment check** — it `os.makedirs`+wrote to the computed path.

**Impact:** importing a crafted file (which the user must still confirm) could write
attacker-supplied **bytes to a path outside `~/Documents/M110`**, path chosen by the
attacker. Mitigating factors that keep this *Medium*, not *High*: the write is
constrained to content-type extensions (`_is_content_file` — no `.desktop`/`.plist`/
`.sh`, so no direct autostart/exec drop), `_free_dest` avoids overwriting existing
files, and the plan is shown before confirm. Still a genuine write-primitive outside
the store (nuisance/DoS, clobber-adjacent, foothold).

**Fix (this branch):**
- `_safe_segment()` reduces any object name to a single safe path segment (strips
  `/ \ ..` control chars, leading dots; ordinary names like `"M81 M82"` unchanged),
  applied in `canonical_target`.
- **Hard containment guard in `apply_ops`** (defense in depth): the only writer
  resolves every destination and refuses (`ValueError`) any op landing outside
  `config.DATA_ROOT` — catches *every* vector regardless of how the op was built.
- Tests: `test_safe_segment_neutralizes_traversal`,
  `test_canonical_target_cannot_escape_the_store`,
  `test_apply_ops_refuses_writes_outside_the_store`.

### F2 — Vulnerable Pillow floor (untrusted image decode) · **Medium** · FIXED
**Where:** `pyproject.toml` pinned `pillow>=10`, and the dev env resolved to **12.2.0**,
which `pip-audit` flags for **PYSEC-2026-2253…2257** (fixed in 12.3.0). M110 decodes
untrusted imported rasters with Pillow, so a stale floor is a real supply-chain risk.
**Exploitability in M110 today is low** — the flagged paths are PCF/BDF/GD **font**
parsing and the **Windows image-viewer** shell command, none of which M110 exercises
(it decodes JPG/PNG/TIFF and never calls `Image.show()`). But the `>=10` floor
permitted years-old vulnerable builds.
**Fix:** floor raised to `pillow>=12.3`; dev env updated to 12.3.0 (`pip-audit` now
clean); golden-render tests pass unchanged.

### F3 — No decompression-bomb ceiling on imported images · **Low** · FIXED
**Where:** `build_images._open_image` called `Image.open` with Pillow's default
`MAX_IMAGE_PIXELS` (~178 MP warn / 2× error), on untrusted rasters during
refresh/thumbnailing. A tiny crafted file can decode to gigapixels → memory
exhaustion (DoS).
**Fix:** set an explicit `Image.MAX_IMAGE_PIXELS = 300_000_000` (comfortably above any
real astro frame/mosaic; Pillow raises past it, already caught by the surrounding
`except`).

### F4 — CI workflow had no explicit `permissions` · **Low** · FIXED
**Where:** `.github/workflows/ci.yml` set no `permissions:` block, so the job's
`GITHUB_TOKEN` inherited the repo/org default (which can be read/write). A fork PR
runs untrusted code; least privilege matters.
**Fix:** added `permissions: contents: read`. (The `release.yml` job already scopes
`contents: write` correctly, and CI uses `pull_request` — not the dangerous
`pull_request_target` — so fork code never runs with repo secrets.)

### F5 — Privacy: geocode + crash report leak local context · **Informational**
- `geocode` sends the typed place name to Nominatim (third party). Acceptable for an
  explicit online action; worth a one-line note in the field's tooltip/docs.
- `error_report.build_report` includes the data-root path and log tail in the
  prefilled GitHub issue URL. It's user-reviewed before submit and `SECURITY.md` warns
  to redact — adequate. No change needed.

### F6 — Unsigned beta installers · **Accepted (documented)**
macOS/Windows/Linux builds ship unsigned during the beta (a deliberate cost decision;
users are told to bypass Gatekeeper/SmartScreen). This shifts integrity trust to
"downloaded from the right GitHub release over HTTPS." Acceptable for a beta with a
small audience; **must** be revisited (Developer-ID/notarization, already the plan)
before a wider release, because "teach users to click through the OS warning" is a
habit an attacker benefits from.

**Nothing rated High or Critical.** No RCE path, no privilege escalation, no
network-reachable surface.

---

## 4. Development / build / distribution pipeline

| Stage | Posture | Note |
|---|---|---|
| **Source** | GitHub, PR-based, CI-gated | solo maintainer — no second-reviewer control; branch protection worth enabling |
| **CI** (`ci.yml`) | `pull_request` (not `_target`), now least-priv | fork code can't reach secrets ✅ |
| **Deps** | floors only, no lockfile, **no hash pinning** | reproducibility + supply-chain gap (§5) |
| **Actions** | pinned to **major tags** (`@v4`), not SHAs | mutable, but first-party (actions/*) — low risk; Dependabot now tracks them |
| **Build** (`release.yml`) | PyInstaller onedir → native installers on tag | bundles the resolved dep tree at build time |
| **Distribution** | **unsigned** GitHub Releases (beta) | integrity = HTTPS + repo trust (F6) |

**Supply-chain observations:**
- No lockfile / hash pinning means a compromised or typo-squatted transitive could
  enter a build. Low likelihood for this dep set, but a `pip install` at build time
  trusts PyPI's current state. A `requirements.lock` (or `pip install --require-hashes`)
  for the *release build* would close this without burdening dev.
- PyInstaller bundles whatever resolves at build time — so keeping deps patched (F2 +
  Dependabot) directly protects the shipped artifact.
- No SBOM emitted. Nice-to-have for a downloadable app; low priority pre-1.0.

---

## 5. Tooling — GitHub-native, and FOSSA/Semgrep-class options

The question was whether "things like FOSSA and Semgrep" are available on GitHub and
worth it. Summary: **the highest-value pieces are free and native; enable those first;
the paid SaaS tools are optional for a project this size.**

**Enable now (free for public repos, low effort):**
1. **Dependabot** — *added in this change* (`.github/dependabot.yml`, pip +
   github-actions, weekly). This is the direct answer to "surface an issue if a
   dependency needs a security update": it opens a CI-validated PR automatically. Also
   turn on **Dependabot **alerts**** and **security updates** in repo Settings →
   Security (one toggle each; they use GitHub's advisory DB, same source as pip-audit).
2. **CodeQL** (GitHub's native SAST — the closest free analogue to Semgrep) via the
   "CodeQL Analysis" default setup for Python. Catches injection/traversal/tainted-data
   patterns; would likely have flagged F1. ~10 lines of workflow or one Settings click.
3. **Secret scanning + push protection** — Settings toggle; cheap insurance for when
   the remote-publish credentials land.

**Optional / when it grows:**
- **Semgrep** — the free CLI + `semgrep-action` (or Semgrep Cloud free tier) runs
  custom + community rulesets in CI. More configurable than CodeQL and good for
  project-specific rules (e.g. "no `subprocess` without a comment", "no `Image.open`
  without a bomb guard"). Worth it if you want tailored rules; CodeQL covers the
  baseline.
- **FOSSA** — its sweet spot is **license compliance + dependency governance** at
  org/enterprise scale. For a solo Apache-2.0 project whose deps are all
  OSI-permissive, it's overkill; `pip-audit` (vulns) + Dependabot (updates) + a manual
  license glance cover the real needs. Revisit only if M110 takes on
  corporate/redistribution obligations.
- **`pip-audit` in CI** — a lightweight belt over Dependabot: fails the build on a
  known-vuln dep at PR time (Dependabot is asynchronous). One job; recommended.

**Bottom line:** Dependabot (+ alerts/security-updates) and CodeQL default setup are
the two switches that give ~80% of the value for ~0 cost. FOSSA/Semgrep-cloud are not
warranted yet.

---

## 6. Recommendations (prioritized)

**Done in this change:** F1 (traversal fix + guard), F2 (Pillow floor), F3 (bomb
ceiling), F4 (CI permissions), Dependabot config.

**Next, low-effort, high-value:**
1. Toggle on **Dependabot alerts + security updates**, **CodeQL** default setup, and
   **secret scanning + push protection** (all repo Settings).
2. Add a **`pip-audit` CI job** (fail on known-vuln deps at PR time). Filed as a
   follow-up issue.
3. **Branch protection** on `main` (require CI green; the solo-maintainer's guardrail).

**Before a wider (post-beta) release:**
4. **Sign + notarize** installers (F6) — already the roadmap plan.
5. **Hash-pinned / locked** dependency set for the *release build* (supply-chain).
6. Consider an **SBOM** attached to releases.

**Watch when the surface widens:**
7. Remote-publish credentials → OS keychain, never logs/reports (SECURITY.md already
   pre-commits to this — hold the line).

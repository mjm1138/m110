# M110 — Threat Model & Security Assessment

*Point-in-time review, **refreshed 2026-07-30** against `main` at `v0.2.0b8`, ahead of
the 0.3.0-beta.1 cut. Supersedes the 2026-07-15 review (v0.2.0-beta.1), whose findings
F1–F6 are retained below with their status. Companion to the user-facing
[`SECURITY.md`](../SECURITY.md) (reporting policy). This document is the engineering
assessment: attack surface, findings, pipeline, and tooling.*

**What changed since the last review:** the **assistant/MCP layer** (item 4 M0 + M0.5
outbox) and the **sky map** landed, and **GitHub Pages publishing** shipped. Two of
those move the threat model rather than merely extending it — for the first time
M110 sends user data to a third party by design (§2.4), and for the first time text
M110 did not author can influence a suggestion the user is invited to accept (F7).

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
the user didn't intend** on that user's account. The assessment still centers there.

Since the last review a **second** boundary matters: M110 can now hand library
content to an **external AI client**, and that client's model can hand suggestions
back. Nothing crosses that boundary without the user asking, and nothing the model
returns takes effect without the user accepting it — but "text M110 didn't write,
shown to a user who may act on it" is a new shape, and F7 addresses it.

### Assets
- The user's capture library + `library.toml` / journals (integrity).
- The user's wider account: home dir, autostart/login items, other apps' files
  (a traversal or code-exec bug is a foothold into these).
- **The user's privacy** — what the assistant sends to a model provider, and what
  publishing puts on the public web. Confidentiality is now a first-class asset,
  not just integrity.
- The release artifacts other users download (supply-chain integrity).

### Trust boundaries
| Boundary | Trusted | Untrusted |
|---|---|---|
| **Ingest** | the M110 code, `config.DATA_ROOT` | source folder names, **FITS headers**, file bytes, filenames, on-device sidecars |
| **Network** | the user's request (Add-object, geocode, update-check, publish) | Simbad / Nominatim / GitHub API responses |
| **Restore** | the snapshot manifest the user chose | file contents inside a snapshot |
| **Assistant** | the user's accept click in the app | **everything the model returns** — proposals, drafted artifacts, tool arguments; and any library text the model read to produce them |
| **Publish** | the user's section/gallery/journal choices | — (outbound only; the risk is over-sharing, not input) |
| **Pipeline** | the maintainer's commits | third-party deps, GitHub Actions, PyPI, **an unpinned git dependency (F8)** |

### Explicitly out of scope (by design)
No server, no auth, no multi-tenant data, **no secrets at rest** (the one remote
publish target delegates auth to the user's own git; the assistant delegates model
access to the user's MCP client — so M110 still holds no credential of any kind).
Signing/notarization of installers is deferred for the beta (a known, documented
gap — see §5).

---

## 2. Attack-surface walk-through

### 2.1 Network

All user-initiated except the update check, all HTTPS.

- `updates.py` → `api.github.com/repos/<fixed>/releases`, parsed with `json.loads`;
  version compare via `packaging`; **degrades silently** on any error. Response is
  data, never `eval`'d; no auto-download/execute. Runs on launch, throttled to ~daily,
  **on by default** (Preferences → Updates turns it off). ✅ low risk.
- `planning_config.geocode` → `nominatim.openstreetmap.org` with `urllib.parse.urlencode`
  (query is escaped). Sends the user's typed place name to a third party — a
  **privacy** note, not a vuln; it's an explicit online action.
- `catalog` online enrichment → Simbad via `astroquery`. Note the framing correction
  in this cycle: packaged builds **bundle** astroquery, so the `online` extra is not
  the control a user experiences — explicit invocation is.
- **`publish/ghpages.py` → the user's own GitHub repo.** New since the last review and
  the only path that **uploads user content** (rendered pages, journals, images) to a
  potentially public location. Runs the **system `git`** in argument-vector form
  (`subprocess.run(["git", *args])`, no shell), scoped to a scratch
  `--git-dir`/`--work-tree`; auth is the user's own SSH key or credential helper, so
  **M110 handles no token**. Deliberately never `checkout`/`reset --hard` — the work
  tree is the user's rendered site. Risk here is **over-sharing**, mitigated by the
  publish dialog's section toggles, the finished-only gallery default, and the
  per-object `private: true` opt-out. ✅ no injection surface (no user string reaches
  a shell); the residual is a user-judgment risk, correctly surfaced in the UI.

### 2.2 Subprocess use

The engine is free of `os.system` / `shell=True` / `eval` / `exec` / `pickle`. It does
spawn processes in three places, all argument-vector form:

- `launch.py` — starts Siril / an external tool on a user-chosen working dir. On macOS
  via `/usr/bin/open -a <bundle> --args -d <dir>` (a signing-context requirement, see
  CLAUDE.md), elsewhere a detached `Popen`. Env is sanitized (`_child_env`) so our
  venv/Qt discovery vars don't poison the child.
- `publish/ghpages.py` — the system `git`, above.
- `assistant/client_config.py` — resolves the server command to advertise; may call
  `shutil.which`. Reads PATH, which an attacker who can already write to the user's
  PATH directories has no need of. ✅ not a finding.

Desktop "Open folder" / external links go through `QDesktopServices.openUrl` on
app-controlled or user-chosen paths.

### 2.3 File parsing (still the largest untrusted-input surface)

- **FITS** via `astropy.io.fits` — headers drive classification *and* destination
  folders (see F1). Astropy is a maintained scientific lib; header parsing is the hot
  path.
- **Rasters** via **Pillow** (`Image.open` on imported jpg/png/tif) and **tifffile**
  (Siril float TIFs) — see F2/F3.
- **Sky-map rendering** (`skymap.py` → `uranometria`) consumes coordinates M110
  computed from its own catalog and library, not file bytes. Its risk is
  supply-chain, not parsing — see F8.

### 2.4 The assistant (MCP) — new

**Transport.** `assistant/mcp_server.py` speaks MCP over **stdio**; the client spawns
it as a child process and talks over pipes. **No socket is opened, no port is bound** —
nothing on the network or the local machine can reach it except the process that
started it, running as the same user. This is the single most important structural
fact about the feature and it keeps the whole layer out of "network-reachable
surface".

**Read tools resolve by enumeration, not by path.** Reviewed specifically because
model-supplied identifiers reaching a filesystem call is the obvious way this goes
wrong, and it is consistently avoided:

- `saved_plans(name=)` matches against `fieldguide.list_guides()` and then
  **re-anchors and re-checks containment** against `PLANS_DIR` before reading.
- `get_image(slug, which, name=)` resolves through the derived gallery
  (`derived.images_for`), never concatenating model input into a path.
- `get_skill(id)` looks the id up in a list loaded from the package's own
  `skills/*/SKILL.md` glob.

So there is no model-controlled arbitrary-file-read, which would otherwise be the
highest-impact bug available here (it would exfiltrate to a third-party model in one
step). ✅ built defensively.

**The write boundary.** M0 was strictly read-only; M0.5 relaxed it precisely: no tool
modifies or deletes anything, and a tool may **create** a file only inside
`.m110_internal_data/assistant/outbox`. `outbox._resolved_within` resolves **then**
checks containment (the correct order — checking first is how symlink escapes get
through), `safe_name` discards any directory part rather than resolving it, and quotas
(200 files / 2 MB each / 32 MB total) bound a looping model. Nothing in the outbox is
authoritative: the store reads none of it, `backup.py` excludes it, deleting it loses
only pending suggestions.

**The apply path is not reachable from the server.** `assistant/apply.py` is the only
module in the package that calls engine writers, and nothing under `tools/`, nor
`registry`, nor `mcp_server` imports it — asserted by a test in
`test_assistant_registry`. Applying a proposal re-runs its preview against the store
*as it is now* and refuses on drift unless forced. The writable actions are an
allowlist of five (`SAFE_WRITE_ACTIONS`), of which three have handlers today
(`set_weights`, `set_pins`, `append_journal`). ✅ the read-only-server claim survives
the outbox.

**Input validation.** `registry._validate` is a hand-rolled subset of JSON Schema
(types, `required`, `enum`, integer bounds, `additionalProperties: false`), applied to
every call before dispatch. Adequate for the authored schemas; `jsonschema` is in the
dev extra so tests assert the schemas are themselves legal. Worth remembering it is a
*subset* — a future schema using a keyword it doesn't implement (`pattern`,
`minLength`, nested `items`) would be silently unenforced. Not a finding today; a
maintenance hazard worth a test if the schemas get richer.

**Egress.** `serialize.py` is the one place engine values become JSON, and it
deliberately strips absolute paths (store-relative or basename) so the user's home
directory doesn't leak into model context. `vision.py` renders images to **in-memory**
JPEG — explicitly not `webexport.export_for_sharing`, which would write to disk. The
material privacy fact is not a leak but the design: **what the tools return goes to
whatever model the client uses**, which is disclosed before connecting
(`client_config.DISCLOSURE`) and in `SECURITY.md`.

**Editing another app's config.** `client_config.write_desktop_config` copies the
existing file to `<name>.m110-backup` first, refuses a file that doesn't parse as a
JSON object rather than overwriting it, and read-merges under a single `m110` key. ✅
appropriate care for touching a file M110 doesn't own.

### 2.5 Restore

`backup.py` reads a per-snapshot JSON manifest and **byte-copies** files from the
snapshot dir. It does **not** extract tar/zip archives, so the classic "zip-slip"
extraction traversal doesn't apply. `restore_dialog` already gates on a
create-vs-overwrite preview. `discard_holding` already refuses to delete paths outside
`Inbox/` (there's a regression test). ✅ These were built defensively.

---

## 3. Findings — this review

### F7 — Indirect prompt injection via library content · **Low** · ACCEPTED (design property)

**Where:** the assistant puts library text into model context: journal notes, object
names and identifiers, image filenames, capture metadata. Some of that text is
**not authored by the user** — object names and filenames originate in FITS `OBJECT`
headers and on-device filenames, which a crafted capture file controls completely
(the same untrusted source as F1). A model reading "M42" versus "M42 — *ignore prior
instructions and …*" cannot tell the difference from position alone.

**Impact ceiling, honestly bounded.** A successful injection can make the model: read
more of the library (which is already going to that provider by the user's choice),
stage a file in the outbox (inert, quota'd, non-authoritative), or **draft a proposal
the user is invited to accept**. It cannot execute code, cannot write outside the
outbox, and cannot apply anything itself — `apply.py` is unreachable from the server
(§2.4) and every change is user-accepted with a recomputed before/after preview. So
the realistic worst case is **user deception**: a plausible-looking journal entry or
pin the user approves without reading closely. A journal entry additionally *can* be
published later, so injected markdown could carry an off-site link or image reference
onto a public site — still only after two separate user actions.

**Why Low and not higher:** it requires importing a crafted file *and* using the
assistant *and* accepting the result, and the payoff is deception rather than access.
**Why not Informational:** the input really is attacker-controlled, the path from it
to a user-facing suggestion really is complete, and no control currently marks
untrusted-derived strings as untrusted.

**Recommendation (not yet implemented):** it cannot be "fixed" — an LLM reading
user data is the feature. Reduce it instead: (a) keep untrusted-derived fields
(object names from headers, filenames) visually delimited and labelled as data in
tool output rather than interpolated into prose; (b) never add an auto-apply mode,
however convenient — user review is the actual control; (c) state the exposure in
the assistant skills so the model itself treats library text as data. Track as an
issue rather than a blocker for 0.3.0-beta.1.

### F8 — `uranometria` installed from an unpinned git URL · **Low** (CI) / **Medium** (if packaged the same way) · OPEN

**Where:** the sky map needs `uranometria`, which is not yet on PyPI, so it is
deliberately kept out of `pyproject.toml` (a direct URL requirement would break any
future PyPI upload). CI installs it as:

```
pip install "uranometria @ git+https://github.com/devonjones/uranometria"
```

That resolves to **whatever is on the default branch at install time** — no tag, no
commit SHA, no hash. Two consequences beyond the usual: it is **invisible to
Dependabot** (not a registry package), and `pip-audit` **explicitly skips it**
("Dependency not found on PyPI and could not be audited"), so both of the supply-chain
controls this project relies on have a blind spot exactly here.

This is a statement about the *install mechanism*, not about the library or its
author. Today the blast radius is CI only (the sky-map render tests), which is why
it's Low. The `pyproject.toml` comment says packaged builds *will* install it — at
that point the same unpinned line would bake an unreviewed upstream state into
artifacts users download, which is Medium.

**Recommendation:** pin to a tag or commit SHA now
(`uranometria @ git+https://github.com/devonjones/uranometria@<sha>`), and treat
bumping it as a reviewed change. Revisit when it reaches PyPI, at which point it
becomes a normal extra and Dependabot picks it up.

### F9 — The journal writer trusts an upstream slug check · **Low** · OPEN

**Where:** `apply._apply_append_journal` takes `slug` from a proposal payload and calls
`objects.write_journal(slug, …)` → `journal_path(slug)` →
`objects.object_folder_name(slug)`, which falls back to **the raw slug** when the
object isn't in the library and neutralizes only `/`:

```python
return obj_id.replace("/", "-").strip()
```

A bare `..` survives (writing one level above `Objects/`, still inside the data root),
and on **Windows** `\` is untouched — `..\..\x` is a working separator there, so the
`/`-only replacement does not contain it.

**Not currently reachable.** `propose_journal_entry` validates the slug against
`catalog.load_library()` before the envelope is ever built, envelopes reach the outbox
only through that tool, and library slugs themselves derive from folder names already
reduced by F1's `_safe_segment`. So this is a **latent** gap, not a live traversal —
which is precisely why it's worth recording: it is the same shape as F1 (validation
upstream, no containment at the writer), and F1's own lesson was that the guard
belongs at the writer where it catches *every* vector regardless of how the input got
there.

**Recommendation:** reduce `object_folder_name` to a safe single segment (reuse
`ingest._safe_segment`), and/or assert containment under `config.OBJECTS_DIR` in
`objects.write_journal`. Cheap, and it makes the property local rather than emergent
from three cooperating modules. Add a test mirroring
`test_apply_ops_refuses_writes_outside_the_store`.

### Dependency posture at this review

`pip-audit` over the current dev environment: **no known vulnerabilities**. The
Pillow floor from F2 (`>=12.3`) is holding. Two packages are skipped as un-auditable:
`m110` itself (expected — not published) and `uranometria` (F8).

---

## 4. Prior findings (2026-07-15 review)

Retained as history; all statuses re-checked for this refresh.

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

**Fix:**
- `_safe_segment()` reduces any object name to a single safe path segment (strips
  `/ \ ..` control chars, leading dots; ordinary names like `"M81 M82"` unchanged),
  applied in `canonical_target`.
- **Hard containment guard in `apply_ops`** (defense in depth): the only writer
  resolves every destination and refuses (`ValueError`) any op landing outside
  `config.DATA_ROOT` — catches *every* vector regardless of how the op was built.
- Tests: `test_safe_segment_neutralizes_traversal`,
  `test_canonical_target_cannot_escape_the_store`,
  `test_apply_ops_refuses_writes_outside_the_store`.

*Still in force. F9 notes a second writer that did not inherit the guard.*

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
`except`). *Now also covers the assistant's vision path, which reuses `_open_image`.*

### F4 — CI workflow had no explicit `permissions` · **Low** · FIXED
**Where:** `.github/workflows/ci.yml` set no `permissions:` block, so the job's
`GITHUB_TOKEN` inherited the repo/org default (which can be read/write). A fork PR
runs untrusted code; least privilege matters.
**Fix:** added `permissions: contents: read`. (The `release.yml` job already scopes
`contents: write` correctly, and CI uses `pull_request` — not the dangerous
`pull_request_target` — so fork code never runs with repo secrets.) *Re-verified in
this review; both workflows still scoped correctly.*

### F5 — Privacy: geocode + crash report leak local context · **Informational**
- `geocode` sends the typed place name to Nominatim (third party). Acceptable for an
  explicit online action; now documented in `SECURITY.md`'s network table.
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

**Nothing in either review is rated High or Critical.** No RCE path, no privilege
escalation, no network-reachable surface — the assistant included (§2.4).

---

## 5. Development / build / distribution pipeline

| Stage | Posture | Note |
|---|---|---|
| **Source** | GitHub, PR-based, CI-gated, branch protection on `main` | solo maintainer — no second-reviewer control |
| **CI** (`ci.yml`) | `pull_request` (not `_target`), least-priv | fork code can't reach secrets ✅ |
| **Deps** | floors only, no lockfile, **no hash pinning**; one **unpinned git dep** | reproducibility + supply-chain gap (F8, §6) |
| **Actions** | pinned to **major tags** (`@v4`), not SHAs | mutable, but first-party (actions/*) — low risk; Dependabot tracks them |
| **Build** (`release.yml`) | PyInstaller onedir → native installers on tag | bundles the resolved dep tree at build time |
| **Distribution** | **unsigned** GitHub Releases (beta) | integrity = HTTPS + repo trust (F6) |

**Supply-chain observations:**
- No lockfile / hash pinning means a compromised or typo-squatted transitive could
  enter a build. Low likelihood for this dep set, but a `pip install` at build time
  trusts PyPI's current state. A `requirements.lock` (or `pip install --require-hashes`)
  for the *release build* would close this without burdening dev.
- **The `uranometria` git URL is the sharpest version of that gap** (F8), because it
  is unpinned *and* invisible to both Dependabot and `pip-audit`.
- PyInstaller bundles whatever resolves at build time — so keeping deps patched
  (F2 + Dependabot) directly protects the shipped artifact.
- No SBOM emitted. Nice-to-have for a downloadable app; low priority pre-1.0.

---

## 6. Tooling

Unchanged in substance from the last review; status updated.

**Landed:** `.github/dependabot.yml` (pip + github-actions, weekly, grouped);
`permissions:` on both workflows; branch protection on `main`.

**Still recommended:**
1. **Dependabot alerts + security updates**, **CodeQL** default setup, and **secret
   scanning + push protection** — all repo Settings toggles, not visible from the
   working tree, so **verify these are actually on** rather than assuming. CodeQL is
   the free SAST analogue to Semgrep and would likely have flagged F1 (and would be
   the standing check for F9-shaped bugs).
2. **`pip-audit` in CI** — a lightweight belt over Dependabot: fails the build on a
   known-vuln dep at PR time (Dependabot is asynchronous). One job. Note it will *not*
   cover `uranometria` (F8) — pinning is the control there, not scanning.

**Not warranted at this size:** Semgrep Cloud (the free CLI is fine if you want
project-specific rules); FOSSA (license/dependency governance at enterprise scale —
overkill for a solo Apache-2.0 project whose deps are all OSI-permissive).

---

## 7. Recommendations (prioritized)

**Before 0.3.0-beta.1:**
1. **Pin `uranometria` to a commit SHA or tag** (F8) — one line in `ci.yml`, and get
   it right *before* packaging adopts the same command.

**Soon after, low-effort:**
2. **Containment guard in `objects.write_journal`** + safe-segment
   `object_folder_name` (F9), with a test.
3. **Verify the repo Settings toggles** (Dependabot alerts/security updates, CodeQL,
   secret scanning) are on; add the **`pip-audit` CI job**.
4. **File F7 as a tracked issue** with the three reductions listed there. It is not a
   release blocker — it is a property to manage as the assistant grows.

**Before a wider (post-beta) release:**
5. **Sign + notarize** installers (F6) — already the roadmap plan.
6. **Hash-pinned / locked** dependency set for the *release build*.
7. Consider an **SBOM** attached to releases.

**Watch when the surface widens:**
8. If an in-app transport or an auto-apply mode is ever considered for the assistant,
   re-read §2.4 and F7 first — the read-only-server property and the user-accept gate
   are carrying the whole design, and both are easy to erode by accident.
9. Remote-publish credentials → OS keychain, never logs/reports (`SECURITY.md`
   pre-commits to this — hold the line).

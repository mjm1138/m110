# M110 — Claude Code / contributor context

**M110** is a cross-platform desktop app for managing a smart-telescope deep-sky
imaging collection: catalog/library, capture tracking, ingest from the telescope,
processing round-trips (Siril, AstroWizard), session planning, backup, publishing,
and an MCP assistant. North star: **"Lightroom for smart telescopes."**

- **Name:** M110 = the completion number of the Messier catalog. Package id `m110`;
  deliberately avoids the ZWO "Seestar" trademark. Tagline: *Complete the catalog.*
- **License:** Apache-2.0 (`LICENSE` / `NOTICE`).

**This file is deliberately short — it is loaded into every turn.** The long-form
per-module notes, the data-store detail, the full conventions and the gotchas
archive live in **[`DONE.md`](DONE.md) → "Engineering reference — archived from
CLAUDE.md"**. **Grep that section by module or symbol name before changing a
subsystem** — it records *how and why* each piece is built, which is usually the
missing context behind "why is it done this way?".

---

## TL;DR for a new session

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate          # or: python3 -m venv .venv && pip install -e ".[dev]"
m110                               # run the app  (== python -m m110.ui.main)
m110-stack "NGC 6543"              # measure + propose a stack (read-only; --run executes)
pytest -q                          # run tests
```

- **Python 3.11+** (dev/CI on 3.14). Engine is **Qt-free**; the UI is **PySide6**,
  importing the engine **in-process** (no API server).
- The app **owns its data store** (default `~/Documents/M110`), created and seeded
  on first launch. It needs no other project to run.
- Offscreen smoke (no display): `QT_QPA_PLATFORM=offscreen python -m m110.ui.main`.

### Working in a git worktree

One venv at the main checkout serves every worktree, but the editable install
hardcodes **main's** package dir, so *how you launch* decides which code runs:

```bash
cd ~/Documents/Code/m110/.claude/worktrees/<name>
source ~/Documents/Code/m110/.venv/bin/activate
python -m m110.ui.main             # ✅ the worktree's code  (NOT `m110`)
pytest -q                          # ✅ the worktree's code
PYTHONPATH=$PWD python tools/x.py  # ✅ tools/ needs the path set
```

**The `m110` console script always runs `main`'s code from any worktree** (its
`sys.path[0]` is `.venv/bin`); same trap for `python tools/<script>.py`. Rule:
**`-m` or `pytest` from the worktree root; everything else needs `PYTHONPATH=$PWD`.**
Never `pip install -e .` inside a worktree (re-points the shared venv). Runbook +
safe-data-root protocol: [`TESTING.md`](TESTING.md) §0.

---

## Where it came from

M110 ports a mature text-based astrophotography workflow (the sibling **Astronomy**
project: TOML/JSONL/Markdown + scripts + a static site) into an installable engine
with a native GUI. `scan_sessions` / `build_derived` / the image pipeline were
faithful ports; byte-for-byte compat was consciously retired with the two-axis
store (#13) — validate against this repo's fixtures, not the originals. M110 is
standalone (own seed catalog, own derived data). Canonical roadmap:
[`ROADMAP.md`](ROADMAP.md); shipped-work archive: [`DONE.md`](DONE.md).

---

## Architecture

```
PySide6 UI  (m110/ui/)   ── imports in-process ──▶   headless engine (m110/)
```

- **Headless engine = source of truth.** Pure Python, **no Qt imports** in engine
  modules, so it stays testable and reusable (CLI, MCP server, a future client).
- **UI is a thin client.** Renders engine data, calls engine functions. Slow work
  runs on `QThread` workers behind modal progress dialogs with a working Cancel.

### Data store

**Canonical model: [`DATA_MODEL.md`](DATA_MODEL.md)** (entity hierarchy, per-file
catalog, lifecycle, future seams). Quick sketch — two visible content axes (objects
and capture targets are many-to-many) plus one hidden machine-state dir:

```
<data_root>/                        (default ~/Documents/M110)
  Objects/<catalog id>/journal.md   catalog-object axis (a stub for every Library object)
  Images/<target>/                  capture-target axis
    lights/ rejected/ stacks/ seestar-stacks/ finished/ previews/
    siril/  astrowizard/            per-workflow sandboxes (config.SANDBOX_LINKED_INPUTS)
  Media/<Category>_photo|_video/    lunar/planetary/scenery media
  Inbox/                            ingest holding area
  Plans/                            saved field guides
  .m110_internal_data/              library.toml goals.toml priorities.toml pins.toml
                                    sessions.jsonl profiles/ derived/ renders/ .store_version (=4)
```

- **Data-root resolution** (`config.py`): `M110_DATA_ROOT` env → saved preference
  (`~/.m110/settings.json`) → default. `ensure_data_root()` migrates
  (`migrate.migrate_store()`, idempotent, version-stamped, never destructive),
  creates the skeleton, seeds an **empty** `library.toml` (the Library *is* the
  captured collection) — all idempotent, never overwrites. Root change = restart.
- Settings live **outside** the data root at `~/.m110/settings.json`; the log at
  `~/.m110/logs/m110.log`.

---

## Module map

Full descriptions (design rationale, invariants, the bugs each seam fixed) are in
DONE.md's archived reference — grep the module name there.

**Engine (`m110/`, Qt-free):**

| Module | Role |
|---|---|
| `config.py` | data-root resolution + bootstrap/seed, per-target path helpers, settings, Seestar mount detection (`VOLUMES_DIR`), `FIT_EXTS`/`is_fits_file`, `rejected_dir`, `SANDBOX_LINKED_INPUTS`/`SANDBOX_DIRNAMES` (the one registry of workflow sandboxes) |
| `migrate.py` | in-place idempotent store migration to the two-axis layout |
| `catalog.py` | Library (`library.toml`) vs bundled reference/catalog lists; add/remove/enrich entries; `season_from_ra`; `object_identifiers`; Simbad via optional astroquery (`OnlineLookupError`) |
| `derived.py` | read generated rollups (`derived/*.json`) |
| `processing.py` | workflow registry (Siril + AstroWizard), `run_autoprep`, `prepare_missing` (creates only absent sandboxes), `reconcile_rejected` |
| `scan_sessions.py` | `Images/<target>/lights/` → `sessions.jsonl`; header-driven (`DATE-OBS`/`EXPTIME`/`FILTER`, `EQMODE`), Seestar filename only as a fast path |
| `build_derived.py` | totals/priorities/summary/processing/goals JSON; `deep_threshold` |
| `build_images.py` | thumbnails + heroes + `images.json`, content-hash cached; hero keyed on source identity (`.src` sidecar) |
| `ingest.py` | read-only scan **plan** (`scan_directory_plan`, recursive, layout registry incl. Seestar + Dwarf 3) + gated `apply_ops` (the only writer); holding area + identification aids |
| `roundtrip.py` | tool-neutral half of a processing sandbox: classify, keep-both collision handling, `scan_finished`/`apply_import`/`archive_run`, `prune_archives` (keep-N, name-parsed only), the `Sandbox` descriptor |
| `siril.py` | prepare-and-guide round-trip: `plan_prep`/`apply_prep` (hardlinked `lights/`, Naztronomy preset preserved once hand-edited), `autoprep`, import delegations over `SANDBOX`, `prune_rejected`, `working_dirs` |
| `astrowizard.py` | the finishing round-trip (thin `roundtrip` consumer): `is_master`/`is_autosave`/`is_handoff` (sidecar-keyed, never filename), `prepare_lights` |
| `stacking.py` | headless Siril stacking (`m110-stack`): `build_plan` (read-only) vs `run_siril`; three-phase solve·register·stack; `clear_scratch`; `apply_handoff`, `handoff_candidates`, `_is_stretched` (HISTORY cards) |
| `launch.py` | external-app launcher (`_TOOLS` registry: Siril, AstroWizard, StackingWizard); `find_app`, `launch_processing`, `launch_with_file`, sanitized `_child_env()` |
| `hints.py` | user-editable finished/intermediate filename vocabulary (`finished_hints` setting) |
| `objects.py` | journal read/write, frontmatter upserts, per-image curation |
| `refresh.py` | `run_refresh()` = add_captured_objects → scan → derive → render |
| `logsetup.py` | rotating log at `~/.m110/logs/m110.log` |
| `media.py` | recursive non-catalog media listing, poster resolution, sidecar cleanup |
| `webexport.py` | size-budgeted PNG/JPEG export for sharing |
| `backup/` | snapshot engine: `destination` (folder or `s3://`), `backends/` (local, memory, S3), `mirrored` + `pooled` formats, `scope` (denylist + `essentials` tier), `retention` (24h-grace GC), `probe`, `schedule`, `recovery`; façade in `__init__` |
| `planning.py` | twilight (memoized), `observability`, `night_track`, `plan_night`, `sequence_plan`, moon impact (topocentric AltAz) |
| `fieldguide.py` | printable observing plan markdown; saved under `Plans/` |
| `planning_config.py` | site/device profiles (`profiles/*.toml`), glow layer, `DEVICE_PRESETS`, active-profile selection, `geocode` |
| `prioritize.py` | deterministic ranker; slow `build_contexts` split from instant `rank`; cached `derived/prioritized.json` |
| `horizon.py` / `glow.py` | horizon mask + light-dome floor (Walker's Law over GeoNames `cities1000`) |
| `goals.py` / `pins.py` | per-store active goals + custom lists; manual pin/deprioritize overrides |
| `updates.py` | GitHub release check (`packaging`), throttle prefs, `version_tag`/`user_guide_url` (pinned to the release tag) |
| `assistant/` | MCP assistant: `registry` (tools populated by importing `tools/`), 16 provider-neutral tools, `serialize`, `proposals`, `outbox` (the only writer, create-only), `apply` (app-side only), `mcp_server` (SDK v2, stdout→stderr) |
| `seed/` | bundled `objects.toml` reference, `catalogs/*.toml`, empty `priorities.toml`, GeoNames subset; generated by `tools/gen_*.py` at build time |
| `publish/` | publisher registry: `site` (Jinja2 static site + stale sweep), `ghpages` (system git, replace/incremental modes, streamed progress, cancel kills push), `select`, `images` (gallery levels), `options` |

**UI (`m110/ui/`, PySide6):**

| Module | Role |
|---|---|
| `main.py` | shell: nav rail → 5 pages **Library · Overview · Planning · Import · Processing**; `_build_menus()` (File/View/Library/Tools/Help, `MenuRole` hoisting); `RefreshWorker`; auto-sync on launch/focus/ingest; `open_object(slug)`; `_ready` gates launch workers |
| `widgets.py` | shared table/thumbnail helpers (`ThumbnailLoader`, `fit_table_height`, `fit_cell_widgets`), launch helpers, **`drain_worker`**, **`modal_loop_active`/`defer`/`connect_context_menu`** |
| `image_grid.py` | reusable tile grid (model + delegate), app-data-agnostic |
| `detail.py` | per-object `DetailPane`: hero, notes, Finished/Working gallery, image menu, processing/sessions tables, handoff/import buttons |
| `pages/catalog.py` | the Library: List/Grid/Feed views + Deep-sky/Media scope, filters, right-click actions |
| `pages/overview.py` | landing dashboard of collapsible sections (goals, pins, integration, checklists, manage goals) |
| `pages/processing.py` · `pages/sessions.py` · `pages/journal.py` · `pages/media.py` | Siril queue · session log (dialog) · feed view · media browser |
| `pages/planning.py` + `night_timeline.py` + `field_guide_dialog.py` + `site_profile_editor.py` | planning pane: ranking, night plan/sequencer, saved guides, site profiles; astropy workers fire only on explicit actions |
| `pages/import_page.py` · `ingest_dialog.py` · `holding_inspect_dialog.py` | import flow: preview-then-confirm, holding area, bulk assign |
| `import_dialog.py` · `handoff_dialog.py` · `export_dialog.py` · `add_object_dialog.py` · `image_viewer.py` | import finished work · send stack to a workflow · export for sharing · add object · gallery viewer |
| `media_detail.py` · `media_cleanup_dialog.py` | media detail pane · sidecar cleanup |
| `preferences.py` · `publish_dialog.py` · `backup_dialog.py` · `restore_dialog.py` · `mcp_details_dialog.py` | settings (scrolling, wrapping) · publish · backup (folder or S3) · restore · MCP connection details |
| `about_dialog.py` · `update_notice.py` · `error_report.py` · `first_run_dialog.py` | about + update status · update banner/worker · crash dialog + excepthook · first-launch prompt |
| `theme/` | design system: `tokens` (light/dark), `qss.build_qss`, `manager.ThemeManager` (follows OS), bundled JetBrains Mono, `brand` (recolored logo, fixed app icon). **Pull colors/spacing from tokens, never hardcode hex** |

---

## Conventions & rules

- **Feature branch per unit of work** (`feature/<short-name>` off `main`); docs-only
  edits may go straight to `main`. **Close out every change** with `pytest -q` green
  **and** the matching doc updates in the same commit: `ROADMAP.md`/`BUGS.md`
  (what landed), `DATA_MODEL.md`/`TESTING.md` when the data model or manual-test
  surface changed, a user-facing **`CHANGELOG.md` `[Unreleased]`** entry (written for
  a user; engineering detail goes in `DONE.md`). `tools/release.py` only *moves*
  `[Unreleased]` and hard-fails when it is empty.
- **Full disclosure on user-facing security bugs** in `CHANGELOG.md` `### Security`:
  name the vector and real impact, calibrated in both directions, linking
  `docs-archive/SECURITY_ASSESSMENT.md`.
- **Record data-model changes in `DATA_MODEL.md`**; on-disk changes also bump
  `.store_version` and add an idempotent, never-destructive `migrate.py` step.
- **Never write into the content tree without explicit confirmation.** Every write
  feature is **preview-then-confirm**: a read-only `scan_*_plan()`, then one gated
  writer (`apply_ops`) after the dialog confirms.
- **Engine stays Qt-free** (no `PySide6` in `m110/*.py`; only under `m110/ui/`).
- **Slow ops run on a `QThread` worker** behind a modal `QProgressDialog` with a
  working Cancel (`threading.Event`). Workers talk to widgets only via signals.
- **Minimal main-window chrome.** One control per meaning, sensible defaults;
  density belongs in detail panes and dialogs (`UI_ROADMAP.md` → Vision).
- **Tests run on temp fixtures, never live data.** A session-autouse seal in
  `tests/conftest.py` points `M110_DATA_ROOT`, the `config.*` globals,
  `SETTINGS_FILE` and `APP_CONFIG_DIR` at a throwaway dir for the whole run; keep
  per-test `seed_root` + the MainWindow `_ready = False` guard anyway.
- **The manual-test harness ships with the change.** Carry engine renames through
  `tools/make_test_corpus.py` (+ `create_test_harness.sh`) in the same commit
  (`tests/test_make_test_corpus.py` runs the real generator), and ask what the
  corpus must *contain* for a tester to see the feature.
- **Dependencies:** core = PySide6, astropy, numpy, pillow, tifffile. Extras:
  `online` (astroquery), `s3` (boto3 + keyring), `publish` (jinja2 + markdown),
  `dev` (pytest, pytest-qt), `build` (pyinstaller, self-references `online`+`s3`).
  Optional `uranometria` (sky map) is **not** declared in `pyproject.toml` (not on
  PyPI); build jobs install it explicitly and the specs `collect_data_files` it.
  **Frozen-build rule:** anything that reads dist-info or data files at import
  (astropy `copy_metadata`, its PLY parsetabs, botocore service models,
  uranometria JSON) must be collected in the PyInstaller specs — and **validated
  against a real PyInstaller build**, not a loose-`.py` reconstruction (#64, #74, #75).

---

## Testing

```bash
pytest -q                 # all (~1570 tests, fixture-based)
pytest -q tests/test_ingest.py
QT_QPA_PLATFORM=offscreen python -m m110.ui.main
```

UI is driven offscreen with **pytest-qt** (`qtbot`); shared fixtures in
`tests/_helpers.py`, offscreen platform in `tests/conftest.py`. Rendering has
golden-image tests (`tests/test_render_golden.py`; refresh with
`M110_UPDATE_GOLDENS=1`). Add tests alongside any engine change; for UI, prefer
extracting logic into the engine and testing that — and **click every button you
add in a test** (`tests/test_ui_button_wiring.py`). Manual/regression runbook:
[`TESTING.md`](TESTING.md). Open issues: [`BUGS.md`](BUGS.md).

---

## Roadmap

**[`ROADMAP.md`](ROADMAP.md)** is canonical (decisions, build order, status);
completed milestones are archived to [`DONE.md`](DONE.md). At a glance: v0.1 "the
Library" feature-complete; two-axis store; ingest with any-directory recursive
scan + holding area; Seestar + Dwarf 3; preference-driven automatic
processing-prep; Siril + AstroWizard round-trips and headless stacking; publishing
to a folder or GitHub Pages; backup to folder or S3; session planning (prioritizer,
site profiles, night sequencer, field guides); read-only MCP assistant. Decisions:
open-source / Developer-ID distribution, PySide6 over a headless engine, processing
is prepare-and-guide (the stacker is the one place M110 drives Siril).

---

## Gotchas — the short list

Each line is a rule; the full story (repro, measurements, why the obvious fix was
wrong) is under the same heading in DONE.md's archived reference.

**Launching external tools**
- On macOS launch Siril via `/usr/bin/open -a … --args -d <dir>`, never a direct
  `Popen`: its hardened bundled Python is SIGKILLed unless Siril is its own
  responsible process. `--args` only applies on a cold start.
- Every launched tool gets `launch._child_env()`: strips `VIRTUAL_ENV`/`PYTHON*`/
  `_MEI*` **and** the bundled-Qt vars (`QT_PLUGIN_PATH`, `QML*_IMPORT_PATH`) — the
  two-Qt SIGABRT only bites a **frozen** build, so regression-test the sanitizer.
- The macOS `.app` must set `LSBackgroundOnly: False` explicitly (the console MCP
  EXE makes PyInstaller stamp it True → no menu bar, no Dock icon). Diagnose with
  `lsappinfo list`, not the spec.

**Data & files**
- FITS extensions are `.fit` **and** `.fits` — always via `config.FIT_EXTS`/`is_fits_file`.
- Session facts come from the FITS **header**, not filenames (device conventions differ).
- Copy from the Seestar (SMB) with `shutil.copyfile` → `.part` → `os.replace`; `copy2` EPERMs.
- Never trust mtime for provenance/freshness; use header dates (`DATE-OBS`, stack `DATE`).
- The real Siril stack often sits in `working_files/`, not `stacks/`; readers look there.
- `processing.json` stamps `generated_at`, so it churns; everything else in `derived/` is deterministic.
- A backup destination that can't hardlink is probed up front (`backup.probe_destination`,
  on a worker) and switches to the pooled format, telling the user. Pooled objects are
  mode 0444, so Windows deletes need `chmod` first.
- Library = per-store `library.toml` (mutable corpus); reference = `seed/objects.toml`;
  catalogs = `seed/catalogs/*.toml` (immutable). Captured folders are auto-added to the
  Library on refresh (`catalog.add_captured_objects`).
- Processing-prep is automatic + idempotent (full on ingest, missing-only on refresh;
  hand-edited presets preserved). No manual "Prepare" button.

**Qt lifetime & threading**
- **Drop every worker reference through `widgets.drain_worker(w)`** (wait → deleteLater).
  Dropping it inside the worker's own result slot defeats the teardown guard and
  qFatals on close; undrained `QThreadPool` decodes were the CI SIGSEGV.
- **Never tear down widgets under a nested event loop, and never open a modal/menu
  from inside an item-view handler.** Check `modal_loop_active()` before rebuilding;
  open dialogs/menus via `defer()` / `connect_context_menu()` off a snapshot of the data.
  Assert the policy (`tests/test_ui_modal_safety.py`); the crash itself segfaults pytest.
- Cross-thread Qt only via signals; never touch widgets from a worker.

**Qt rendering & styling**
- Never `QIcon(path)` for a fixed-size icon — JPEGs decode straight to the target
  size and squash; PNGs don't, so a synthetic test passes. Use `ThumbnailLoader` /
  `detail._square_icon`.
- Styling any property of a widget hands its whole rendering to QSS, sub-controls
  included (spinbox arrows need the bundled chevrons). Item check indicators are
  stylesheet-drawn on purpose — keep the `::indicator` rules and `:checked` image.
- Measure a styled control against native before "fixing" its size (`sizeHint()`
  with vs without the sheet in a real cocoa app). QSS `min-height` is an
  anti-clipping floor, not sizing.
- `QT_QPA_PLATFORM=offscreen` falls back to Fusion; it cannot validate macOS
  painting, and a delegate that raises in `paint` passes model-state tests —
  render a real window to a QPixmap when touching a delegate.
- A callback body isn't evaluated until clicked: click buttons in tests and keep the
  unbound-name AST scan (`tests/test_ui_button_wiring.py`).
- `&` in a widget label is a mnemonic — write `&&` (source-scanned).
- A dialog's reject button says "Cancel" only while there are unsaved edits (track
  dirty from `textChanged`, not `textEdited`); otherwise "Close".

**Safety when scripting the app**
- Never validate rendering/refresh against a live data root.
- An ad-hoc GUI script must isolate **`config.SETTINGS_FILE` and `APP_CONFIG_DIR`**,
  not just `M110_DATA_ROOT` — settings live in `~/.m110`, and constructing a dialog
  is enough to overwrite real preferences. Prefer a sealed pytest case.
- Screenshots: build `MainWindow()` offscreen, set `win._ready = False` (no store
  writes, no update-check thread), pump events, `win.render(pm)` at 2×.

---

## Repo layout

```
m110/            engine package (+ ui/ subpackage, seed/ data, assistant/, backup/, publish/)
tests/           pytest suite (fixture-based, goldens/)
tools/           release.py · build_docs.py · make_test_corpus.py · smoke_mcp.py ·
                 drill_backup_s3.py (real MinIO) · repro_modal_uaf.py · gen_*.py
packaging/       common/ (PyInstaller shims + hooks) · macos/ · linux/ · windows/
site/            m110.space landing page + docs/<tag>/ versioned user guide (committed)
.github/         ci.yml (pytest) · release.yml (tag builds) · issue/PR templates
docs/            user guide · docs-archive/  point-in-time records
ROADMAP.md · DONE.md · BUGS.md · TESTING.md · DATA_MODEL.md · UI_ROADMAP.md · CHANGELOG.md
README.md · CONTRIBUTING.md · CODE_OF_CONDUCT.md · SECURITY.md · LICENSE / NOTICE
.venv/           local virtualenv (gitignored; shared by every worktree)
```

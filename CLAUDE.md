# M110 — Claude Code / contributor context

**M110** is a cross-platform desktop app for managing a smart-telescope
deep-sky imaging collection: catalog/library, capture tracking, ingest from the
telescope/staging, and Siril processing-prep. North star: **"Lightroom for
smart telescopes."**

- **Name:** **M110** (decided) — the completion number of the Messier catalog
  (and, fittingly, a row in the app's own catalog). Package import id `m110`;
  deliberately avoids the ZWO "Seestar" trademark. Tagline: *Complete the catalog.*
- **License:** Apache-2.0 (see `LICENSE` / `NOTICE`).

This file is the entry point for working in this repo productively. Read it
first.

---

## TL;DR for a new session

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate          # or: python3 -m venv .venv && pip install -e ".[dev]"
m110                        # run the app  (== python -m m110.ui.main)
pytest -q                          # run tests
```

- **Python 3.11+** required (dev/CI on 3.14). Engine is **Qt-free**; the UI is
  **PySide6**, importing the engine **in-process** (no API server in the MVP).
- The app **owns its data store** (default `~/Documents/M110`), created
  and seeded on first launch. It does **not** require any other project to run.
- Offscreen smoke (no display): `QT_QPA_PLATFORM=offscreen python -c "..."`.

---

## What this is, and where it came from

M110 grew out of a mature text-based astrophotography workflow (the
sibling **Astronomy** project: TOML/JSONL/Markdown data + Python scripts + a
generated static site). That workflow proved out the data model, the positional
math, the tracker rollups, and the image pipeline. M110 **ports that
proven logic into an installable engine** and puts a native-feeling GUI on top.

- The **canonical roadmap** is [`ROADMAP.md`](ROADMAP.md) in this repo (status,
  build order, decisions). The long-form *rationale and history* behind the big
  decisions lives in the sibling Astronomy project's `workflow_app_plan.md`
  (optional background; this repo stands alone without it).
- Several engine modules are **faithful ports** of Astronomy `scripts/`
  (`scan_sessions`, `build_derived`, the image pipeline). They
  were validated to reproduce the original output byte-for-byte. **When changing
  these, preserve behavior compatibility** — the data store schema is shared.
- M110 is standalone: it carries its own seed catalog and generates its
  own derived data and image renders. It does not read the Astronomy repo.

---

## Architecture

```
PySide6 UI  (m110/ui/)   ── imports in-process ──▶   headless engine (m110/)
   main.py        Library window (table + detail/gallery), Refresh, Ingest, Preferences
   ingest_dialog  preview-then-confirm ingest (threaded, progress/cancel)
   preferences    choose the data folder
```

- **Headless engine = the source of truth.** Pure Python, **no Qt imports** in
  engine modules, so it stays testable and reusable (a future web/Swift client,
  or CLI, could sit on the same engine — that's when a FastAPI layer would
  return; not needed for PySide6).
- **UI is a thin client.** It renders engine data and calls engine functions.
  Slow/long operations run on `QThread` workers behind modal progress dialogs.

### Data store

**Canonical model: [`DATA_MODEL.md`](DATA_MODEL.md)** — the authoritative,
human-readable data model (entity hierarchy, per-file catalog with
mutability/lifecycle/retention, the data-flow diagram, and the designed-for-future
seams: multi-catalog goals, device-under-target multi-telescope, planning profiles,
the SQLite index seam). The sketch below is a quick reference; DATA_MODEL.md is the
source of truth.

The app reads/writes a single **data root** with this layout (same conventions
as the Astronomy workflow):

The store has **two visible content axes** — `Objects/` (catalog-object axis)
and `Images/` (capture-target axis) — kept distinct because objects and capture
targets are **many-to-many** (one `M81 M82` capture feeds two catalog objects).
All machine state lives in a single **hidden** `.m110_internal_data/`.

```
<data_root>/                         (default ~/Documents/M110)
  Objects/<catalog id>/              catalog-object axis (slug→id, e.g. Objects/M101/)
    journal.md          per-object journal (YAML-ish frontmatter + Markdown body); + future artifacts
                        (a stub is created for *every* catalog object from journal_template.md)
  Images/<target>/                   capture-target axis (= the old object_dir)
    lights/             raw light frames (subs)
    stacks/             Siril stacks (.fit/.tif)
    seestar-stacks/     Seestar in-app stacks
    finished/           hand-finished renders
    siril/              contained Siril sandbox (processing-prep): literal lights/ (hardlinks;
                        per-filter siril/<FILTER>/ for mixed filters), presets/<naztronomy preset>,
                        next-steps.md, archive/<ts>/ (past runs). Siril runs *here* (keeps the
                        tiers clean); M110 imports finished work → finished/ + stacks/, then
                        archives the run (keeps lights/ + preset ready for the next run; never deletes).
    (darks/ flats/ biases/ preserved if present)
  Media/<Category>_photo|_video/     lunar/planetary/scenery media
  Inbox/                             staging area for ingest
  .m110_internal_data/               hidden machine state (README: "don't touch")
    library.toml        the user's Library {slug: {id,name,type,magnitude,size,season,filter,...}}
                        (seeded from bundled seed/objects.toml; v2→v3 renamed catalog.toml)
    priorities.toml     priority targets (optional `track=false` for campaign entries)
    sessions.jsonl      one capture session per line (generated by scan_sessions)
    processing_overrides.toml
    journal_template.md reference journal format (stubs are generated from it)
    derived/            generated rollups: totals/priorities/summary/processing/images.json
    renders/            generated thumbnails + hero/<slug>.jpg (gallery assets)
    .store_version      layout version stamp (= 3)
```

**Migration:** `config.ensure_data_root()` calls `migrate.migrate_store()` first,
which brings an older store (the flat `data/` + jargon `Images/` + `site/` shape)
up to this layout in place — **idempotent**, version-stamped, same-fs renames,
resume-safe, never destructive. Only ever exercised on temp/throwaway roots in
tests (never a live root).

**Data-root resolution** (in `config.py`, Qt-free): `M110_DATA_ROOT` env
→ saved preference (`~/.m110/settings.json`) → default
`~/Documents/M110`. `ensure_data_root()` (called on launch) migrates, creates the
skeleton, seeds `library.toml` (from the bundled object reference) + `priorities.toml` into `.m110_internal_data/` from
`m110/seed/` if missing, writes the internals README + `journal_template.md`, and
creates an `Objects/<id>/journal.md` stub (from the template) for **every catalog
object** — all **idempotent, never overwrites**. Changing the root in Preferences
takes effect on **restart**.
Per-target paths come from `config.{target,lights,stacks,seestar_stacks,finished}_dir(name)`.

---

## Module map

**Engine (`m110/`)** — Qt-free:

| Module | Role |
|---|---|
| `config.py` | data-root resolution, dir bootstrap/seed, per-target path helpers, settings persistence, Seestar mount detection (`find_seestar_myworks`) |
| `migrate.py` | in-place, idempotent, version-stamped migration of an older store to the two-axis layout (`migrate_store`) |
| `catalog.py` | `load_library` (per-store `library.toml` — the user's corpus); `load_reference` (bundled `seed/objects.toml`) + `load_bundled_catalog` (bundled `seed/catalogs/<name>.toml` membership lists); `catalog_sort_key`/`season_sort_key`; `load_coords` (reference coords + per-store library `ra_deg/dec_deg`); `add_captured_objects` (promote captured-but-uncatalogued folders into the Library) |
| `derived.py` | **read** generated rollups (totals/priorities/summary/processing/images.json) |
| `processing.py` | workflow registry (Siril active; PixInsight/others disabled "soon") + `run_autoprep` (preference-driven, runs after ingest) + `prepare_missing` (refresh-time/on-demand backfill — creates only *absent* sandboxes, never rewrites existing) |
| `scan_sessions.py` | scan `Images/<target>/lights/` → `sessions.jsonl` (ported) |
| `build_derived.py` | compute totals/priorities/summary/processing → `.m110_internal_data/derived/*.json` (ported) |
| `build_images.py` | thumbnails + heroes + `images.json` into `.m110_internal_data/renders` (ported from build_site/generate_hero); content-hash cached |
| `ingest.py` | staging/Seestar scan **plan** (read-only) + gated `apply_ops` (the only writer into the content tree); cancellable |
| `siril.py` | processing-prep **round-trip** (prepare-and-guide). Prepare: `plan_prep`/`apply_prep` arrange a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks, Naztronomy preset by drizzle-frame-count, per-filter jobs); `autoprep` runs it automatically after ingest (skips targets with pending finished output). Import: `has_unimported_output`/`scan_finished`/`apply_import` copy renders→`finished/` + stack→`stacks/`, optionally set hero (or keep current), then **archive** the run into `siril/[<FILTER>/]archive/<ts>/` (keeps `lights/`+preset ready for re-runs; never deletes, never escapes `siril/`). Bundled-guidance access |
| `objects.py` | per-object journal read **and write** (`Objects/<id>/journal.md`: `read_journal` frontmatter+body, `read_journal_text`/`write_journal` raw, `set_frontmatter_key` upsert for hero); slug→id folder name; hero path |
| `refresh.py` | `run_refresh()` = scan_sessions → build_derived → build_images (the UI refresh worker also runs `processing.prepare_missing` so missing working folders self-heal on any sync) |
| `media.py` | **read** non-catalog media — `scan()` enumerates `Media/<Category>_photo\|_video/` (Qt-free; backs the Media page) |
| `seed/` | bundled `objects.toml` (object **reference**: id/type/mag/size/season + J2000 coords) · `catalogs/<name>.toml` (catalog membership lists, e.g. Messier) · `priorities.toml` (package-data) |
| `guidance/` | bundled Siril/Seestar workflow playbooks (`*.md`, package-data) surfaced in processing-prep |

**UI (`m110/ui/`)** — PySide6:

| Module | Role |
|---|---|
| `main.py` | **Shell**: left nav rail (`QListWidget`) → `QStackedWidget` of pages [Summary · Catalog · Processing · Sessions · Journal · Media]; **Summary is the landing page**. Global Ingest (Ctrl+I) toolbar + M110 menu (Refresh Ctrl+R, Prepare working folders, Preferences Cmd+,). `RefreshWorker` (scan→derive→render + `prepare_missing`) drives `page.reload()`; **auto-syncs** on launch / window-focus / after ingest. `open_object(slug)` routes any page's object link → Catalog + selects it. Journal-edit lock disables nav + global actions |
| `widgets.py` | shared `NumItem` (sort-key cell), `status_label`/colors, `targets_for_slug`, `make_table` |
| `detail.py` | shared per-object `DetailPane`: header/status, hero (scales to pane), journal **view/edit** (raw `journal.md`), gallery (double-click → image viewer), **Import finished work** entry, + per-object **Processing** + **Sessions** tables and a **Catalog details** block. Shows real filenames |
| `pages/catalog.py` | catalog+status table (Object/Name/Type/Season/Mag/Size/Filter/Status/Integration/Sessions; sortable; sort persists across rebuilds; Season sorts by month) + **search box** + captured/deep/total **stat row**, hosting the shared `DetailPane`; `select_object`/`reload`; per-object import flow; edit-lock |
| `pages/summary.py` | landing dashboard — category progress, processing-queue snapshot, current integrations, priority targets; object rows → `open_object` |
| `pages/processing.py` | Siril queue grouped by status with stack-meta columns; rows → `open_object` |
| `pages/sessions.py` | capture-session log (sortable table Date/Object/Frames/Exp/Filter/Integration/Mount, default Date-desc) + search box; from `derived.load_sessions()`; rows → `open_object` |
| `pages/journal.py` | reverse-chron **feed** of object cards (header · hero · status/stats · rendered notes) — every captured object + any noted-but-uncaptured; ordered by latest image mtime (reprocess re-orders); search box; cards → `open_object` |
| `pages/media.py` | **Media** browser for non-catalog `Media/<Category>_photo\|_video/` (ingest already captures it): per-category sections — photo gallery (double-click → image viewer) + video rows (Open → OS player); search box; read from `media.scan()` |
| `ingest_dialog.py` | source selector (staging=move / Seestar=copy), **per-object grouped + checkbox-selectable** preview (Object · Kind · Files · Size · Pointing · → dest; select all/none; live size total), **name canonicalization + RA/DEC pointing check with a remap dropdown** (#12), threaded scan→group→annotate & apply behind modal progress+Cancel (applies only checked/retargeted groups) |
| `processing_dialog.py` | (legacy) manual **Prepare** preview — no longer launched (prep is automatic on ingest); kept pending a future processing-management view |
| `import_dialog.py` | **Import finished work** preview (detected renders/stacks, hero pick, cleanup choice) → threaded `apply_import` behind modal progress+Cancel |
| `image_viewer.py` | `ScalableImage` (pixmap that refits on resize — used for the hero) + `ImageViewer` (full-frame gallery viewer: Prev/Next, ←/→, Esc) |
| `preferences.py` | choose data folder (save + restart) + **"Prepare objects for processing in:"** workflow checkboxes (Siril; others disabled "soon") → `processing_workflows` setting |

---

## Conventions & rules

- **Record data-model changes in [`DATA_MODEL.md`](DATA_MODEL.md).** Any change to
  the on-disk layout, a file format, a derived-JSON shape, or `.store_version`
  **must** be reflected there (it's canonical). On-disk changes additionally bump
  `.store_version` and add a `migrate.py` step (idempotent, never destructive).
- **Never write into the content tree without explicit user confirmation.**
  Ingest is strictly **preview-then-confirm**: `scan_*_plan()` is read-only and
  returns a plan; `apply_ops()` (the only writer) runs only after the dialog's
  confirm. Mirror this for any future write feature.
- **Engine stays Qt-free.** No `PySide6` imports in `m110/*.py` (only in
  `m110/ui/`). Keeps the engine headless/testable.
- **Slow ops run off the UI thread** on a `QThread` worker behind a modal
  `QProgressDialog` with a working Cancel (see Refresh and Ingest). A
  synchronous scan/copy will freeze the window — don't.
- **Ported modules: behavior-compat was consciously retired for the two-axis
  store** (#13). `scan_sessions` / `build_derived` / `build_images` no longer
  match the Astronomy byte-for-byte goldens (new paths + `scan_sessions`/
  `build_derived` now read `config.*` dynamically instead of binding paths at
  import). The `display_names` port was **removed** entirely — M110 shows real
  filenames, not standardized display names (the convention may return behind a
  future publishing function). Validate against the repo's own fixtures, not the
  Astronomy originals.
- **Tests run on temp fixtures, never live data.** Engine functions take
  `config.*` paths dynamically or accept injected paths so tests can
  `monkeypatch` `config.IMAGES_DIR` / `DERIVED_DIR` / etc. Don't point tests (or
  ad-hoc validation) at a real data root.
- **Dependencies:** core = PySide6, astropy, numpy, pillow, tifffile (FITS
  stack-metadata reads + image rendering). Dev = pytest. Declared in
  `pyproject.toml`.

---

## Testing

```bash
pytest -q                 # all
pytest -q tests/test_ingest.py
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # (won't render, but imports/constructs)
```

81 tests, all fixture-based. UI is smoke-tested offscreen (construct windows,
drive workers via `app.processEvents()`), not pixel-tested. Add tests alongside
any engine change; for UI, prefer extracting logic into the engine and testing
that.

**Manual / regression testing:** see [`TESTING.md`](TESTING.md) — a runbook for
the GUI flows that aren't unit-tested (ingest, rendering, data-root), including a
safe-temp-root protocol and explicit regression checks for the fixed bugs. Open
issues / improvement backlog live in [`BUGS.md`](BUGS.md).

---

## Roadmap

**The canonical roadmap lives in [`ROADMAP.md`](ROADMAP.md)** — foundational
decisions (distribution, tech, processing model, data), the v0.1 build order
with status, later phases, and open decisions. Keep `ROADMAP.md` current as work
lands.

Current status at a glance: **v0.1 ("the Library") feature-complete — 0.1a–0.1f
done**, plus the two-axis store reshape (#13), the image-rendering port, and the
ingest backlog **#9/#10** (grouped + selectable preview) and **#12** (name
canonicalization + RA/DEC pointing check). Processing-prep is **preference-driven
and automatic** (runs on ingest; missing working folders self-heal on refresh —
#15). The **Media page** (#11) now displays non-catalog media. The full
**site-parity multi-page UI** is in (Summary · Catalog · Processing · Sessions ·
Journal · Media). **Still open:** **#16** (robust, layout-flexible, multi-telescope
ingest). **Next: post-MVP phases** (session planning, etc.). Foundational
decisions in brief: open-source / Developer-ID distribution (not App Store);
PySide6 over a headless engine; processing is prepare-and-guide, not direct Siril
control.

---

## Gotchas / lessons learned

- **EPERM copying from the Seestar (SMB).** `shutil.copy2`'s `copystat` fails
  setting the source's flags/xattrs on the destination. Ingest copies **bytes
  only** (`shutil.copyfile`) to a `.part` temp then `os.replace()` (atomic; no
  partial files). Don't reintroduce `copy2` for the copy path.
- **`processing.json` isn't byte-stable across runs** — it stamps a
  `generated_at` timestamp (intentional). Everything else in `derived/` is
  deterministic. Don't be alarmed by a churning `processing.json` diff.
- **Never validate rendering/refresh against a live data root.** (A render
  pointed at the wrong root once clobbered a real `images.json`.) Use a temp
  copy or a throwaway root.
- **Changing the data root: Preferences saves + prompts restart by design.**
  (Engine modules now read `config.*` paths dynamically — import-time path
  binding was removed in #13 — so `config.set_data_root()` is reliable in tests;
  the restart is just the simplest UX, not a hard requirement anymore.)
- **Cross-thread Qt:** workers communicate via signals; never touch widgets
  from a worker thread. Cancellation uses a `threading.Event` set by the
  progress dialog's `canceled` signal.
- **Library vs reference vs catalogs (item 5a).** The per-store `library.toml` is
  the user's mutable corpus (objects they track). The bundled **reference**
  (`seed/objects.toml`, J2000 coords + type/mag/size, produced at build time via
  Simbad — asterisms like "Markarian's Chain" don't resolve and skip the pointing
  check) and bundled **catalog lists** (`seed/catalogs/*.toml`) are immutable
  reference data, independent of the store. A fresh Library is seeded from the
  reference; the **v2→v3** migration renamed an existing store's `catalog.toml` →
  `library.toml`. Use `catalog.load_library()` for the corpus, `load_reference()` /
  `load_bundled_catalog()` for bundled data.
- **Captured-but-uncatalogued objects are auto-added to the Library on refresh.** A
  capture folder whose name maps to no Library slug (e.g. a freshly-shot `NGC
  6992`) would otherwise show only in folder-derived views (Processing/Sessions)
  and have no Library row / object page. `catalog.add_captured_objects()` (run
  first in `run_refresh`, before scan) adds a minimal entry (id = folder, type
  "unknown") + best-effort Simbad coords (`astropy from_name`; offline → minimal),
  so it becomes first-class. **Writes to the store `library.toml`** (additive,
  idempotent, never overwrites). `load_coords` merges those per-store coords over
  the bundled `seed/objects.toml` reference.
- **Processing-prep is automatic + idempotent.** It runs on ingest (full prep:
  links new lights + rewrites the preset for the current frame count) and on
  every refresh as a **missing-only** backfill (`processing.prepare_missing` —
  creates only absent `siril/` sandboxes, **never** rewriting an existing one, so
  hand-edited presets + in-progress runs are safe). There is **no manual "Prepare"
  button**; the workflow set is the `processing_workflows` preference (Siril only,
  for now). Don't reintroduce per-object manual prep.

---

## Repo layout

```
m110/            engine package (+ ui/ subpackage, seed/ data)
tests/                  pytest suite (fixture-based)
tools/                  dev utilities (make_test_corpus.py → synthetic manual-test store)
pyproject.toml          deps + entry point (gui-script: m110)
README.md               user-facing quickstart
CLAUDE.md               this file
ROADMAP.md              canonical roadmap
TESTING.md              manual / regression test runbook
BUGS.md                 open issues + improvement backlog
LICENSE / NOTICE        Apache-2.0
.venv/                  local virtualenv (gitignored)
```

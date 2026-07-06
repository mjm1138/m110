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
    library.toml        the user's Library = captured/annotated collection {slug: {id,name,type,…}}
                        (5d: starts empty, grows by capture/Add-object; v2→v3 renamed catalog.toml)
    goals.toml          per-store active goals (`active = [...]`, default Messier)
    priorities.toml     priority targets (optional `track=false` for campaign entries)
    sessions.jsonl      one capture session per line (generated by scan_sessions)
    processing_overrides.toml
    journal_template.md reference journal format (stubs are generated from it)
    profiles/           observing-site / device planning profiles (default.toml seeded;
                        [site] lat/lon/elev/tz + [horizon] .hrz mask + [glow] light-dome layer)
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
skeleton, seeds an **empty** `library.toml` (5d — the Library is the captured collection) + `priorities.toml` into `.m110_internal_data/` from
`m110/seed/` if missing, writes the internals README + `journal_template.md`, and
creates an `Objects/<id>/journal.md` stub (from the template) for **every Library
object** — all **idempotent, never overwrites**. Changing the root in Preferences
takes effect on **restart**.
Per-target paths come from `config.{target,lights,stacks,seestar_stacks,finished}_dir(name)`.

---

## Module map

**Engine (`m110/`)** — Qt-free:

| Module | Role |
|---|---|
| `config.py` | data-root resolution, dir bootstrap/seed (`_seed_library` now writes an **empty** Library — 5d: it's the captured collection, grown by capture/Add-object; also seeds `profiles/default.toml` for session planning), per-target path helpers, `GOALS_TOML`/`LIBRARY_TOML`/`PROFILES_DIR` per-store paths, settings persistence, Seestar mount detection (`find_seestar_myworks`) |
| `migrate.py` | in-place, idempotent, version-stamped migration of an older store to the two-axis layout (`migrate_store`) |
| `catalog.py` | `load_library` (per-store `library.toml` — the user's corpus); `load_reference` (bundled `seed/objects.toml`) + `load_bundled_catalog`/`list_bundled_catalogs` (bundled `seed/catalogs/*.toml` membership) + `catalogs_for_slug` (which catalogs an object is in) + `add_goal_members_to_library` (additively grow the Library from a catalog); `catalog_sort_key`/`season_sort_key`; `load_coords` (reference coords + per-store library `ra_deg/dec_deg`); `object_identifiers`/`object_label` (all designations ordered by catalog hierarchy Messier→Caldwell→NGC/IC) + `catalog_sort_key` (M/C/NGC/IC numeric); `add_captured_objects` (promote captured folders into the Library — known catalog objects pull full bundled-reference metadata, off-catalog ones get a minimal stub + Simbad coords); **5d removal**: `remove_library_entry(slug)` (manual "Remove from Library"; non-destructive) + `remove_goal_members_from_library(goal_id, members=)` (goal-deselect prune of uncaptured/un-noted/not-in-another-active-goal members); `season_from_ra` (derive the observing-season window from RA — calibrated to the curated Messier seasons, ≈98% match; shared with `tools/gen_caldwell.py`); `fill_missing_metadata(slug, online=)`/`fill_all_missing_metadata` (backfill an existing Library entry's **missing** fields from the bundled reference + derived season; `online=True` adds a Simbad tier for gaps the reference lacks; never overwrites real user values; the right-click / "Library → Fill missing metadata" + "Enrich online" actions) via `_write_library` (in-place rewriter preserving every key); **5c add/enrich**: `resolve_new_object(identifier, online=)` (cascade reference→online→coords for the Add-object flow, no write), `add_library_entry` (commit a new object + journal stub; refuses duplicates), `resolve_object_online`/`enrich_online` (batched Simbad; `OnlineLookupError` when astroquery/network absent), `_simbad_type`/`_simbad_row_to_entry` |
| `derived.py` | **read** generated rollups (totals/priorities/summary/processing/images/goals.json) |
| `processing.py` | workflow registry (Siril active; PixInsight/others disabled "soon") + `run_autoprep` (preference-driven, runs after ingest) + `prepare_missing` (refresh-time/on-demand backfill — creates only *absent* sandboxes, never rewrites existing) |
| `scan_sessions.py` | scan `Images/<target>/lights/` → `sessions.jsonl` (ported) |
| `build_derived.py` | compute totals/priorities/summary/processing/goals → `.m110_internal_data/derived/*.json` (ported). `build_totals` also surfaces **Seestar-stack-only** targets (a `seestar-stacks/` folder with no `lights/` → no sessions) as zero-integration captures, so they're first-class (gallery/status/`targets_for_slug`) — matching what `add_captured_objects` promotes |
| `build_images.py` | thumbnails + heroes + `images.json` into `.m110_internal_data/renders` (ported from build_site/generate_hero); content-hash cached |
| `ingest.py` | staging/Seestar scan **plan** (read-only) + gated `apply_ops` (the only writer into the content tree); cancellable |
| `siril.py` | processing-prep **round-trip** (prepare-and-guide). Prepare: `plan_prep`/`apply_prep` arrange a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks, Naztronomy preset tuned by frame count — drizzle + star-quality filters — and **preserved once hand-edited** via `is_default_preset`, per-filter jobs); `autoprep` runs it automatically after ingest (skips targets with pending finished output). Import: `has_unimported_output`/`scan_finished`/`apply_import` copy renders→`finished/` + stack→`stacks/`, optionally set hero (or keep current), then **archive** the run into `siril/[<FILTER>/]archive/<ts>/` (keeps `lights/`+preset ready for re-runs; never deletes, never escapes `siril/`). Bundled-guidance access |
| `objects.py` | per-object journal read **and write** (`Objects/<id>/journal.md`: `read_journal` frontmatter+body, `read_journal_text`/`write_journal` raw, `set_frontmatter_key` upsert for hero); slug→id folder name; hero path |
| `refresh.py` | `run_refresh()` = scan_sessions → build_derived → build_images (the UI refresh worker also runs `processing.prepare_missing` so missing working folders self-heal on any sync) |
| `media.py` | **read** non-catalog media — `scan()` enumerates `Media/<Category>_photo\|_video/` (Qt-free; backs the Media page) |
| `backup.py` | **Library backup engine** (item 10; Qt-free). Hardlinked dated snapshots to a user-chosen destination *outside* the store (`<dest>/M110-Backups/<store>/<ts>/` mirrors the store; unchanged files `os.link` to the prior snapshot — near-free incrementals). Denylist scope (skips `derived/`/`renders/`/`sessions.jsonl` + `siril/` sandboxes); byte-only copy (`.part`+`os.replace`, mtime-preserved) for new/changed files; per-snapshot `.m110-backup-manifest.json` (sha256) for **`verify`**; atomic (`.incomplete`→rename); hardlink-support probe + full-copy fallback. `create_snapshot`/`list_snapshots`/`verify`/`preview_restore`/`restore`/`apply_retention` + `options_from_settings`/`due_for_auto_backup`; `BackupError`/`BackupDestinationError`. External-output → no `.store_version` impact |
| `planning.py` | **session-planning engine** (ROADMAP item 1; astropy, lazy-imported). `twilight`/`moon_summary`/`transit_altitude` + the seasonal/tonight **`observability()`** gate → `{observable, hours_clear, transit_alt, nights_to_close, season}` (continuous `hours_clear` so the scorer can *grade* short windows). Coords from `catalog.load_coords`, season from `catalog.season_from_ra`; glow-aware via `horizon.effective_floor`. Consumer = the auto-prioritizer (#21) |
| `planning_config.py` | observing-**site** + **device** profiles loaded from `config.PROFILES_DIR/<name>.toml` (one profile = one location), in-code defaults when absent. `Site` carries lat/lon/elev/tz + the `[glow]` light-pollution layer (`bortle`/`sqm_zenith`/`glow_mask`/`glow_mask_narrowband`), `zoneinfo` DST, filter-aware `glow_path`; `list_profiles`/`load_site`/`load_device` |
| `horizon.py` | local **horizon / obstruction mask** (`.hrz`/CSV parse + interpolation + 0/360 wrap; `load_mask`/`horizon_alt`/`is_obstructed`) + the **glow layer**: `effective_floor`/`is_below_floor` compose physical horizon with the light-dome floor as `max(physical, glow)` |
| `goals.py` | **goals** = bundled catalogs **or** custom object lists, **per-store** in `.m110_internal_data/goals.toml` (`config.GOALS_TOML`, default Messier; `active = [...]` + `[[custom]]` blocks) — `active_goal_ids`, `set_active_goals` (persists the active set; a deactivation prunes via `catalog.remove_goal_members_from_library`; **no bulk seed** as of 5d), `goal_members`/`goal_name`/`list_goals` (unify bundled + custom), `create_custom_goal`/`edit_custom_goal`/`delete_custom_goal`. 5d retired the bulk goal-seed + `ensure_library_has_active_goals` |
| `seed/` | bundled `objects.toml` (object **reference**: id/type/mag/size/season + J2000 coords; 448 objects — Messier, Caldwell, RASC Finest, Best-of-Sharpless, Bennett, Lacaille; `season` derived from RA, coords/size/mag via Simbad at build time) · `catalogs/<name>.toml` (catalog membership `[members]` slug→designation): **messier, caldwell, rasc-finest, sharpless-best, bennett, lacaille** · `priorities.toml`. Generated by `tools/gen_caldwell.py` (Caldwell) + `tools/gen_catalogs.py` (the rest; idempotent, manages its own marked section in `objects.toml`) — both build-time only, runtime stays offline |
| `guidance/` | bundled Siril/Seestar workflow playbooks (`*.md`, package-data) surfaced in processing-prep |
| `publish/` | **publishing engine** (item 8a; Qt-free, optional `publish` extra = jinja2+markdown). Publisher **registry** mirroring `processing.WORKFLOWS` (`PUBLISHERS`/`run_publish`/`enabled_target_ids`, `SETTING_KEY="publish_targets"`): `static-site` available, `github-pages`/`netlify` registered-disabled. `site.py` renders Jinja2 `templates/*` (port of Astronomy `build_site.py`, real filenames) → a **local folder** from `derived.load_*()` + `build_images` derivatives + `objects` journals; `select.py` = testable selection/privacy (`publishable_slugs`, `journal_visible`, `filter_*`); `images.py` reuses `build_images` for web thumb/full; `options.PublishOptions` (output_dir/sections/exclude_journals/site_title); `errors.PublishDepsMissing` (degrade-gracefully). Per-object opt-out via `catalog.set_publish_flag` + journal `private` frontmatter |

**UI (`m110/ui/`)** — PySide6:

| Module | Role |
|---|---|
| `main.py` | **Shell**: left nav rail (`QListWidget`) → `QStackedWidget` of pages [Summary · Goals · Library · Processing · Sessions · Journal · Media]; **Summary is the landing page**. `goals` page's `dirty` → `_do_refresh`. Global Ingest (Ctrl+I) + **Library** menu (Refresh Ctrl+R, Prepare working folders, Add object…, Fill missing metadata — bulk reference backfill, Enrich online… — bulk Simbad enrichment on a worker, Publish, Back up/Restore, Preferences Cmd+, — which folds into the macOS **app menu** by role) + **Help** menu (About M110). No separate "M110" menubar menu. On macOS the app-menu/dock name is set to "M110" via a best-effort NSBundle patch (`_set_macos_app_name`, needs `pyobjc-framework-Cocoa`; the durable fix is a packaged `.app`). `RefreshWorker` (scan→derive→render + `prepare_missing`) drives `page.reload()`; **auto-syncs** on launch / window-focus / after ingest. `open_object(slug)` routes any page's object link → Catalog + selects it. Journal-edit lock disables nav + global actions |
| `widgets.py` | shared `NumItem` (sort-key cell), `status_label`/colors, `targets_for_slug`, `make_table`, async cached row-thumbnail loading (`ThumbnailLoader` + `RowThumbnails`, hero-backed; Library/Sessions/Processing row icons; `ThumbnailLoader.request(..., crop=)` supports both the row-icon aggressive crop and a milder "square" crop for bigger tiles), `paint_status_chip()` (the tinted-rounded-chip paint primitive, shared by `StatusPillDelegate` and the Library grid's `TileDelegate`) |
| `image_grid.py` | reusable tile-grid component (`TileItem`/`TileModel`/`TileDelegate` — `QAbstractListModel` + `QStyledItemDelegate`), app-data-agnostic (no imports from `catalog`/`objects`/`derived`) so a future cross-object image browser can reuse it; the Library grid (`pages/catalog.py`) is the first consumer |
| `detail.py` | shared per-object `DetailPane`: header/status, hero (scales to pane), **Object Notes** **view/edit** (raw `journal.md` — the object's entry in the top-level Journal feed; labeled "Object Notes" to leave room for future Session/Processing Notes), gallery (double-click → image viewer, items carry `_gallery_meta()` display metadata — Source/Date/Size always, Integration/Filter when unambiguously derivable; compact center-cropped-square contact-sheet grid via `_square_icon()`, elided filenames with a full-name tooltip), **Import finished work** entry, + per-object **Processing** + **Sessions** tables and an **Object details** block (type/mag/size/season, RA/Dec in decimal + sexagesimal, filter rule, slug, capture targets, **Remarks** = the library `notes` field). Shows real filenames |
| `pages/catalog.py` | the **Library**: a table view (Object/Name/Type/Season/Mag/Size/Filter/Status/Integration/Sessions; Object shows all identifiers via `catalog.object_identifiers`, e.g. "C20 (NGC 7000)") **and** a **grid view** (`image_grid.TileModel`/`TileDelegate`, one tile per object — hero + id/name + status chip + integration), toggled by two `QToolButton`s + a zoom `QSlider` (persisted view mode + tile size) in a `QStackedWidget`; both views build from one shared `_current_items()`/filter pipeline so search/catalog-filter/captured-only and selection stay in sync across the toggle + a **Catalog filter** selector (All / Messier / Caldwell …) + a **"Captured only"** checkbox (default off; composes with catalog + search) + **search** + captured/deep/total **stat row** (per-filter), hosting the shared `DetailPane`; `select_object`/`reload` work identically regardless of active view; per-object import flow; **right-click → "Fill in missing metadata"** (reference) + **"Enrich online"** (Simbad, on a worker; `OnlineLookupError`→dialog) + **"Remove from Library"** (`catalog.remove_library_entry`; confirm, non-destructive); edit-lock |
| `pages/summary.py` | landing dashboard — **goal progress** (per active catalog), category progress, processing-queue snapshot, current integrations, priority targets; object rows → `open_object` |
| `pages/goals.py` | **Goals** page (5d): manage tracked goals (bundled + custom) — activate/deactivate checkboxes (→ `goals.set_active_goals`, emits `dirty`), **New custom goal…**/Edit/Delete (member identifiers resolved offline via `catalog.resolve_new_object`); per-active-goal **progress** + **in-progress captures** (clickable → `open_object`) + a **Remaining (uncaptured)** membership checklist. Goal management lives here, not Preferences |
| `pages/processing.py` | Siril queue grouped by status with stack-meta columns; rows → `open_object` |
| `pages/sessions.py` | capture-session log (sortable table Date/Object/Frames/Exp/Filter/Integration/Mount, default Date-desc) + search box; from `derived.load_sessions()`; rows → `open_object` |
| `pages/journal.py` | reverse-chron **feed** of object cards (header · hero · status/stats · rendered notes) — every captured object + any noted-but-uncaptured; ordered by latest image mtime (reprocess re-orders); search box; cards → `open_object` |
| `pages/media.py` | **Media** browser for non-catalog `Media/<Category>_photo\|_video/` (ingest already captures it): per-category sections — photo gallery (double-click → image viewer) + video rows (Open → OS player); search box; read from `media.scan()` |
| `ingest_dialog.py` | source selector (staging=move / Seestar=copy), **per-object grouped + checkbox-selectable** preview (Object · Kind · Files · Size · Pointing · → dest; select all/none; live size total), **name canonicalization + RA/DEC pointing check with a remap dropdown** (#12), threaded scan→group→annotate & apply behind modal progress+Cancel (applies only checked/retargeted groups) |
| `processing_dialog.py` | (legacy) manual **Prepare** preview — no longer launched (prep is automatic on ingest); kept pending a future processing-management view |
| `import_dialog.py` | **Import finished work** preview (detected renders/stacks, hero pick, cleanup choice) → threaded `apply_import` behind modal progress+Cancel |
| `add_object_dialog.py` | **Add object** dialog (5c): type a name/designation → instant offline reference resolve into an editable preview + **"Look up online"** (Simbad, worker thread) → `catalog.add_library_entry`; preview-then-confirm; emits `added(slug)` |
| `image_viewer.py` | `ScalableImage` (pixmap that refits on resize — used for the hero) + `ZoomableImage` (`QScrollArea`-based Fit/explicit-zoom + click-drag pan) + `ImageViewer` (full-frame gallery viewer: Prev/Next, ←/→/Home/End, zoom toolbar, toggleable metadata overlay, Esc). Accepts `(name, path)` tuples or `{"name","path","meta"}` dicts; app-data-agnostic (metadata content built by callers) |
| `preferences.py` | choose data folder (save + restart) + **"Prepare objects for processing in:"** workflow checkboxes → `processing_workflows`. (Goals moved to the Goals page in 5d.) |
| `publish_dialog.py` | **Publish / share** dialog (item 8a, off the Library menu): section checkboxes + global "exclude journals" + target picker (`publish.PUBLISHERS`, "(soon)" for disabled) + site-title + output-folder chooser → threaded `_PublishWorker` running `publish.run_publish` behind modal progress+Cancel; persists the selection to settings; "Open folder" on success |
| `backup_dialog.py` | **Back up Library** dialog (item 10, Library menu): destination **pre-seeded from the saved setting** (Browse overrides ad-hoc; a run saves it back) + snapshot-status line + Automation/retention group (auto-on-launch · interval · keep-N/days/min-free) → threaded `_BackupWorker` running `backup.create_snapshot` behind modal progress+Cancel; "Open folder" on success; **Restore…** button opens the restore dialog |
| `restore_dialog.py` | **Restore from backup** dialog (item 10): snapshot picker (by date) + a checkable file **tree** (from the snapshot manifest) + restore target (**extract to a folder** default, or **into the store** behind a create-vs-overwrite conflict preview + confirm) + **Verify integrity** (`backup.verify`); threaded `_Worker` (shared by verify + restore) behind modal progress+Cancel |
| `about_dialog.py` | **About M110** dialog (UI Phase 4 branding; Help menu, `AboutRole` so macOS folds it into the app menu): theme-recolored logo + tagline ("Complete the catalog.") + version (`importlib.metadata`) + Apache-2.0 line |
| `theme/` | **design system** (UI Phase 0; `m110/ui/theme/`). `tokens.py` = light+dark semantic palette (`LIGHT`/`DARK` `Tokens`; roles like `window`/`surface`/`text_secondary`/`accent`/`status_deep`) + `SPACE`/`RADIUS`/`FONT_SIZE` scales + `active()`/`set_active`. `qss.build_qss(tokens)` generates the app-wide stylesheet. `manager.ThemeManager` applies it + **follows the OS appearance** (`QStyleHints.colorScheme()`, live via `colorSchemeChanged` on Qt≥6.8 else focus-in `refresh_system`) with a persisted `ui_theme` override. `fonts.py` bundles **JetBrains Mono** (`fonts/*.ttf`, OFL) + `mono_font()`. Façade: `install(app)` (in `main()`), `set_mode`, `active_tokens`, `status_color`/`muted_color`/`ink_color`, plus the brand helpers `app_icon`/`logo_pixmap`/`logo_icon`. `brand.py` = theme-aware branding (UI Phase 4): `logo_pixmap(height, color)` recolors the bundled `brand/m110-logo.svg` ink — any near-black `fill` (style **or** attribute form) → the target color, then applies an **alpha dilation** (`LOGO_STROKE_WIDTH`, viewBox units — Qt's SVG renderer silently ignores strokes on this complex path, so weight is added by dilating the rendered ink, not an SVG stroke) so hairlines read when scaled — then tight-crops (fast path = path bounds; fallback = transparent-pixel autocrop, so a **drop-in replacement SVG needs no code changes** as long as it's black ink on transparent). Wordmark reads in light **and** dark; the nav-rail mark recolors on `ThemeManager.changed`. `app_icon()` composes the ink (deep sepia) on a **fixed parchment tile**, inset ~80% of the canvas (dock-icon grid) — app/dock icons intentionally **don't** follow the theme; `tools/gen_app_icon.py` exports `brand/app-icon.png` for packaging. (A warm-sepia `accent` was tried in Phase 4 but **reverted** — the accent stays the neutral blue.) **New UI code pulls color/spacing from tokens — never hardcode hex.** Programmatic (non-QSS) colors repaint via a page `restyle()` on `ThemeManager.changed`; muted labels use the `QLabel[muted="true"]`/`[caption="true"]` QSS rules |

---

## Conventions & rules

- **Work on a feature branch; close out by updating the roadmap.** Land each unit of
  work on a dedicated branch off `main` (convention: `feature/<short-name>`) — never
  commit feature work directly to `main`. **Conclude the same change** with `pytest -q`
  green **and** an appropriate update to **[`ROADMAP.md`](ROADMAP.md) and/or
  [`BUGS.md`](BUGS.md)** marking what landed (roadmap items marked done; new fixes get
  a brief done entry) — plus [`DATA_MODEL.md`](DATA_MODEL.md) / [`TESTING.md`](TESTING.md)
  when the change touches the data model or the manual-test surface. Docs ship *with*
  the code, not later.
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
- **Minimal main-window chrome.** Keep the main window's primary views' visible
  controls to a minimum — one control per meaning, sensible defaults over
  seldom-flipped toggles, unobtrusive but legible. Added UI density belongs in
  special-purpose/editing surfaces (object detail, processing management,
  dialogs), not the main pages. Full rationale + examples in
  [`UI_ROADMAP.md`](UI_ROADMAP.md) → Vision.
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
  ad-hoc validation) at a real data root. **A session-autouse seal in
  `tests/conftest.py` (`_seal_live_store`/`_reset_to_seal`) hard-points
  `M110_DATA_ROOT` + the `config.*` globals + `SETTINGS_FILE` at a throwaway dir for
  the whole run** — so even a `QThread` worker that leaks past its per-test
  `monkeypatch` (which once corrupted a live `library.toml`) can never read/write
  `~/Documents/M110`. Keep per-test `seed_root` + the MainWindow `_ready = False`
  guard anyway (defense in depth).
- **Dependencies:** core = PySide6, astropy, numpy, pillow, tifffile (FITS
  stack-metadata reads + image rendering). Optional `online` extra = astroquery
  (Simbad lookups for Add object / Enrich online — runtime stays offline unless
  installed; the online actions degrade gracefully via `OnlineLookupError`). Dev =
  pytest (+ astroquery for `tools/gen_caldwell.py`). Declared in `pyproject.toml`.

---

## Testing

```bash
pytest -q                 # all
pytest -q tests/test_ingest.py
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # (won't render, but imports/constructs)
```

223 tests, all fixture-based. The **UI is driven offscreen with pytest-qt**
(`qtbot` — clicks/keys/dropdowns + signal/state assertions, not just construct):
ingest dialog, processing-prep, library/detail. Shared store/builder fixtures live
in `tests/_helpers.py`; offscreen platform in `tests/conftest.py`. **Rendering has
golden-image tests** (`tests/test_render_golden.py` vs committed `tests/goldens/`,
tolerance pixel-compare; refresh with `M110_UPDATE_GOLDENS=1`). Add tests alongside
any engine change; for UI, prefer extracting logic into the engine and testing
that. (`pip install -e ".[dev]"` pulls pytest + pytest-qt.)

**Manual / regression testing:** see [`TESTING.md`](TESTING.md) — a runbook for
the GUI flows that aren't unit-tested (ingest, rendering, data-root), including a
safe-temp-root protocol and explicit regression checks for the fixed bugs. Open
issues / improvement backlog live in [`BUGS.md`](BUGS.md).

---

## Roadmap

**The canonical roadmap lives in [`ROADMAP.md`](ROADMAP.md)** — foundational
decisions (distribution, tech, processing model, data), the v0.1 build order
with status, later phases, and open decisions. Keep `ROADMAP.md` current as work
lands. Completed milestones are archived to [`DONE.md`](DONE.md) (item numbers
match their original ROADMAP slot) — **skim it when fixing a bug in or extending an
existing subsystem**: it records *how and why* each piece shipped, which is often
the missing context behind a "why is it built this way?" question.

Current status at a glance: **v0.1 ("the Library") feature-complete — 0.1a–0.1f
done**, plus the two-axis store reshape (#13), the image-rendering port, and the
ingest backlog **#9/#10** (grouped + selectable preview) and **#12** (name
canonicalization + RA/DEC pointing check). Processing-prep is **preference-driven
and automatic** (runs on ingest; missing working folders self-heal on refresh —
#15). The **Media page** (#11) now displays non-catalog media. The full
**site-parity multi-page UI** is in (Summary · Catalog · Processing · Sessions ·
Journal · Media). **Import #16 (item 6)** is substantially done — 6a–6c (any-directory
recursive source, FITS-header classification + layout registry, holding-area manual
assign); 6d (lazy device-under-target) deferred until a 2nd device exists. **Publishing
(item 8a)** landed: a Qt-free `publish/` engine + Library → Publish / share… exports a
selective static site to a local folder (GitHub Pages / other targets deferred).
**Next: post-MVP phases** (session planning, etc.). Foundational
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
- **Don't trust file mtime for provenance / freshness.** Ingest + import copy
  bytes with `shutil.copyfile` (mtime = copy time), and a bulk import (e.g. the
  Astronomy port) flattens every file's mtime to when it landed — so "is this
  stack newer than these lights?" via mtime silently lies. Derive freshness from
  **content the pipeline recorded**: capture dates live in the FITS headers
  (surfaced by `scan_sessions` → `sessions.jsonl`), and a stack's own FITS `DATE`
  is when it was made. `build_processing` compares those (frames captured after
  the stack `DATE` = the unintegrated backlog; rejection% is `1 − STACKCNT /
  frames_present_at_stack`, not `/ running_total`). Reach for mtime only as a
  last-resort fallback when no such recorded timestamp exists.
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
- **Captured objects are auto-added to the Library on refresh (5d: the Library *is*
  the captured collection).** A capture folder whose name maps to no Library slug
  would otherwise show only in folder-derived views (Processing/Sessions) and have
  no Library row / object page. `catalog.add_captured_objects()` (run first in
  `run_refresh`, before scan) adds it: a **known catalog object** (slug in the
  bundled reference, e.g. a freshly-shot `M101`) pulls its **full reference
  metadata**; an **off-catalog** target gets a minimal entry (id = folder, type
  "unknown") + best-effort Simbad coords (offline → minimal). **Writes to the store
  `library.toml`** (additive, idempotent, never overwrites). `load_coords` merges
  those per-store coords over the bundled `seed/objects.toml` reference. (This is
  the main way the otherwise-empty Library fills up.)
- **Processing-prep is automatic + idempotent.** It runs on ingest (full prep:
  links new lights + re-tunes the preset for the current frame count — but **only
  if the preset is still an unedited default**, detected by `siril.is_default_preset`
  comparing it to the generated default at any count bucket; a hand-edited preset is
  preserved) and on every refresh as a **missing-only** backfill
  (`processing.prepare_missing` — creates only absent `siril/` sandboxes, **never**
  rewriting an existing one, so hand-edited presets + in-progress runs are safe).
  There is **no manual "Prepare"
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
ROADMAP.md              canonical roadmap (open/active work + decisions)
DONE.md                 archive of shipped work (how/why it landed) — read when touching an existing subsystem
TESTING.md              manual / regression test runbook
BUGS.md                 open issues + improvement backlog
LICENSE / NOTICE        Apache-2.0
.venv/                  local virtualenv (gitignored)
```

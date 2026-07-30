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
    previews/           optional per-sub JPG previews (#25; only when `import_sub_previews` pref on;
                        kept out of lights/ + the gallery tiers — a review archive)
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
    pins.toml           manual Pin/Deprioritize priority overrides (#3): `[pins]` slug→"pin"|"deprioritize"
                        (lazily created, additive, survives regeneration; the scorer will compose over it)
    sessions.jsonl      one capture session per line (generated by scan_sessions)
    processing_overrides.toml
    journal_template.md reference journal format (stubs are generated from it)
    profiles/           observing-site / device planning profiles (default.toml seeded;
                        [site] lat/lon/elev/tz + [horizon] .hrz mask + [glow] light-dome layer)
    derived/            generated rollups: totals/priorities/summary/processing/images.json
    renders/            generated thumbnails + hero/<slug>.jpg (gallery assets)
    .store_version      layout version stamp (= 4)
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
| `config.py` | data-root resolution, dir bootstrap/seed (`_seed_library` now writes an **empty** Library — 5d: it's the captured collection, grown by capture/Add-object; also seeds `profiles/default.toml` for session planning), per-target path helpers, `GOALS_TOML`/`LIBRARY_TOML`/`PROFILES_DIR` per-store paths, settings persistence, Seestar mount detection (`find_seestar_myworks`). **`FIT_EXTS`/`is_fits_file`** = the single authority for FITS extensions (`.fit` **and** `.fits` — Dwarf 3 writes `.fits`), used by `is_light_frame` + import/sessions/prep so a new device's extension is recognized everywhere at once |
| `migrate.py` | in-place, idempotent, version-stamped migration of an older store to the two-axis layout (`migrate_store`) |
| `catalog.py` | `load_library` (per-store `library.toml` — the user's corpus); `load_reference` (bundled `seed/objects.toml`) + `load_bundled_catalog`/`list_bundled_catalogs` (bundled `seed/catalogs/*.toml` membership) + `catalogs_for_slug` (which catalogs an object is in) + `add_goal_members_to_library` (additively grow the Library from a catalog); `catalog_sort_key`/`season_sort_key`; `load_coords` (reference coords + per-store library `ra_deg/dec_deg`); `object_identifiers`/`object_label` (all designations ordered by catalog hierarchy Messier→Caldwell→NGC/IC) + `catalog_sort_key` (M/C/NGC/IC numeric); `add_captured_objects` (promote captured folders into the Library — known catalog objects pull full bundled-reference metadata, off-catalog ones get a minimal stub + Simbad coords); **5d removal**: `remove_library_entry(slug)` (manual "Remove from Library"; non-destructive) + `remove_goal_members_from_library(goal_id, members=)` (goal-deselect prune of uncaptured/un-noted/not-in-another-active-goal members); `season_from_ra` (derive the observing-season window from RA — calibrated to the curated Messier seasons, ≈98% match; shared with `tools/gen_caldwell.py`); `fill_missing_metadata(slug, online=)`/`fill_all_missing_metadata` (backfill an existing Library entry's **missing** fields from the bundled reference + derived season; `online=True` adds a Simbad tier for gaps the reference lacks; never overwrites real user values; the right-click / "Library → Fill missing metadata" + "Enrich online" actions) via `_write_library` (in-place rewriter preserving every key); **5c add/enrich**: `resolve_new_object(identifier, online=)` (cascade reference→online→coords for the Add-object flow, no write), `add_library_entry` (commit a new object + journal stub; refuses duplicates), `resolve_object_online`/`enrich_online` (batched Simbad; `OnlineLookupError` when astroquery/network absent), `_simbad_type`/`_simbad_row_to_entry` |
| `derived.py` | **read** generated rollups (totals/priorities/summary/processing/images/goals.json) |
| `processing.py` | workflow registry (Siril active; PixInsight/others disabled "soon") + `run_autoprep` (preference-driven, runs after ingest) + `prepare_missing` (refresh-time/on-demand backfill — creates only *absent* sandboxes, never rewrites existing) |
| `scan_sessions.py` | scan `Images/<target>/lights/` → `sessions.jsonl` (ported). **Header-driven** (`_session_key`): each sub's `(date, exp, filter)` comes from the Seestar/mosaic **filename** when it matches (fast path, no header read), else from the FITS **header** (`DATE-OBS`/`EXPTIME`/`FILTER`) — so any device's subs (Dwarf 3, …) produce sessions regardless of filename convention. Accepts `.fit`/`.fits`. **Mount mode = the reported `EQMODE` header card** (`_mount_mode`/`_read_eqmode`): Seestar **and** Dwarf 3 both write `EQMODE` (int 1=EQ / 0=Alt-Az, "Equatorial mode"), read once per session-segment; falls back to the legacy `EQ_FROM` date heuristic only when the card is absent (pre-`EQMODE` firmware). The date rule is Mike-Seestar-specific — header truth wins so other users/devices aren't mislabeled |
| `build_derived.py` | compute totals/priorities/summary/processing/goals → `.m110_internal_data/derived/*.json` (ported). `build_totals` also surfaces **Seestar-stack-only** targets (a `seestar-stacks/` folder with no `lights/` → no sessions) as zero-integration captures, so they're first-class (gallery/status/`targets_for_slug`) — matching what `add_captured_objects` promotes |
| `build_images.py` | thumbnails + heroes + `images.json` into `.m110_internal_data/renders` (ported from build_site/generate_hero); content-hash cached. **Hero cache keys on source *identity*** (a `hero/<slug>.src` sidecar = source rel-path + `img_hash`), not mtime — so a set-hero to an *older* image re-renders instead of leaving a stale hero (#17). `rebuild_hero(slug)` re-renders one object's hero synchronously (interactive set-hero, no full refresh) |
| `ingest.py` | staging/Seestar scan **plan** (read-only) + gated `apply_ops` (the only writer into the content tree); cancellable. **One deterministic scanner (#32):** all entry points go through the recursive `scan_directory_plan` (`os.walk`, depth-agnostic) — `scan_seestar_plan`/`scan_staging_plan` delegate to it (the old shallow one-level `_scan_base` was retired, it silently missed nested subfolders); the walk logs every dir visited + its layout + pruned subtrees + a final `scan_summary` (`m110` logger → `~/.m110/logs/m110.log`), and `scan_summary(ops)` gives the UI headline counts (objects / to-import / to-holding). Holding area (6c): `scan_holding`/`assign`/`discard_holding` + **`annotate_holding`/`identify_holding`** (#26 aids — per held group, `frame_info` header facts + suggested object [OBJECT header → slug via `_slug_for_object`, else nearest catalog by RA/Dec within `IDENTIFY_TOL_DEG`] + suggested kind [IMAGETYP]). **Per-sub preview import** (#25, default off — `import_sub_previews` setting): the `_sub` branch optionally routes the Seestar's per-sub `.jpg` previews to `Images/<target>/previews/` (new `"preview"` kind) instead of ignoring them. **DwarfLab Dwarf 3** (`dwarf` layout, `_classify_dwarf_dir`, keyed on the `DWARF_RAW_*`/`STARTRAILS_*` session-folder prefix): `.fits` subs → `lights/` (object from `OBJECT` header), in-app `stacked-16_*` + `stacked.jpg` → the `seestar-stacks/` device-stack tier, `Thumbnail/` (added to `_SKIP_DIRS`) + aux rasters (`img_*`, `*_thumbnail`) ignored, **startrails** → `Media/Startrails_{video,photo}/`. `_usable_object` treats `OBJECT` of `''`/`Unknown` as absent → holding area (identify-by-pointing). Loose re-grouped Dwarf FITS fall to `raw-fits` (routed by `OBJECT`) |
| `siril.py` | processing-prep **round-trip** (prepare-and-guide). Prepare: `plan_prep`/`apply_prep` arrange a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks, Naztronomy preset tuned by frame count — drizzle + star-quality filters — and **preserved once hand-edited** via `is_default_preset`, per-filter jobs); `autoprep` runs it automatically after ingest (skips targets with pending finished output). Import: `has_unimported_output`/`scan_finished`/`apply_import` copy renders→`finished/` + stack→`stacks/`, optionally set hero (or keep current), then **archive** the run into `siril/[<FILTER>/]archive/<ts>/` (keeps `lights/`+preset ready for re-runs; never deletes, never escapes `siril/`). **Name-collision = keep-both, content-aware** (`_resolve_import_dest`/`_same_bytes`): a byte-identical incoming file is skipped (true duplicate, dedup against every `<stem>-N` sibling), a *different* same-name file lands as the first free `<stem>-N<ext>` (both kept — never clobbers, never the old silent-skip-then-archive footgun); `has_unimported_output` + the "Ready to import" flag treat a differing same-name file as unimported, and hero pinning follows the name the render actually landed under. **Finished-output discovery = sandbox + object-dir fallback** (`_finished_outputs` = `_sandbox_outputs` ∪ `_root_outputs`): the fallback scans `Images/<target>/` too — skipping the managed tiers/raw inputs/`siril/`/`process/` — so output from a run whose Siril **working directory was mis-set to the object dir** (one level above the sandbox) is still picked up. `working_dirs(target)` = the working dirs to offer "Process in Siril" (per-filter job dirs if split, else the sandbox root; `[]` when no sandbox) |
| `launch.py` | **external-app launcher** (#19 "Process in…" / "Open In…", Qt-free). Starts a processing/viewer tool and gets out of the way — never controls it. `find_app(tool_id)` = user override (`external_app_paths` setting) → OS-standard locations (macOS `/Applications/Siril.app/Contents/MacOS/siril`, Linux `siril`/`siril-cli` via `which`, Windows Program Files) → `None`; `launch_processing(tool_id, working_dir)` builds the tool's working-dir argv (Siril `-d <dir>`): **macOS** goes through `_launch_macos` (`/usr/bin/open -a <Siril.app bundle> --args -d <dir>` — LaunchServices makes Siril its own *responsible process* so its hardened bundled Python can spawn; see the gotcha), **elsewhere** `_spawn`s the binary detached; both with a sanitized `_child_env()` (strips our `VIRTUAL_ENV`/`PYTHON*`/PyInstaller `_MEI*` + bundled-Qt plugin paths `QT_PLUGIN_PATH`/`QML*_IMPORT_PATH` + restores bundle libpaths) so a launched tool's own Python **and Qt** aren't poisoned by ours. `LaunchError` when not found / spawn fails. `_TOOLS` registry (Siril only today; extensible). The UI (`ui/widgets.process_in_siril`) falls back to revealing the folder on `LaunchError` |
| `hints.py` | **finished / intermediate filename hints** (#17) — the single, user-editable vocabulary deciding whether a filename marks a *finished* deliverable vs an *intermediate* by-product. Case-insensitive substring keywords (defaults `processed/final/finished` + `starless/starmask`), persisted in `settings.json` under `finished_hints`, read live. `is_finished_name`/`is_intermediate_name` + `get_hints`/`set_hints`. **Three consumers** draw from it (replacing their old hardcoded regexes, the source of stranger-file misclassification): `siril._classify` (import finished work), `ingest._is_finished_raster` (loose finished-render recognizer), `build_images._is_intermediate_fit` (hero-tier selection). Edited in Preferences |
| `objects.py` | per-object journal read **and write** (`Objects/<id>/journal.md`: `read_journal` frontmatter+body, `read_journal_text`/`write_journal` raw, `set_frontmatter_key` upsert for hero, `get/set_frontmatter_list` for JSON-array keys); **per-image curation** (#17) `get_curation`/`set_curation` (filename→`"finished"`\|`"working"` overrides in `finished_extra`/`working_extra` frontmatter, one list each); slug→id folder name; hero path |
| `refresh.py` | `run_refresh()` = scan_sessions → build_derived → build_images (the UI refresh worker also runs `processing.prepare_missing` so missing working folders self-heal on any sync) |
| `logsetup.py` | **application logging** (Qt-free; the beta crash-reporting arc). `setup_logging()` (idempotent) configures the `m110` logger with a `RotatingFileHandler` at `~/.m110/logs/m110.log` (+ stderr); `log_path`/`read_log_tail` surface it in the crash report. Called first thing in `main()` |
| `media.py` | **read** non-catalog media — `scan()` enumerates `Media/<Category>_photo\|_video/` (Qt-free; backs the Media page) |
| `webexport.py` | **size-budgeted image export for web sharing** (`feature/image-export`, Qt-free). `export_for_sharing(src, dest, *, strategy=, max_bytes=None)` writes the best-quality file that fits an **optional** byte budget: **lossless** = optimized PNG → (only if a max is set and over it) binary-search the long edge (Lanczos) for the largest lossless PNG that fits (optional `pyoxipng` on the winner; floor `MIN_LONG_EDGE`, else `ExportError`); **quality** = full-res JPEG (`subsampling=0` 4:4:4, baseline — progressive tripped libjpeg on incompressible frames). **`max_bytes=None` = no maximum** (full-res PNG/JPEG, no ladder). Reuses `build_images._open_image` (FITS/float-TIF percentile-stretched to 8-bit RGB) so exports match the app render — which folds the 16→8-bit reduction in for free (a 30 MB 16-bit finished PNG lands ~11 MB at full res). Output format deterministic from the strategy (lossless→PNG, quality→JPEG); `suggested_name`=`[Object]-[maxsize]-[YYYYMMDD].[ext]`; `SAFETY_MARGIN` headroom; byte-identical originals copy verbatim (fast path). External-folder output → no `.store_version` impact. *(No site presets — a bare max-size + No-maximum control, per user feedback)* |
| `backup.py` | **Library backup engine** (item 10; Qt-free). Hardlinked dated snapshots to a user-chosen destination *outside* the store (`<dest>/M110-Backups/<store>/<ts>/` mirrors the store; unchanged files `os.link` to the prior snapshot — near-free incrementals). Denylist scope (skips `derived/`/`renders/`/`sessions.jsonl` + `siril/` sandboxes); byte-only copy (`.part`+`os.replace`, mtime-preserved) for new/changed files; per-snapshot `.m110-backup-manifest.json` (sha256) for **`verify`**; atomic (`.incomplete`→rename); hardlink-support probe + full-copy fallback. `create_snapshot`/`list_snapshots`/`verify`/`preview_restore`/`restore`/`apply_retention` + `options_from_settings`/`due_for_auto_backup` (launch: newest snapshot older than the 12h interval) / `due_for_scheduled_backup` (hourly-tick daily 02:00 while running, interval as min-age guard); `BackupError`/`BackupDestinationError`. External-output → no `.store_version` impact |
| `planning.py` | **session-planning engine** (ROADMAP item 1; astropy, lazy-imported). `twilight`/`moon_summary`/`transit_altitude` + the seasonal/tonight **`observability()`** gate → `{observable, hours_clear, transit_alt, nights_to_close, season}` (continuous `hours_clear` so the scorer can *grade* short windows). Coords from `catalog.load_coords`, season from `catalog.season_from_ra`; glow-aware via `horizon.effective_floor`. **Checkpoint B (tonight's plan):** `night_track` (per-target alt/az samples across the dark window → transit time+alt, longest contiguous up-window above min-alt+glow floor, moon separation, the `(time,alt,clear)` series for the timeline) + `plan_night` (dark window + moon + per-target tracks, **auto-ordered by `up_end`** = sets-soonest first, tiebreak by score; `order="manual"` preserves input; computes twilight ONCE and reuses via `window=`). Consumers = the auto-prioritizer (#21) + the planner UI. **Tuning arc (docs-archive/PLANNING_ROADMAP.md):** `pick_start` (start-altitude ceiling — highest *clear* sample at/below the device ceiling −`START_CEILING_MARGIN_DEG`; hard = refuse, soft = flag `over_ceiling`), per-slot **moon** (`plan_night` moon = `{illum, alt, set_time, rise_time, track}`; per-entry `moon_alt_at_best`+`moon_impact`), `moon_impact` (illum × proximity, narrowband ×0.25, `None` when moon down — separations computed **topocentrically in a common AltAz frame**, never `icrs.separation(gcrs_moon)`: that re-expresses the moon from the barycenter, the 101°-vs-45° bug), and **`sequence_plan`** (pure night sequencer, #40–42: non-overlapping 10-min slots, priority order w/ ties-to-the-setter, deep-remaining duration caps, `fill` past count to dawn, `marginal` ⚠ ≤`MARGINAL_SLOT_MIN` window-cut descending slots, `forced_order` for the UI reflow) |
| `fieldguide.py` | **session-plan field guide** (`feature/session-planner`, Qt-free). `render_markdown(site, day, plan)` → a printable observing plan (dark window + moon, ordered target table with best time/alt/up-window/moon°/filter + per-target season+notes), rendered in-app by `QTextBrowser.setMarkdown` (no dep). `save`/`list_guides`/`read` manage saved guides under the **`Plans/`** visible axis (`config.PLANS_DIR`, created by `ensure_data_root`; `Plans/<date>_<slug>.md`). Renders the **`## Schedule`** table when `plan["schedule"]` is present (`sequence_plan` slots: start/duration ⚠/alt ^/filter/moon); `moon_headline` (whole-night moon line) + `moon_cell` (gated on moon-up) + `start_cells` (startable slot, falls back to transit for old dicts) are shared with the Planning table; footer stamps generation date *and* plan night |
| `planning_config.py` | observing-**site** + **device** profiles loaded from `config.PROFILES_DIR/<name>.toml` (one profile = one location), in-code defaults when absent. `Site` carries lat/lon/elev/tz + the `[glow]` light-pollution layer (`bortle`/`sqm_zenith`/`glow_mask`/`glow_mask_narrowband`), `zoneinfo` DST, filter-aware `glow_path`; `list_profiles`/`load_site`/`load_device`. **Writers (Planning UI, `feature/planning-profiles`):** `save_site`/`delete_profile` (default protected) + `format_site_toml` (hand-written TOML, no writer dep), `import_horizon_mask` (validates via `horizon.load_mask`, copies beside the profile), the **active-profile** selection (`active_profile`/`set_active_profile`/`load_active_site`, persisted in settings under `active_site_profile`), and an optional online **`geocode`** (Nominatim, degrades offline). `Device` carries `start_alt_ceiling_deg` + **`ceiling_is_hard`**; **`DEVICE_PRESETS`** = the researched per-device ceilings (Seestar S50/S30/S30 Pro hard 78° — S30s assumed from the shared app, unverified; Dwarf 3/Mini soft 80°) |
| `assistant/` | **the assistant layer** (ROADMAP item 4; Qt-free). **The invariant: no tool MODIFIES or DELETES anything; a tool may CREATE a file, only in the outbox, under quota** — relaxed from M0's zero-write once saving a plan proved impossible without it. The property that matters was never "no bytes written" but "can't damage or silently alter what you made". `registry.py` = 13 engine operations as provider-neutral JSON-Schema `Tool` descriptors — imports **neither MCP nor any LLM SDK**, so the future in-app transport consumes the same objects; `call_with_media` returns `(json, image blobs)` and `call` is the JSON-only convenience over it. `serialize.py` = **the one place** engine values become JSON (naive-local datetimes get the site's real offset — never an implied UTC; Paths become store-relative or a basename, so no home-directory leak; `ToolResult.drop_keys` strips the chart arrays, 83% of a plan payload). `proposals.py` = the `m110.proposal/v1` envelope: `preview` runs the **pure** scorer twice so a before/after ranking can't be fabricated, `basis.store_state` fingerprints the data so a later apply path can detect drift, `apply.safe_write` is the allowlist seam. `vision.py` = in-memory FITS/TIF → JPEG for image critique (NOT `webexport.export_for_sharing`, which writes to disk). `skills.py` + `skills/<id>/SKILL.md` (the Claude Skill layout) served as MCP prompts **+** resources **+** a `get_skill` tool from one loader. `store.py` raises `StoreUnavailable` rather than a bare `FileNotFoundError` when the pinned data root is wrong. `mcp_server.py` = the only module importing `mcp`; it redirects `sys.stdout` → stderr **first** (13 bare `print()`s in the engine would corrupt the JSON-RPC stream). `client_config.py` = Claude Desktop config merge (Qt-free, so the Preferences button stays a thin widget). `outbox.py` = **the only writer** — create-only, one directory, name-sanitized, resolved-then-contained (so traversal/symlink escapes fail closed), quota'd; holds Tier-1 artifacts *and* staged proposal envelopes so the app has one queue. `apply.py` = **app-side only**, the sole caller of engine writers; a test asserts nothing the server can reach imports it, which is what keeps the proof airtight rather than merely narrower. Proven by a byte-identical manifest *outside the outbox*, write-syscall interception, a static AST denylist (+ a one-entry `SANCTIONED_WRITES` carve-out that is itself re-validated), and adversarial containment tests |
| `updates.py` | **in-app update check** (Qt-free, stdlib `urllib`; `feature/update-check`). `check()` fetches the GitHub `/releases` (not `/releases/latest` — the beta is a pre-release), picks the newest by PEP 440 (`packaging`), and compares to `current_version()` → `UpdateInfo{current,latest,url,is_newer}`; degrades silently offline (returns `None`). Throttle/prefs in `settings.json`: `update_check_enabled` (default on), `last_update_check` (`should_check`/`record_check` gate the launch check ~daily), `update_skip_version` (`skip_version`/`is_skipped`). `REPO` = the one repo constant. `about_dialog.app_version` delegates to `current_version` |
| `prioritize.py` | **deterministic target prioritizer** (`feature/prioritizer`, Qt-free) — ranks targets, replacing the hand-edited `priorities.toml`. Weighted sum of ~0..1 factors: **goal** membership · **urgency** (season closing, **× completion** so finished targets get 0 credit) · **completion** (strategy-shaped: capture-many ↔ go-deep) · **tonight** (transit alt + graded clear hours) · optional per-type weight. Pins compose on top (pin→top, deprioritize→excluded). **Type-aware deep threshold** via `build_derived.deep_threshold` (S50-calibrated: 90-min SNR floor, galaxies 240, nebulae 360). `build_contexts` (slow, astropy observability from the active site) is split from `rank` (instant), so the Planning UI computes contexts **once/day** (`write_contexts`/`load_contexts`/`is_stale` → `derived/prioritized.json`) and **re-ranks live** as the user moves the strategy/weight controls. `build_prioritized`/`refresh_prioritized`; `Weights` + strategy persist in settings. Degrades to goal+completion+pins with no site/astropy |
| `horizon.py` | local **horizon / obstruction mask** (`.hrz`/CSV parse + interpolation + 0/360 wrap; `load_mask`/`horizon_alt`/`is_obstructed`) + the **glow layer**: `effective_floor`/`is_below_floor` compose physical horizon with the light-dome floor as `max(physical, glow)` |
| `glow.py` | **light-dome glow floor** (`feature/glow-automap`, Qt-free). Builds an azimuth-dependent light-pollution floor from nearby towns: Walker's Law (skyglow ∝ population × distance⁻²·⁵) → per-town **domes** (peak alt + angular half-width; brighter/closer ⇒ taller/wider) → **upper envelope** `glow_floor(az)`. `build_glow_floor`/`compute_site_glow` (+ `haversine_km`/`bearing_deg`, hemisphere-agnostic), optional **Bortle** nudge (`_bortle_scale`) + a softer **narrowband** floor (`NARROWBAND_FACTOR`); emits an `.hrz`-format az/alt table (`glow_mask_text`/`write_glow_masks` → `<profile>.glow.hrz`). Towns from the bundled **GeoNames `cities1000`** subset (`load_towns` → `seed/geonames/cities1000.tsv.gz`, CC-BY 4.0 in NOTICE; `gen_geonames.py` builds it — **not `cities15000`**, which would drop the small nearby towns that dominate skyglow). Degrades to open sky if the data's absent. Scaling constants are calibration defaults |
| `goals.py` | **goals** = bundled catalogs **or** custom object lists, **per-store** in `.m110_internal_data/goals.toml` (`config.GOALS_TOML`, default Messier; `active = [...]` + `[[custom]]` blocks) — `active_goal_ids`, `set_active_goals` (persists the active set; a deactivation prunes via `catalog.remove_goal_members_from_library`; **no bulk seed** as of 5d), `goal_members`/`goal_name`/`list_goals` (unify bundled + custom), `create_custom_goal`/`edit_custom_goal`/`delete_custom_goal`. 5d retired the bulk goal-seed + `ensure_library_has_active_goals` |
| `pins.py` | **manual Pin/Deprioritize priority overrides** (#3 — the self-contained slice of the ROADMAP-1 auto-prioritizer, shipped ahead of the scorer so the Overview **Priority targets** section has a reason to exist for a fresh user). Per-store `.m110_internal_data/pins.toml` (`config.PINS_TOML`, `[pins]` slug→`"pin"`\|`"deprioritize"`; legacy `"mute"` read-mapped forward), Qt-free, additive/lazily-created, **survives derived regeneration** (not computed). `load`/`get_state`/`set_state`/`pinned_slugs`/`deprioritized_slugs`. Today's manual slice: **pin = always shown, deprioritize = hidden** (no season/rank logic until the scorer). Consumers: `pages/overview.py` (Priority targets is **pins-only** now — right-click Pin/Deprioritize on those rows + on the Manage-goals membership rows), Library right-click, each with a ▲/▼ marker |
| `seed/` | bundled `objects.toml` (object **reference**: id/type/mag/size/season + J2000 coords; 448 objects — Messier, Caldwell, RASC Finest, Best-of-Sharpless, Bennett, Lacaille; `season` derived from RA, coords/size/mag via Simbad at build time) · `catalogs/<name>.toml` (catalog membership `[members]` slug→designation): **messier, caldwell, rasc-finest, sharpless-best, bennett, lacaille** · `priorities.toml` (ships **empty** — header/schema comment + a commented example; fresh installs start with no priority targets so a stranger doesn't inherit hand-authored ones, mirroring 5d's empty `library.toml`). Generated by `tools/gen_caldwell.py` (Caldwell) + `tools/gen_catalogs.py` (the rest; idempotent, manages its own marked section in `objects.toml`) — both build-time only, runtime stays offline |
| `publish/` | **publishing engine** (item 8a; Qt-free, optional `publish` extra = jinja2+markdown). Publisher **registry** mirroring `processing.WORKFLOWS` (`PUBLISHERS`/`run_publish`/`enabled_target_ids`, `SETTING_KEY="publish_targets"`): `static-site` + `github-pages` available, `netlify` registered-disabled; `run_publish` runs targets in registry order and hands deploy targets `prior=` (the static-site result) so both enabled = one render. `site.py` renders Jinja2 `templates/*` (port of Astronomy `build_site.py`, real filenames) → a **local folder** from `derived.load_*()` + `build_images` derivatives + `objects` journals; **`ghpages.py`** (#27a, port of the Astronomy `deploy.sh`/ghp-import workflow) publishes the rendered folder to a `gh-pages` branch via the **system git** (scratch `--git-dir`+`--work-tree`, `.nojekyll`, git stderr → `PublishError`; `normalize_repo` owner/repo→SSH, `pages_url` → `https://<owner>.github.io/<repo>/`). **Two `DEPLOY_MODES`** (`PublishOptions.github_deploy_mode`): **`replace`** (default) = fresh single-commit orphan branch, force-pushed (ghp-import `-f`; lean repo forever, whole site re-uploads); **`incremental`** = `_fetch_tip` reads the deployed tip (**`--filter=blob:none --depth 1`**, falling back to plain shallow where filters are unsupported) + `update-ref` so the commit descends from it → the push sends **only changed objects** (verified 5-vs-17 in tests; web derivatives are content-hashed, so unchanged images are the same blob) at the cost of history that keeps superseded images. **Never `checkout`/`reset --hard`** in `deploy` — the work tree *is* the user's rendered site; the empty index + `add -A` makes the commit tree mirror the folder exactly (so sweeps propagate as deletions). The deploy repo **neutralises `core.excludesFile`** + uses `info/exclude` for OS junk only — a user's global `*.jpg` rule would otherwise silently strip the gallery (the ghp-import force-add lesson). Network git runs through **`_git_stream`** (streamed `Popen`: `--progress` stderr → `progress(done,total)`, a `status` stage-label channel, **no wall-clock timeout** — `_GIT_TIMEOUT` guards local plumbing only — and **cancel kills the process**, never leaving an orphaned transfer racing the next deploy); `select.py` = testable selection/privacy (`publishable_slugs`, `journal_visible`, `filter_*`); `images.py` reuses `build_images` for web thumb/full + the **three-level gallery filter** (`GALLERY_LEVELS` finished/device-stacks/all via `_image_tier`; explicit curation wins outright; `PublishOptions.gallery_level`, default "finished" — working files stay off the public site); `site.render` **sweeps stale output** (tracks emitted files; `_sweep_stale` deletes anything else under `img/`/`objects/` + unemitted optional pages — never on a cancelled render) so re-publishing with narrower options shrinks the folder *and* the deployed branch; `options.PublishOptions` (output_dir/sections/exclude_journals/site_title/gallery_level/github_repo/github_branch/github_deploy_mode); `errors.PublishDepsMissing` (degrade-gracefully). Per-object opt-out via `catalog.set_publish_flag` + journal `private` frontmatter |

**UI (`m110/ui/`)** — PySide6:

| Module | Role |
|---|---|
| `main.py` | **Shell**: left nav rail (`QListWidget`) → `QStackedWidget` of pages [**Library · Overview · Planning · Import · Processing**] — a 5-pane rail (**Planning** added post-beta for the session-planning arc; the pre-launch cleanup had merged Goals+Summary into **Overview** and absorbed Media/Journal/Sessions into the Library). **Library (grid) is the landing "home"**; a fresh empty store lands on **Overview** (welcome/CTA). `overview` page's `dirty` → `_do_refresh`. Global Ingest (Ctrl+I) + **Library** menu (Refresh Ctrl+R, Prepare working folders, Add object…, Fill missing metadata — bulk reference backfill, Enrich online… — bulk Simbad enrichment on a worker, Publish, Back up/Restore, Preferences Cmd+, — which folds into the macOS **app menu** by role) + **Help** menu (Check for updates… → `updates` via a worker, Report a problem… → `error_report`, About M110). A quiet **update banner** (`update_notice.UpdateBanner`) shows above the page stack when the throttled launch check finds a newer release. No separate "M110" menubar menu. On macOS the app-menu/dock name is set to "M110" via a best-effort NSBundle patch (`_set_macos_app_name`, needs `pyobjc-framework-Cocoa`; the durable fix is a packaged `.app`). `RefreshWorker` (scan→derive→render + `prepare_missing`) drives `page.reload()`; **auto-syncs** on launch / window-focus / after ingest. `open_object(slug)` routes any page's object link → Catalog + selects it. Overview's `go_to_import` (empty-state CTA) → `_open_ingest`. `main()` calls `logsetup.setup_logging()` + `error_report.install_excepthook(app)` (crashes → dialog+log, not abort) + `first_run_dialog.run_first_run_if_needed()` before the window (first-launch data-folder prompt). `_maybe_backup_nudge` (in `_on_refresh_done`) prompts a backup **once ever**, only once captures exist (`backup_nudge_seen` setting). Journal-edit lock disables nav + global actions |
| `widgets.py` | shared `NumItem` (sort-key cell), `status_label`/colors, `targets_for_slug`, `make_table`, async cached row-thumbnail loading (`ThumbnailLoader` + `RowThumbnails`, hero-backed; Library/Sessions/Processing row icons; `ThumbnailLoader.request(..., crop=)` supports both the row-icon aggressive crop and a milder "square" crop for bigger tiles), `paint_status_chip()` (the tinted-rounded-chip paint primitive, shared by `StatusPillDelegate` and the Library grid's `TileDelegate`), `CollapsibleSection` (the macOS disclosure-triangle collapsible group used across the Overview pane; `on_toggle` lets the owner persist open/closed state), `fit_table_height(tbl, max_rows=, half_row_pad=)` (size a populated table to `header + Σ row heights` + ½ row so it neither truncates a row nor leaves dead space; `max_rows` caps + turns on the scrollbar — the single fix for the beta table-height bugs, used by processing/overview/detail), **external-app launch helpers** (#19): `working_dirs_for_slug`/`can_process_slug`, `process_in_siril`/`process_target_in_siril` (single dir → launch, split sandbox → job-folder chooser, `launch.LaunchError` → reveal-folder fallback dialog), `open_in_default`/`reveal_in_manager` (`QDesktopServices`) |
| `image_grid.py` | reusable tile-grid component (`TileItem`/`TileModel`/`TileDelegate` — `QAbstractListModel` + `QStyledItemDelegate`), app-data-agnostic (no imports from `catalog`/`objects`/`derived`) so a future cross-object image browser can reuse it; the Library grid (`pages/catalog.py`) is the first consumer |
| `detail.py` | shared per-object `DetailPane`: header/status, hero (scales to pane), **Object Notes** **view/edit** (raw `journal.md` — the object's entry in the top-level Journal feed; labeled "Object Notes" to leave room for future Session/Processing Notes), gallery — **split into "Finished" / "Working files" groups** (#17; base tier = finished/ folder vs stacks/seestar, overridden per-image by `objects.get_curation`), double-click → image viewer (items carry a global index so the viewer navigates across both groups + `_gallery_meta()` display metadata — Source/Date/Size always, Integration/Filter when unambiguously derivable; compact center-cropped-square contact-sheet grid via `_square_icon()`, elided filenames with a full-name tooltip); **right-click a tile → Set as hero** (writes `hero` frontmatter + `build_images.rebuild_hero`, emits `saved`) / **Mark as finished\|working** (`objects.set_curation`, in-place regroup) / **Export for sharing…** (`export_dialog`) / **Open in default app**\|**Reveal in file manager** (#19, `widgets.open_in_default`/`reveal_in_manager`) — the **same menu is on the hero image** (`_run_image_menu`, acting on the hero's *source* via `build_images.hero_source_path`), **Import finished work** + **Process in Siril** + **Reveal working folder** buttons (#19), + per-object **Processing** + **Sessions** tables and an **Object details** block (type/mag/size/season, RA/Dec in decimal + sexagesimal, filter rule, slug, capture targets, **Remarks** = the library `notes` field). Shows real filenames |
| `pages/catalog.py` | the **Library**: a table view (Object/Name/Type/Season/Mag/Size/Filter/Status/Integration/Sessions; Object shows all identifiers via `catalog.object_identifiers`, e.g. "C20 (NGC 7000)") **and** a **grid view** (`image_grid.TileModel`/`TileDelegate`, one tile per object — hero + id/name + status chip + integration), **and** a **Feed view** (embeds `JournalPage` — the reverse-chron object-card feed, absorbing the old Journal pane), selected by a **three-way List·Grid·Feed segment** (`_view_btns`, persisted; **grid is the default home view**) + a zoom `QSlider` in a `QStackedWidget`; the object views build from one shared `_current_items()`/filter pipeline so search/catalog-filter/captured-only and selection stay in sync + a **Catalog filter** selector (All / Messier / Caldwell …) + **search** + captured/deep/total/**integration** **stat row** (per-filter; the compact Library header strip). Both segments share **one control row** (Deep sky·Media left, List·Grid·Feed right), each a **joined segmented control** (`_make_segment` → `#segControl`/`#segButton` QSS); the view segment lives here (not on the hideable catalog-filter row) so it can't shift in Feed mode, and it hides in Media scope. A top **Deep sky · Media segment** (`_scope_stack`) switches the whole page between catalog objects and an embedded `MediaPage` (absorbing the old Media pane); routing to an object forces the Deep-sky scope + a selectable view. Hosts the shared `DetailPane`; `select_object`/`reload` work identically regardless of active view; per-object import flow; **right-click → "Fill in missing metadata"** (reference) + **"Enrich online"** (Simbad, on a worker; `OnlineLookupError`→dialog) + **"Remove from Library"** (`catalog.remove_library_entry`; confirm, non-destructive) + **"Pin as priority" / "Deprioritize"** (`pins.set_state`, #3 — a ▲/▼ marker on the Object cell/tile via `_pin_marker`; `pins_changed`→shell lightweight reload) + **"Process in Siril"** (#19, shown when the object has a working folder → `widgets.process_in_siril`); edit-lock |
| `pages/overview.py` | **Overview** — the landing dashboard, merging the former Summary + Goals pages into one pane of **collapsible sections** (`widgets.CollapsibleSection`, the macOS disclosure-triangle pattern; each section's open/closed state persists across launches via settings `overview_sections`). Sections (in order): **Goals** (progress hero) · **Priority targets** (`_priority_rows`: **manual pins only** — the legacy `priorities.toml` source was dropped since the auto-prioritizer isn't shipped; carries an "in development" caption; right-click Pin/Deprioritize via `pins_changed`) · **Integration Time and Sessions** (per-target integration table + a "Last 5 Sessions" table + a "View all sessions…" button → `SessionsPage` in a dialog) · **Goal checklists** (per-active-goal membership tables, green check per Captured/Deep) · **Progress by category** · **Manage goals** (goal *setup* demoted here, wrapped in a bordered `#manageGoalsBox` frame since it's the one non-table section: activate/deactivate catalogs + custom-goal CRUD, nested collapsible hemispheres; → `goals.set_active_goals`, emits `dirty`). Tables sized via `widgets.fit_table_height`. **Empty store** → welcome card + "Import images…" CTA (`go_to_import`) + Manage goals so a new user can pick a catalog. Object rows → `open_object` |
| `pages/processing.py` | Siril queue grouped by status; a **"Ready to import"** group (targets with unimported Siril output — `derived` `ready_for_import` flag, set via `siril.has_unimported_output`) takes precedence over the status groups; **Up to date** is not shown (nothing to do). Columns: Object/Raw integ/In stack/Rejected/+ new/Latest stack/Last capture/**Notes** (the Star-removal column was dropped). Tables use `widgets.fit_table_height`; rows → `open_object`; **right-click a row → "Process in Siril"** (#19, per-target via `widgets.process_target_in_siril`, shown only when that target has a sandbox) |
| `pages/sessions.py` | capture-session log (sortable table Date/Object/Frames/Exp/Filter/Integration/Mount, default Date-desc) + search box; from `derived.load_sessions()`; rows → `open_object`. **No longer a nav pane** — opened in a dialog from Overview's "View all sessions…"; per-object sessions live in the `DetailPane` |
| `pages/journal.py` | reverse-chron **feed** of object cards (header · hero · status/stats · rendered notes) — every captured object + any noted-but-uncaptured; ordered by latest image mtime (reprocess re-orders); search box; cards → `open_object`. **No longer a nav pane** — embedded as the Library's **Feed** view |
| `pages/media.py` | **Media** browser for non-catalog `Media/<Category>_photo\|_video/` (ingest already captures it): per-category sections — photo gallery (double-click → image viewer) + video rows (Open → OS player); search box; read from `media.scan()`; `show_title` flag. **No longer a nav pane** — embedded as the Library's **Media** scope |
| `pages/planning.py` | **Planning** pane — session-planning home. A **location selector** (`planning_config`, sets `active_site_profile`); the **Priority targets** table = the **prioritizer ranking** (`prioritize.load_contexts` → `rank`) with a **Strategy** toggle + **Tuning weights** spinboxes (persisted; re-rank the cache **instantly**) + **Recompute**; a **Plan a night** section (date picker → `_PlannerWorker` runs `planning.plan_night` over the top-ranked candidates → summary + an ordered target table with include-checkboxes + Move up/down + the **`NightTimeline`** altitude chart → **Save field guide** via `fieldguide`); a **Saved field guides** browser (list + View `FieldGuideDialog` / Reveal / Delete); and a **Manage site profiles** collapsible hosting `SiteProfileEditor`. Both astropy workers (`_PrioritizerWorker` on `ensure_ranking`, `_PlannerWorker` on Generate) fire **only** on explicit actions — never from construction/reload — so offscreen tests don't spawn/leak them. Right-click Pin/Deprioritize; rows → `open_object`. **Sequencer UI (#40–42):** a **Targets** spinbox (default 4) sizes the slots and re-sequences the cached plan instantly; the plan table shows the **schedule** (Object·Start·Duration ⚠·Alt·Moon); move up/down **reflows** via `forced_order`, unchecking **excludes** + reflows; the plan's `day` rides in `_plan_meta` (the field-guide save stamps the computed night, never the widget) and a date/location change **invalidates** the stale plan (the #36 desync fix) |
| `night_timeline.py` | **altitude-vs-time chart** (`feature/session-planner`) — `NightTimeline(QWidget)` paints each planned target's altitude curve across dusk→dawn (from its `samples`), the min-alt floor line + axis ticks; theme-token colors, repaints on theme change |
| `field_guide_dialog.py` | **field-guide viewer** — `QTextBrowser.setMarkdown` renders a saved `Plans/*.md` (Qt-native, no dep) + Copy/Close |
| `site_profile_editor.py` | **site-profile editor** form (`feature/planning-profiles`) over `planning_config` writers: name/lat/lon/elev/timezone + Bortle/SQM + **Import** horizon `.hrz` (`import_horizon_mask`) + **Compute light-dome…** (`glow.compute_site_glow`/`write_glow_masks` — Walker's-Law floor from nearby towns, radius-adjustable) + **Look up location…** (online `geocode`) + New/Save/Delete (default protected). Emits `saved`/`created`/`deleted`; the Planning page reloads the selector on each |
| `update_notice.py` | **update-availability UI** (`feature/update-check`) over `m110.updates`: `UpdateCheckWorker` (QThread launch/manual check) + `UpdateBanner` (quiet dismissible strip — Download · Skip this version · ✕) + `show_manual_result` (Help → Check for updates dialog) |
| `ingest_dialog.py` | source selector (staging=move / Seestar=copy), **per-object grouped + checkbox-selectable** preview (Object · Kind · Files · Size · Pointing · → dest; select all/none; live size total), **name canonicalization + RA/DEC pointing check with a remap dropdown** (#12), threaded scan→group→annotate & apply behind modal progress+Cancel (applies only checked/retargeted groups). Shared workers/helpers reused by `pages/import_page.py` |
| `pages/import_page.py` | the **Import page** (6a) — pick any source dir (device/Recent/Browse) → recursive `scan_directory_plan` → the grouped/selectable preview → gated copy. Hosts the **holding-area (6c) panel**: unclassifiable files land in `Inbox/`, listed per source folder with Object/Kind pickers + a per-row **Actions** cell — **Assign** (route into the collection), **Reveal** (open the `Inbox/<folder>` in the OS file manager via `QDesktopServices`), **Discard** (confirm → `ingest.discard_holding`, Inbox-scoped delete + empty-dir prune). **Bulk assign (#33):** the holding table is row-multi-select with a bulk bar ("Selected → Object · Kind · Assign N selected") that routes every selected row to one object/kind via one `_ApplyWorker`. **Identification aids (#26):** `ingest.annotate_holding` reads one FITS header per held group → the Object/Kind pickers are **pre-filled with the suggested identity** (OBJECT header → slug, else nearest catalog object by RA/Dec) + kind (IMAGETYP); **double-click a row → `HoldingInspectDialog`** (header facts + thumbnail preview + suggestion) |
| `holding_inspect_dialog.py` | **holding-area file inspector** (#26): read-only look at a held file — FITS-header facts (OBJECT/IMAGETYP/FILTER/RA·Dec decimal+sexagesimal) + a rendered **thumbnail** (`build_images._open_image` → QPixmap; degrades to no-thumb) + the suggested identity. Opened by double-clicking a holding row |
| `import_dialog.py` | **Import finished work** preview (detected renders/stacks, hero pick, cleanup choice) → threaded `apply_import` behind modal progress+Cancel |
| `add_object_dialog.py` | **Add object** dialog (5c): type a name/designation → instant offline reference resolve into an editable preview + **"Look up online"** (Simbad, worker thread) → `catalog.add_library_entry`; preview-then-confirm; emits `added(slug)` |
| `image_viewer.py` | `ScalableImage` (pixmap that refits on resize — used for the hero) + `ZoomableImage` (`QScrollArea`-based Fit/explicit-zoom + click-drag pan) + `ImageViewer` (full-frame gallery viewer: Prev/Next, ←/→/Home/End, zoom toolbar, toggleable metadata overlay, **⤓ Export…** button → `export_dialog`, Esc). Accepts `(name, path)` tuples or `{"name","path","meta"}` dicts; app-data-agnostic (metadata content built by callers; `export_dialog` is lazy-imported so the module stays engine-only) |
| `export_dialog.py` | **Export-for-sharing dialog** (`ExportShareDialog`, `feature/image-export`) over `webexport`: a **Max size** spinbox + **No maximum** checkbox + lossless/quality strategy radios; **Export…** → the **native OS save panel** (`QFileDialog.getSaveFileName`, native — rename/relocate) pre-filled with `suggested_name` (`[Object]-[maxsize]-[YYYYMMDD]`), then a threaded `_ExportWorker` runs the ladder behind a busy `QProgressDialog`+Cancel (status = the ladder step trail; `_finish_worker` **waits** the thread before `deleteLater` — else ~QThread SIGSEGVs on teardown); success → summary + Reveal/Open. Entry points: detail-pane gallery right-click + the hero image ("Export for sharing…") + the image viewer's ⤓ Export…; last strategy/max-MB/no-max/dir persist in settings |
| `mcp_details_dialog.py` | **MCP connection details** — the client-neutral half of the assistant setup. The server is plain MCP over stdio, so this offers the same connection in the three shapes clients ask for (a `mcpServers` JSON block · command+env · the `claude mcp add` line), each with Copy, over `client_config.connection_details()`. Preferences keeps a one-click path for Claude Desktop only because its config is a JSON file M110 can merge into safely — not because it is the only supported client |
| `preferences.py` | choose data folder (save + restart) + **"Prepare objects for processing in:"** workflow checkboxes → `processing_workflows` + **"Processing tools"** → Siril application path (`external_app_paths.siril`, override for `launch.find_app`; placeholder shows the auto-detected path; #19) + **"Finished-image hints"** editable keyword fields (finished / intermediate) → `hints.set_hints` (#17) + **Import** → "Import per-sub JPG previews" checkbox → `import_sub_previews` (#25) + theme + **Updates** → "Check for updates on launch" → `updates.set_check_enabled` + **AI assistant** → Connection details… (any MCP client) · Set up Claude Desktop… · Disconnect · "save plans straight to Plans/" (`assistant_direct_save`). **The settings column scrolls and every explanatory label wraps** — the dialog outgrew a laptop screen, and both overflows showed up as text with a line sliced off rather than an obviously-too-small window (vertical: Qt squeezes wrapped labels below `heightForWidth`; horizontal: one *unwrapped* label's single-line width becomes the dialog's minimum width). `test_no_explanatory_text_is_cut_off` guards both. (Goal management lives in Overview → **Manage goals**.) |
| `publish_dialog.py` | **Publish / share** dialog (item 8a, off the Library menu): section checkboxes + global "exclude journals" + target picker (`publish.PUBLISHERS`, "(soon)" for disabled) + a **Repository field + Uploads mode combo under GitHub Pages** (`owner/repo` or git URL, persisted `publish_github_repo`; replace ↔ incremental, persisted `publish_github_deploy_mode`, default replace — both live only while that target is checked) + a **gallery-level combo** under Image galleries (finished / +device stacks / all; `publish_gallery_level`, default finished) + site-title + output-folder chooser → threaded `_PublishWorker` running `publish.run_publish` behind modal progress+Cancel (stage labels via the worker `status` signal — "Rendering site…"/"Uploading to GitHub…" — the bar resets per stage; a user cancel closes quietly, and the engine kills the git push so teardown can't beach-ball); **Save** persists every choice without publishing; "Open folder" (+ "Open site" with the pages URL after a GitHub Pages deploy) on success |
| `backup_dialog.py` | **Back up Library** dialog (item 10, Library menu): destination **pre-seeded from the saved setting** (Browse overrides ad-hoc; a run saves it back) + snapshot-status line + Automation/retention group (auto on · interval · **Back up now** beside the toggle · keep-N snapshots (default all) · min-free-GB (default 100); no age-based "older than N days" policy — it would wipe history after a gap in use) → threaded `_BackupWorker` running `backup.create_snapshot` behind modal progress+Cancel; bottom buttons are **Save**/**Cancel** (Save persists settings without running a backup) + **Restore…**; "Open folder" on success |
| `restore_dialog.py` | **Restore from backup** dialog (item 10): snapshot picker (by date) + a checkable file **tree** (from the snapshot manifest) + restore target (**extract to a folder** default, or **into the store** behind a create-vs-overwrite conflict preview + confirm) + **Verify integrity** (`backup.verify`); threaded `_Worker` (shared by verify + restore) behind modal progress+Cancel |
| `about_dialog.py` | **About M110** dialog (UI Phase 4 branding; Help menu, `AboutRole` so macOS folds it into the app menu): theme-recolored logo + tagline ("Complete the catalog.") + version (`importlib.metadata`) + Apache-2.0 line |
| `error_report.py` | **global error handling + crash/report flow** (the beta crash-reporting arc). `install_excepthook(app)` (called in `main()`) replaces PySide6's abort-on-uncaught-slot-error with: log the traceback, show `ErrorReportDialog` ("M110 hit a problem", copyable report + prefilled GitHub new-issue via `issue_url`), and **return without aborting**. Worker-thread exceptions marshal to the GUI thread (`_Dispatcher` queued signal); re-entrancy-guarded. `build_report(exc_info=)` = env (version/OS/Qt/data-root/log) + traceback + log tail. Same dialog (non-crash) backs **Help → "Report a problem…"**. `REPO_URL` is the one knob to change when the public repo name is settled |
| `first_run_dialog.py` | **first-launch welcome / data-folder prompt** (onboarding). `run_first_run_if_needed()` (called by `main()` before the window): when `config.is_first_run()` (no env, no saved pref, no store at the default), shows `FirstRunDialog` (branded welcome + a data-folder field pre-filled with the default + Browse + "Get started") → persists the choice (`save_data_root`) + bootstraps (`ensure_data_root`); cancel falls back to the default. Persisting the pref means no re-prompt next launch; a returning user (existing default store) is never prompted |
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
  **User-facing changes also get their [`CHANGELOG.md`](CHANGELOG.md) `[Unreleased]`
  entry in the same PR** — written for a *user* (what they'll notice), not a
  contributor; the engineering detail belongs in [`DONE.md`](DONE.md).
  `tools/release.py` only *moves* `[Unreleased]` into a dated section and
  hard-fails when it's empty ("the script moves them, it can't author them"), so
  leaving the prose to release time is what made the changelog trail both
  0.1.0-beta.3 and 0.2.0-beta.1.
- **Full disclosure on user-facing security bugs.** M110 is open source, so a
  security fix that affected users is **disclosed plainly** in
  [`CHANGELOG.md`](CHANGELOG.md) under a `### Security` section — never buried in a
  vague "hardening" line, and never omitted because the bug was ours. Name the
  **vector** and the **real impact** in the user's terms (e.g. "a crafted capture
  file could write outside your data folder — an object name from a FITS `OBJECT`
  header went into the destination path unsanitized"), and link the assessment
  behind it ([`docs-archive/SECURITY_ASSESSMENT.md`](docs-archive/SECURITY_ASSESSMENT.md)).
  **Calibrate honestly in both directions:** don't soften real exposure, and don't
  inflate it either — if an advisory is in a code path M110 never exercises, say so
  (that's calibration the reader needs, not spin). Users decide what the risk meant
  for them; the changelog's job is to give them the facts to decide with.
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
  (Simbad lookups for Add object / Enrich online — from **source**, runtime stays
  offline unless installed; the online actions degrade gracefully via
  `OnlineLookupError`, whose "not installed" message is build-aware). **Packaged
  builds bundle astroquery** — the `build` extra self-references `m110[online]` so
  `pip install -e '.[build]'` pulls it, and the three specs `collect_submodules`/
  `collect_data_files`/`copy_metadata` it (+ pyvo/keyring), since a frozen app user
  can't add the extra themselves (issue #64). The specs **also `copy_metadata("astropy")`**
  — astroquery calls `minversion('astropy')` at import, which reads astropy's dist-info,
  so without it the frozen Simbad import dies with `KeyError('astropy')` even though
  astropy's *modules* are bundled; planning never version-checks astropy, so it works
  while enrich breaks (issue #74). **`hook-astropy` also `collect_data_files("astropy.units.
  format", include_py_files=True)`** — astropy's PLY unit parser needs its `generic_parsetab.py`/
  `lextab.py` tables as **files on disk**, not just PYZ modules; missing, `import astropy.units`
  dies on the first unit parse and *every* coordinate transform fails (planning + prioritizer
  show "astronomy engine unavailable"; astroquery can't load either — issue #75). **Validate
  frozen-app fixes against a real PyInstaller build, not a PYZ reconstruction** — a
  loose-`.py` reconstruction hid this (the parsetab existed as a file there). Dev = pytest
  (+ astroquery for `tools/gen_caldwell.py`). Declared in `pyproject.toml`.

---

## Testing

```bash
pytest -q                 # all
pytest -q tests/test_ingest.py
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # (won't render, but imports/constructs)
```

581 tests, all fixture-based. The **UI is driven offscreen with pytest-qt**
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
#15). The UI settled into a **5-pane nav rail** — **Library · Overview · Planning ·
Import · Processing** (Planning added post-beta) — after a pre-launch 8→4 IA cleanup (Summary+Goals merged into
**Overview**; Media/Journal/Sessions absorbed into the **Library** as a Deep-sky/Media
scope, a List/Grid/Feed view segment, and the object detail pane). A second device,
the **DwarfLab Dwarf 3**, is supported (header-driven ingest + a `dwarf` layout).
**Import #16 (item 6)** is substantially done — 6a–6c (any-directory
recursive source, FITS-header classification + layout registry, holding-area manual
assign); 6d (lazy device-under-target) deferred until a 2nd device exists. **Publishing
(item 8a)** landed: a Qt-free `publish/` engine + Library → Publish / share… exports a
selective static site to a local folder **and/or straight to GitHub Pages**
(system-git force-push to `gh-pages`; Netlify / other targets deferred).
**Session planning (item 1 + 2) shipped** — the Planning pane (prioritizer ranking + strategy/weights, site profiles w/ horizon+glow, the night sequencer + field guides), tuned release-ready via two ground-truth reviews (see `docs-archive/`). **Next:** remaining post-MVP items (assistant, publishing targets, 6d multi-device). Foundational
decisions in brief: open-source / Developer-ID distribution (not App Store);
PySide6 over a headless engine; processing is prepare-and-guide, not direct Siril
control.

---

## Gotchas / lessons learned

- **On macOS, launch Siril via `open` (LaunchServices), NOT a direct `Popen` (#19).**
  Siril bundles its own **hardened-runtime, library-validated** Python
  (`Siril.app/Contents/Frameworks/Python.framework`, signed team `SW3D6BB6A6`). That
  Python only runs when the **responsible process** is Siril itself. A direct child-process
  launch (`Popen [.../MacOS/siril, -d, dir]`) leaves **M110** as the responsible process,
  so the moment Siril spawns its Python macOS SIGKILLs it — Siril reports "unable to spawn
  python" / "Python version check failed" (reproduced: the framework python is `Killed: 9`
  even from a clean-env shell, `env -i`; it is NOT an environment problem). `open -a
  Siril.app` makes Siril its own responsible process (the Dock/Finder context), so its
  Python works. `launch._launch_macos` therefore runs `/usr/bin/open -a <bundle> --args -d
  <dir>` with a sanitized env (`open` forwards *its* env to the app, so `_child_env` still
  keeps our venv out). Trade-off: LaunchServices honors `--args -d` only on a **cold
  start** — if Siril is already open, the working dir isn't changed (user sets it, or uses
  Reveal working folder). Siril *does* accept `-d <working_directory>` (verified for `siril`
  + `siril-cli`); the reason we don't `Popen` it directly is the signing context, not the
  flag. Non-macOS keeps the direct `Popen`. Auto-detect paths are only exercised on macOS +
  in tests — **verify Linux/Windows locations on real machines**. Degrades to
  reveal-the-folder when the tool isn't found.
- **Also don't leak our Python env into launched tools (`launch._child_env`).** Secondary
  to the responsible-process fix above, but still correct defense-in-depth: strip
  `_PY_LEAK_VARS` (`VIRTUAL_ENV`/`PYTHON*` + PyInstaller `_MEI*`), restore bundle library
  paths from `<VAR>_ORIG` (else drop them), and remove the venv's bin from `PATH` (only when
  actually in a venv/frozen build — never a shared system bin). Passed to both `_spawn` and
  the macOS `open` (which forwards its own env to the app). Every launched tool inherits
  this. (During debugging, sanitizing the env alone appeared to move Siril *past* the
  version check — but the framework Python is SIGKILLed even with `env -i`, so the real
  fix was launching via `open`; keep both.) If Siril still reports the Python error *and*
  it also fails launched from the Dock, that's a Siril-side venv setup issue (its Get
  Scripts → "Reset python venv") — not ours.
- **Also strip our bundled-Qt discovery paths (`_QT_LEAK_VARS`) — the two-Qt crash.** When
  M110 is **frozen**, the PyInstaller PySide6 runtime hook exports `QT_PLUGIN_PATH` /
  `QML2_IMPORT_PATH` into `M110.app/Contents/Frameworks` (and prepends `_MEIPASS` to
  `DYLD_LIBRARY_PATH`). `open` forwards our env to Siril, whose `sirilpy` scripts ship their
  **own** PyQt6 — so Siril's Python loaded *M110's* cocoa platform plugin next to PyQt6's,
  pulling **two QtCore/QtGui frameworks into one process** → objc duplicate-class warnings,
  "loading two sets of Qt binaries", "Could not load the Qt platform plugin cocoa", then
  SIGABRT (signal 6). Reported 2026-07-18 from a packaged build. `_child_env` now drops
  `_QT_LEAK_VARS` (`QT_PLUGIN_PATH`/`QT_QPA_PLATFORM_PLUGIN_PATH`/`QML*_IMPORT_PATH`); the
  DYLD half was already cleared via `_LIBPATH_VARS`. Only bites the **frozen** app (from
  source those vars aren't set), so it can't be caught by a dev-run — regression-test the
  env sanitizer, not a live launch.
- **FITS extensions: `.fit` AND `.fits`.** Seestar/the Astronomy port use `.fit`;
  the Dwarf 3 (and most other rigs) write `.fits`. Any new extension check must go
  through `config.FIT_EXTS`/`config.is_fits_file` — never a bare `endswith(".fit")`
  (which silently excludes `.fits` — this once diverted every Dwarf sub to
  `working_files/` and produced zero sessions).
- **Don't parse device filenames for session facts — read the header.** Filename
  conventions are per-device (Seestar `Light_<obj>_<exp>s_<filt>_…`, Dwarf
  `<obj>_<exp>s<gain>_<filt>_…`); `scan_sessions` derives `(date, exp, filter)` from
  the FITS header (`DATE-OBS`/`EXPTIME`/`FILTER`) with the Seestar filename only as a
  fast path. Add device support in `ingest._classify_*` + the header path, not by
  extending a filename regex.
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
- **The real Siril stack often lives in `working_files/`, not `stacks/`.** The
  ingest lights-guard diverts any non-sub `.fit` (a stack or a processing product —
  they carry a `NxEXPsec`/`_processed` token) into `working_files/`, so the
  authoritative stack FITS (STACKCNT/LIVETIME/DATE) frequently ends up there. Both
  `build_derived.read_latest_stack_metadata` (root/stacks first, then
  `working_files/`) and `build_images.discover_images` (gallery, filtered by
  `_is_intermediate_fit`) look there — without this, finished-render-only objects
  showed a blank "In stack" and an mtime-inflated "+ new" (the M10 case). Reading
  where the stack *is* fixes existing libraries with no re-import; a proper
  classification fix (route the stack → `stacks/`, `_processed` → `finished/`) is a
  separate, deferred change.
- **`QT_QPA_PLATFORM=offscreen` cannot validate macOS-style painting.** Offscreen
  falls back to the **Fusion** style; force the real `macOS` style there and it
  renders *nothing* — text, checkboxes, everything comes out blank. So an offscreen
  "the widget doesn't paint" result is **meaningless**, and offscreen green says
  nothing about how the native style paints. To check real macOS painting, run a
  **real cocoa** window (no `QT_QPA_PLATFORM`) and `render()` into a QPixmap — and
  size the pixmap to *all* the rows you care about, since a short render silently
  crops the very rows that would show the bug. Corollary: styling gaps that only
  bite under QMacStyle (see the item check-indicator entry in `DONE.md`) can't be
  regression-tested by painting — assert on the generated QSS instead.
- **Item check indicators are stylesheet-drawn on purpose.** The
  `QTableView::indicator` rules in `theme/qss.py` are load-bearing: without them
  QMacStyle paints a check indicator only for the *current* row and every other row
  goes blank (clicks still toggle, invisibly). Don't drop them, and keep an
  `image:` glyph on `:checked` — a stylesheet indicator draws no checkmark of its own.
- **Never validate rendering/refresh against a live data root.** (A render
  pointed at the wrong root once clobbered a real `images.json`.) Use a temp
  copy or a throwaway root.
- **Capturing UI screenshots — render offscreen, don't drive the live app.** For
  marketing/site screenshots (or any "show me the UI" grab), skip computer-use
  entirely: it's deterministic, needs no window management/coordinate mapping, and
  writes nothing. Recipe: `QT_QPA_PLATFORM=offscreen`, build `MainWindow()` against
  a data root, **set `win._ready = False`** (neuters the deferred launch refresh so
  it can't write to the store — this is what makes rendering against the *live* store
  safe/read-only — **and** the launch **update-check** network thread, so a short-lived
  script doesn't exit with a running `QThread` → SIGABRT → a macOS "Python quit
  unexpectedly" dialog; both launch workers gate on `_ready`), pump `app.processEvents()` in a loop for a few seconds so the
  **async thumbnail/hero loaders** populate, then `win.render(pm)` into a QPixmap with
  `setDevicePixelRatio(2)` for 2× retina crispness. Navigate with
  `win.nav.setCurrentRow(win._overview_index)` / `win.open_object(slug)`; widen
  `win.catalog.splitter.setSizes([...])` for a hero-focused detail shot; and
  `win.statusBar().hide()` so the local data-root path isn't baked into the image.
  Site assets are 1240×780 (render at 2× → 2480×1560), re-saved as progressive JPEG
  (~q82) into `site/assets/shot-*.jpg`.
- **Changing the data root: Preferences saves + prompts restart by design.**
  (Engine modules now read `config.*` paths dynamically — import-time path
  binding was removed in #13 — so `config.set_data_root()` is reliable in tests;
  the restart is just the simplest UX, not a hard requirement anymore.)
- **Cross-thread Qt:** workers communicate via signals; never touch widgets
  from a worker thread. Cancellation uses a `threading.Event` set by the
  progress dialog's `canceled` signal.
- **Drain background workers before Qt tears down — or the process segfaults.**
  An async task still running when Qt is destroyed runs native code against a
  half-gone Qt and crashes on a worker thread. Two forms bit us: a `QThread`
  `deleteLater`'d before it finished (export dialog — `_finish_worker` now
  `wait()`s), and `ThumbnailLoader`'s decodes on the **global `QThreadPool`**,
  which was never drained (`widgets.drain_thumbnail_pool()` = `waitForDone()` now
  runs on `aboutToQuit` and after every test via an autouse conftest fixture).
  This was the intermittent **CI SIGSEGV (exit 139) that "passed on re-run"** — a
  thread-timing race, not a test failure; a green re-run never cleared it. Don't
  "fix" a QRunnable lifetime by holding a Python ref + `setAutoDelete(False)`: a
  QRunnable isn't a QObject, so PySide can't track a pool-side delete → double-free.
  Drain instead.
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
tools/                  dev utilities (release.py → one-command release cutter;
                        make_test_corpus.py → synthetic manual-test store;
                        smoke_mcp.py → drive the assistant MCP server over real
                        pipes with no AI client, to tell "server broken" apart
                        from "client can't find it")
packaging/              native installers: common/ (shared PyInstaller entry shim +
                        astropy hook override) · macos/ (.app→sign/notarize→.dmg) ·
                        linux/ (onedir→AppDir→AppImage) · windows/ (onedir→.ico→Inno Setup)
site/                   m110.space landing page (static; Cloudflare Pages, deploy dir = site/)
.github/workflows/      ci.yml (pytest on push/PR) · release.yml (build Linux+Windows on tag)
.github/ISSUE_TEMPLATE/ + PULL_REQUEST_TEMPLATE.md  contribution templates
pyproject.toml          deps + entry point (gui-script: m110); [build] extra = pyinstaller
README.md               user-facing README (what it is / download / features)
CLAUDE.md               this file
ROADMAP.md              canonical roadmap (open/active work + decisions)
DONE.md                 archive of shipped work (how/why it landed) — read when touching an existing subsystem
TESTING.md              manual / regression test runbook
BUGS.md                 open issues + improvement backlog
docs/                   user guide (linked from the app Help menu + the website)
docs-archive/           point-in-time records (the planning tuning arc: PLANNING_ROADMAP,
                        the two ground-truth reviews)
CONTRIBUTING.md · CODE_OF_CONDUCT.md · SECURITY.md · CHANGELOG.md   OSS project docs
LICENSE / NOTICE        Apache-2.0
.venv/                  local virtualenv (gitignored)
```

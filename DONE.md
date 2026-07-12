# M110 — Shipped work (archive)

Completed milestones, moved out of [`ROADMAP.md`](ROADMAP.md) to keep the roadmap
scannable. **ROADMAP.md** tracks open/active work + decisions; **this file** is the
chronological record of what shipped. Section/item numbers match their original
ROADMAP slot so cross-references (`item 5`, `item 0`, …) still resolve.

---

## MVP (v0.1) — "the Library"

| Step | Status | What |
|---|---|---|
| 0.1a | ✅ | engine package + read functions (config, catalog, derived, objects) |
| 0.1b | ✅ | read-only Library: capture-status table (natural M/NGC sort) + object detail/gallery |
| 0.1c | ✅ | in-app **Refresh** (threaded) — ported scan_sessions + build_derived |
| —    | ✅ | **Own data root** (`~/Documents/M110`) + bootstrap/seed + Preferences + Seestar mount detection |
| —    | ✅ | **Image rendering** port (build_images: thumbnails / heroes / images.json, cached) |
| 0.1d | ✅ | **Ingest** — preview-then-confirm; sources: staging (move) + mounted Seestar `MyWorks` (copy); threaded + cancellable |
| —    | ✅ | **Two-axis data store** (BUGS #13) — `Objects/` (catalog axis) + `Images/` (capture-target axis), hidden `.m110_internal_data/`, in-place idempotent migration. Landed *before* 0.1e/0.1f so both build on the final layout |
| 0.1e | ✅ | **inline journal editing** — Edit/Save/Cancel the raw `Objects/<id>/journal.md` in the detail pane (table + actions lock while editing) |
| 0.1f | ✅ | **processing-prep round-trip** — prepare a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks + Naztronomy preset by frame count + guidance), set up **automatically on ingest**; then **import finished work** (renders→`finished/`, stack→`stacks/`, hero pick) and clean the sandbox up. Detail-pane entry points |


---

## Later phase 0 — Site-parity multi-page UI *(done)*

   Brought the app to functional
   parity with the published static site's pages. Left **nav rail + stacked
   pages**, Summary as the landing page, one shared Object detail reachable from
   every object link. **Phase 1 done:** shell + **Summary** + **Processing**
   (Catalog = the relocated Library). **Phase 2 done:** **Sessions** (sortable log   + search) + **Journal** feed (reverse-chron object cards by latest image
   activity); `derived.load_sessions()` added.
   **Phase 3 done:** Object view enriched (per-object Processing + Sessions tables + Catalog-details block) + Catalog parity (Size/Filter columns, search box,
   captured/deep/total stat row). **Site-parity multi-page UI complete.** All
   backed by existing derived data; only `derived.load_sessions()` was net-new.
   **Plus a Media page** (BUGS #11) — browses non-catalog `Media/` (photos →
   viewer, videos → OS player) via a new Qt-free `media.scan()`.

---

## Later phase 1 — Session planning: **Checkpoint A** *(done 2026-07-12)*

The first shippable checkpoint of the session-planning arc (ROADMAP item 1) —
**site profiles + light-dome + deterministic prioritizer + tuning UI** — landed as
a stack of four feature branches (`feature/planning-profiles` → `glow-automap` →
`prioritizer`; the independent update-check side task shipped separately in beta.2).
Checkpoints B (session planner + plan-file emit) and C (assistant) remain open.

- **Planning nav pane + site profiles** (`feature/planning-profiles`). A 5th nav
  pane (**Library · Overview · Planning · Import · Processing**) surfaces the
  previously-headless planning engine. Location profiles are conceptually
  subordinate to planning, so they live here (not a standalone pane): a **location
  selector** (persisted `active_site_profile`), a priority-targets table, and a
  **Manage site profiles** editor. `planning_config` gained *writers*
  (`save_site` / `delete_profile` / `import_horizon_mask` / `active_profile` /
  `set_active_profile` / `load_active_site` + hand-written `format_site_toml`, no
  writer dep) and an optional online **`geocode`** (Nominatim, degrades offline).
  Additive authored config under the hidden dir — **no `.store_version` bump**.
- **Light-dome glow auto-map** (`feature/glow-automap`, `m110/glow.py`, Qt-free).
  Fills the site profile's `[glow]` seam so the observability floor demotes targets
  low *toward* a city while leaving low-*away* ones alone. Walker's Law
  (skyglow ∝ population × distance⁻²·⁵) → per-town light domes (peak alt + angular
  half-width) → **upper-envelope** `glow_floor(az)`, composed as `max(physical,
  glow)` via `horizon.effective_floor`. Optional **Bortle** nudge + a softer
  **narrowband** floor; hemisphere-agnostic (haversine/bearing on signed coords).
  Authored from the profile editor's **Compute light-dome…** button →
  `<profile>.glow.hrz`, hand-editable. Town data = a bundled trimmed **GeoNames
  `cities1000`** subset (147k towns worldwide, 2.6 MB gzip, CC-BY 4.0 in `NOTICE`;
  `tools/gen_geonames.py`). **Decision:** `cities1000`, *not* `cities15000` —
  skyglow is dominated by nearby towns of a few thousand, so a 15k floor would drop
  the sources that matter most to rural/dark-site users (and biases against the
  sparser southern hemisphere; the Reddit audience is global). *Real-data fix:* a
  town at the observer's own location (near-zero distance, unstable bearing) made a
  spurious maxed dome — now excluded (`MIN_DOME_DIST_KM`; that all-sky glow is the
  Bortle anchor's job).
- **Deterministic prioritizer** (`feature/prioritizer`, `m110/prioritize.py`,
  Qt-free) — ranks targets, replacing the hand-edited `priorities.toml`. Weighted
  sum of ~0..1 factors: **goal** membership · **urgency** (season closing pressure
  from `observability()['nights_to_close']`, **×completion** so a *finished* target
  gets no urgency credit — the Astronomy-prototype M81-vs-M12 close-out fix) ·
  **completion** (strategy-shaped: *capture-many* favours new, *go-deep* favours
  started-but-shallow) · **tonight** (transit altitude + graded clear hours) ·
  optional per-type weight. **Pins compose on top** (pin→top, deprioritize→excluded).
  Filter derived from type (emission/planetary → LP) so the glow floor is
  filter-aware. Degrades to goal+completion+pins with no site/astropy.
- **Type-aware deep-stack threshold** (`build_derived.deep_threshold` /
  `DEEP_MIN_BY_TYPE`) — required integration scales with surface brightness, so a
  flat 60 min falsely marked faint nebulae "done." **Shared** between the status
  badge (`build_totals`, per-slug + per-folder) and the prioritizer's completion
  factor so they always agree. **Calibrated to S50 experience with the user:** a
  **90-min SNR floor** (nothing deep below it, on a low-cost sensor), planetaries
  180, galaxies 240, emission/SNR/reflection/dark **360**. A per-object user-set
  integration target is a planned override (ROADMAP).
- **Tuning UI + cost architecture.** The Planning priority table is the scorer's
  ranking with a live tuning surface: a **Strategy** toggle (capture ↔ deep) +
  per-factor **weight** spinboxes (persisted; both **re-rank the cache instantly**),
  a Recompute button, right-click Pin/Deprioritize. The slow part (astropy
  observability over every goal member, ~45s/151 targets) is **split** from ranking
  (`build_contexts` vs `rank`), computed **once/day** on a background
  `_PrioritizerWorker`, cached to `derived/prioritized.json`
  (`write_contexts`/`load_contexts`/`is_stale`). The worker fires **only** when the
  shell navigates to Planning in a `_ready` window (`ensure_ranking`) — never from
  widget construction / focus-refresh / offscreen tests, so a focus-refresh never
  runs astropy and tests don't leak the thread. (Wiring it into `run_refresh` was
  tried and reverted — it added ~45s to every focus-refresh.)
- **Profile-editor refresh preservation.** The app-wide focus refresh reloaded the
  `SiteProfileEditor` and wiped unsaved edits. The editor is now **dirty-aware**
  (`is_dirty`/`current_stem`; `_loading` suppresses `load()`'s own signals) and the
  Planning page skips reloading it while dirty on the same profile — unsaved values
  survive a refresh, resetting only on an explicit profile switch, Save, or restart.

---

## Later phase 5 — Library, catalogs & goals *(done; catalog library still growing)*

5. **Library, catalogs & goals — multi-list tracking + arbitrary objects.**
   Today everything is one implicit list (Messier). Generalize into four clear
   concepts:
   - **Object** — an astronomical target with intrinsic reference data (coords,
     type, magnitude, size). Season is **derived** from coords + site, not stored.
   - **Catalog / List** — a curated, named, **app-bundled, immutable** reference
     set (Messier, Caldwell, RASC Finest, Herschel 400, Sharpless, Arp, Lunar 100,
     …). Ships with the app.
   - **Goal** — a catalog the user is *actively pursuing* (selection over catalogs,
     with progress tracking + a dashboard/list view).
   - **Library** — the user's **personal corpus**: every object in their store —
     catalog members they track **plus arbitrary/captured additions**. Mutable,
     per-user. (Lightroom's "Library.") Objects are many-to-many with catalogs (the
     Veil is a non-Messier add *and* Caldwell C33/C34) — membership, not partition.

   **Phase 5a (done):** foundation — per-store `catalog.toml` → **`library.toml`**
   (v2→v3 store migration); bundled data split into an **object reference dataset**
   (`seed/objects.toml`, id → coords/type/mag/size) + **catalog membership lists**
   (`seed/catalogs/*.toml`; Messier ships). A fresh Library seeds from the
   reference. Nav "Catalog" → "Library". No new user-facing behavior yet.
   **Phase 5b (done):** Goals — active-catalog selection (Preferences), stored
   **per-store** in `.m110_internal_data/goals.toml` (`goals.py`; default Messier).
   Per-store, not the old global `active_goals` setting, so each store tracks its
   own goals, a fresh store starts genuinely Messier-only, and the Library is
   reconciled to the active goals on launch (no manual Save). Per-goal progress on
   Summary (`build_goals` → `goals.json`), an object **Catalogs** membership line,
   and a 2nd bundled catalog — **Caldwell** (109 objects via `tools/gen_caldwell.py`
   + Simbad; astroquery is build-time only). Fresh Library seeds the active goals'
   members (Messier); activating a goal adds its members to the Library (additive).
   Library has a **catalog-filter selector** (browse one catalog's members), a
   **"Captured only"** filter (interim collection view; default off), and shows
   **all of an object's identifiers** ordered by a catalog hierarchy
   (Messier→Caldwell→NGC/IC; e.g. "C20 (NGC 7000)").
   **5c — reference enrichment (done):** a
   **"Fill missing metadata"** action (Library right-click + a **Library** menu bulk
   pass) backfills an existing entry's missing fields from the bundled reference and
   derives `season` from RA (`catalog.fill_missing_metadata` / `season_from_ra`),
   never overwriting user values. Fixes stale stubs (e.g. captured-but-uncatalogued
   objects added before their catalog was bundled). The bundled Caldwell reference was
   regenerated to ship a derived `season` for every member.
   **5c — add object + online enrich (done):** **Add object** (Library menu) resolves a typed name/designation via a
   cascade — bundled reference → online Simbad → coords-only (season always derived) —
   previews it editably, and commits a new Library entry + journal stub
   (`catalog.resolve_new_object`/`add_library_entry`). **Online enrichment** fills gaps
   the bundled reference can't (e.g. the Veil's mag/size) for existing entries too:
   right-click **"Enrich online"** (single) + Library → **"Enrich online…"** (batched),
   `fill_missing_metadata(online=)`/`enrich_online`. Online is opt-in (explicit action)
   on the **optional `astroquery` extra** — graceful `OnlineLookupError` when it's
   absent/offline; runtime stays offline by default.

   **Add arbitrary objects + auto-enrich.** A user can add any object to their
   Library; the app fills the data fields via a cascade (generalizes
   `catalog.add_captured_objects`):
   1. **Bundled reference** (covers catalog objects — instant, offline, complete);
   2. else **online lookup by name** — **astroquery** (Simbad/VizieR) for
      type/mag/size/coords. *(c): bundled-first, astroquery as enrichment, mainly
      for objects outside any supported catalog.* New optional dependency; network.
   3. else **embedded coordinates** — FITS `RA`/`DEC` or the filename pointing data
      (reuses ingest #12); type stays "unknown" for the user to complete.
   4. **Season is always derived** from the resolved coords (no lookup).

   Default goal ships as Messier; users add other goals from the bundled catalog
   library (or import their own). See the sibling Astronomy project's
   `next_catalog_lists.md` for candidate lists.

   **Bundled catalog library (done / growing).** Six catalogs ship today: **Messier**
   + **Caldwell** (`gen_caldwell.py`), and **RASC Finest NGC** (111), **Best of
   Sharpless** (30, curated), **Bennett** (152, southern), **Lacaille 1755** (29,
   southern) — all generated by `tools/gen_catalogs.py` (Simbad coords/size/mag at
   build time, season derived from RA; idempotent, runtime offline). Still candidates
   from `next_catalog_lists.md`: **Herschel 400**, **Arp**, **Lunar 100**, AL Double
   Star — mostly more data-generation in the same tool.

   **5d — Goals view + the Library-=-collection reframe (done).** A dedicated
   **Goals** nav page (left rail) where goals are **selected, created, and edited** —
   including **custom goals built from an arbitrary object list** (`[[custom]]` in
   `goals.toml`), not just bundled catalogs. Each active goal shows a **progress
   summary** + an **"in-progress captures"** list (captured but below the deep-stack
   target) + a **Remaining (uncaptured)** membership checklist. The model reframe
   landed: the **Library is the captured/annotated collection** (a fresh
   `library.toml` starts empty), and **uncaptured catalog members live in the Goals
   view**, not the Library. What shipped:
   - **Dropped the bulk Library goal-seed** (5b's "activating a goal adds all
     members") + the launch-time reconcile. The Library grows only by capture
     (`add_captured_objects`, now pulling full reference metadata for known
     objects), the Add-object flow, or annotation.
   - **Goal de-select removal** — deactivating a goal (or deleting a custom one)
     prunes its uncaptured, un-noted, not-in-another-active-goal members
     (`catalog.remove_goal_members_from_library`). Captured/annotated objects stay.
   - **Manual removal** — Library right-click **"Remove from Library"**
     (`catalog.remove_library_entry`; non-destructive).
   - **Resolved:** annotated-but-uncaptured targets live in the **Library**.
   - Goal management moved **fully to the Goals page** (removed from Preferences).

---

## Later phase 6 — Import, robust/layout-flexible *(6a–6c done 2026-06-26/27)*

Ingest renamed **Import** + promoted to a top-level nav page; **6d** (lazy
device-under-target) is still open in [`ROADMAP.md`](ROADMAP.md) item 6.

- **6a — Import view + any-directory source.** Directory chooser + Favorites/Recent
  places (Seestar + Inbox auto-appear); **recursive** `ingest.scan_directory_plan`
  walks an arbitrary tree; always **copy** (source untouched), preserving filenames,
  with content-aware **collision handling** (`apply_ops`: checksum/size → duplicate-skip
  vs. distinct `_N` suffix). The old modal Ingest dialog superseded (`Ctrl+I` repointed).
- **6b — Header-based classification + layout registry.** Classifies by FITS header
  (`ingest.frame_info` → OBJECT/IMAGETYP/FILTER/RA/DEC); calibration frames route to
  `darks/`/`flats/`/`biases/`; **header wins over folder name**. The **layout registry**
  (`ingest.LAYOUTS`, mirrors `processing.WORKFLOWS`) names the detected source per group:
  **seestar**, **m110-store** (the `~/Astronomy/Images` precursor; `process/`+`siril/`
  skipped), **raw-fits**, **finished-render** (a loose `*_processed/final/finished`
  raster → the object's `finished/`), **asiair** (disabled placeholder). The app's own
  `Images/` is never re-imported (`_in_own_store`).
- **6c — Holding area + manual assign.** Nothing is silently ignored: `_classify_dir`
  **sweeps** every unclaimed content file into the `Inbox/` holding area
  (`kind="unassigned"`), surfaced in an always-visible **Holding area panel** with
  per-folder Object+Kind **Assign** (`ingest.scan_holding`/`assign` → move into the
  content tree; alias learning). `Inbox/` is no longer a user-facing source.

---

## Later phase 8 — Publishing, static-site export *(8a done 2026-06-29)*

New Qt-free `m110/publish/` package — a publisher **registry** (`PUBLISHERS`,
`run_publish`, `enabled_target_ids`) mirroring `processing.WORKFLOWS`: `static-site`
available, `github-pages`/`netlify` registered-disabled. `site.py` (ported from the
Astronomy `build_site.py`) renders Jinja2 templates → a user-chosen **local folder**
from the derived JSON + `build_images` derivatives + journals; `select.py` =
testable selection/privacy; `images.py` reuses `build_images`. Per-object `publish`
flag (`catalog.set_publish_flag`, Library right-click) + journal `private` frontmatter.
**Library → Publish / share…** dialog (sections/target/output) on a threaded worker.
Optional `publish` extra (jinja2 + markdown; degrades via `PublishDepsMissing`).
*Deferred follow-ups (BUGS #27):* GitHub Pages deploy, Netlify/S3/CMS targets, per-list
flags, cross-publish cache reuse, auto-publish.

---

## UI design system — Phase 0 + Phase 1 *(done 2026-06-29/30)*

Design-system-first UI refresh (full plan in [`UI_ROADMAP.md`](UI_ROADMAP.md)).
- **Phase 0 — tokens + theming.** `m110/ui/theme/` = `tokens` (light+dark semantic
  palette + spacing/type scales), `qss.build_qss`, `manager.ThemeManager` (follow OS
  appearance + manual `ui_theme` override + live re-apply), `fonts` (bundled JetBrains
  Mono). Installed in `main()`; **Preferences → Appearance**. Migrated all hardcoded
  status/muted colors onto tokens.
- **Phase 1 — restyle surfaces.** Status **pill chips** (sort-safe delegate),
  alternating rows, **tabular numerals** (mono numeric columns), uniform page padding,
  nav-rail polish, DetailPane status pill, dialog spacing. Removed the redundant Import
  toolbar button. **Live-store test seal** (`tests/conftest.py`) so no test can read/
  write the real `~/Documents/M110`.

---

## Fixed bugs & shipped improvements *(archive)*

Concise log; full root-cause writeups are in git history. Lessons that constrain
future work live in `CLAUDE.md` "Gotchas / lessons learned".

**Beta fast-follows (post-`v0.1.0-beta.1`)**
- **Update notifications** (`feature/update-check`, shipped in beta.2). Qt-free
  `m110/updates.py` checks the GitHub Releases API (`/releases`, *not*
  `/releases/latest` — the beta is a pre-release), compares the newest tag to the
  running version (PEP 440), and shows a quiet, dismissible launch banner
  (Download · Skip · ✕) when newer. Help → **Check for updates…** for a manual check;
  **Preferences → Updates** toggles the throttled (~daily) launch check. Stdlib
  `urllib`, degrades silently offline; no new dependency. *(A follow-up gated the
  launch check on `_ready` — its network `QThread` was aborting short-lived
  test/screenshot processes at teardown; SIGABRT → macOS "Python quit" dialogs.)*
- **Import: one deterministic recursive scanner (#32).** Beta-tester report
  (Windows): nested Seestar subfolders weren't scanned. Root cause = two scan paths
  of different depth; unified everything on the recursive `scan_directory_plan`
  (retired the shallow `_scan_base`) + added scan logging + a user-visible post-scan
  summary (objects / to-import / to-holding).
- **Holding area (#33/#34).** Multi-select bulk assign (row multi-select + a bulk
  bar routing many held rows to one object/kind); and the Object picker made
  discoverable as **type-or-pick** (it was always editable + the engine always
  accepted arbitrary names, but it looked like a fixed drop-down).
- **Window resizes narrower.** A few long, non-wrapping description labels pinned the
  window to a wide minimum (worst on the empty-library Overview); wrapping them lets
  it shrink normally.

**Data store**
- **#13 — Two-axis store (architectural).** Split the data root into `Objects/`
  (catalog-object axis) + `Images/` (capture-target axis), with all machine state in a
  hidden `.m110_internal_data/` — because objects and capture targets are many-to-many.
  In-place, idempotent, version-stamped migration (`migrate.py`, `migrate_store`); landed
  before 0.1e/0.1f. `scan_sessions`/`build_derived` read `config.*` dynamically.
- **#14 — Orphan-render pruning.** `render_images` now unlinks `renders/<hash>.jpg`
  thumbnails + `hero/<slug>.jpg` heroes the manifest no longer references (full renders
  only; returns a `pruned` count) — the cache no longer grows when a source reprocesses.
- **#20 — Data Model documented** → canonical [`DATA_MODEL.md`](DATA_MODEL.md).
- **M42_mosaic / `library.toml` corruption** — duplicate `[catalog.<slug>]` blocks
  (from concurrent leaked test refreshes, now sealed) bricked the app. Hardened:
  `_append_library_entries` never writes a duplicate slug; `load_library` self-heals a
  duplicate-block file.

**Import / ingest**
- **#9 — Group preview by object** (Object · Files · Size · → dest); ops carry `size_bytes`.
- **#10 — Per-object import checkboxes** (select all/none; live size total).
- **#11 — Media page** displays non-catalog `Media/` (photo viewer + video open).
- **#12 — Name canonicalization + RA/Dec pointing check** (alias table; `⚠ → M82?` remap).
- **#15 — Working folders self-heal on refresh** (`processing.prepare_missing`).
- **#22 — Siril autoprep race** (`SameFileError`): `_link_or_copy` idempotent;
  `_do_refresh` skips while Import is busy.
- **Holding-area importer polish** (2026-07-09). (1) The holding panel was cramped by
  default — the splitter now seeds a ~40% height (`setSizes`) + a 2:1 stretch. (2) The
  Rescan/Select/Import button row sat flush against the splitter handle → bottom margin
  on the top layout. (3) A held Inbox folder spanning multiple objects collapsed into one
  row with one Object/Kind picker; `scan_holding` now tags each held FITS with its
  detected object (shared `_suggest_slug` — OBJECT header / nearest by RA·Dec), so
  `group_ops` splits it into one **independently assignable** row per object (unidentified
  files stay bundled per folder). Selection-restore rekeyed on `(folder, object)`.
  `tests/test_holding.py`.
- **DwarfLab Dwarf 3 support** (2026-07-09). Validated against real Dwarf 3 output.
  Two `.fit`-only bugs made Dwarf `.fits` captures invisible: `config.is_light_frame`
  diverted every sub to `working_files/`, and `scan_sessions` skipped `.fits` + parsed
  Seestar-only filenames → zero sessions. Fixed with a shared `config.FIT_EXTS`
  (`.fit`/`.fits`) engine-wide + a header-driven `scan_sessions` (`DATE-OBS`/`EXPTIME`/
  `FILTER`, Seestar filename as fast path). Added a `dwarf` layout recognizer
  (`_classify_dwarf_dir`): subs → `lights/`, `stacked-16_*` + `stacked.jpg` →
  `seestar-stacks/`, startrails → `Media/Startrails_{video,photo}/`, `Thumbnail/`
  (→ `_SKIP_DIRS`) + aux ignored; `_usable_object` sends `''`/`Unknown` to holding.
  No `.store_version` bump. `tests/test_ingest_dwarf.py`.
- **Recursive-import grouping** — `group_ops` keyed on the resolved object, not the bare
  folder name (a precursor store's per-object `lights/` no longer collapse into one row).
- **Loose finished render → holding** — new `finished-render` recognizer routes a loose
  `*_processed` raster to the object's `finished/`.
- **Copy modal** didn't close / crash-on-cancel / "Copying files…" label + progress bar.
- **Holding area** (#63–66): filenames on hover; Assign-button legibility; selections
  survive a focus/modal refresh; a just-imported object lists in the dropdown; the
  summary line wraps instead of forcing window width.

**Catalog / Library**
- **#23 — Messier 108/110 → 110/110** (hand-authored M40 + M73, which don't resolve in Simbad).
- **#24 — Goals page redundant label** "M51 (m51)" → "M51".
- **Season-column sort** by first month (Jan→Dec; Year-round last).

**Detail view / processing**
- **No images for FITS-only stacks** — thumbnails/heroes now render from FITS (percentile
  stretch); ingest also copies device preview JPGs.
- **NGC 6992 finished work not picked up** — `siril._classify` was vetoing pipeline-step
  tokens (`_spcc_processed`); only star layers (`starless`/`starmask`) veto now.
- **Detail pane:** gallery un-truncated + click-to-view (`ImageViewer`), hero scales to
  pane (`ScalableImage`), journal renders Markdown wrapped to width, Object-Notes edit
  re-renders the Journal feed + wraps at width, stale-button crash + over-large viewer fixed.
- **Preferences** is a live panel (workflows persist on toggle, theme live, single
  **Close** button; no redundant "saved" modal).

---

## Design notes & feedback (historical)

Brainstorm that drove the import improvements above (kept for rationale):

- **#9 group-by-object** was the keystone — the per-frame table was slow
  (1,500+ items over SMB), unreadable, and worsened modal churn; `stat()` for sizes
  must stay on the scan worker. **#10 select-to-import** pairs naturally. **#11
  "display everything"** needed a new surface → the Media page.
- **Resumability** is already good (skip-if-present + atomic temp+rename), so a
  cancelled/failed import just re-runs — worth surfacing in the UI (see the open
  "surface skipped files" backlog item).

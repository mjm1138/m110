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

## Later phase 1 — Session planning: **Checkpoint B** *(done 2026-07-13)*

Turns the Checkpoint-A prioritizer into a plan for a **specific night** + a saved,
browsable **field guide** (`feature/session-planner`). Device plan-files (SSC/NINA,
the deferred half of item 2) remain open; the Checkpoint C assistant (item 4)
shipped its M0 — a read-only MCP server over the engine.

- **Per-target night math** (`m110/planning.py`, Qt-free, reusing `twilight` /
  `moon_summary` / `to_utc` / `_location`). `night_track(target, day, site, filter=)`
  samples a target's alt/az across the astro-dark window and returns its **transit
  time + altitude**, the **longest contiguous up-window** (above `min_alt` AND the
  filter-aware horizon+glow floor), **moon separation** at transit, and the
  `(local_time, alt, clear)` **sample series** for the timeline chart. `plan_night`
  returns `{window, moon, entries}` — every observable target's track,
  **auto-ordered by `up_end`** (the target *setting soonest* goes first; tiebreak by
  prioritizer score); `order="manual"` preserves the caller's order. Twilight (the
  18h sun scan) is computed **once** and reused via `window=` (~0.9 s for 15 targets,
  vs. per-target). Astropy moon-separation frame-transform warnings suppressed.
- **Field guide artifact + store** (`m110/fieldguide.py`, Qt-free). `render_markdown`
  → a printable observing plan: header (date, site, dark window, moon illum/altitude)
  + an ordered target table (best time = transit, altitude, up-window, moon°, filter
  from `prioritize.filter_for_type`) + per-target season/notes. Plain Markdown so the
  app renders it with **`QTextBrowser.setMarkdown`** (Qt-native — no dependency) and it
  prints/shares. `save`/`list_guides`/`read` manage saved guides under a **new visible
  `Plans/` axis** (`config.PLANS_DIR`, `Plans/<date>_<slug>.md`, created idempotently
  by `ensure_data_root` — additive external output, **no `.store_version` bump**).
- **Plan-a-night UI** (`pages/planning.py`). A **Plan a night** section: a date picker
  → a background `_PlannerWorker` runs `plan_night` over the **top-ranked candidates**
  (reusing the cached prioritizer contexts to bound the astropy work) → a dark-window
  + moon summary, an ordered **target table** with include-checkboxes + **Move up/down**
  (the manual-reorder option), and a **`NightTimeline`** widget
  (`m110/ui/night_timeline.py`) painting each included target's altitude curve across
  dusk→dawn + the min-alt floor line. **Save field guide…** writes the Markdown via
  `fieldguide`. A **Saved field guides** browser section lists guides with **View**
  (`FieldGuideDialog`, `m110/ui/field_guide_dialog.py`) / **Reveal** / **Delete**.
- **Worker discipline.** Both astropy workers (`_PrioritizerWorker` on `ensure_ranking`,
  `_PlannerWorker` on **Generate**) fire only on **explicit user actions** — never from
  widget construction / reload / focus-refresh — so a background refresh never runs
  astropy and offscreen tests can't spawn/leak the thread (verified: no teardown
  aborts across repeated full-suite runs).
- **Decisions (with the user):** field-guide-only export (browsable/viewable in-app;
  SSC/NINA later) · a visual altitude timeline · auto-ordered plan with a manual
  reorder option.

---

## Later phase 1 — Session planning: **tuning arc** *(done 2026-07-14; shipped in v0.2.0-beta.1)*

The pre-release hardening of the prioritizer + planner, driven by two independent
astropy-ground-truth reviews. The phase-by-phase record lives in
**[`docs-archive/PLANNING_ROADMAP.md`](docs-archive/PLANNING_ROADMAP.md)** (with the
reviews: [`prioritizer-review.md`](docs-archive/prioritizer-review.md),
[`PLANNING_BUGS.md`](docs-archive/PLANNING_BUGS.md)). In brief:

- **Phase 1 — correct ranked data** (#35/#38/#39): the prioritizer became the single
  ranked source (`priorities.toml` retired end-to-end); uncaptured goal members get
  their true type from the bundled reference; combined/mosaic folders roll up into
  their members before scoring; a **feasibility gate** (non-DSO types near-excluded,
  faint targets graded by surface brightness derived from mag+size).
- **Phase 2 — moon model** (#36): the infamous "0% lit, −17°" header was a
  **date/plan desync**, fixed at both ends; per-slot moon (`set/rise/track`), the
  Moon column gated on moon-up, filter-aware `moon_impact`. The harness review also
  caught a 2× separation error — the astropy `icrs.separation(gcrs_moon)`
  barycentric pitfall — fixed topocentrically.
- **Phase 3 — start-altitude ceiling** (#37): researched per-device
  (`DEVICE_PRESETS`: Seestar hard 78°, Dwarf soft 80°); `pick_start` proposes
  rising/setting-side slots under ceiling−3°, never the over-ceiling transit.
- **Phase 4 — the sequencer** (#40–42): `sequence_plan` — non-overlapping
  10-min slots, priority order with ties-to-the-setter, deep-stack duration caps,
  night **fill** to dawn, ⚠ marginal last-chance slots, Targets count control,
  reorder/exclude reflow, the field-guide `## Schedule` table.
- **Phase 5 — UI** (#43): the calendar popup's "…"-elided days (the theme's table
  item padding hitting a QTableView subclass) + the dark-mode `QDateEdit`; timeline
  overlays (moon track, ceiling, slot bands).

Alongside the arc: **#40c** — a capture *target* is not a catalog *object*
(`add_captured_objects` promotes a combined folder's **members**; store **v3→v4**
prunes the synthetic pseudo-objects; Processing's first column renamed **Target**).

## Later phase 1 — Session planning: **priority-list tuning** *(done 2026-07-17; `feature/prioritizer-tuning`)*

A second tuning pass driven by planning a real night in the app (2026-07-17). Three
independent complaints, three fixes — engine stays the source of truth, UI is thin:

- **Out-of-season targets no longer clutter the priority list.** The scorer only
  *softly* graded observability, and half of `tonight_score` came from the **season-blind
  transit altitude** (`90 − |lat − dec|`, a geometric max that ignores whether that
  transit happens in daylight). So an uncaptured winter Messier (M44 transits 70°… at 2 pm
  in July) still banked ~0.5 tonight credit and, with goal=1.0 + a shallow-object
  completion, planted itself in the top 20 (M44/M97/M3/M35/M36…). Fix chosen (over
  re-scoring, to keep the full list usable for future-date planning): a **"Visible
  tonight"** toggle on the Planning page (default on, persisted `planning_visible_tonight`)
  that filters the rendered ranking via `prioritize.filter_visible_tonight` — hides
  `observable is False`, **keeps** `None` (degraded / no-astropy) so a site-less ranking
  isn't emptied. A caption reports the hidden count; unchecking shows the full ranking.
- **The night sequencer now honors the Targets count.** Root cause of "always 7 targets,
  some 10-min slots": `sequence_plan` ran `fill=True` and its `deep_remaining` cap trimmed
  every near-deep primary to a stub, which `fill` then backfilled to dawn. Per the user's
  call — *"overshoot a primary's integration rather than cut it to free 30 min for
  something marginal"* — the **deep-stack duration cap was removed** (each of the N chosen
  objects runs its full `base = span ÷ count` slot, capped only by its own up-window and
  dawn), a **`MIN_SLOT_MIN = 30`** floor **drops** any sub-30 slot instead of scheduling a
  stub (and floors `base`), and `fill` is retained so early-*setting* targets still don't
  strand the back half of the night. `count` now genuinely sizes the plan (count=2 → ~2–3
  long slots; count=7 → ~30–40 min each). `deep_remaining` removed from the engine
  signature + the UI caller.
- **Per-type weight controls.** `Weights.type_weights` (a per-type score multiplier) had
  been applied by the scorer since Checkpoint A but had no UI. Added **`TYPE_GROUPS`** +
  `type_weights_from_groups`/`groups_from_type_weights` (Galaxies / Globular / Open
  clusters / Nebulae → underlying catalog types; Nebulae = emission/planetary/reflection/
  dark/SNR), surfaced as four spinboxes in Planning → *Tuning weights* alongside the factor
  weights — boost galaxies/nebulae, damp clusters to break up a cluster-heavy Messier.
  Neutral (1.0) groups aren't stored, so a fresh install's weights stay empty.

Tests: `test_planning_night` (overshoot, min-slot drop, fill-after-setters rewritten off
the removed deep-cap), `test_prioritize` (visible filter, group↔type-weight round-trip,
type-weight lift), `test_ui_pages` (toggle filters + persists, type spin persists).

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

## Later phase 6 — Import, robust/layout-flexible *(6a–6c done 2026-06-26/27; Dwarf 3 done 2026-07-09)*

Ingest renamed **Import** + promoted to a top-level nav page; **6d** (lazy
device-under-target + the Dwarf remainders) is still open in
[`ROADMAP.md`](ROADMAP.md).

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
- **DwarfLab Dwarf 3 support** *(done 2026-07-09, `feature/dwarf3-ingest`)*. A second
  device validated end-to-end against real Dwarf 3 output. Fixed two `.fit`-only
  assumptions that made Dwarf `.fits` captures invisible (`config.is_light_frame`
  diverted every sub to `working_files/`; `scan_sessions` skipped `.fits` + parsed
  Seestar-only filenames → zero sessions): a shared `config.FIT_EXTS` now covers
  `.fit`/`.fits` engine-wide, and `scan_sessions` is **header-driven** (`DATE-OBS`/
  `EXPTIME`/`FILTER`, Seestar filename as a fast path). Added a `dwarf` layout
  recognizer (`ingest._classify_dwarf_dir`, keyed on the `DWARF_RAW_*`/`STARTRAILS_*`
  session-folder prefix) routing on-device session folders (subs → `lights/`,
  `stacked-16_*` + `stacked.jpg` → the `seestar-stacks/` device-stack tier,
  startrails → `Media/Startrails_{video,photo}/`, `Thumbnail/`/aux ignored), and
  `_usable_object` so an `OBJECT` of `''`/`Unknown` goes to the holding area instead
  of a literal target. No `.store_version` bump. Tests in `tests/test_ingest_dwarf.py`.
  *(Still open under ROADMAP 6d: `DWARF_DARK`/`CALI_FRAME` routing, `Restacked/`,
  TIFF subs, the `shotsInfo.json` sidecar, volume auto-detection, Dwarf II.)*

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
*Deferred follow-ups (BUGS #27):* Netlify/S3/CMS targets, per-list
flags, cross-publish cache reuse, auto-publish.

**GitHub Pages deploy** *(done 2026-07-15, `feature/publish-ghpages` — BUGS #27a;
the port of the Astronomy `deploy.sh`/ghp-import workflow, the last piece of that
workflow M110 hadn't absorbed).* New Qt-free `m110/publish/ghpages.py`: shells out
to the user's installed **git** (no new dependency; auth = their existing SSH key /
credential helper), builds a fresh single-commit orphan branch in a scratch repo
(`--git-dir`/`--work-tree`, local commit identity) and **force-pushes** it to
`gh-pages` — ghp-import `-f` semantics, so the remote stays lean no matter how
often heroes/thumbnails re-render. Writes `.nojekyll` (ghp-import `-n`); refuses to
push a folder with no `index.html`; git stderr surfaces in a `PublishError` so
auth/repo problems are actionable. `normalize_repo` accepts `owner/repo` (→ SSH
URL), https, or ssh forms; `pages_url` derives the served
`https://<owner>.github.io/<repo>/` URL (root for an `<owner>.github.io` repo).
Registry: `github-pages` flipped available; `run_publish` now runs publishers in
registry order and passes `prior=` (the static-site result) so enabling both
targets renders **once** and deploys that folder. `PublishOptions` gained
`github_repo`/`github_branch`. Dialog: a Repository field under the GitHub Pages
checkbox (persisted `publish_github_repo`, enabled with the target), validation,
and a success message with the pages URL + **Open site**. Tests
(`tests/test_publish_ghpages.py`) run against a local `file://` bare repo — no
network: nojekyll/content assertions, force-replace keeps `rev-list --count` at 1,
missing-git/missing-index/empty-repo errors, `prior` reuse, registry chaining.

**Live-library hardening (same branch, pre-merge)** — a real 224 MB publish
surfaced five defects, all fixed: (1) **finished-only galleries**
(`PublishOptions.finished_only`, default **on**; the shared
`objects.image_state` rule — curation override over tier — now backs both the
detail-pane groups and the publish filter), cutting the published site to
deliberate deliverables instead of every stack/working file; (2) the push
**wall-clock timeout removed** (`_GIT_TIMEOUT` now guards only local plumbing) —
a first full-site upload on a home uplink legitimately exceeds any fixed cap;
(3) **cancel kills the push process** (`_push` = `Popen` + poll loop + `kill()`)
— previously a cancelled/quit publish left an orphaned `git push` racing the
next deploy for the branch (observed live: two concurrent force-pushes); (4)
**real deploy progress** — `git push --progress` stderr is streamed and parsed
("Writing objects: n/m" → `progress`), with a `status` stage-label channel
through the publisher contract ("Rendering site…" / "Uploading to GitHub…"), so
the bar no longer sits at a stale 100% during the upload; (5) a **Save** button
persists every dialog choice without publishing, and a user cancel closes
quietly instead of raising a "failed" dialog (the kill also unblocks the
teardown `wait()` that beach-balled the app). Cancel-kill is regression-tested
with a stalling `pre-receive` hook on the bare-repo remote.

**Round 2 (same branch):** (6) **stale output is swept** — `site.render` tracks
every file it emits and `_sweep_stale` deletes anything else under the
renderer-owned `img/`/`objects/` + the optional top-level pages, so narrowing
options genuinely shrinks the folder *and the deployed branch* (previously
"finished-only" hid images from pages but the stale derivatives still uploaded;
verified e2e: branch 37→24 files on a re-publish); a cancelled render never
sweeps (incomplete emit set). (7) `finished_only` generalized to a **three-level
`gallery_level`** — finished / +device stacks / all — via `_image_tier` (explicit
curation wins outright; device stacks are their own tier), a combo in the
dialog. (8) **`docs/publishing.md`** — user-guide page covering
sections/privacy/gallery levels + the GitHub Pages setup (SSH check, repo,
enable Pages, URL, force-replace caveat); linked from the guide index. (9)
**processing.html mirrors the app's Processing page** — "Ready to import" group
first, up-to-date omitted, Target column + Rejected/Latest stack/Notes.
(Sessions/summary already matched.)

**Round 3 — incremental deploy mode + the global-excludes guard.** A live deploy
measured ~4–5 Mbit/s (a single TCP stream on a residential uplink, not GitHub
throttling), which makes force-replace's "re-upload the whole site every time"
the dominant cost once a gallery is large (185 MB at *finished + device stacks*
≈ 6 min per publish, even for a one-line journal edit). So `deploy` gained a
second **mode** (`DEPLOY_MODES`, `PublishOptions.github_deploy_mode`, default
**replace** — repo hygiene stays the default): **`incremental`** fetches the
deployed tip and commits on top of it, so the push transfers only objects the
remote lacks (**5 vs 17** objects in the test; because web derivatives are
content-hashed, an unchanged image *is* the same blob and never re-uploads).
The tip fetch uses **`--filter=blob:none --depth 1`** — the trees alone
negotiate the push, so reading the tip costs ~3 objects instead of
re-downloading the site (verified against a bare repo with
`uploadpack.allowFilter`, GitHub's config); servers without filter support fall
back to a plain shallow fetch, and a missing branch (first deploy) proceeds
parentless. Cost: history keeps every superseded image — one publish in
`replace` mode collapses it again. **Load-bearing detail:** `deploy` must never
`checkout`/`reset --hard` (the work tree *is* the user's rendered site) —
`update-ref` + an empty index + `add -A` makes the commit tree mirror the folder
exactly, so the stale-sweep's deletions propagate in both modes. Also fixed a
latent stranger-bug the Astronomy `webhosting.md` had flagged: the deploy repo
now **neutralises `core.excludesFile`** and excludes only OS junk via
`info/exclude`, so a user's global `*.jpg`/`*.png` rule can't silently strip the
gallery (regression-tested with a global-ignore fixture; this machine's globals
are benign, which is why it never bit). `_push` generalized to **`_git_stream`**
(shared by fetch + push).

Incremental backups to a user-defined destination + selective restore + retention.
Qt-free engine `m110/backup.py` writes **hardlinked dated snapshots**
(`rsync --link-dest` semantics in pure Python): each snapshot is a full, browsable
tree, but files unchanged since the previous snapshot (all the immutable raws) are
hardlinked, so incrementals cost only the changed bytes (verified: a 2nd no-change
snapshot of the test store added **0 new bytes**). Scope is a **denylist** —
everything under the store except regenerable derived data (`derived/`, `renders/`,
`sessions.jsonl`) and the `siril/` working sandboxes — so new authored data is
captured automatically. Each snapshot carries a **checksum manifest** for
integrity/bit-rot verification. **Restore** defaults to extracting selected paths
to a chosen folder (never touches the live store); restoring back into the store is
available behind a create-vs-overwrite conflict preview + confirm. **Retention**
(keep-N snapshots, default all / min-free-GB, default 100) prunes whole oldest
snapshots, explicitly, never the last one. UI: Library → **Back up…** / **Restore…**
(`backup_dialog.py` / `restore_dialog.py`, mirroring the publish worker/progress
pattern) + an opt-in **auto-backup** (background, unobtrusive): fires at **launch**
when the last snapshot is older than the interval (default **12h**), *and* on an
**hourly tick** that runs a **daily 02:00** snapshot while the app stays open (so a
long-running session still gets daily backups, not just launch ones) — the interval
doubles as a min-age guard so a fresh launch backup doesn't re-fire at 02:00
(`due_for_auto_backup` / `due_for_scheduled_backup`). Both share one cancel-on-quit
worker; an interrupted snapshot is atomic (`*.incomplete` → rename, swept on next
run) so quitting mid-backup never corrupts. It's an external-output feature (writes
outside `<data_root>`) → no `.store_version` impact. *Deferred:* cloud/remote
destinations, multiple destinations (3-2-1).

**Pooled (content-addressed) storage — issue #92** *(2026-08-02,
`fix/backup-destination-probe` → `refactor/backup-package` →
`feature/backup-pooled-storage`)*. The hardlink model above has a failure mode that
was invisible by design: where the destination filesystem can't `os.link` — many SMB
shares, appliance NASes, exFAT — it byte-copies *everything*, so a nightly backup
quietly stored a **full copy of the library every run**, and the only signal was a
`hardlinks: false` field in a manifest that didn't exist until after the first run.
@devonjones hit it on a NAS.

Three changes, deliberately separate:

1. **Probe the destination and say what you found.** `backup.probe_destination` →
   `DestinationInfo` (exists / writable / hardlinks / free bytes / snapshots /
   resolved format), read-only: it creates no `M110-Backups/` tree for a candidate
   the user hasn't committed to, and leaves no probe files. The dialog runs it on a
   `_ProbeWorker` — the status line previously called `list_snapshots()` **on the GUI
   thread on every `textChanged` keystroke**, which on a dead SMB mount blocks
   indefinitely; it now fires on `editingFinished`/Browse and memoizes per path.
2. **`backup.py` → a layered `backup/` package** (pure move, behavior-identical, its
   own commit so the storage diff was readable). `destination` imports no format
   module and `retention`/`probe` sit above `mirrored`, so a second format slots in
   *beside* it rather than underneath. Also dropped two private-name couplings the
   package made untenable: `restore_dialog` built its tree from
   `backup._read_manifest` (now the public `snapshot_files`), and tests patched
   `backup.os.link` — which only worked while everything shared one module namespace.
3. **A second format.** Objects under `objects/ab/cd/<sha256>` (mode 0444), one
   self-contained gzipped manifest per backup under `snapshots/`. Dedup moves from
   the *filesystem* ("hardlink to the previous snapshot") to the *application*
   ("does this hash already exist?"), which is what makes it work anywhere.

**Why a second format and not a replacement.** The tempting move was to convert
everyone. But mirrored has a property nothing else does — a snapshot is your files,
in dated folders, restorable in Finder with no software at all — and conversion is
cheap exactly where it isn't needed and ruinous exactly where it is (on a link-less
destination, converting means re-copying the whole library). So **mirrored stays the
default**, pooled takes over only where mirrored can't work, and both stay listable,
verifiable and restorable at the same destination forever. The namespaces are
provably disjoint: `list_snapshots` has always parsed identity from the directory
*name*, and `objects`/`snapshots`/`latest` can never parse as a timestamp. No flag
day, no migration, nothing stranded.

Design points worth keeping:

- **The invariant.** *A manifest exists ⇒ every object it names exists* — enforced by
  writing the manifest last. That is what makes retention a refcount rather than a
  dependency graph, and what makes an interrupted first sync **resume for free**: its
  orphaned objects are content-addressed, so the next run simply finds them.
- **No chain.** Explicitly rejected the tape-era full+incrementals model, which buys
  restores needing an intact chain, retention that can't drop a full until its
  dependents expire, and a corruption blast radius spanning days.
- **Recoverability was the real cost, so it was paid explicitly.** `objects/` alone is
  a bag of hash-named blobs — and `latest/` (the browsable hardlink tree, free) is
  absent precisely in the auto-switch case, since it needs the links the destination
  lacks. So a pooled backup also writes `INDEX.tsv` (plain text), a mirrored
  `latest-manifest.json.gz`, `README.txt`, and a **stdlib-only `restore.py` into the
  backup root** — the way back travels with the data instead of living in docs the
  user won't have at that moment. Drilled with `/usr/bin/python3` outside the venv.
- **Hash cache** (`~/.m110/backup-hashes.sqlite3`, keyed
  `(path,size,mtime_ns,inode,dev)`) — else a 500 GB library rehashes nightly. A miss
  only costs a rehash; the one hazard is a stale *hit*, caught by cross-checking the
  size the destination already has for that hash (free — sizes come back with the
  object listing). Strictly stronger than mirrored's reuse test, which matches
  size+mtime and then inherits a sha it never recomputes.
- **GC safety without a lock**: a 24h grace window on object mtime. An object being
  written by a concurrent run is by definition recent, so it's never swept.
- **`object_sizes()` enumerates once per run**, not `exists()` per file — 100k
  round-trips is minutes of latency over SMB, and one paginated LIST on S3.
- The `backends/` seam (`LocalBackend` + a shipped `MemoryBackend` that is both
  reference implementation and conformance-suite double) is registry-shaped like
  `publish.PUBLISHERS`, so **#93's `S3Backend` is an adapter, not a rewrite**.

Verified on a real FAT32 disk image (the only honest test for "no hardlinks"): three
backups of a 1.2 MB library occupy 1.3 MB, an unchanged re-run stores 0 new bytes, a
one-line journal edit stores 34, and the oldest snapshot still verifies and restores
its own older contents. Also fixed a pre-existing retention bug found while
rewriting: the min-free loop read free space inside a loop that deleted nothing until
afterwards, so the reading never moved and one pass queued every survivor but one.
*Still deferred to #93:* the destinations list, per-destination scope tiers, S3.

---

## Sharing / Export — image export for web sharing *(done 2026-07-21, `feature/image-export`)*

First slice of the Sharing/Export arc (the destination model + a "Share" nav pane
remain deferred — see ROADMAP item 8). New Qt-free **`m110/webexport.py`**: take any
finished image (Siril `.png`, finished `.fit`/`.tif`, any raster) and write the
highest-quality file that fits an **optional** size budget. `export_for_sharing(src,
dest, *, strategy, max_bytes=None, …)` + a **quality ladder**: *lossless* strategy
encodes an optimized PNG and, only if a max is set and it's over, **binary-searches
the long edge** (Lanczos) for the largest lossless PNG that fits (fast
`compress_level` during the search, `optimize` + optional `pyoxipng` on the winner;
floor `MIN_LONG_EDGE`, else `ExportError`); *quality* strategy writes a
full-resolution JPEG (`subsampling=0` 4:4:4, `optimize`, **baseline not progressive**
— progressive tripped libjpeg's "Suspension not allowed" on incompressible frames
and buys nothing since Reddit & co. re-encode). **`max_bytes=None` = no maximum** —
lossless writes a full-res PNG, quality a full-res JPEG, no ladder. Reuses
**`build_images._open_image`** as the front end so exported pixels match the app's
render (FITS/float-TIF percentile-stretched to 8-bit RGB) — which also folds the
16→8-bit reduction in for free (on Mike's real 30 MB 16-bit M11 PNG that alone lands
~11 MB at *full resolution*, no downscale). Output format is deterministic from the
strategy — lossless→PNG, quality→JPEG — so the save panel's suggested extension is
known up front. `SAFETY_MARGIN` (~3 %) leaves rounding headroom; a byte-identical
lossless original that already fits is copied verbatim (fast path). `pyoxipng` is a
best-effort optional accelerator, **no new required dependency**. (Design note: an
initial version had a `SharePreset` registry with per-site presets — Reddit/Discord
budgets, per-platform `max_dim` caps; simplified to a bare **max-size + No-maximum**
control per user feedback, dropping presets, `formats`, and `max_dim`.)

UI: **`ui/export_dialog.py`** (`ExportShareDialog`) — a **Max size** spinbox + **No
maximum** checkbox (disables the spinbox), lossless/quality strategy radios;
**Export…** goes straight to the **native OS save panel** (`QFileDialog.getSaveFileName`,
native dialog left on → the Cocoa save sheet, freely rename + relocate), pre-filled
with `webexport.suggested_name` = **`[Object]-[maxsize]-[YYYYMMDD].[ext]`** (e.g.
`M42-20mb-20260721.png`, or `…-nomax-…`; the object token is the catalog id via the
detail pane's `_export_stem`). Then a `QThread` worker runs the ladder behind a busy
`QProgressDialog` (status = the ladder's step trail) with working Cancel; success
shows a summary + **Reveal**/**Open**. Entry points: the detail-pane gallery
right-click **and the hero image** (a shared `_run_image_menu` — same actions as a
gallery tile, acting on the hero's *source* file resolved via new
**`build_images.hero_source_path`**, which reads the `hero/<slug>.src` sidecar), plus
a **⤓ Export…** button in `image_viewer.py` (lazy-imported to avoid a cycle; the
viewer stays app-data-agnostic — `webexport` imports only `build_images`; the pane
threads the object id in as `export_stem`). Last strategy/max-MB/no-max/dir persist
in settings. External-folder output → no `.store_version` impact. Tests:
`tests/test_webexport.py` (ladder, fast path, FITS render, no-maximum, no-oxipng,
un-fittable, cancel/callbacks, filename/label helpers) + `tests/test_export_dialog.py`
(offscreen: No-maximum toggle + a stubbed end-to-end export). Verified on real
30 MB+ finished frames, the hero right-click wiring on a live object, and real cocoa
dialog grabs.
**Teardown gotcha:** the worker emits `done` from `run()` *as it returns*, so
`_finish_worker` must `wait()` for the thread before `deleteLater()` — otherwise
the deferred `~QThread` can run on a not-yet-finished thread and SIGSEGV during
event delivery (crashed on a real save; offscreen timing never reproduced it,
so the fix is `wait()`-before-delete, not a test).

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

- [x] **Crash (SIGSEGV) when a sync finished while an image viewer or menu was open**
  *(2026-07-31, `fix/refresh-during-modal`)*. Reported from 0.3.0b3 as "crashed while
  sitting in the background"; the crash report says otherwise — thread 0 died in
  `QAbstractItemView::mouseDoubleClickEvent` (via `QListWidgetWrapper`, i.e. one of the
  detail pane's gallery views) on a garbage `d`-pointer, with **`RefreshWorker` still
  running** on thread 8. Root cause, a textbook Qt use-after-free: the gallery opened
  `ImageViewer(...).exec()` **directly from `itemDoubleClicked`**, which Qt emits from
  inside the view's own C++ mouse handler. That nested event loop pumps everything —
  including the auto-sync's `done` signal (started by the very click that raised the
  window: `changeEvent` → `_do_refresh`). `_on_refresh_done` unconditionally
  `reload()`ed every page → `DetailPane.show_object` → `_clear()` → `deleteLater()` on
  the gallery. A `deleteLater()` issued *inside* a nested loop takes effect as that loop
  iterates, so the widget was destroyed before `exec()` returned and Qt resumed the
  double-click handler on freed memory. Reproducible as: leave the app in the background
  with an object open, click in, double-click a thumbnail, let the sync land, close the
  viewer. Fixed in two layers. **(1) Don't tear down under a nested loop** —
  `MainWindow._apply_refresh` (split out of `_on_refresh_done`) skips the page rebuild
  while `widgets.modal_loop_active()` (any modal dialog *or* popup menu) is true, parks
  the summary in `_pending_refresh`, and retries on a parented 250 ms timer; the
  prep-feedback and backup-nudge modals ride along, so a modal never stacks on a modal.
  **(2) Don't start a nested loop from inside an item-view handler** — `widgets.defer`
  (a `QTimer.singleShot(0, context, fn)`) pushes the viewer past the handler, and
  `widgets.connect_context_menu` replaces every `setContextMenuPolicy` +
  `customContextMenuRequested.connect` pair (Library table/grid, detail gallery + hero,
  Overview priority/member tables, Planning, Processing, Media) so no right-click menu
  spins its loop under a view either. Deferred openers work off a **snapshot** of the
  gallery items, so a rebuild landing in between can't shift the index. Layer 1 alone
  fixes the reported crash; layer 2 makes the whole class unreachable — the guarantee is
  "no nested event loop ever runs beneath an item-view frame", which also covers a
  right-click menu left open across a sync. Guarded by `tests/test_ui_modal_safety.py`
  (6 tests: the modal detection, refresh deferral + retry, the immediate path, `defer`,
  the context-menu wiring, and the exact double-click path with a stubbed viewer) — plus
  **`tools/repro_modal_uaf.py`**, a 40-line stand-in that proves the mechanism rather
  than the policy: offscreen, `buggy` exits **139** (dying exactly where the crash report
  did, before "returned from the double-click dispatch" prints) and `fixed` exits 0. It's
  a manual diagnostic on purpose — a regression segfaults the interpreter instead of
  failing an assertion, which would take a whole CI run down.

- [x] **Gallery file actions acted on the render, not the source file** *(2026-07-22,
  `fix/gallery-source-path`)*. Reported as "Reveal in file manager on a `.fit` opens the
  renders directory". Root cause: `images.json` only recorded `full` (the *displayable*
  full-size raster) **for viewable images** — for a FITS it was `None`, so the detail pane's
  gallery item fell back to `"path" = the thumbnail render`, and Reveal/Open/**Export** all
  used that one path. Two further instances of the same conflation: **Export for sharing on
  a `.fit` exported the ~480px thumbnail** instead of re-rendering the FITS at full
  resolution (a real defect in the just-shipped exporter), and `_hero_gallery_item` matched
  `hero_source_path()` against `"path"`, so a **FITS hero never matched** its gallery item.
  Fix: `build_images` now writes **`src`** (the actual source file, data-root-relative) on
  *every* record — `full` keeps its "displayable raster" meaning (still `None` for FITS) —
  and the UI carries both: `"path"` to display, `"src"` for Reveal/Open/Export and the hero
  match. `ImageViewer._normalize` gained the same optional `src` (defaulting to `path`, so
  the Media page and tuple-form callers are unaffected). Backward compatible: a store whose
  `images.json` predates this falls back to the old path and self-heals on the next refresh
  (which runs on launch/focus). Derived-only shape change → regenerated, no `.store_version`
  bump; recorded in [`DATA_MODEL.md`](DATA_MODEL.md). Guarded by
  `test_gallery_item_src_is_the_real_file_for_fits` + a `src` assertion in the FITS
  `images.json` test. *(Design note: the `renders/` cache stays — FITS/TIF aren't
  displayable by Qt at all, so a render is required, not merely an optimization, and it also
  backs row/grid icons, the Feed, heroes, and the publish pipeline.)*

- [x] **A single-object stack in a combined capture folder was read as the pair's stack**
  *(2026-07-22, `feature/stack-object-match`)*. Follow-up to the mtime→`DATE` fix below,
  and the one target that fix made *worse*. `Images/M81 M82/stacks/` holds
  `M_81_271x20sec_…_og.fit` — `OBJECT = "M 81"`, 271 frames, LP, 1883×3037 against the
  mosaic stacks' 1413×2187, with a sidecar reading `Object: M 81`. It was shot on
  2026-06-03/04 with the scope on M81 alone, but the frames (and the resulting stack) landed
  in the combined folder. It carries the folder's **newest header `DATE`**, so once
  selection started trusting DATE it won outright: In-stack **271** measured against the
  pair's **4799** captured frames = **94% rejected**, obvious nonsense (mtime had been
  landing on a 3250-frame starmask — plausible, and also wrong). Fix: on a target whose
  `slugs` name 2+ objects, a stack whose `OBJECT` header resolves to a **strict subset** of
  them is sorted *below* the stacks covering all of them. M81 M82 now reads its 1983-frame
  2026-06-04 mosaic stack. Deliberate properties: **header truth, not filename** — `OBJECT`
  is mapped by the same `scan_sessions.folder_to_slugs` already used for folder names
  (`"M 81"` → `[m81]`, `"M81 M82"` → `[m81, m82]`), so no naming convention is involved;
  **demote, don't drop** — implemented as a sort key, so if every candidate is partial one
  is still returned rather than regressing to no stack metadata; **absence of evidence never
  demotes** — a missing/unrecognized `OBJECT` keeps its place; and it **cannot fire on a
  single-object target**, since no non-empty strict subset of a one-object set exists.
  A *disjoint* `OBJECT` (a wholly unrelated stack) is left alone on purpose — that's a
  misfiled stack, a different problem, logged in BUGS.md. `load_catalog_slugs()` is resolved
  once per `build_processing`, and only when some target is combined. Guarded by
  `test_single_object_stack_demoted_on_a_combined_target`,
  `test_partial_stack_still_used_when_it_is_the_only_one`,
  `test_no_signal_or_unrelated_object_never_demotes` (parametrized over absent/empty/
  unrecognized/unrelated), and `test_single_object_target_is_unaffected_by_the_partial_rule`.

- [x] **"Latest stack" was picked by file mtime, so In-stack / "+ new" / rejection were
  wrong on a quarter of the library** *(2026-07-22, `feature/stack-date-selection`)*.
  `build_derived.read_latest_stack_metadata` sorted its candidates by
  `-f.stat().st_mtime` and read the first one carrying STACKCNT/LIVETIME. But ingest and
  Siril-import copy **bytes** (`shutil.copyfile`), so mtime is *copy* time: a superseded
  stack re-copied into `stacks/` later carries the newest mtime while being months old by
  content. Found on the live library's **M71** — a 118-frame stack (header `DATE`
  2026-06-10, copied in 2026-07-16) was beating the real 393-frame one (`DATE` 2026-07-10),
  so the Processing view read **In stack 118 (0:39)** instead of 393 (2:23) and **"+ new"
  417** instead of 123. **11 of 47 targets** were affected; four (M106, M13, M5, NGC 2903)
  showed a reprocess backlog that didn't exist and should have read `up_to_date`.
  The tell that this was the bug and not the design: `build_processing` *already* judged
  freshness by the stack's header `DATE` — the selection feeding it that DATE was the one
  place still trusting mtime. Fix: read every candidate's header up front and sort by
  header `DATE` (descending), mtime only as a fallback for a stack whose header has no
  DATE, and a dated candidate always outranks an undated one. The existing root/`stacks/`
  → `working_files/` directory precedence is preserved (see the open BUGS.md item).
  **Deliberately not** filtered by filename: a `starless_`/`_crop`/`_stretch` derivative
  *inherits* its parent's STACKCNT and LIVETIME, so it is arithmetically interchangeable
  with the parent — measured across the live library, name-filtering changed the math on
  exactly **one** target, and there for an unrelated reason (a stray single-object stack in
  the `M81 M82` folder, excluded only because it happened to end `_og`). The DATE sort also
  lands on the final product on its own, since the last processing step is written last —
  it fixed M51's cosmetic `starmask_…` display name for free. The rule this settles:
  **filename hints are for display decisions, where being wrong costs a label; never for
  arithmetic, where being wrong costs a number.** Guarded by
  `test_latest_stack_picked_by_header_date_not_mtime` (mtime-inverted two-stack fixture),
  `test_processing_derivative_yields_identical_numbers`, and
  `test_undated_stack_falls_back_to_mtime_and_loses_to_a_dated_one`.

- [x] **Intermittent CI segfault (exit 139) — the flaky test suite** *(2026-07-21,
  `fix/thumbnail-pool-teardown`)*. CI failed at random with `Fatal Python error:
  Segmentation fault` / exit 139 — **not** a test assertion — and passed on any re-run,
  the classic thread-timing flake. Root cause: `widgets.ThumbnailLoader` decodes
  gallery/row thumbnails on the **global `QThreadPool`**, and the pool was **never
  drained**, so a decode still running on a pool thread when Qt was torn down (test-session
  end, or app quit) ran native `QImageReader`/`QImage` code against a half-destroyed Qt →
  SIGSEGV on the worker thread (the crash log showed empty Python stacks on both threads +
  `PIL._imaging` loaded — a decode in flight). Fix: `widgets.drain_thumbnail_pool()` =
  `QThreadPool.globalInstance().waitForDone()`, called (a) after every test via an autouse
  `conftest` fixture so no decode outlives the test/QApplication, and (b) on
  `QApplication.aboutToQuit` in `main()`, which also fixes the same **rare crash on quit**
  for users. Deliberately avoided the QRunnable-ownership route (holding task refs +
  `setAutoDelete(False)`): a QRunnable isn't a QObject, so PySide can't track a pool-side
  delete, and that route trades the race for a double-free footgun. Guarded by
  `test_drain_thumbnail_pool_waits_for_inflight_decode`. (Same crash *class* as the export
  dialog's `~QThread` wait-before-delete fix — an async worker outliving its Qt teardown.)

- [x] **`filter` no longer counts as an enrichable metadata gap** *(2026-07-19,
  `fix/filter-not-enrichable-gap`; NGC 6960 follow-up)*. `filter` is a per-capture setting,
  so no reference catalog or Simbad ever provides it — yet it was in `_FILLABLE`, where it was
  a no-op in `_compute_fill`/`resolve_new_object` (the reference has no `filter`) and only ever
  produced a **false gap** in `_has_gaps`. That made objects otherwise complete offer "Enrich
  online" → "Simbad had nothing to add" (the NGC 6960 report). Dropped `filter` from `_FILLABLE`
  (still a real Library field via `_LIB_ORDER`). Guarded by `test_filter_is_not_an_enrichable_gap`.
  Note: doesn't change objects with *real* missing fields Simbad also lacks (e.g. NGC 6960 has no
  Simbad V-mag/size) — that's the deeper "surface objects that need enrichment" backlog item.

- [x] **Simbad enrichment `OverflowError` on Windows (int too large for C long)** *(2026-07-19,
  `fix/simbad-windows-overflow`; @devonjones, on C34/NGC 6960)*. With astroquery finally importing
  (#74/#75), the query itself failed: `Simbad lookup failed: OverflowError: … Python int too large
  to convert to C long (… col 'object_number_id')`. astroquery's **batch** `query_objects` injects
  Simbad's `object_number_id` (oid) as an **int64** column; astropy's VOTable parser overflows
  converting it on **Windows**, where a C `long` is 32-bit (the value is tiny — `1` for NGC 6960 —
  so it's the int64 column/null handling, not the magnitude). macOS/Linux have a 64-bit long, so it
  only bit Windows. The **singular** `query_object` returns none of that (no int64 columns; verified
  its colnames), so `catalog.resolve_object_online` now loops `query_object` per name, keyed by the
  input name (the singular query resolves the name itself — no `user_specified_id` echo needed).
  Per-name is fine: single lookups are the common case, and bulk enrich is backgrounded/cancellable.
  Graceful: a per-name error is tolerated when others resolve (partial), all-error surfaces
  `OnlineLookupError`, an unresolved name is skipped quietly. Guarded by
  `test_resolve_online_queries_per_name_not_batch` (+ partial / all-fail / no-match). The third and
  final layer of the Windows-enrich fix (after astropy metadata #74 + parser tables #75).

- [x] **Frozen astropy incompletely bundled → planning/ranking dead + enrich dead; + About
  reported an older beta** *(2026-07-19, `fix/issue-74-astroquery-metadata-and-version`; #74 +
  #75, @devonjones on Windows 0.2.0-beta.5)*.

  **astropy unit-parser tables not bundled as files (#75, the root one).** In a *real* frozen
  build, `import astropy.units` dies with `ValueError: 'm / (s)' did not parse … No such file:
  …/astropy/units/format/generic_parsetab.py`. astropy's PLY unit parser needs its generated
  tables (`generic_parsetab.py`/`generic_lextab.py`) as **files on disk**; `collect_submodules`
  puts them only in the **PYZ**, so the parser can't find the file, tries to regenerate + write
  next to the module, and fails in a read-only bundle. The first unit parse happens *at
  `import astropy.units`*, so **every** coordinate transform dies → the prioritizer shows
  "astronomy engine unavailable" and Plan-a-night can't run (#75), **and** astroquery — which
  imports astropy.units — can't load either (so this also blocked #74's enrich, before the
  metadata check below). **This was missed when the codata2018 planning fix shipped because that
  fix was validated against a loose-file PYZ *reconstruction* (where the .py table existed on
  disk), not a real PyInstaller build — the lesson: validate frozen fixes against a real build.**
  Fix: `hook-astropy` `collect_data_files("astropy.units.format", include_py_files=True)`
  (confirmed against a real minimal build: `import astropy.coordinates` + transforms then work).

  **astropy metadata not bundled (#74's second layer).** With units working, astroquery next
  hit `astroquery.utils.commons` → `astropy.utils.introspection.minversion('astropy')` **at
  import**, which reads astropy's **dist-info** → `KeyError('astropy')` (specs bundle astropy's
  modules but not its metadata). Fix: `copy_metadata("astropy")` in all three specs (the frozen
  `Simbad()` then imports + configures). Also **log the swallowed import error** in
  `catalog.resolve_object_online` — it was hidden behind the generic "not available" message.

  **Version reported an older beta (#74).** The Windows Inno installer `[Files]` adds/overwrites
  but never deletes, and AppVersion is numeric `0.2.0` for every beta — so an in-place upgrade
  left the old `m110-0.2.0bN.dist-info` beside the new one and `importlib.metadata.version` read
  the alphabetically-first (older) one. macOS (.app replace) / Linux (single-file AppImage)
  don't accumulate → Windows-only. Fix: `[InstallDelete] {app}\*` (clean replace) +
  `updates.current_version()` prefers compiled-in `m110.__version__` when frozen. Disambiguated
  by the reporter's clean-install test (version fixed by reinstall, enrich/ranking did not).

  Guarded by `test_hook_astropy_bundles_unit_parser_tables`, `test_specs_copy_astropy_metadata`,
  `test_current_version_prefers_dunder_when_frozen`, `test_online_import_failure_is_logged`.
  **Rebuild required.**

- [x] **Disabled menu items didn't look disabled** *(2026-07-19,
  `fix/menu-disabled-items-greyed`; #64 follow-up)*. A beta user found the Library
  right-click **Fill in missing metadata** / **Enrich online** items "non-functional" —
  they weren't recognized as *greyed out*, just as dead (no hover highlight, no response).
  Root cause: the theme QSS styles `QMenu::item` (padding + `:selected`), and once a
  subcontrol is stylesheet-drawn Qt stops auto-greying its **disabled** state — so a
  disabled entry rendered at full-strength text. Buttons already had the fix
  (`QPushButton:disabled { color: text_disabled }`); menus never got the equivalent. Fix:
  add `QMenu::item:disabled { color: text_disabled }` — app-wide, every menu. Kept the
  data-gating (Fill/Enrich are correctly disabled when an object has no fillable gaps —
  most catalog objects carry full reference metadata) rather than the earlier
  always-selectable-then-modal approach (rejected: a modal to dismiss per complete object).
  Extracted `_object_menu` (build menu + actions, no `exec`) from `_on_context_menu` so the
  enabled state is testable headless — PySide6's `QMenu.exec` can't be monkeypatched (it
  blocks). Guarded by `test_disabled_menu_items_are_greyed` (asserts the QSS rule, per the
  can't-paint-native-menus-offscreen gotcha) + `test_context_menu_fill_enrich_reflect_gaps`.

- [x] **Import silently skipped (then archived) a re-processed same-name file** *(2026-07-18,
  `feature/import-collision-policy`)*. *Import finished work* routed a finished `.png`/stack
  to `finished/`/`stacks/` and, on a name collision, did `if dest.exists(): skipped` — the
  incoming file was **not** imported, and the default `cleanup="archive"` then swept it into
  `siril/[<FILTER>/]archive/<ts>/`. So a re-processed, *improved* render saved under the same
  name appeared to vanish (it was moved, never discarded — but out of `finished/` and out of
  the sandbox root). Fix: **content-aware keep-both** (`_resolve_import_dest` + `_same_bytes`):
  a byte-identical incoming file is a true duplicate → skip (no pile-up; dedupes against every
  existing `<stem>-N` sibling), a **different** one lands as the first free `<stem>-N<ext>` so
  both are kept. `has_unimported_output` now uses the same disposition (a differing same-name
  file counts as unimported, so the Processing "Ready to import" flag fires); `scan_finished`
  marks only true duplicates `already` (a re-process is checked by default) and carries a
  `note` ("kept as M42-2.png") the import dialog shows; **hero pinning follows the name the
  render actually landed under** (a renamed hero would otherwise point at a missing file).
  Deliberately not `filecmp.cmp` — its stat-signature cache can return a stale verdict when a
  same-size file is rewritten within the mtime resolution. Never clobbers, matching the store's
  non-destructive ethos.
- [x] **"Enrich online" dead in packaged builds — astroquery never bundled** *(2026-07-19,
  `fix/bundle-astroquery-online`; issue #64, reported by @devonjones on Windows 0.2.0-beta.4)*.
  Right-click → **Enrich online** (or Add object → **Look up online**) in a packaged build
  raised `OnlineLookupError("… pip install 'm110[online]'")` — useless advice for a frozen app
  with no pip. Two-part root cause: (1) astroquery is the optional **`online`** extra, and the
  build scripts / CI install only **`.[build]`**, so astroquery wasn't present at build time
  and PyInstaller couldn't bundle it; (2) even once installed, astroquery/pyvo/keyring have
  **no PyInstaller-contrib hooks** and load submodules/data dynamically (keyring discovers its
  backends via entry points; `astroquery.query` imports keyring at import), so a naive bundle
  would still miss pieces — the hook-astropy `codata2018` lesson. Fix: (a) the **`build`** extra
  now self-references **`m110[online]`**, so every `pip install -e '.[build]'` pulls astroquery
  (source installs stay lean — `online` is still opt-in); (b) all three specs `collect_submodules`
  + `collect_data_files(..., excludes=["**/tests/**"])` + `copy_metadata` for astroquery/pyvo/
  keyring (certifi/urllib3/charset_normalizer have their own contrib hooks; requests/bs4/html5lib
  are static). Excluding test fixtures kept the real runtime data (incl. `simbad/data/
  query_criteria_fields.json`) while dropping ~430 test files → the added bundle weight is
  mostly code, not the feared 28 MB. Also made the "astroquery missing" message **build-aware**
  (`catalog._astroquery_missing_message`): frozen builds say "not available in this build —
  please report" instead of the impossible pip line; source keeps the extra hint. Validated the
  specs compile + the collection runs (692 modules, Simbad core + data + a keyring backend
  present); **the frozen import still needs a per-OS build to confirm** (esp. keyring on Windows).
  Guarded by `test_packaging_deps` (build→online) + build-aware-message tests. **Rebuild required.**

- [x] **Mount mode was a hardcoded date guess, not reported data** *(2026-07-18,
  `fix/mount-mode-eqmode`)*. `scan_sessions` set `mount_mode` from `EQ_FROM = 2026-03-17` `scan_sessions` set `mount_mode` from `EQ_FROM = 2026-03-17`
  (this store's Seestar switchover) — a Mike-Seestar-specific constant that would mislabel
  **every other user** (an alt-az-only shooter's post-March sessions all tagged "EQ") and
  **every other device** (a Dwarf date-stamped after the cutover → "EQ"). Turns out the
  truth is in the header: **both** the Seestar and the DwarfLab Dwarf 3 write an `EQMODE`
  card (int `1`=Equatorial / `0`=Alt-Az, comment "Equatorial mode") — verified across real
  files of both devices (Seestar back to its first 2026-03-13 alt-az night = `EQMODE 0`;
  Dwarf startrails `0`, M86 EQ run `1`; absent only on Dec-2025 pre-firmware Dwarf subs).
  Fix: `_read_eqmode` + `_mount_mode` read `EQMODE` (device-agnostic) and fall back to the
  legacy date heuristic **only** when it's absent, read **once per session-segment** (mount
  mode is constant within a capture run — negligible next to the filename fast-path). Also
  surfaced two Seestar-only header niceties for the rejection-analysis backlog: `SITELAT`/
  `SITELONG` (so altitude is self-contained per Seestar sub — Dwarf headers lack them) and
  `FOCUSPOS`. `mount_mode` is display-only (Sessions table + publish templates), so no logic
  changed. Sibling `pre_new_start` (`NEW_START = 2026-04-04`) is still a store-specific
  guess — noted, not fixed (it's a collection-reset marker, not a header fact).
- [x] **Planning fails loudly, not silently, when astropy can't load** *(2026-07-18,
  `fix/planning-astropy-diagnostics`)*. Follow-up to the packaged-build astropy breakage:
  the reason that bug was invisible for so long is that the engine **swallowed** every
  astropy failure with no signal. `prioritize.build_contexts` caught each per-target
  `observability()` exception into `obs=None` and returned a quietly degraded ranking; the
  planner worker caught `plan_night`'s exception into `plan=None`, and the UI rendered that
  as *"No astronomical darkness for that night here"* — misreporting an engine failure as
  an astronomical fact. Now: (a) `build_contexts` logs one WARNING (with the first
  traceback) when observability fails for any target, and `_PlannerWorker` logs the
  `plan_night` traceback — so the real error (`ModuleNotFoundError: astropy.constants.
  codata2018`, or anything else) lands in `~/.m110/logs/m110.log` and the crash report; (b)
  the Planning page distinguishes **`plan is None`** (engine unavailable → "the astronomy
  engine isn't available") from a real plan with an **empty window** (genuine no-astro-dark
  night → keeps the darkness message); (c) Recompute's status says "ranking degraded —
  astronomy engine unavailable" when no target got an observability result, instead of the
  reassuring "up to date". Engine stays Qt-free (stdlib `logging`). Tests: a raising
  `observability_fn` still returns contexts + logs the warning; the planner-ready handler's
  two branches produce distinct messages; the degraded-status path.
- [x] **Session planning dead in every packaged build (astropy dynamic submodules missing)**
  *(2026-07-18, `fix/packaging-astropy-dynamic-submodules`; reported on 0.2.0-beta.4 macOS)*.
  In the **frozen** app (all three platforms), the entire Planning pane was silently broken:
  **Recompute** returned in <0.1 s with a degraded goal+completion ranking (every target's
  `obs=None` — verified in the live `derived/prioritized.json`), and **Plan a night** always
  reported *"No astronomical darkness for that night here."* Root cause: the local
  `packaging/common/pyinstaller-hooks/hook-astropy.py` override had replaced the upstream
  hook's `collect_submodules("astropy")` with **four explicit `hiddenimports`**, which left
  out astropy's **dynamically-imported** submodules — the load-bearing one being
  `astropy.constants.codata2018`, which `astropy.constants.config` pulls via
  `importlib.import_module()` (invisible to static analysis). So in the bundle every
  `import astropy.units`/`astropy.coordinates` raised `ModuleNotFoundError: No module named
  'astropy.constants.codata2018'` — swallowed per-target by `prioritize.build_contexts`
  (`except Exception: obs = None`) and caught by the planner worker (→ the misleading "no
  darkness" message). The override existed because the upstream blanket
  `collect_submodules("astropy")` imports `astropy.visualization.wcsaxes`, whose
  `pytest.importorskip("matplotlib")` raises pytest's `Skipped` (a `BaseException`) and
  aborts the build. Fix: `collect_submodules("astropy", filter=<exclude
  astropy.visualization>)` — collects all the dynamic submodules (verified: 921 modules incl.
  `codata2018`/`iau2015`/`codata2022`) while the filter stops the walker from importing the
  matplotlib-requiring subtree, so the build no longer chokes. Diagnosed by extracting the
  app's `PYZ.pyz` and reproducing the frozen import (`ModuleNotFoundError` on `codata2018`),
  then confirming end-to-end that supplying the missing constants modules restores the
  sun/moon transforms. Bundle-only (running from source was never affected); the shared hook
  fixes macOS/Linux/Windows at once. **Requires a rebuild to reach users.**

- [x] **Siril script crash from a packaged launch (two Qt sets in one process)** *(2026-07-18,
  `fix/siril-qt-env-leak`; reported on 0.2.0-beta.3 macOS)*. "Process in Siril" from the
  **frozen** M110.app made Siril's `sirilpy` (PyQt6) scripts SIGABRT at startup: objc
  duplicate-class warnings + "loading two sets of Qt binaries" + "Could not load the Qt
  platform plugin cocoa", because M110's PySide6 QtCore/QtGui frameworks loaded alongside
  Siril's own PyQt6. Vector: the PyInstaller PySide6 runtime hook exports **`QT_PLUGIN_PATH`**
  + **`QML2_IMPORT_PATH`** into `M110.app/Contents/Frameworks` (and prepends `_MEIPASS` to
  `DYLD_LIBRARY_PATH`); `open` forwards our env to Siril, so Siril's Python was pointed at
  *our* Qt plugins and pulled in our Qt. `launch._child_env` already cleared the DYLD half
  (via `_LIBPATH_VARS`, dropped since the hook saves no `_ORIG`) but not the Qt plugin
  paths. Fix: strip **`_QT_LEAK_VARS`** (`QT_PLUGIN_PATH`/`QT_QPA_PLATFORM_PLUGIN_PATH`/
  `QML*_IMPORT_PATH`) in `_child_env`. Only manifests in the **frozen** build (from source
  those vars are unset), so it's guarded by an env-sanitizer unit test
  (`test_child_env_strips_qt_plugin_paths`), not a live launch — the definitive check is a
  packaged M110.app driving a Siril script. Confirms the CLAUDE.md rule that a dev-run can't
  catch bundle-only env leaks.

- [x] **#56 — Windows build crashed on launch (`tzdata` / `zoneinfo`)** *(2026-07-17,
  `fix/windows-tzdata`; reported by @devonjones on 0.2.0-beta)*. The frozen Windows app
  quit at import with `zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with
  key UTC'` — `planning.py` resolves `_UTC = ZoneInfo("UTC")` at module import (reached
  from `main` via `night_timeline → planning`), and **Windows ships no system IANA tz
  database**, so `zoneinfo` needs the `tzdata` PyPI package as its fallback. `tzdata` was
  neither a declared dependency nor collected by the PyInstaller specs, so nothing was
  bundled. Fix: add **`tzdata`** to core `dependencies` (unconditional — harmless on
  macOS/Linux, which search the OS db first and only fall back to the package), and
  collect it in all three specs (`collect_data_files("tzdata")` for the ~600 tz files +
  `collect_submodules("tzdata")` so `zoneinfo`'s region subpackages import). Reproduced
  locally with `zoneinfo.reset_tzpath([])` (no system db) → the exact error; guarded by
  `test_zoneinfo_resolves_without_a_system_tzdb`. macOS/Linux were unaffected (system tz
  db present) but now bundle it too, for self-contained builds.

### Archived from BUGS.md, 2026-07-15 housecleaning

- [x] **Processing tables: default sort + sort persistence** *(2026-07-15,
  `feature/processing-sort`)*. The grouped tables now default to **"+ new"
  descending** (most new lights on top — "what needs restacking most"), and the
  user's per-group sort choice is remembered across `reload()` — previously the
  window-focus auto-sync rebuilt every table and reset the sort indicator to
  none. In-memory per session (`ProcessingPage._sort`, keyed by group), recorded
  via `sortIndicatorChanged`. Test in `tests/test_ui_library.py`.

- [x] **Processing page fixes.** (1) Tables are now **sortable by column**
  (click a header; numeric columns sort by value via `NumItem`, not string) —
  the queue order is the initial view until a column is picked. (2) Each grouped
  table now **sizes to fit all its rows** (page scrolls) instead of a capped
  min-height that truncated the "out of date" table. (3) `build_processing` now
  counts **finished/ renders** (raster or FITS) as processed output, so imported
  objects (e.g. from the Astronomy library) whose only processed output is a
  finished PNG — no raw Siril stack — no longer misclassify as **not processed**
  (they read up-to-date / out-of-date). `FINISHED_EXTS` added; regression test in
  `tests/test_build_derived.py`.

- [x] **Processing freshness + rejection% audit (mtime → capture date).** Two
  linked bugs surfaced on the imported ~/Astronomy library: (1) **Rejection%** was
  `1 − STACKCNT / total_frames_captured`, so frames shot *after* the stack inflated
  it (M64 read 67%, M5 52%) instead of Siril's real ~6–10%. (2) Objects with
  hundreds of unintegrated frames read **up_to_date** because the mtime comparison
  failed — the bulk import copied lights + renders with fresh/clustered mtimes, so
  "newest light < newest processed" even though the stack predated the new lights.
  Fixed by judging freshness on **capture date vs. the stack's FITS `DATE`**: frames
  captured after the latest stack ⇒ `out_of_date`; rejection is measured against
  `frames_at_stack` (frames present when stacked), now emitted in `stack_meta`.
  Falls back to the mtime comparison only when no stack `DATE` exists. On the live
  store this moved 14 objects from up_to_date → out_of_date and normalized every
  rejection% to a plausible range. Tests in `tests/test_build_derived.py`;
  `DATA_MODEL.md` updated.

- [x] **Lights/products classification (M27 phantom-`OTHER`-filter bug).** Processing
  reported a huge "+ new" backlog that Siril didn't see. Root cause was **not** the count
  (it was correct) but **processing by-products polluting `lights/`**: the ~/Astronomy
  import (`Images/FITS/<obj>/` is a flat mix of subs + Siril/PixInsight outputs) filed
  products like `M27_final.fit` / `starless_*` / `*_spcc` into `lights/` (19 objects, 179
  files). Prep's `_lights()` then treated any `.fit` as a sub, so unparseable products fell
  into a phantom **`OTHER`** filter → M27 looked multi-filter and spawned a bogus
  per-filter job. Three components disagreed on "what is a sub." Fixed with **one shared
  definition** — `config.is_light_frame` (a `.fit` that isn't a `config.is_processing_product`;
  a *denylist* that fails toward "it's a light", so unknown-rig subs like a future Dwarf's
  aren't misrouted): **(A)** import diverts non-sub `.fit` to a new `working_files/` tier
  instead of `lights/` (`ingest._emit_files`); **(B)** `siril._lights()` ignores products,
  killing phantom filters; **(C)** `ingest.plan_lights_cleanup()` relocates already-mis-filed
  products out of `lights/` (preview-then-confirm via `apply_ops`). Tests in
  `tests/test_lights_classification.py`; `working_files/` documented in `DATA_MODEL.md`.

- [x] **#25 — Optional import of per-sub `.jpg` previews** *(done — `feature/sub-previews`).*
  The Seestar saves a full-size `.jpg` beside every `.fit` sub in a `_sub` folder; ignored
  by default. A preference (**default off**, `import_sub_previews`, Preferences → Import)
  now imports them into a dedicated **`Images/<target>/previews/`** archive (new `preview`
  kind) — **decided:** kept out of `lights/` (sub-only invariant) and out of the gallery/hero
  tiers (a long capture would otherwise flood the gallery with per-sub previews). The `_thn`
  thumbnails stay ignored either way. Lazily created → no `.store_version` bump.

- [x] **#26 — Holding-area identification aids** *(done — `feature/holding-aids`
  + earlier `feature/holding-discard-reveal`).* The 6c panel now helps *figure out* what
  a held file is: (a) ✅ **Reveal** the file location (per-row button → OS file manager);
  (b) ✅ **preview/inspector** — double-click a held row → `HoldingInspectDialog`: FITS
  header view (OBJECT/IMAGETYP/FILTER/RA/Dec via `ingest.frame_info`) + a thumbnail
  preview; (c) ✅ **suggested identity** — `ingest.annotate_holding` suggests the object
  (OBJECT header → slug, else nearest catalog by RA/Dec) + kind (IMAGETYP), **pre-filling
  the Object/Kind pickers**. ✅ **Discard** — per-row button deletes a held group
  (confirm modal; `ingest.discard_holding`, Inbox-scoped + prunes emptied folders).
  *(Headerless plate-solving stays deferred → item 9.)*

- [x] **#32 — Subfolder scanning inconsistent** *(done — `fix/import-subfolder-scan`;
  beta-tester report, Windows).* Two scan paths had **different recursion depth**: the
  Import page used the recursive `scan_directory_plan` (`os.walk`), but the (now-dead)
  device/staging plans used a shallow one-level `_scan_base` that silently missed nested
  subfolders. Unified everything on the single recursive scanner (`scan_seestar_plan` /
  `scan_staging_plan` now delegate to it; `_scan_base` retired), so the importer is
  **deterministic + depth-agnostic** regardless of entry point. Added **diagnostics**: the
  `m110` logger records every directory visited, its detected layout, per-dir counts, pruned
  subtrees, and a final scan summary (→ `~/.m110/logs/m110.log`, so this class of report is
  answerable from the log). Added a user-visible **post-scan headline** on the Import page
  ("Found N object(s), M file(s) to import; K file(s) → holding area") + a clear empty-result
  message, so files routed to the holding area (the most likely "didn't get scanned" cause)
  are no longer a mystery. `ingest.scan_summary()` + tests (`test_ingest.py`: nested-subfolder
  regression for both plans, summary counts).

- [x] **#33 — Multi-select assign in the holding area** *(done —
  `feature/holding-multiselect-assign`; beta-tester request).* Working the holding area
  row-by-row was tedious. The holding table is now **row multi-select** (click the
  Source/Files/Size cells; Ctrl/Shift extend), with a **bulk bar** below it — "Selected →
  [Object] [Kind] [Assign N selected]" — that assigns every selected row to one object +
  kind in a single confirmed, threaded move (`ingest.assign` per group → one `_ApplyWorker`
  over the combined ops). Per-row Assign stays for one-offs. Tests in `test_ui_import.py`
  (enable logic + a two-folder bulk assign lands both under one object).

- [x] **#34 — Arbitrary object names in the holding area** *(done —
  `fix/holding-arbitrary-object-name`; beta-tester report).* The Object picker was already
  an editable combo and `ingest.assign` already accepted any name (an off-catalog target is
  created + promoted to the Library on refresh) — but it **looked like a fixed drop-down**, so
  a tester thought they couldn't assign files for objects not yet in the library. Made the
  affordance obvious: the picker now starts **empty with a "Type a name or pick…" placeholder**,
  a contains-match completer, and a tooltip; the holding header spells out that you can type any
  name. Engine unchanged. Tests in `test_ui_import.py` (combo is empty/editable/typeable) +
  `test_assign_accepts_arbitrary_object_name`.

- [x] **#40c — Capture targets were promoted into the object axis** *(`feature/fix-capture-target-axis`;
  store **v3→v4**).* The two axes are **many-to-many by design** — one `M81 M82` capture feeds two
  catalog objects — but `add_captured_objects` promoted the *capture target* "M81 M82" into the
  **Library** as a synthetic pseudo-object (`m81-m82`, type "unknown"). That fake object then
  **shadowed `folder_to_slugs`** (its first branch returns the whole slug once it's a known
  catalog slug), so the combined folder resolved to `['m81-m82']` instead of `['m81','m82']` —
  self-reinforcing, and the pair's integration never credited M81/M82 (M82 read **13 min** while
  the pair had ~29 h). Fixes: (a) `add_captured_objects` maps a folder to the objects it
  *contains* and promotes **those members** (a combined capture promotes both); only a folder
  matching **no** catalog object becomes an object itself; (b) `scan_sessions.load_catalog_slugs`
  resolves against **Library ∪ bundled reference** (a fresh store could never split a pair), and
  the splitter normalizes spaced designations (`M 97 M 108` → `M97 M108`); (c) `build_totals`
  uses the same slug universe; (d) **migration** `_prune_combined_target_objects` drops the
  pseudo-objects (live store: `m81-m82`, `m108-m97`, `m-97-m-108`), non-destructively —
  `Objects/<id>/` journals are left alone; (e) the Processing page's first column is relabelled
  **Object → Target** (a row is a capture target = one stack to process; a combined target and a
  solo capture of the same object are both legitimate rows — the old label is what made them read
  as duplicate objects). *Supersedes #40b, which wrongly proposed collapsing the queue.*
  **Hardening:** `folder_to_slugs` checks the 2+-member split **before** the whole-slug match,
  so a pseudo-object reintroduced into the Library can't resurrect the shadowing (see #40d).

- [x] **#3 — Manual Pin/Deprioritize priorities** *(the self-contained slice of ROADMAP
  item 1; `feature/manual-pins`, term renamed from "Mute" in `feature/deprioritize-rename`).*
  Ships ahead of the scorer so the Summary **Priority targets** view has a reason to exist
  for a fresh user (empty `priorities.toml`). Per-store `pins.toml` (`m110/pins.py`, survives
  regeneration; legacy `"mute"` value read-mapped) + right-click **Pin/Deprioritize** on
  Library, Goals, **and the Priority-targets rows** with a ▲/▼ marker; pinned objects surface
  in Priority targets (deprioritized excluded) with an empty-state prompt. Today's slice:
  **pin = always shown, deprioritize = hidden** — no season/rank logic until the scorer
  composes over it (numeric nudge + `computed rank + overrides` deferred with the engine).

- [x] **#40 — Non-overlapping, 10-min-aligned sequence** *(PLANNING_ROADMAP Phase 4,
  `feature/session-planner`.)* `planning.sequence_plan` — pure/deterministic (tested on
  synthetic plan dicts, no astropy) — implements the v1 logic verbatim: object 1 = the
  highest-priority target startable right at astronomical dark (clear + under the #37
  ceiling); duration = dark-span ÷ count on 10-min ticks, shortened when the target reaches
  **deep-stack** sooner or its own up-window ends; object N+1 starts at object N's end;
  near-equal scores (2-dp quantum) → the target **closer to setting** first. Gaps advance
  tick-by-tick until something rises. (Grouping by sky region stays a later version.)

- [x] **#41 — Schedule output format** *(shipped with #40.)* The field guide renders a
  `## Schedule` table — object name, start, duration, altitude at start (`^` when a soft
  ceiling let it start high), filter, **moon impact re-evaluated at each slot's start**
  with the #36 plain-language footnote. Object 2 start = object 1 end; no slew/focus
  modelling. Season labels were dropped from the Notes beside dated recommendations
  (review §5e / Phase 4.3).

- [x] **#42 — Target-count control** *(shipped with #40.)* A **Targets** spinbox on the
  plan row (default **4**, range 1–20); changing it re-sequences the cached plan
  instantly (no astropy recompute). The plan table shows the sequenced slots; move
  up/down **reflows** with the forced order, unchecking a row **excludes** the target
  and reflows (a replacement may take the slot; regenerate resets).

- [x] **#43 — Date-picker broken** *(PLANNING_ROADMAP Phase 5, `feature/session-planner`.)*
  The calendar popup's day grid is a **QTableView subclass**, so the theme's generic
  `QTableView::item` padding squeezed the fixed-size day cells until two-digit dates and
  weekday names elided to "…", and the muted table `selection_bg` made the picked date read
  as disabled. Reproduced offscreen (QSS-driven → shows under Fusion too), fixed with scoped
  `QCalendarWidget` rules in `theme/qss.py` (zero item padding · accent selection · nav-bar
  styling), re-render verified in light + dark; a generated-QSS regression test guards it.
  *One live-app eyeball on macOS still worthwhile (native paint isn't pixel-testable
  offscreen).* Shipped alongside: `NightTimeline` overlays — moon track (☾, dashed, only
  while up), the start-ceiling dotted line, and the scheduled slot bands in series colors.

- [x] **#35 — Single ranked view + retire `priorities.toml`.** *(PLANNING_ROADMAP Phase 1.1,
  `feature/session-planner`.)* The prioritizer (`prioritize.py`) was already the single
  source the Planning UI consumes; the real defect was that `build_contexts` read object
  `type` only from the Library, so every **uncaptured** active-goal member scored as
  `type:"unknown"` → wrong filter (IRCUT) + the 90-min deep floor instead of the type-aware
  240/360. Fixed by falling back to the **bundled reference** for type (→ correct
  filter/threshold across the whole sweep). Also **retired the legacy curated path** end to
  end: `build_derived` no longer reads `priorities.toml` or writes `priorities.json`;
  `build_priorities`/`derived.load_priorities`/`select.filter_priorities` deleted; the
  published site's Priority Targets section dropped (the curated data was personal + not
  generalizable). `track=false` campaign exclusion is covered by a pin *deprioritize*.

- [x] **#36 — Moon model "wrong" (planner header).** *(PLANNING_ROADMAP Phase 2,
  `feature/session-planner`.)* **The astronomy was never wrong** — reproducing the night showed
  the engine computes Jul 18 correctly (27% / +5.8° / sets ~23:05). The bad plan file was a
  **date/plan desync**: generated **Jul 13** (its dark window says so) but *titled* Jul 18 —
  `_save_field_guide` read the date widget at save time while the astronomy was from Generate
  time, and Jul 13–14 was the **new moon**, hence "0% lit, −17° at dusk". Fixed both ends
  (the plan's `day` rides in `_plan_meta`; a date/location change invalidates the stale plan),
  plus the genuine model upgrades: **per-slot moon** (`plan_night` → `{illum, alt, set_time,
  rise_time, track}`; header "29% lit · up at dusk (+6°) · sets 23:05"), the **Moon column
  gated on moon-up** at each target's best time ("—" when down), and **filter-aware
  `moon_impact`** (illumination × proximity, narrowband ≈ near-immune) with an explanation
  footnote/tooltip. Regression tests pin the Jul 13 (new moon, down all night) and Jul 18
  (crescent, sets 22–23h) nights + the exact save-desync flow. This is the correctness half of the #193 ask to
  *explain* moon impact.

- [x] **#37 — Start-altitude ceiling ignored in slot selection.** *(PLANNING_ROADMAP Phase 3,
  `feature/session-planner`.)* The 2026-07-18 plan put 4/8 targets at over-ceiling best times
  (M29 88°, Sh2-112 84°, Sh2-115 83°, M39 82°). Shipped as a **typed per-device ceiling**
  (2026-07-14 research, table + sources in PLANNING_ROADMAP Phase 3): Seestar S50/S30/S30 Pro =
  **hard** 78° app start-refusal (S30/S30 Pro assumed from the shared app — unverified);
  Dwarf 3/Mini alt-az = **soft** ~80° quality guideline (no firmware refusal found).
  `planning_config.DEVICE_PRESETS` carries the data; `planning.pick_start` (pure; sky.py's `^`
  semantics) proposes the highest clear sample at/below ceiling−3° margin (the ~75° practical
  rule) — rising- or setting-side, never the transit; soft-ceiling fallback renders `^`. Field
  guide + Planning table show **Start** instead of transit; moon impact anchors to the start
  slot. Live Jul-18: M29 88°→02:55@74.9°, M39→01:35@75.0°, Sh2-112→03:05@74.7°, Sh2-115→00:35@74.9°.

- [x] **#38 — Feasibility / worthiness gate.** *(PLANNING_ROADMAP Phase 1.3,
  `feature/session-planner`.)* No new stored fields were needed: the reference already **types**
  the oddities (M40 = `double_star`, M73 = `asterism` — the type is the non-DSO flag), and mean
  **surface brightness derives** from the existing `magnitude` + `size`
  (`prioritize.surface_brightness`, anchored to published values: M31 22.1, M33 23.1 mag/arcsec²).
  `feasibility_score` **multiplies** the whole score (infeasible can't be rescued by urgency/goal):
  non-DSO → 0.05 · SB ramp 1.0→0.3 across 22–25 · unknown SB neutral, except mag-less **diffuse
  nebulae** at a mild 0.8 prior (the faint-Sharpless-on-50mm case — Simbad has no V-mag for most,
  so a backfill can't gate that set). Ranked rows carry `non_dso` + `factors.feasibility` for UI
  annotation. Live store: M40 145/146, M73 146/146; top-10 = showpieces.

- [x] **#39 — Combined-folder under-count in the prioritizer.** *(PLANNING_ROADMAP Phase 1.2,
  `feature/session-planner`.)* `prioritize.build_contexts` now rolls each combined/mosaic
  capture folder's integration up into its constituent **catalog members** (reusing
  `scan_sessions.folder_to_slugs`) and drops the synthetic combined slug from scoring.
  Verified on the live store: `m81` → 1870 min (126 solo + 1744 pair), `m82` → 1757 min
  (13 + 1744), `m81-m82` dropped (was 126/13/1743 fragments with `obs:null`). Scope was
  **prioritizer-only** by decision — see #40b for the engine-wide rollup.

- [x] **Empty-state guidance** *(done — `feature/onboarding`).* A fresh store (nothing
  captured) shows a **welcome + "Import images…" CTA** on the Summary landing page
  (`go_to_import` → Import page) instead of empty tables, and the Library stat row shows
  an "empty — Import or add an object" hint. The seed `priorities.toml` now ships **empty**
  so a stranger doesn't inherit hand-authored targets.

- [x] **First-launch data-folder prompt** *(done — `feature/onboarding`).* `FirstRunDialog`
  (`config.is_first_run()` + `ui/first_run_dialog.py`) prompts for a data folder on a genuine
  first launch, persists it, and never re-prompts a returning user.


Concise log; full root-cause writeups are in git history. Lessons that constrain
future work live in `CLAUDE.md` "Gotchas / lessons learned".

**Beta fast-follows (post-`v0.1.0-beta.1`)**
- **Import: selection checkboxes rendered blank past the first row**
  (`feature/fix-import-checkbox-paint`; reported against 0.1.0b2, present since the
  table shipped). On macOS only the *current* row's check indicator painted — every
  other row's was invisible, and clicking one appeared to do nothing. Root cause was
  **QMacStyle**, not app code: it fails to paint `PE_IndicatorItemViewItemCheck` for
  non-current rows. Reproduces with a bare `QTableWidget` and **no stylesheet**;
  Fusion paints all rows. The model was never wrong — `SE_ItemViewItemCheckIndicator`
  returned a valid rect for every row and synthetic clicks toggled every row, so
  clicks *were* registering and the cell just never repainted (which is why Select
  all/none, hitting the one row that paints, seemed to be the only thing working).
  Fix: explicit token-driven `::indicator` rules in `theme/qss.py` route the
  indicator through `QStyleSheetStyle`, which paints every row; `theme/icons/*.svg`
  supplies the checked/indeterminate glyphs (a stylesheet-drawn indicator has no
  glyph of its own — without one, checked is an ambiguous filled square). Applies
  app-wide, so `ingest_dialog.py`'s identical table is fixed too. Guarded by
  `tests/test_theme_qss.py` (rule + icon-path assertions — a paint test is
  impossible offscreen, where the macOS style renders *nothing*).
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

### Session-planning arc — decided design + prototype findings (archived from ROADMAP item 1)

The design record behind the Checkpoint A/B/tuning-arc sections above; kept for
the *why* behind the shipped shape. Open refinements moved to ROADMAP →
"Session-planning follow-ups".

**Decided design (2026-07-03, with the user).** The prioritizer and the session
planner are one interdependent arc — the planner *consumes* the prioritizer and
both need the same site/glow foundation — shipped as **three checkpoints** so value
landed incrementally: **A** Profiles + Prioritizer → **B** Session Planner →
**C** Assistant (ROADMAP item 4, still open: the LLM layers over A+B's
deterministic tools; the engine still computes). Equipment inventory was
deliberately deferred out of the arc (the profile carries only what the scorer
needs; multi-device stays 6d). **Score model:** a weighted sum of (a) active-goal
membership · (b) seasonal urgency (closing soon ≫ mid-season ≫ just rising) ·
(c) completion vs. a capture-many ↔ go-deep strategy toggle · (d) optional
per-type weights · (e) tonight feasibility (transit alt, moon, horizon/glow) ·
(f) manual overrides (pins) — all shipped in `m110/prioritize.py`.

**Horizon-input decision:** Stellarium/NINA-style **`.hrz`** files (whitespace
az/alt pairs; CSV also accepted) — **theo.rocks** (mobile web app: pan the phone
around the skyline, export `.hrz`) is the recommended capture tool; the parser
consumes its output directly.

**Findings from the Astronomy prototype (reviewed 2026-06-22)** — the
`scripts/prioritize.py` prototype ran against the full real collection; every
finding shaped the port and all are now resolved:
- **Location/dark-site awareness was the biggest gap** — strategy=new top-picked
  low-southern dark-site-only targets (M16/M17 @34–36°) for a Bortle-5 backyard.
  → The **glow mask**: an azimuth-dependent light-pollution floor layered on the
  physical horizon (`max(physical, glow)`), per **site profile** (a dark-site trip
  uses an empty mask), **filter-aware** (narrowband punches through → softer
  floor). Shipped as `m110/glow.py` (Walker's-Law GeoNames auto-map; VIIRS
  radiance noted as the v2 precision upgrade; the Falchi World Atlas as a
  site-class anchor source).
- **The season gate hard-dropped short-window targets** (`season_min_hours` ate
  M109/M53/the Veil). → Graded: continuous `hours_clear` so the scorer *grades*
  short windows instead of dropping them.
- **Hand metadata was fragile** (folder→object mapping lived on generated priority
  entries). → Stable sources only: the store's library + `pins.toml`; the
  generator's artifact is never read back.
- **Resolve by canonical coords, not display id** ("Veil Nebula (E)" didn't
  resolve). → The port resolves via `catalog.load_coords`.
- **Filter derived from type** (emission/planetary → LP, else IRCUT) — kept
  first-class (`prioritize.filter_for_type`).
- **Strategy mode = the night's character** — new vs deep flips the list, so the
  toggle got UI prominence on the Planning pane.

**Prototype fixes ported (2026-06-22):**
- **Urgency × completion coupling** — deep mode let seasonal urgency pump
  *finished* targets (a done M81 "closing in 7d" outranked the genuine M12
  close-out). Fix: `u = u_raw × c`, so finished targets (c→0) get no urgency
  credit. Ported into `prioritize.py` as designed.
- **Combined-frame captures** — the prototype needed an explicit `[[combine]]`
  prefs group to rank `M81 M82` as one entry. In M110 the two-axis store makes
  the capture *target* the natural unit, and the tuning arc's #39/#40c landed the
  member rollup in the engine — no prefs-file shape was copied.


## 4 — In-app assistant, M0: a read-only MCP server over the engine

*(`feature/assistant-mcp`. ROADMAP item 4, Checkpoint C of the session-planning
arc. The phasing was inverted first — see ROADMAP item 4 for why MCP came before
the chat pane.)*

Qt-free `m110/assistant/`, **read-only and propose-only** — no tool writes to
the data store, the content tree, or settings:

- `registry` — 13 tools as provider-neutral JSON-Schema descriptors. Imports
  neither MCP nor any LLM SDK, so the M1 transport and any future adapter
  consume the same objects.
- `serialize` — the one place engine values become JSON (naive-local datetimes
  get a real offset; Paths become store-relative; no absolute path leaks).
- `proposals` — the `m110.proposal/v1` envelope, whose `preview` is computed by
  running the **pure** scorer twice so a before/after ranking can't be
  fabricated, and whose `basis.store_state` fingerprint lets M1's apply path
  detect a store that moved on underneath it.
- `skills` — three procedures (`plan-a-night`, `explain-the-numbers`,
  `critique-an-image`) in the Claude Skill on-disk layout, served as MCP
  prompts, MCP resources, **and** a `get_skill` tool, from one loader.
- `vision` — in-memory render → JPEG for image critique, delivered as a native
  image block so the client's own model does the looking. No provider SDK.
- `mcp_server` — the only module importing `mcp`; `client_config` writes the
  Claude Desktop entry from Preferences.

**Read-only is proven, not asserted:** a byte-identical store manifest (mtimes
included), write-syscall interception, and a static AST denylist of engine
writers — all parametrized over the registry, so a new tool is covered by
construction.

**Packaging.** `m110-mcp` is a second executable from the same PyInstaller
`Analysis`, sharing the runtime and data files (~5 MB marginal). It must be
`console=True`: on Windows `console=False` links against the GUI subsystem,
where a process has no standard handles at all and a stdio server cannot exist.
The AppImage dispatches via `AppRun --mcp`, having no persistent internal path.

**Disclosure.** M110 no longer holds an API key, but the obligation survives and
sharpens: connecting a client sends journals, capture data, and image bytes to
whatever model that client runs. Preferences states this before writing the
config.

**What the spike settled before any of it was built.** The open question was
whether to depend on the MCP Python SDK or hand-roll JSON-RPC, given the SDK
pulls pydantic v2 (a compiled Rust extension) plus `httpx`, `starlette` and
`uvicorn`. Answer: depend on it. It froze with **zero** hidden-import or
data-file fixes — no custom hook, unlike astropy — and the warm handshake is
0.32 s frozen, *faster* than unfrozen, because the PYZ skips filesystem module
search. A first-run 4.8 s reading turned out to be macOS Gatekeeper verifying a
freshly built unsigned binary, not import cost. Attempting to slim the bundle by
excluding the HTTP tail **fails**: `mcp/shared/session.py` imports `httpx`
unconditionally, even for a stdio-only server — don't retry it.

**Numbers that justified the cached-vs-slow rule.** `prioritize.refresh_prioritized()`
takes ~60 s for 220 contexts; `plan_night` over the cached ones takes ~0.8 s for
28 candidates. Had the tools called `build_contexts`, every question would cost a
minute. Hence: `rank_targets` and `plan_night` read `load_contexts` only, and say
so plainly when the cache is stale or missing rather than appearing broken.

**Two things worth remembering.** Dropping the chart-shaped arrays
(`night_track.samples`, the moon `track`) removes **83%** of a plan payload at
three targets — the planner runs thirty. And `get_image` deliberately resolves
the hero via `build_images.hero_source_path`'s `.src` sidecar rather than
`objects.hero_path`: the latter returns the already-downscaled hero JPG, and
judging star shape on a re-compressed thumbnail is worse than useless.


---

## 4b — MCP Python SDK v2 migration *(done 2026-08-16, `feature/mcp-v2`)*

M110 was pinned to `mcp<2` while v1.x sat in upstream **maintenance mode —
security fixes only**. That pin was the project's one piece of knowingly
unsupported framework, and it is now gone: `assistant/mcp_server.py` runs on
**`mcp>=2,<3`**.

**What v2 actually changed for us.** It removed the low-level `Server` *decorator*
API the module was built on — all six of `list_prompts` / `get_prompt` /
`list_resources` / `read_resource` / `list_tools` / `call_tool`, verified gone by
probing a real 2.0.0 install — in favour of handler callables passed to the
constructor. `mcp.server.fastmcp` went too. Three mechanical consequences, and
they are the whole of the port:

* a handler takes `(context, params)` instead of unpacked domain arguments, so
  `name` / `arguments` / `uri` now arrive on `params`;
* a handler returns a **Result** model instead of a bare list or string —
  `ListToolsResult(tools=…)` where v1 returned the list, and
  `ReadResourceResult(contents=[TextResourceContents(…)])` where v1 could return
  the markdown as a plain `str`;
* the models are snake_case with camelCase aliases and `populate_by_name`, so
  `inputSchema=` / `mimeType=` still bind and were kept as the wire spells them.

The *types* survived (`mcp.types` is a permanent alias; `Tool`/`TextContent`/
`ImageContent`/`Prompt`/`Resource` unchanged), which is why this stayed a
transport change. Nothing in `registry`, `skills` or the tools moved — that
separation is exactly what `registry` owning the content was for.

**Chose the low-level `Server(on_*=…)` constructor over `MCPServer`.** The other
candidate, `mcp.server.mcpserver.MCPServer`, still has `tool`/`prompt`/`resource`
decorators, but they are *per-function* and derive each schema from the
function's type hints. M110's 15 tools are **dynamic** — built from
`registry.all_tools()` with explicit JSON Schema in `Tool.params` — so that shape
would have meant either fabricating typed wrappers per tool or losing schema
fidelity. The low-level constructor takes our dynamic list directly.

**Proved by diffing the wire, not by reading release notes.** A throwaway client
exercised every handler path — `tools/list`, `prompts/list`, `prompts/get` (+
unknown), `resources/list`, `resources/read` (+ unknown), `tools/call` for a good
call, a list call, a missing-argument call, a not-found slug and an unknown tool —
against **old code on 1.28.1** and **ported code on 2.0.0**, and diffed the
normalized responses. Two differences remain, both deliberate:

1. `resources/read` now reports `text/markdown` instead of `text/plain`. v1 was
   internally inconsistent — `resources/list` already advertised `text/markdown`
   while `read` fell back to the SDK's default. The skills are markdown.
2. A bad-argument message now reads `get_object: missing required argument 'slug'`
   instead of jsonschema's `Input validation error: …`. v1's SDK pre-validated
   against `inputSchema`; v2 doesn't, so `registry._validate` — which was always
   there and checks *more* (unexpected args, types, enums, ranges) — is the one
   that speaks. No validation was lost, only a redundant layer.

**One behaviour was preserved on purpose.** Under v1 the decorator wrapper turned
any exception the handler raised into `CallToolResult(isError=True)`, so the
`raise ValueError` on a `ToolInputError` never actually reached the wire as a
protocol error. v2 propagates a raise, so keeping the old shape took saying it
explicitly — the handler now returns `is_error=True` content. Kept deliberately:
a model recovers from an `is_error` result (read the message, retry with the right
argument) far better than from a transport-level failure, and flipping it is a
client-visible protocol change with no business riding along in a transport port.
`ToolError` (a decline — a wrong data root is the likeliest real one) likewise
still returns plain content without `is_error`, exactly as v1 did.

**Packaging verified two ways, because this is the failure mode that ships.** The
specs never name `mcp`; it rides in on PyInstaller's static analysis, which is
precisely the shape of the astropy / uranometria bundling bugs (#64/#74/#75) where
the source run is fine and the frozen app dies.

1. *The mcp-specific risk, isolated.* A minimal PyInstaller build of just the v2
   import chain (`mcp.types`, `mcp.server.lowlevel`, `mcp.server.stdio`) runs clean
   **frozen**: `Server(on_*=…)` constructs, `create_initialization_options()`
   works, and the pydantic models round-trip with their aliases. **No spec change
   is needed** — and notably no `copy_metadata("mcp")`: only `mcp/cli/*` reads
   mcp's own dist-info, both call sites guard with `try/except
   PackageNotFoundError`, and M110 never imports `mcp.cli`.
2. *The real thing.* `release.yml` dispatched on the branch (run
   **31929725089**) built the **Linux AppImage and the Windows installer** with
   `mcp-2.0.0` resolved into the build env, and produced the `m110-mcp` binary on
   both. The only PyInstaller warnings are the two `pycparser.lextab`/`yacctab`
   hidden-import notes, which are **pre-existing** — the same two appear in the
   shipped 0.3.0-beta.4 release build (run 31542846417) and come from cffi, not
   mcp. Nothing was published: `gh release create` is guarded by
   `startsWith(github.ref, 'refs/tags/')` and was skipped.

   *Residual gap, stated plainly:* the frozen `m110-mcp` was **built** on those two
   platforms but not **executed** there (the artifacts are Linux/Windows; the
   development machine is macOS). The macOS frozen probe in (1) is what covers
   "does the collected mcp v2 actually work at runtime"; between them the risk is
   covered, but a first-run check of the packaged binary on a real Linux/Windows
   box is still worth doing when one is at hand.

**The hold came off with it.** The Dependabot `mcp` major-ignore added days
earlier was a stopgap for exactly this unported major; it is deleted. The durable
guard is the CI step that *starts the server* (`tools/smoke_mcp.py`), which is why
`<3` is ordinary prudence rather than a new debt — the next breaking major fails
CI loudly instead of passing green the way #115 and #121 did.

`PROTO` in `tools/smoke_mcp.py` was reviewed and deliberately left at
`2025-06-18`: the server agrees to that exact version under v2, so it still proves
the handshake *and* asserts backward compatibility with what real clients send.
Asking for the SDK's own newest (`2026-07-28`) is a different and weaker test —
the server negotiates it down to `2025-11-25`, so pinning it would assert a
version we never actually speak.


## 4c — Headless stacking + the `siril-stacking` skill *(done 2026-08-19, `feature/siril-stacking`)*

`m110/stacking.py`, ported in from the sibling Astronomy project's
`scripts/siril_stack.py` (1151 lines, already M110-layout-aware — it preferred the
`siril/` sandbox and read our Naztronomy preset to warn on filter disagreement).
Shipped as `m110-stack`, a third console executable from the same PyInstaller
Analysis as the GUI and `m110-mcp`, so a packaged user gets it without a Python
install. The engine reproduces the Naztronomy command sequence through `siril-cli`
plus settings its GUI doesn't expose; every emitted command is stock Siril 1.4.

**Why this amends a foundational decision.** "Prepare-and-guide, not control" was
chosen to avoid the maintenance tax of wrapping volatile CLIs. Stacking is the one
job where the rule's *reasoning* doesn't hold: it is an unattended multi-hour batch,
exactly what a human should not sit through, and nothing here reimplements an
algorithm — only the *choice* of settings is ours, so there is no volatile surface
to wrap. Post-processing stays firmly prepare-and-guide (item 14). The decision text
in ROADMAP was amended rather than left to quietly contradict the code.

**The two-phase split is what makes the assistant safe, not a convention.** The
assistant layer's read-only guarantee is *proven* — a store-manifest diff, write-
syscall interception, and an AST denylist over every file the server can reach — so
a tool that could stack would demolish it. `build_plan(..., deep_measure=False)` is
pure FITS-header reads and skips even the two enrichments that shell out to Siril
(the local-Gaia probe and `measure_fwhm_by_exposure`); `plan_stack` calls only that.
`run_siril` and `apply_handoff` went **onto** `ENGINE_WRITERS`, and the denylist was
verified to bite by planting a violating module and watching layer 3 fail.

Details worth keeping:

- **"Not checked" is not "not found."** `build_proposal` gained `gaia_checked`,
  because the read-only path was reporting the local Gaia catalogue as *missing*
  when nothing had looked for it — a confident wrong answer a user would act on.
- **The path-leak trap has two halves.** `serialize` relativizes a `Path`, but a
  path formatted into a *string* passes through verbatim. The first `how_to_run`
  carried an absolute path for that reason. Fixed at the root: `resolve_input`
  lets `m110-stack` take a bare capture-folder name, so the command handed to a
  model needs no path at all. The regression test asserts on the whole serialized
  blob, not on the fields that happen to hold paths today.
- **All three Siril spawns pass `launch._child_env()`.** Only `run_siril` had it at
  first; `gaia_catalogue` and `measure_fwhm_by_exposure` were spawning bare. The
  two-Qt SIGABRT this prevents only bites a **frozen** build, so a source-scanning
  test (`test_every_siril_spawn_sanitizes_the_child_environment`) enforces the
  shape — a dev run cannot reproduce the failure.
- **Behaviour-equivalence was checked by A/B, not by inspection.** All 29 original
  tests pass against the ported module, and on a real Dwarf 3 set that cannot plate
  solve (2–4 stars per frame) the port and the original fail identically, at the
  same step, with the same timings.
- **Packaging generalised rather than copy-pasted.** A third `console=True` EXE
  re-arms the `LSBackgroundOnly` trap, so the explicit `False` in the macOS
  `info_plist` is now load-bearing for a second reason. `sign_notarize.sh` loops
  over the helper binaries (an unsigned Mach-O in the bundle fails notarization,
  which only surfaces at release), the AppImage `AppRun` dispatches `--mcp` and
  `--stack`, and `test_packaging_deps.py` drives all of it from one `HELPERS` list
  so a fourth binary is covered by the same checks.
- **`--handoff`** hardlinks the finished stack into `Images/<target>/astrowizard/`
  with a provenance sidecar, the sanctioned writer for the item-14 convention. It
  runs in the CLI the user invoked; the assistant only documents the flag.


## 14a — AstroWizard launcher + Send stack to AstroWizard *(done 2026-08-20, `feature/astrowizard-launcher`)*

Makes the `astrowizard/` sandbox reachable from the app rather than only from
`m110-stack --handoff`. A `launch._TOOLS` entry, a Preferences path row per
registered tool, and a preview-then-confirm picker whose write is
`stacking.apply_handoff` — the same function the CLI calls, so the two cannot
drift on what the convention is.

**AstroWizard cannot be handed a file, and that shaped the flow.** Its bundle
registers no `CFBundleDocumentTypes` *and* no URL types, so `open -a AstroWizard
<file>` opens the app and ignores the file; there is no working-directory flag
either. `launch.sets_working_dir` derives that from the spec (empty
`workdir_args`) rather than storing it, so callers ask instead of special-casing
an id. Revealing the destination folder is therefore the primary affordance, not
a fallback — the opposite of the Siril case.

**Linear vs stretched is read from HISTORY, not the filename.** AstroWizard starts
at background extraction and stretching, so a stretched input is wrong. On the
developer's library `stacks/` holds the stacker's output beside the user's own
saved steps, and the newest file is very often one of the latter: rendering the
picker against the real store preselected `_denoise.fit`, whose HISTORY carries
"VeraLux v1.5.2 Stretch" three entries back. Two earlier attempts were rejected on
measurement — `config.is_processing_product` marks *every* stack (the `NxEXPsec`
signature), and `hints.is_finished_name` misses `_denoise` and `_stretch`. Only
stretches disqualify: background extraction, plate solve, SPCC, deconvolution and
denoise all leave the data linear, and treating them as disqualifying would rule
out good inputs. This is the standing "header truth > filenames" rule, applied
where a filename convention looked adequate and was not.

Details worth keeping:

- **Rendering found what the tests could not.** Offscreen tests passed on a dialog
  whose filename column consumed the width and pushed frames, integration and date
  behind a horizontal scrollbar — the columns the choice is actually made on. The
  same render exposed the preselection bug. Cured with a stretched name column,
  left elision (every name in a target shares its prefix; the tail is what
  distinguishes them, and middle elision produced two rows both reading
  `M_27_202...ssed.fit`) and a tooltip carrying the full name.
- **A sortable table cannot be indexed by visual row.** `make_table` enables
  sorting, so populating it re-sorts live *and* a user clicking a header
  permanently desyncs position from the underlying list — meaning the confirmed
  send delivered a **different file than the one highlighted**. The row's index now
  rides on the item (`Qt.UserRole`); the table is populated with sorting off and
  the indicator is then pointed at the order the dialog actually computed.
- **No Size column, deliberately.** The handoff is a hardlink; a size beside "costs
  no extra disk" invites the opposite conclusion. That space went to State.
- **The cheap/expensive split is load-bearing.** `can_hand_off` runs on every
  detail-pane render, so `_candidate_paths` does directory reads only and
  `handoff_candidates` adds provenance — 2ms against 86ms on a 47-stack target.
- **The corpus grew two M63 stacks** (a linear `_og` and a newer stretched
  `_processed`) because without header cards the picker shows a row of dashes and
  the linear/stretched distinction — the whole point of the flow — is invisible to
  a manual tester. TESTING.md §2.4.
### Tuning pass, 2026-08-19 — four bugs the live tool found

The skill was written before the tool had ever been driven against the real
store. Pointing it at NGC 7000 and `M81 M82` found more in an hour than reading
the port had:

- **The read-only path recommended the wrong weighting, and justified it with a
  measurement nobody took.** With mixed exposures and no FWHM pass, the `else`
  branch fell through to noise weighting and said *"exposures are mixed with
  comparable sharpness"*. Same class as the Gaia "not checked is not not found"
  bug but strictly worse, because it changed the recommendation rather than a
  warning — and on M15 the measured answer is the opposite. Now three branches:
  measured-soft, measured-comparable (which quotes its numbers), and unmeasured,
  which picks wFWHM and says it is a default rather than a finding. wFWHM is the
  safe unmeasured choice because the risk is asymmetric.
- **One junk pointing header poisoned every geometry number.** A single frame in
  744 carrying DEC −90 against a target at +69 stretched the sky span from ~1° to
  ~105°, flipped `is_mosaic` on, projected a 76-gigapixel canvas and an 86 GB
  scratch, and would have proposed mosaic settings for a single target.
  `_drop_stray_pointings` cuts them from the geometry (never from the stack) and
  warns. The threshold is scaled off the bulk's own p90 spread rather than a fixed
  distance, because a *real* mosaic's tiles are genuinely far apart — what
  separates a tile from a junk header is company, not distance from centre. A
  synthetic 3×3 mosaic is in the tests precisely to keep that honest.
- **Canvas and disk ignored every override.** They were computed once inside
  `build_proposal`, before overrides applied, so `--no-drizzle` came back with an
  unchanged 86 GB. That is worse than refusing to answer a what-if. `project()` is
  now separate and re-run after overrides + reconcile; the disk warning it emits is
  removed and re-added so an overridden proposal cannot carry two contradictory
  ones. Real numbers now: 86.2 GB → 34.5 GB with drizzle off.
- **`plan_stack` could not open a per-filter split target at all** — it resolved to
  the sandbox root, which has no `lights/` on a mixed-filter target, and died with
  a `StackingError` **that leaked the absolute path**. The earlier leak test only
  checked the success payload; error strings are built by the engine and passed
  through verbatim, which is a second and easily-missed route into a model's
  context. Fixed both: a `filter` argument plus a chooser error listing the filters
  and their frame counts, `resolve_input` understanding `<target>/<FILTER>`, and
  `_scrub` on every engine message the tool re-raises.

Two shaping changes, from the stated long-term direction — the engine decides
settings deterministically and the skill covers what it cannot see, evolving
toward a script the agent manipulates rather than prose it reads:

- **The tool became a manipulation surface**, not a one-shot read. Eleven
  overrides, each recomputing the whole proposal, with `overrides_applied` echoed
  and `how_to_run` growing the matching flags so the command can never drift from
  what was agreed. This is the stacking analogue of `propose_weights`' before/after.
- **The skill stopped duplicating the engine.** Per-setting reasoning already ships
  in `justifications`, so the skill now defers to it and spends its length on the
  cases the scorer cannot see: per-filter splits (broadband and narrowband stack
  separately and are combined afterwards — with the warning to force a common
  drizzle scale, since stacks at different scales do not register to each other),
  mosaics, mixed exposures, and when dropping a night is actually justified.
- **`temps` was dropped from the payload** — one float per frame, ~900 on a mosaic,
  the single largest thing in it and pure noise beside the min/max it collapses to.
  13 KB → 5.4 KB. And `script` became `register_script` + `stack_script`, since the
  old single key held phase 1 only under a name claiming the whole pipeline.

---

## Engineering reference — archived from CLAUDE.md (2026-09-04)

> **What this is.** On 2026-09-04 `CLAUDE.md` was trimmed from ~54k tokens to
> under 10k, because it is loaded into every Claude Code turn. Everything below
> is the long-form body it carried before the trim, **moved here verbatim** (only
> the heading levels were demoted one step). It is the per-module *how and why*:
> the data-store detail, the full module map, the conventions in full, and the
> gotchas / lessons-learned archive. **Grep this section by module or symbol name
> before changing a subsystem.** Some statements are point-in-time (test counts,
> "current status") and are superseded by `ROADMAP.md` / the code.

### What this is, and where it came from

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

### Architecture

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

#### Data store

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
    rejected/           subs the user excluded from processing (#110; user-created by
                        hand, lazily). Same frames, out of the population — not linked
                        into the siril/ sandbox, not counted as integration/sessions,
                        and **not re-imported** (import reads lights/+rejected/ as one
                        population, so the telescope can't re-sync a rejected frame)
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
    astrowizard/        contained AstroWizard sandbox (ROADMAP item 14): the handed-off stack +
                        its .src provenance sidecar, the user's exports, archive/<ts>/. A *sibling*
                        of siril/, not a subdir — these name **workflows**, and the artifacts have
                        different lifetimes (a stack costs hours and is stable, a finish is cheap and
                        iterated), so one shared dir would archive the expensive one on every
                        re-finish. Every sandbox dirname is a key of `config.SANDBOX_LINKED_INPUTS`
                        (`SANDBOX_DIRNAMES` derives from it); backups keep a sandbox's authored
                        work and skip only its declared hardlink trees.
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

### Module map

**Engine (`m110/`)** — Qt-free:

| Module | Role |
|---|---|
| `config.py` | data-root resolution, dir bootstrap/seed (**`_seed_archive_retention`** decides the processing-archive retention default **once**, at the first bootstrap that sees a store, and writes it: an **existing** store gets 0 ("keep all", the behaviour it has always had — retention must never surprise a library that predates it), a **new** store gets 3. Persisted rather than computed, because "is this store new?" is only true once and the user must be able to change it without the next launch overruling them; `save_setting` now also mkdirs `SETTINGS_FILE`'s own parent, which is not always `APP_CONFIG_DIR`) (`_seed_library` now writes an **empty** Library — 5d: it's the captured collection, grown by capture/Add-object; also seeds `profiles/default.toml` for session planning), per-target path helpers, `GOALS_TOML`/`LIBRARY_TOML`/`PROFILES_DIR` per-store paths, settings persistence, Seestar mount detection (`find_seestar_myworks`, scanning **`VOLUMES_DIR`** — module-level so tests can point it at a scratch dir: a telescope is *just a mounted filesystem*, which is what lets the suite drive the real probe against a fake mount instead of stubbing it out; macOS-only today, Linux `/media`+`/mnt` and Windows drive letters are unhandled). **`FIT_EXTS`/`is_fits_file`** = the single authority for FITS extensions (`.fit` **and** `.fits` — Dwarf 3 writes `.fits`), used by `is_light_frame` + import/sessions/prep so a new device's extension is recognized everywhere at once. **`rejected_dir`** (#110) = the sub-exclusion tier beside `lights/` — a sibling directory rather than a flag file precisely because every consumer of subs already reads `lights/` and nothing else. **`SANDBOX_LINKED_INPUTS`** = the single authority for the per-target *workflow* sandboxes (`siril/`, `astrowizard/`), with `SANDBOX_DIRNAMES` **derived from its keys** so the two can't drift; `siril._ROOT_SKIP_DIRS`, `ingest._SKIP_DIRS` and `backup.scope.is_excluded` all read it, so a new workflow adds its name once. The **value** is the question a new workflow must answer — which of its subdirectories are hardlinks to frames already in the managed tiers, as opposed to authored work — which is what `backup.scope` narrows the exclusion to. AstroWizard declares `{"lights"}` since the StackingWizard work gave it a hardlink tree of its own; a workflow that links nothing says so with `frozenset()`, and leaving it out of the mapping entirely would instead silently un-protect the sandbox from all three walks. It exists because each of those three hardcoded `"siril"` and each failed **silently and differently** when a second sandbox appeared — Siril claimed the other tool's exports as its own finished work, ingest re-imported the working area, and backup copied a regenerable hardlink tree into every snapshot (`tests/test_sandbox_dirs.py` asserts the policy, not just its consequences) |
| `migrate.py` | in-place, idempotent, version-stamped migration of an older store to the two-axis layout (`migrate_store`) |
| `catalog.py` | `load_library` (per-store `library.toml` — the user's corpus); `load_reference` (bundled `seed/objects.toml`) + `load_bundled_catalog`/`list_bundled_catalogs` (bundled `seed/catalogs/*.toml` membership) + `catalogs_for_slug` (which catalogs an object is in) + `add_goal_members_to_library` (additively grow the Library from a catalog); `catalog_sort_key`/`season_sort_key`; `load_coords` (reference coords + per-store library `ra_deg/dec_deg`); `object_identifiers`/`object_label` (all designations ordered by catalog hierarchy Messier→Caldwell→NGC/IC) + `catalog_sort_key` (M/C/NGC/IC numeric); `add_captured_objects` (promote captured folders into the Library — known catalog objects pull full bundled-reference metadata, off-catalog ones get a minimal stub + Simbad coords); **5d removal**: `remove_library_entry(slug)` (manual "Remove from Library"; non-destructive) + `remove_goal_members_from_library(goal_id, members=)` (goal-deselect prune of uncaptured/un-noted/not-in-another-active-goal members); `season_from_ra` (derive the observing-season window from RA — calibrated to the curated Messier seasons, ≈98% match; shared with `tools/gen_caldwell.py`); `fill_missing_metadata(slug, online=)`/`fill_all_missing_metadata` (backfill an existing Library entry's **missing** fields from the bundled reference + derived season; `online=True` adds a Simbad tier for gaps the reference lacks; never overwrites real user values; the right-click / "Library → Fill missing metadata" + "Enrich online" actions) via `_write_library` (in-place rewriter preserving every key); **5c add/enrich**: `resolve_new_object(identifier, online=)` (cascade reference→online→coords for the Add-object flow, no write), `add_library_entry` (commit a new object + journal stub; refuses duplicates), `resolve_object_online`/`enrich_online` (batched Simbad; `OnlineLookupError` when astroquery/network absent), `_simbad_type`/`_simbad_row_to_entry` |
| `derived.py` | **read** generated rollups (totals/priorities/summary/processing/images/goals.json) |
| `processing.py` | workflow registry (Siril + **AstroWizard** active; PixInsight/others disabled "soon"). `Workflow.importer` names the module owning the workflow's **return** leg, kept separate from `autoprep` because the halves are independent — AstroWizard has no prepare step at all, which is why **`preparing_workflows()`** (not `WORKFLOWS`) backs the Preferences checkboxes; **`workflows_with_output(target)`** answers *which* tool is holding finished work, a question one `ready_for_import` boolean cannot + `run_autoprep` (preference-driven, runs after ingest) + `prepare_missing` (refresh-time/on-demand backfill — creates only *absent* sandboxes, never rewrites existing) + **`reconcile_rejected`** (#110 refresh-time prune of working-folder links for subs excluded since prep, over `_rejected_targets()` — only targets that *have* a `rejected/` tier, so the common store costs one listdir. Kept **separate** from `prepare_missing` on purpose: that one's invariant is "never touches an existing sandbox" and this one exists to touch one, so two functions keep the invariant a true statement rather than one with an exception) |
| `scan_sessions.py` | scan `Images/<target>/lights/` → `sessions.jsonl` (ported). **Header-driven** (`_session_key`): each sub's `(date, exp, filter)` comes from the Seestar/mosaic **filename** when it matches (fast path, no header read), else from the FITS **header** (`DATE-OBS`/`EXPTIME`/`FILTER`) — so any device's subs (Dwarf 3, …) produce sessions regardless of filename convention. Accepts `.fit`/`.fits`. **Mount mode = the reported `EQMODE` header card** (`_mount_mode`/`_read_eqmode`): Seestar **and** Dwarf 3 both write `EQMODE` (int 1=EQ / 0=Alt-Az, "Equatorial mode"), read once per session-segment; falls back to the legacy `EQ_FROM` date heuristic only when the card is absent (pre-`EQMODE` firmware). The date rule is Mike-Seestar-specific — header truth wins so other users/devices aren't mislabeled |
| `build_derived.py` | compute totals/priorities/summary/processing/goals → `.m110_internal_data/derived/*.json` (ported). `build_totals` also surfaces **Seestar-stack-only** targets (a `seestar-stacks/` folder with no `lights/` → no sessions) as zero-integration captures, so they're first-class (gallery/status/`targets_for_slug`) — matching what `add_captured_objects` promotes |
| `build_images.py` | thumbnails + heroes + `images.json` into `.m110_internal_data/renders` (ported from build_site/generate_hero); content-hash cached. **Hero cache keys on source *identity*** (a `hero/<slug>.src` sidecar = source rel-path + `img_hash`), not mtime — so a set-hero to an *older* image re-renders instead of leaving a stale hero (#17). `rebuild_hero(slug)` re-renders one object's hero synchronously (interactive set-hero, no full refresh) |
| `ingest.py` | staging/Seestar scan **plan** (read-only) + gated `apply_ops` (the only writer into the content tree); cancellable. **One deterministic scanner (#32):** all entry points go through the recursive `scan_directory_plan` (`os.walk`, depth-agnostic) — `scan_seestar_plan`/`scan_staging_plan` delegate to it (the old shallow one-level `_scan_base` was retired, it silently missed nested subfolders); the walk logs every dir visited + its layout + pruned subtrees + a final `scan_summary` (`m110` logger → `~/.m110/logs/m110.log`), and `scan_summary(ops)` gives the UI headline counts (objects / to-import / to-holding). Holding area (6c): `scan_holding`/`assign`/`discard_holding` + **`annotate_holding`/`identify_holding`** (#26 aids — per held group, `frame_info` header facts + suggested object [OBJECT header → slug via `_slug_for_object`, else nearest catalog by RA/Dec within `IDENTIFY_TOL_DEG`] + suggested kind [IMAGETYP]). **Per-sub preview import** (#25, default off — `import_sub_previews` setting): the `_sub` branch optionally routes the Seestar's per-sub `.jpg` previews to `Images/<target>/previews/` (new `"preview"` kind) instead of ignoring them. **DwarfLab Dwarf 3** (`dwarf` layout, `_classify_dwarf_dir`, keyed on the `DWARF_RAW_*`/`STARTRAILS_*` session-folder prefix): `.fits` subs → `lights/` (object from `OBJECT` header), in-app `stacked-16_*` + `stacked.jpg` → the `seestar-stacks/` device-stack tier, `Thumbnail/` (added to `_SKIP_DIRS`) + aux rasters (`img_*`, `*_thumbnail`) ignored, **startrails** → `Media/Startrails_{video,photo}/`. `_usable_object` treats `OBJECT` of `''`/`Unknown` as absent → holding area (identify-by-pointing). Loose re-grouped Dwarf FITS fall to `raw-fits` (routed by `OBJECT`) |
| `roundtrip.py` | **workflow round-trip machinery** (14b) — **`prune_archives`** is the keep-N-latest bound on `archive/<ts>/` (default 3, `processing.archive_keep`), and it is the one place M110 deletes processing history, so it is narrow by construction: `keep<=0` keeps everything, only dirs whose **name** parses as the `%Y%m%d-%H%M%S` stamp are candidates (containment on a recursive delete — the `clear_scratch` lesson, since a user may drop their own folder in `archive/`), ordering is by that name and **never mtime** (copy time lies), and it runs **only** from an `apply_import` that actually archived — never on refresh, never on cleanup="none". It reverses DATA_MODEL's earlier "never automatic" pledge on purpose: archives only accumulate, a real library hit **42 GB across 36 dirs**, and AstroWizard turned one finish into ~2 GB of autosaves. Also here: the half of a processing sandbox that is not about any particular tool: `classify` (directory-first, then the `hints` vocabulary), `same_bytes`/`resolve_import_dest` (keep-both on a content collision), `sandbox_outputs`/`root_outputs`/`finished_outputs`, `scan_finished`, `apply_import`, `archive_run`, `FinishedItem`/`ImportPlan`. What is tool-specific is a **`Sandbox` descriptor**, not a fork — and each field is a real difference the second workflow forced into the open: **`scan_root`** (Siril also claims output left loose in the object dir, the mis-pointed-working-directory recovery; AstroWizard must **not**, because two workflows both claiming loose files is how one tool's importer offers the other's exports), **`loose_fits_kind`** (a loose finished FITS is a *stack* for Siril, which turns frames into one, and a *deliverable* for AstroWizard, which is handed a stack — filing an AW `…_final.fits` under `stacks/` would put a stretched, star-reduced image in the tier `build_derived` reads for STACKCNT/LIVETIME/DATE), **`skip_file`** (the workflow's input is never its output; Siril says that structurally via `lights/` in `skip_dirs`, AstroWizard needs it at file level), **`split_jobs`** and **`archive_keep`**. `root_outputs` skips **every** registered sandbox (`config.SANDBOX_DIRNAMES`) — not tidiness: before it existed, Siril's import offered files Siril never made and `has_unimported_output` went true off another tool's output, which made `autoprep` skip the target |
| `astrowizard.py` | **the finishing round-trip** (14b) — the thin second consumer of `roundtrip`. **Two tools share this sandbox**, because StackingWizard's whole purpose is to hand off to AstroWizard. It has **no CLI at all** (verified: `argv` in no code object of the shipped 2026.08.22 build, re-verified unchanged in 2026.08.27 — see BUGS.md for the `settings.json` `last_folder` seam) and finds frames by walking the folder it is given — hence **`lights/`**, a hardlink tree like Siril's, built by **`autoprep`/`prepare_lights`** and declared in `SANDBOX_LINKED_INPUTS` (see the +139 GB note there). It writes `<object>_wizardstack.fits` into the sandbox root itself. **`is_master`** recognises that — and returns **False for an autosave**, since AstroWizard names every step after the file it opened so the whole `_AW<n>_` chain carries the master's stem; without that the sweep spared the entire working area. The master is the sandbox's **input**: `archive_keep` spares it and `lights/`, which is what lets one dir hold both halves without re-running the lifetime argument that split `siril/` from `astrowizard/` — a cheap iterated finish can't archive an expensive stable stack, because the stack is never output. Prep is gated on the Preferences checkbox, so that tick now means the same thing for both workflows. Earlier note ("no prepare step:") `stacking.apply_handoff` hardlinks a stack in with a `.src.json` sidecar, and that is the whole of handing work in. **`is_handoff`** keys on the sidecar, never the filename — the user names their own exports, so a stack handed over as `M27_final_stack.fit` would otherwise be offered back to them as a deliverable. **`is_autosave`** (`_AW<n>_`) is the counterpart: the ROADMAP's "AstroWizard's output cannot be recognised by filename" is true of its **exports** (native save dialog, user types the name) and false of its **autosaves**, which are machine-named — and that matters because the chain also emits *rasters*, which are deliverables by default with no hint required (a real M27 finish put a 41 MB `…_AW10_str_dee_sn_in.tif` in the preview beside the two genuine exports). The archive sweep is load-bearing here in a way it isn't for Siril: AW autosaves one file per user action (26 files / 2.02 GB measured), nothing under `astrowizard/` is excluded from backup, and mirrored dedups by *path* — so an un-swept chain lands in full in every future snapshot |
| `siril.py` | processing-prep **round-trip** (prepare-and-guide). **The import half now lives in `roundtrip.py`** (14b) — `scan_finished`/`apply_import`/`has_unimported_output`/`working_dirs` and the private names the suite reaches for are thin delegations over `siril.SANDBOX`, so the extraction was an internal move rather than an API break. Prepare: `plan_prep`/`apply_prep` arrange a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks, Naztronomy preset tuned by frame count — drizzle + star-quality filters — and **preserved once hand-edited** via `is_default_preset`, per-filter jobs); `autoprep` runs it automatically after ingest (skips targets with pending finished output). Import: `has_unimported_output`/`scan_finished`/`apply_import` copy renders→`finished/` + stack→`stacks/`, optionally set hero (or keep current), then **archive** the run into `siril/[<FILTER>/]archive/<ts>/` (keeps `lights/`+preset ready for re-runs; never deletes, never escapes `siril/`). **Name-collision = keep-both, content-aware** (`_resolve_import_dest`/`_same_bytes`): a byte-identical incoming file is skipped (true duplicate, dedup against every `<stem>-N` sibling), a *different* same-name file lands as the first free `<stem>-N<ext>` (both kept — never clobbers, never the old silent-skip-then-archive footgun); `has_unimported_output` + the "Ready to import" flag treat a differing same-name file as unimported, and hero pinning follows the name the render actually landed under. **Finished-output discovery = sandbox + object-dir fallback** (`_finished_outputs` = `_sandbox_outputs` ∪ `_root_outputs`): the fallback scans `Images/<target>/` too — skipping the managed tiers/raw inputs/`siril/`/`process/` — so output from a run whose Siril **working directory was mis-set to the object dir** (one level above the sandbox) is still picked up. `working_dirs(target)` = the working dirs to offer "Process in Siril" (per-filter job dirs if split, else the sandbox root; `[]` when no sandbox). **`prune_rejected(target)`** (#110) = the reconcile that makes the `rejected/` tier bite on an *already-prepped* target: `apply_prep` is add-only, so a sub rejected after prep keeps its hardlink and goes on being stacked. Unlinks **only** when that name is present in `rejected/` (a sub that merely vanished from `lights/` may be the last copy — left alone, counted as an orphan), only inside a job's `lights/` (never the archive/presets/calibration), skips a target with un-imported output (`autoprep`'s in-progress guard), and walks `_sandbox_lights_dirs` — wider than `_job_dirs` so it reaches the stale `siril/lights/` a target leaves behind when it becomes multi-filter (BUGS #28) |
| `stacking.py` | **headless Siril stacking** (`m110-stack`; port of the Astronomy `siril_stack.py`, Qt-free). Reproduces the Naztronomy command sequence through `siril-cli` plus settings its GUI doesn't expose — rejection by depth, overlap norm, noise weighting, Rice compression on intermediates. Every emitted command is stock Siril 1.4; only the *choice* of settings is ours. **Two-phase, and the split is load-bearing:** `build_plan(dir, Overrides(), deep_measure=)` measures and proposes and **writes nothing** — `deep_measure=False` further skips the only two enrichments that shell out to Siril (the local-Gaia probe, `measure_fwhm_by_exposure`), which is what lets the assistant's `plan_stack` be genuinely read-only; `run_siril` executes, reached only from `main`. **Execution is three Siril invocations — solve · apply registration · stack — and the seams are the fix, not a tidy-up:** Siril can fail the whole *script* on a partial `seqplatesolve` ("Finalizing sequence processing failed") while having already computed the astrometric registration and written it into the `.seq` — so a single script threw away work that was on disk and usable. **Not every partial solve does this, and the count is not what decides**: M27 lost 76 of 2312 and finished fine; M81/LP died losing 98 of 221 *and again losing 1 of 114* — that one being frame #1, the sequence reference. *"Reference image was not platesolved, changing reference"* is in both failing logs and neither passing one. The split does not depend on that being exactly right — phase 1 ends before registration either way. **`clear_scratch`** is the other half of the same lesson: `process/` survives a failed run by design and Siril **will not rebuild an existing `.seq`**, so a re-run inherited the previous run's derived sequences and `unselect` applied to `lights_` alone — `--exclude-night` silently stacked the night it was told to drop, while the proposal printed the reduced count. Cleared at the start of every run but `--restack`. `build_ssf_solve` therefore stops at the solve, `build_ssf_apply` is a fresh process that reads the sequence back and registers the solved subset (**`-filter-included` is load-bearing** — without it Siril builds its filter from the quality percentiles alone and plans to register frames that have no solution, thresholds computed over the unsolved population), and `build_ssf_stack` is unchanged. `parse_solve_log`/`failures_by_night` then attribute the failures to the **night** each frame came from — sequence index N is `read_frames()[N-1]`, since `link` ingests `lights/` in the same sorted order — because solve failures cluster by session, so the named night is one `--exclude-night` away from a clean re-run. `--min-solved` (default 25%) is the line between "a bad night" and "a broken setup"; a spread of failures across every night is itself the signal for the latter. **This is the one place M110 drives Siril rather than guiding to it** — see the amended processing-model decision in ROADMAP. **Coverage depth, not frame count**, drives drizzle + rejection (a mosaic's depth is far below its frame count). `resolve_input` takes a directory *or* a bare capture-folder name, which is what lets `plan_stack` hand back a runnable command with no absolute path in it (`serialize` relativizes a `Path`, but a path formatted into a string sails straight through). **`apply_handoff(stack, tool)`** hardlinks a finished stack into `Images/<target>/<tool>/` with a `.src.json` provenance sidecar built from the stack's own `DATE`/`STACKCNT`/`LIVETIME` header cards — never mtime (ingest and import both copy bytes, so mtime is copy time and lies) and never a content hash (expensive, no extra certainty). All three Siril spawns pass `launch._child_env()`; a source-scanning test enforces it, because the leak only bites a **frozen** build and a dev run can't reproduce it. **`handoff_candidates(target)`** (14a) = the stacks that could be handed over, across `stacks/` + `seestar-stacks/` + a fresh result still in the Siril sandbox, newest-stacked first; `_candidate_paths` is the header-free half so the detail pane's per-render "is there anything?" costs one listdir (2ms vs 86ms on a 47-stack target). **`_is_stretched`** reads the stack's **HISTORY cards** to say whether it is still linear — filename is a convention, HISTORY is a fact the pipeline recorded, and on a real library `stacks/` holds `_og`, `_denoise` and `_finished` side by side where only the header separates them (`_denoise` sounds like a linear step and carries "VeraLux Stretch" three entries back). Only *stretches* disqualify: background extraction, plate solve, SPCC, deconvolution and denoise all leave the data linear |
| `launch.py` | **external-app launcher** (#19 "Process in…" / "Open In…", Qt-free). Starts a processing/viewer tool and gets out of the way — never controls it. `_TOOLS` also registers **StackingWizard** (`workdir_args=[]`, no `file_args` — it takes no arguments at all, so M110 can start it and nothing more; `widgets.stack_in_stackingwizard` reveals the sandbox so the folder chooser opens on the right place). **`launch_with_file`/`opens_file`/`file_exts`** hand a tool one file (`file_args` in the spec, derived predicates so callers ask rather than hardcode): AstroWizard's 2026-08-18 release reads `sys.argv[1]` and accepts `.fits/.fit/.tiff/.tif/.xisf` — verified in the shipped 2026.08.21 bytecode — which retires the old note that nothing could route a file to it. It is **not** `CFBundleDocumentTypes` (its Info.plist declares none) nor `::tk::mac::OpenDocument`, so Finder "Open With" and Dock drops (both `odoc` Apple events) are not the route; appending the path to a **cold** `open -a … --args` is, with the same already-running caveat as Siril's `-d`. `find_app(tool_id)` = user override (`external_app_paths` setting) → OS-standard locations (macOS `/Applications/Siril.app/Contents/MacOS/siril`, Linux `siril`/`siril-cli` via `which`, Windows Program Files) → `None`; `launch_processing(tool_id, working_dir)` builds the tool's working-dir argv (Siril `-d <dir>`): **macOS** goes through `_launch_macos` (`/usr/bin/open -a <Siril.app bundle> --args -d <dir>` — LaunchServices makes Siril its own *responsible process* so its hardened bundled Python can spawn; see the gotcha), **elsewhere** `_spawn`s the binary detached; both with a sanitized `_child_env()` (strips our `VIRTUAL_ENV`/`PYTHON*`/PyInstaller `_MEI*` + bundled-Qt plugin paths `QT_PLUGIN_PATH`/`QML*_IMPORT_PATH` + restores bundle libpaths) so a launched tool's own Python **and Qt** aren't poisoned by ours. `LaunchError` when not found / spawn fails. `_TOOLS` registry (**Siril + AstroWizard**); `tool_ids`/`sets_working_dir` let callers enumerate and ask rather than hardcode — AstroWizard registers no `CFBundleDocumentTypes` **and** no URL types, so nothing can hand it a file (`open -a AstroWizard <file>` opens the app and ignores the file), which is why its `workdir_args` is `[]` and the handoff flow reveals the folder as the primary affordance rather than a fallback. The UI (`ui/widgets.process_in_siril`) falls back to revealing the folder on `LaunchError` |
| `hints.py` | **finished / intermediate filename hints** (#17) — the single, user-editable vocabulary deciding whether a filename marks a *finished* deliverable vs an *intermediate* by-product. Case-insensitive substring keywords (defaults `processed/final/finished` + `starless/starmask`), persisted in `settings.json` under `finished_hints`, read live. `is_finished_name`/`is_intermediate_name` + `get_hints`/`set_hints`. **Three consumers** draw from it (replacing their old hardcoded regexes, the source of stranger-file misclassification): `siril._classify` (import finished work), `ingest._is_finished_raster` (loose finished-render recognizer), `build_images._is_intermediate_fit` (hero-tier selection). Edited in Preferences |
| `objects.py` | per-object journal read **and write** (`Objects/<id>/journal.md`: `read_journal` frontmatter+body, `read_journal_text`/`write_journal` raw, `set_frontmatter_key` upsert for hero, `get/set_frontmatter_list` for JSON-array keys); **per-image curation** (#17) `get_curation`/`set_curation` (filename→`"finished"`\|`"working"` overrides in `finished_extra`/`working_extra` frontmatter, one list each); slug→id folder name; hero path |
| `refresh.py` | `run_refresh()` = scan_sessions → build_derived → build_images (the UI refresh worker also runs `processing.prepare_missing` so missing working folders self-heal on any sync) |
| `logsetup.py` | **application logging** (Qt-free; the beta crash-reporting arc). `setup_logging()` (idempotent) configures the `m110` logger with a `RotatingFileHandler` at `~/.m110/logs/m110.log` (+ stderr); `log_path`/`read_log_tail` surface it in the crash report. Called first thing in `main()` |
| `media.py` | **read** non-catalog media (Qt-free; backs the Media page). `list_media()` = one flat `MediaItem` list, **recursive** (`os.walk`) with **kind decided per file by extension** — so `Video_Stacked_*.jpg`/`.fit` sitting in a `_video/` folder, and whole processing-output subtrees (`ASIVideoStack_Output/`), are surfaced instead of hidden by the old shallow, folder-suffix-gated `scan()` (the depth-agnostic lesson `ingest.scan_directory_plan` already learned). `is_sidecar` = the one `_thn.` definition (shared with `ingest`); **a video's `<stem>_thn.jpg` is content, a photo's is a duplicate** — that asymmetry drives everything else here. `poster_for` = the tiered still resolver (video→sibling sidecar · Qt-decodable photo→itself · FITS→`build_images.make_thumb` into `config.MEDIA_RENDERS_DIR`), ordered so a decoded frame-grab tier can slot in without reshaping callers. `cleanup_candidates`/`discard` = the sidecar/junk cleanup; `discard` **recomputes** the candidate set and re-checks containment, so a stale UI selection can never delete a live poster. `captured` = the filename timestamp, display ordering only |
| `webexport.py` | **size-budgeted image export for web sharing** (`feature/image-export`, Qt-free). `export_for_sharing(src, dest, *, strategy=, max_bytes=None)` writes the best-quality file that fits an **optional** byte budget: **lossless** = optimized PNG → (only if a max is set and over it) binary-search the long edge (Lanczos) for the largest lossless PNG that fits (optional `pyoxipng` on the winner; floor `MIN_LONG_EDGE`, else `ExportError`); **quality** = full-res JPEG (`subsampling=0` 4:4:4, baseline — progressive tripped libjpeg on incompressible frames). **`max_bytes=None` = no maximum** (full-res PNG/JPEG, no ladder). Reuses `build_images._open_image` (FITS/float-TIF percentile-stretched to 8-bit RGB) so exports match the app render — which folds the 16→8-bit reduction in for free (a 30 MB 16-bit finished PNG lands ~11 MB at full res). Output format deterministic from the strategy (lossless→PNG, quality→JPEG); `suggested_name`=`[Object]-[maxsize]-[YYYYMMDD].[ext]`; `SAFETY_MARGIN` headroom; byte-identical originals copy verbatim (fast path). External-folder output → no `.store_version` impact. *(No site presets — a bare max-size + No-maximum control, per user feedback)* |
| `backup/` | **Library backup engine** (item 10; Qt-free package). Dated snapshots to a user-chosen destination *outside* the store → no `.store_version` impact. A destination is a folder **or an `s3://bucket/prefix`** (#93); `destination.parse_destination` is the one place that's decided, and above the seam nothing joins paths itself — **only `LocalBackend` knows what a filesystem is**. **Two formats, both always readable at one destination** (`formats.py`): **mirrored** (default) and **pooled**; resolution is destination-first (what's already there → the `backup_format` pref → *unless* the FS can't hardlink, then pooled, and the app persists that — detect, don't ask). Object storage forces pooled and **doesn't persist it** — `backup_format` is global, and a bucket says nothing about the user's external drive. Namespaces are provably disjoint (mirrored dirs parse as a timestamp, `objects/`/`snapshots/`/`latest/` never will) so they coexist with no flag day, no conversion, and no stranded backup. Modules: `errors` (+ **`BackupDepsMissing`** / `deps_missing_message`, build-aware like `catalog._astroquery_missing_message`) · `options` (value types + `SETTING_*`, leaf; **`SnapshotRef`** = destination+key, the handle for a snapshot with no filesystem path, and `SnapshotInfo.path` is now `| None`, deliberately not faked with a pseudo-path) · `scope` (`is_excluded`/`iter_source_files` — a **denylist**: skips `derived/`/`renders/`/`sessions.jsonl`/`assistant/` + a workflow sandbox's **linked inputs** only (the `config.SANDBOX_LINKED_INPUTS` hardlink trees — `siril/lights/`, `siril/<FILTER>/lights/`, calibration), so new authored data is captured without an allowlist to maintain. **Not** the whole sandbox: `archive/<ts>/` runs, presets and exports are hours of hand-work nothing regenerates, and the deliverable imported to `finished/` doesn't carry its intermediates. The two errors are silent in opposite directions — keeping the link trees in costs **+139 GB on a 186 GB library** (mirrored dedups by *path*, so a link is a second full copy) and buys nothing; leaving the work out costs 39 GB of authored history the user misses only when they want it back. **Tiers** (#93) layer on top: `everything` (default, unchanged) vs **`essentials`**, which also drops the raw-frame tiers (`lights/`/`rejected/`/`previews/`) *and* sandbox `archive/<ts>/` runs — the latter despite being authored work, because they're bounded and disposable by the app's own keep-N policy and one real library hit 42 GB of them. Recorded per snapshot (`SnapshotInfo.scope`; **`None` = written before tiers = everything**) so a restore can say what a backup didn't contain) · `destination` (**`Destination`/`parse_destination`** — only a known scheme makes a destination remote, so a Windows drive letter can't parse as one, and **`__fspath__` raises for a bucket** rather than inventing `s3:/bucket/prefix`, which is what makes a not-yet-migrated call site fail loudly; + `store_backup_root`, `backup_root_key`, `supports_hardlinks`, `free_bytes` — no format imports, so both formats build on it) · `backends/` (the storage seam pooled writes through: put/get/exists/list/delete + `link` for `latest/`; `LocalBackend` + `MemoryBackend` (ships — reference impl *and* the conformance-suite double) + **`S3Backend`**, registry-shaped like `publish.PUBLISHERS`. **`object_sizes()` enumerates the whole store once per run** — 100k per-file `exists()` calls are minutes of latency over SMB and one paginated LIST on S3) · **`backends/s3`** (boto3 with **`endpoint_url`** — the point, not a nicety: B2/R2/Wasabi are where the money argument works. Secret in the **OS keyring**, access key id in settings (an identifier, not a secret — the UI must show which key is configured); with neither set, boto3's own chain applies. `capabilities()` drives three behaviours elsewhere: no `latest/`, min-free retention skipped, and **`cheap_list=False` → shallow verify**. `_client_config` pins **`request_checksum_calculation="when_required"`** (botocore ≥1.36 attaches `x-amz-checksum-crc32` to every PUT and several S3-compatible services reject it) and **path-style addressing whenever a custom endpoint is set**, both guarded so an older botocore degrades instead of raising. `_transfer_config` returns None without boto3 — which is what lets the conformance suite run the real adapter against an **injected fake client**, with no AWS SDK and no network) · `hashcache` (sqlite in `~/.m110`, keyed `(path,size,mtime_ns,inode,dev)`; a **miss is always safe**, a stale hit is caught by cross-checking the stored object's size; degrades to plain hashing if sqlite won't open) · **`mirrored`** (`<dest>/M110-Backups/<store>/<ts>/` full browsable trees, unchanged files `os.link`ed to the prior snapshot; byte-only copy (`.part`+`os.replace`, mtime-preserved); per-snapshot `.m110-backup-manifest.json` `{rel:{size,mtime,sha256}}`; atomic `.incomplete`→rename. **Local-only by definition** — it *is* directories and hardlinks. **Kept as the default because a snapshot needs no software to restore**) · **`pooled`** (`objects/ab/cd/<sha256>` mode 0444 + `snapshots/<ts>.json.gz`; per-file manifest entries byte-identical to mirrored, so verify/expand/preview/tree-build don't branch. **Invariant: a manifest exists ⇒ every object it names exists** — written last, which is also why a cancelled first sync resumes free. **`_resolve(ref)`** is the whole of how this format became destination-agnostic: a `SnapshotInfo`/`SnapshotRef` resolves via `backend_for`, a bare `Path` resolves exactly as it always did — which is why the de-Path refactor was not an API break. `_upload_pool`/`_drain` fan uploads out at `Capabilities.parallel_puts` (hashing stays serial — the hash cache isn't thread-safe) and **drain before the manifest write**, which is what keeps the invariant true once uploads run concurrently. **`verify(deep=)`** defaults to the destination's `cheap_list`: full re-hash locally, presence-and-size from one LIST on a bucket, because a deep verify over the internet is a full download with the egress bill to match — the result reports which ran and callers must not claim otherwise) · `recovery` (`latest/` diff-relinked hardlink tree + `INDEX.tsv` + `latest-manifest.json.gz` + a stdlib-only `restore.py` and `README.txt` written *into* the backup root — `objects/` alone is hash-named blobs, so the way back travels with the data; on a bucket `latest/` is simply absent, the rest still written) · `retention` (cross-format `apply_retention` + **`sweep_objects`** mark-and-sweep with a **24h grace window** on object mtime — that, not a lock, is what makes GC safe against a concurrent run; count + min-free, oldest-first, never the last one; no age policy by design — it would wipe history after a vacation. Marking from *every surviving manifest* is also what makes a scope narrowing safe: dropped frames stay referenced until the wider snapshots are pruned. **min-free is skipped where `free_bytes is None`** — a 0 reading on a bucket would prune a cloud history to one snapshot per run) · `probe` (**`probe_destination`** → `DestinationInfo`, the pre-flight capability + resolved-format answer for the UI; read-only — creates nothing, persists nothing, leaves no probe files. For a bucket, `ensure_root()` *is* the reachability check, since there are no directories to create) · `schedule` (`options_from_settings`/`due_for_auto_backup` launch check / `due_for_scheduled_backup` hourly-tick daily 02:00, interval as min-age guard; a cloud destination is taken on trust rather than probed — due-ness is a question about *time*, and a reachability round-trip at every launch and hourly tick is a timeout, not an answer, on a laptop that's offline). `__init__` is the façade (+ a process-wide run lock: the dialog's "Back up now" worker and the window's scheduled worker don't know about each other) — import `m110.backup` and use the re-exports |
| `planning.py` | **session-planning engine** (ROADMAP item 1; astropy, lazy-imported). `twilight` (**memoized per (site, date)** via `_twilight_cached` — it's a pure function of site geometry + timezone + night, and it sits under `observability`, which the prioritizer calls *per target* across a ~22-date grid; uncached that was 535 calls for 22 distinct nights, 91% of a 23 s ranking pass. The key is the four `Site` fields the math actually reads and the cached function takes **only** those, so it can't quietly grow a dependency the key doesn't cover. Cost is now O(nights), not O(targets × nights)) /`moon_summary`/`transit_altitude` + the seasonal/tonight **`observability()`** gate → `{observable, hours_clear, transit_alt, nights_to_close, season}` (continuous `hours_clear` so the scorer can *grade* short windows). Coords from `catalog.load_coords`, season from `catalog.season_from_ra`; glow-aware via `horizon.effective_floor`. **Checkpoint B (tonight's plan):** `night_track` (per-target alt/az samples across the dark window → transit time+alt, longest contiguous up-window above min-alt+glow floor, moon separation, the `(time,alt,clear)` series for the timeline) + `plan_night` (dark window + moon + per-target tracks, **auto-ordered by `up_end`** = sets-soonest first, tiebreak by score; `order="manual"` preserves input; computes twilight ONCE and reuses via `window=`). Consumers = the auto-prioritizer (#21) + the planner UI. **Tuning arc (docs-archive/PLANNING_ROADMAP.md):** `pick_start` (start-altitude ceiling — highest *clear* sample at/below the device ceiling −`START_CEILING_MARGIN_DEG`; hard = refuse, soft = flag `over_ceiling`), per-slot **moon** (`plan_night` moon = `{illum, alt, set_time, rise_time, track}`; per-entry `moon_alt_at_best`+`moon_impact`), `moon_impact` (illum × proximity, narrowband ×0.25, `None` when moon down — separations computed **topocentrically in a common AltAz frame**, never `icrs.separation(gcrs_moon)`: that re-expresses the moon from the barycenter, the 101°-vs-45° bug), and **`sequence_plan`** (pure night sequencer, #40–42: non-overlapping 10-min slots, priority order w/ ties-to-the-setter, deep-remaining duration caps, `fill` past count to dawn, `marginal` ⚠ ≤`MARGINAL_SLOT_MIN` window-cut descending slots, `forced_order` for the UI reflow) |
| `fieldguide.py` | **session-plan field guide** (`feature/session-planner`, Qt-free). `render_markdown(site, day, plan)` → a printable observing plan (dark window + moon, ordered target table with best time/alt/up-window/moon°/filter + per-target season+notes), rendered in-app by `QTextBrowser.setMarkdown` (no dep). `save`/`list_guides`/`read` manage saved guides under the **`Plans/`** visible axis (`config.PLANS_DIR`, created by `ensure_data_root`; `Plans/<date>_<slug>.md`). Renders the **`## Schedule`** table when `plan["schedule"]` is present (`sequence_plan` slots: start/duration ⚠/alt ^/filter/moon); `moon_headline` (whole-night moon line) + `moon_cell` (gated on moon-up) + `start_cells` (startable slot, falls back to transit for old dicts) are shared with the Planning table; footer stamps generation date *and* plan night |
| `planning_config.py` | observing-**site** + **device** profiles loaded from `config.PROFILES_DIR/<name>.toml` (one profile = one location), in-code defaults when absent. `Site` carries lat/lon/elev/tz + the `[glow]` light-pollution layer (`bortle`/`sqm_zenith`/`glow_mask`/`glow_mask_narrowband`), `zoneinfo` DST, filter-aware `glow_path`; `list_profiles`/`load_site`/`load_device`. **Writers (Planning UI, `feature/planning-profiles`):** `save_site`/`delete_profile` (default protected) + `format_site_toml` (hand-written TOML, no writer dep), `import_horizon_mask` (validates via `horizon.load_mask`, copies beside the profile), the **active-profile** selection (`active_profile`/`set_active_profile`/`load_active_site`, persisted in settings under `active_site_profile`), and an optional online **`geocode`** (Nominatim, degrades offline). `Device` carries `start_alt_ceiling_deg` + **`ceiling_is_hard`**; **`DEVICE_PRESETS`** = the researched per-device ceilings (Seestar S50/S30/S30 Pro hard 78° — S30s assumed from the shared app, unverified; Dwarf 3/Mini soft 80°) |
| `assistant/` | **the assistant layer** (ROADMAP item 4; Qt-free). **The invariant: no tool MODIFIES or DELETES anything; a tool may CREATE a file, only in the outbox, under quota** — relaxed from M0's zero-write once saving a plan proved impossible without it. The property that matters was never "no bytes written" but "can't damage or silently alter what you made". `registry.py` = the **registration / validation / dispatch machinery** only (`register`, `all_tools`, `get`, `call`) — imports **neither MCP nor any LLM SDK**, so the future in-app transport consumes the same objects; `call_with_media` returns `(json, image blobs)` and `call` is the JSON-only convenience over it. **`tools/` holds the 16 operations themselves** as provider-neutral JSON-Schema `Tool` descriptors, one concern per module (12: `overview` · `library` · `objects` · `images` · `processing` · `ranking` · `planning` · `stacking` · `proposing` · `saving` · `docs` · `guides`), and the registry is populated **by import side effect** — so `registry.all_tools()` returns **empty** until `m110.assistant.tools` has been imported. `mcp_server` gets that through the package `__init__`; a script or test that imports `registry` alone sees **zero tools** and reads as a broken registry rather than a missing import. `tools/` must stay **astropy-free** — the MCP handshake budget depends on it, so the planning tools import `m110.planning` inside their function bodies, never at module scope (mirroring `prioritize.build_contexts`). `serialize.py` = **the one place** engine values become JSON (naive-local datetimes get the site's real offset — never an implied UTC; Paths become store-relative or a basename, so no home-directory leak; `ToolResult.drop_keys` strips the chart arrays, 83% of a plan payload). `proposals.py` = the `m110.proposal/v1` envelope: `preview` runs the **pure** scorer twice so a before/after ranking can't be fabricated, `basis.store_state` fingerprints the data so a later apply path can detect drift, `apply.safe_write` is the allowlist seam. `vision.py` = in-memory FITS/TIF → JPEG for image critique (NOT `webexport.export_for_sharing`, which writes to disk). `skills.py` + `skills/<id>/SKILL.md` (the Claude Skill layout) served as MCP prompts **+** resources **+** a `get_skill` tool from one loader. `store.py` raises `StoreUnavailable` rather than a bare `FileNotFoundError` when the pinned data root is wrong. `mcp_server.py` = the only module importing `mcp`; it redirects `sys.stdout` → stderr **first** (13 bare `print()`s in the engine would corrupt the JSON-RPC stream). Built on **SDK v2** (`mcp>=2,<3`): handlers are callables passed to `Server(on_list_tools=…, on_call_tool=…, …)`, take `(context, params)`, and return Result models — the v1 decorator API (`@server.list_tools()`) was removed upstream. Chose the low-level constructor over `MCPServer`, whose decorators are per-function and derive schemas from type hints: our 16 tools are **dynamic**, built from `registry.all_tools()` with explicit JSON Schema, so the constructor takes that list directly. A `ToolInputError` deliberately returns `is_error=True` **content** rather than raising (v1's wrapper converted raises into `isError` results, and a model recovers from a result far better than from a transport failure). Don't trust the suite here — it never imports `mcp`; `tools/smoke_mcp.py` (wired into `ci.yml`) starts the server for real, which is what makes the `<3` bound a checked claim rather than a comment. `client_config.py` = Claude Desktop config merge (Qt-free, so the Preferences button stays a thin widget). `outbox.py` = **the only writer** — create-only, one directory, name-sanitized, resolved-then-contained (so traversal/symlink escapes fail closed), quota'd; holds Tier-1 artifacts *and* staged proposal envelopes so the app has one queue. `apply.py` = **app-side only**, the sole caller of engine writers; a test asserts nothing the server can reach imports it, which is what keeps the proof airtight rather than merely narrower. Proven by a byte-identical manifest *outside the outbox*, write-syscall interception, a static AST denylist (+ a one-entry `SANCTIONED_WRITES` carve-out that is itself re-validated), and adversarial containment tests |
| `updates.py` | **in-app update check** (Qt-free, stdlib `urllib`; `feature/update-check`). Also owns **`version_tag`/`user_guide_url`**: Help → User guide is pinned to the running build's **release tag**, never `main` — `docs/` on main describes unshipped work, so linking a user there documents features they do not have. A tag is immutable, so a build's guide always matches the app in the reader's hands. Points at **`m110.space/docs/<tag>/`** — rendered by `tools/build_docs.py`, published by `release.py`'s `docs` phase; `USER_GUIDE_URL` (GitHub `main`) survives only as the fallback for a source/dev build, whose code is ahead of every published version, so the newest *release*'s copy would be the same mismatch in the other direction. The tag derivation mirrors `tools/release.py` (the authority, which computes version and tag from one argument so they can't disagree) and a test pins the two together. `check()` fetches the GitHub `/releases` (not `/releases/latest` — the beta is a pre-release), picks the newest by PEP 440 (`packaging`), and compares to `current_version()` → `UpdateInfo{current,latest,url,is_newer}`; degrades silently offline (returns `None`). Throttle/prefs in `settings.json`: `update_check_enabled` (default on), `last_update_check` (`should_check`/`record_check` gate the launch check ~daily), `update_skip_version` (`skip_version`/`is_skipped`). `REPO` = the one repo constant. `about_dialog.app_version` delegates to `current_version` |
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
| `main.py` | **Shell**: left nav rail (`QListWidget`) → `QStackedWidget` of pages [**Library · Overview · Planning · Import · Processing**] — a 5-pane rail (**Planning** added post-beta for the session-planning arc; the pre-launch cleanup had merged Goals+Summary into **Overview** and absorbed Media/Journal/Sessions into the Library). **Library (grid) is the landing "home"**; a fresh empty store lands on **Overview** (welcome/CTA). `overview` page's `dirty` → `_do_refresh`. The **brand mark** (`_LogoLabel`) sits at the **foot of the nav column**, just above the status bar, and is **clickable → About** (through `widgets.defer` — `.exec()` must not open inside the label's own mouse handler); the **column**, not the rail, paints the `surface` + `border-right`, so the divider runs full height behind the mark — hence `WA_StyledBackground` on `#navColumn`. Menus are built by **`_build_menus()`** into **File · View · Library · Tools · Help** — *one* structure on every platform, no `sys.platform` branch, because the `MenuRole`s hoist About/Preferences/**Quit** into the macOS app menu by themselves (the old two-menu Library+Help shape only read acceptably *because* of that hoisting: off macOS it filed Preferences under "Library" and offered no way to quit at all). **File** = Import… Ctrl+I · Publish / share… · Exit (`QuitRole`); **View** = the five panes, checkable + exclusive, Ctrl+1–5, built from `NAV` and kept in sync both ways with the rail (`_sync_view_menu`); **Library** = Refresh Ctrl+R/F5 · Add object… · Fill missing metadata (bulk reference backfill) · Enrich online… (bulk Simbad on a worker); **Tools** = Prepare working folders · Back up/Restore · Preferences… (`PreferencesRole`); **Help** = User guide · Check for updates… (`updates` via a worker) · Report a problem… (`error_report`) · About M110 (`AboutRole`). The one platform conditional (`hoists_roles`) is *cosmetic, not structural*: on macOS the separator introducing Exit/Preferences is skipped, because Qt leaves it behind **unhidden** in the NSMenu once the action hoists away — a dangling rule at the foot of File and Tools (verify with `NSApplication.sharedApplication().mainMenu()`, not by reading the Qt-side `menu.actions()`, which still lists the hoisted action in place). The status bar carries the **data root** + operation extras only — the captured/total count was dropped (it duplicated the Library's own stat row). A quiet **update banner** (`update_notice.UpdateBanner`) shows above the page stack when the throttled launch check finds a newer release. No separate "M110" menubar menu. On macOS the app-menu/dock name is set to "M110" via a best-effort NSBundle patch (`_set_macos_app_name`, needs `pyobjc-framework-Cocoa`; the durable fix is a packaged `.app`). `RefreshWorker` (scan→derive→render + `prepare_missing`) drives `page.reload()`; **auto-syncs** on launch / window-focus / after ingest. `open_object(slug)` routes any page's object link → Catalog + selects it. Overview's `go_to_import` (empty-state CTA) → `_open_ingest`. `main()` calls `logsetup.setup_logging()` + `error_report.install_excepthook(app)` (crashes → dialog+log, not abort) + `first_run_dialog.run_first_run_if_needed()` before the window (first-launch data-folder prompt). `_maybe_backup_nudge` (in `_on_refresh_done`) prompts a backup **once ever**, only once captures exist (`backup_nudge_seen` setting). Journal-edit lock disables nav + global actions + `view_actions` (else Ctrl+1–5 walks around it) |
| `widgets.py` | shared `NumItem` (sort-key cell), `status_label`/colors, `targets_for_slug`, `make_table`, async cached row-thumbnail loading (`ThumbnailLoader` + `RowThumbnails`, hero-backed; Library/Sessions/Processing row icons; `ThumbnailLoader.request(..., crop=)` supports both the row-icon aggressive crop and a milder "square" crop for bigger tiles), `paint_status_chip()` (the tinted-rounded-chip paint primitive, shared by `StatusPillDelegate` and the Library grid's `TileDelegate`), `CollapsibleSection` (the macOS disclosure-triangle collapsible group used across the Overview pane; `on_toggle` lets the owner persist open/closed state), `fit_table_height(tbl, max_rows=, half_row_pad=)` (size a populated table to `header + Σ row heights` + ½ row so it neither truncates a row nor leaves dead space; `max_rows` caps + turns on the scrollbar — the single fix for the beta table-height bugs, used by processing/overview/detail), **`fit_cell_widgets(tbl, *cols)`** (its partner for tables holding a cell **widget**: the QSS pads `QTableView::item`, Qt lays cell widgets out *inside* that padded rect, and `resizeColumnsToContents` measures items and skips widgets — so a button cluster clips horizontally *and* vertically. Sizes the named columns + every row from the widgets' own `sizeHint`, in the same `SPACE` tokens the stylesheet uses so they can't drift. **Call it before `fit_table_height`**, and note the height must be a *minimum section size*: `fit_table_height` runs `resizeRowsToContents`, which re-measures from the items and would undo a per-row height), **external-app launch helpers** (#19): `working_dirs_for_slug`/`can_process_slug`, `process_in_siril`/`process_target_in_siril` (single dir → launch, split sandbox → job-folder chooser, `launch.LaunchError` → reveal-folder fallback dialog), `open_in_default`/`reveal_in_manager` (`QDesktopServices`), **`drain_worker(w)`** (wait → `deleteLater` → return `None`; **the** way to drop a QThread reference — the unsafe version defeats the teardown guards and aborts the process, see the gotcha), **nested-loop safety** (`fix/refresh-during-modal`): `modal_loop_active()` (a modal dialog or popup owns a nested event loop → don't tear down widgets), `defer(widget, fn)` (`QTimer.singleShot(0, …)` — run *after* the current Qt handler returns) and `connect_context_menu(view, handler)` (**the** way to wire a right-click menu: policy + a deferred open, so `QMenu.exec` never spins inside the view's own C++ mouse handler) |
| `image_grid.py` | reusable tile-grid component (`TileItem`/`TileModel`/`TileDelegate` — `QAbstractListModel` + `QStyledItemDelegate`), app-data-agnostic (no imports from `catalog`/`objects`/`derived`) so a future cross-object image browser can reuse it; the Library grid (`pages/catalog.py`) and the Media grid (`pages/media.py`) are its consumers. Owns `GRID_ZOOM_MIN/MAX/DEFAULT` (a grid concern, so the Media grid doesn't import the Library page). `TileItem.badge` = an optional glyph painted over the thumbnail (▶ for video) — generic, so the module stays app-data-agnostic |
| `detail.py` | shared per-object `DetailPane`: header/status, hero (scales to pane), **Object Notes** **view/edit** (raw `journal.md` — the object's entry in the top-level Journal feed; labeled "Object Notes" to leave room for future Session/Processing Notes), gallery — **split into "Finished" / "Working files" groups** (#17; base tier = finished/ folder vs stacks/seestar, overridden per-image by `objects.get_curation`), double-click → image viewer (items carry a global index so the viewer navigates across both groups + `_gallery_meta()` display metadata — Source/Date/Size always, Integration/Filter when unambiguously derivable; compact center-cropped-square contact-sheet grid via `_square_icon()`, elided filenames with a full-name tooltip); **right-click a tile → Set as hero** (writes `hero` frontmatter + `build_images.rebuild_hero`, emits `saved`) / **Mark as finished\|working** (`objects.set_curation`, in-place regroup) / **Export for sharing…** (`export_dialog`) / **Open in default app**\|**Reveal in file manager** (#19, `widgets.open_in_default`/`reveal_in_manager`) — the **same menu is on the hero image** (`_run_image_menu`, acting on the hero's *source* via `build_images.hero_source_path`), and **double-clicking the hero opens the viewer at the hero's own place in the gallery** (`_hero_gallery_index` → `_open_hero_viewer`, so Prev/Next carry on across both groups instead of restarting at tile 0; deferred past `mouseDoubleClickEvent` like the gallery's, and a no-op when the hero isn't one of the gallery's images), **Import finished work** + **Process in Siril** + **Reveal working folder** buttons (#19), + per-object **Processing** + **Sessions** tables and an **Object details** block (type/mag/size/season, RA/Dec in decimal + sexagesimal, filter rule, slug, capture targets, **Remarks** = the library `notes` field). Shows real filenames |
| `pages/catalog.py` | the **Library**: a table view (Object/Name/Type/Season/Mag/Size/Filter/Status/Integration/Sessions; Object shows all identifiers via `catalog.object_identifiers`, e.g. "C20 (NGC 7000)") **and** a **grid view** (`image_grid.TileModel`/`TileDelegate`, one tile per object — hero + id/name + status chip + integration), **and** a **Feed view** (embeds `JournalPage` — the reverse-chron object-card feed, absorbing the old Journal pane), selected by a **three-way List·Grid·Feed segment** (`_view_btns`, persisted; **grid is the default home view**) + a zoom `QSlider` in a `QStackedWidget`; the object views build from one shared `_current_items()`/filter pipeline so search/catalog-filter/captured-only and selection stay in sync + a **Catalog filter** selector (All / Messier / Caldwell …) + **search** + captured/deep/total/**integration** **stat row** (per-filter; the compact Library header strip). Both segments share **one control row** (Deep sky·Media left, List·Grid·Feed right), each a **joined segmented control** (`_make_segment` → `#segControl`/`#segButton` QSS); the view segment lives here (not on the hideable catalog-filter row) so it can't shift in Feed mode, and it hides in Media scope. A top **Deep sky · Media segment** (`_scope_stack`) switches the whole page between catalog objects and an embedded `MediaPage` (absorbing the old Media pane); routing to an object forces the Deep-sky scope + a selectable view. Hosts the shared `DetailPane`; `select_object`/`reload` work identically regardless of active view; per-object import flow; **right-click → "Fill in missing metadata"** (reference) + **"Enrich online"** (Simbad, on a worker; `OnlineLookupError`→dialog) + **"Remove from Library"** (`catalog.remove_library_entry`; confirm, non-destructive) + **"Pin as priority" / "Deprioritize"** (`pins.set_state`, #3 — a ▲/▼ marker on the Object cell/tile via `_pin_marker`; `pins_changed`→shell lightweight reload) + **"Process in Siril"** (#19, shown when the object has a working folder → `widgets.process_in_siril`); edit-lock |
| `pages/overview.py` | **Overview** — the landing dashboard, merging the former Summary + Goals pages into one pane of **collapsible sections** (`widgets.CollapsibleSection`, the macOS disclosure-triangle pattern; each section's open/closed state persists across launches via settings `overview_sections`). Sections (in order): **Goals** (progress hero) · **Priority targets** (`_priority_rows`: **manual pins only** — the legacy `priorities.toml` source was dropped since the auto-prioritizer isn't shipped; carries an "in development" caption; right-click Pin/Deprioritize via `pins_changed`) · **Integration Time and Sessions** (per-target integration table + a "Last 5 Sessions" table + a "View all sessions…" button → `SessionsPage` in a dialog) · **Goal checklists** (per-active-goal membership tables, green check per Captured/Deep) · **Progress by category** · **Manage goals** (goal *setup* demoted here, wrapped in a bordered `#manageGoalsBox` frame since it's the one non-table section: activate/deactivate catalogs + custom-goal CRUD, nested collapsible hemispheres; → `goals.set_active_goals`, emits `dirty`). Tables sized via `widgets.fit_table_height`. **Empty store** → welcome card + "Import images…" CTA (`go_to_import`) + Manage goals so a new user can pick a catalog. Object rows → `open_object` |
| `pages/processing.py` | Siril queue grouped by status; a **"Ready to import"** group (targets with unimported Siril output — `derived` `ready_for_import` flag, set via `siril.has_unimported_output`) takes precedence over the status groups; **Up to date** is not shown (nothing to do). Columns: Object/Raw integ/In stack/Rejected/+ new/Latest stack/Last capture/**Notes** (the Star-removal column was dropped). Tables use `widgets.fit_table_height`; rows → `open_object`; **right-click a row → "Process in Siril"** (#19, per-target via `widgets.process_target_in_siril`, shown only when that target has a sandbox) |
| `pages/sessions.py` | capture-session log (sortable table Date/Object/Frames/Exp/Filter/Integration/Mount, default Date-desc) + search box; from `derived.load_sessions()`; rows → `open_object`. **No longer a nav pane** — opened in a dialog from Overview's "View all sessions…"; per-object sessions live in the `DetailPane` |
| `pages/journal.py` | reverse-chron **feed** of object cards (header · hero · status/stats · rendered notes) — every captured object + any noted-but-uncaptured; ordered by latest image mtime (reprocess re-orders); search box; cards → `open_object`. **No longer a nav pane** — embedded as the Library's **Feed** view |
| `pages/media.py` | **Media** browser for non-catalog `Media/<Category>_photo\|_video/` — structurally a sibling of the Deep-sky scope: one filtered `media.list_media()` list feeding a **List** (sortable table + `media_detail.MediaDetailPane`) and a **Grid** (`image_grid` tile wall + zoom slider), category/kind/search filters, persisted `media_view_mode`/`media_grid_zoom`. Photos → `ImageViewer` positioned within the filtered photo set; videos → OS player; both via `widgets.defer`, menus via `connect_context_menu`. `set_view_mode` is driven by the Library's shared segment, and `view_mode_changed` travels **back** so a programmatic change can't leave those buttons stale. Thumbnails go through `ThumbnailLoader` — see the QIcon gotcha. **No longer a nav pane** — embedded as the Library's **Media** scope |
| `media_detail.py` | per-media detail pane (preview via `ScalableImage`, file facts, Open/Reveal/Export). Its own module rather than bolted onto `detail.py`, which is entirely catalog-object-shaped. Also home to the shared `fmt_size`/`fmt_date` |
| `media_cleanup_dialog.py` | **Tools → Clean up imported sidecars** — checkable tree of `media.cleanup_candidates()` grouped by folder, nothing pre-selected, confirm before `media.discard`. A live video poster is never listed |
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
| `handoff_dialog.py` | **Send a stack to a post-processing workflow** (ROADMAP 14a). Preview-then-confirm over `stacking.handoff_candidates`; the write is `stacking.apply_handoff`, the same function `m110-stack --handoff` calls, so CLI and app can't drift on the convention. Preselects a **linear** stack (from HISTORY, not the filename) because the newest file in `stacks/` is very often one of the user's own stretched steps; a stretched pick is allowed but says so. Row identity is carried on the item (`Qt.UserRole`), never the visual row — `make_table` enables sorting, and reading a selection back by position sent a *different* file than the one highlighted. No Size column on purpose: the handoff is a hardlink, so showing a size beside "costs no extra disk" invites the opposite conclusion. `can_hand_off` is the cheap gate the detail pane calls per render |
| `export_dialog.py` | **Export-for-sharing dialog** (`ExportShareDialog`, `feature/image-export`) over `webexport`: a **Max size** spinbox + **No maximum** checkbox + lossless/quality strategy radios; **Export…** → the **native OS save panel** (`QFileDialog.getSaveFileName`, native — rename/relocate) pre-filled with `suggested_name` (`[Object]-[maxsize]-[YYYYMMDD]`), then a threaded `_ExportWorker` runs the ladder behind a busy `QProgressDialog`+Cancel (status = the ladder step trail; `_finish_worker` **waits** the thread before `deleteLater` — else ~QThread SIGSEGVs on teardown); success → summary + Reveal/Open. Entry points: detail-pane gallery right-click + the hero image ("Export for sharing…") + the image viewer's ⤓ Export…; last strategy/max-MB/no-max/dir persist in settings |
| `mcp_details_dialog.py` | **MCP connection details** — the client-neutral half of the assistant setup. The server is plain MCP over stdio, so this offers the same connection in the three shapes clients ask for (a `mcpServers` JSON block · command+env · the `claude mcp add` line), each with Copy, over `client_config.connection_details()`. Preferences keeps a one-click path for Claude Desktop only because its config is a JSON file M110 can merge into safely — not because it is the only supported client |
| `preferences.py` | choose data folder (save + restart) + **"Processing workflows you use:"** checkboxes → `processing_workflows` (14b: reframed from "Prepare objects for processing in:" because AstroWizard has no prep step — Siril checked = auto-prep, AstroWizard checked = offer Send-to/Import; stored as a **`{id: bool}` map** via `processing.set_enabled_workflows` so a workflow added later reads as *unanswered* rather than *declined*, which is what stops an upgrade silently switching AstroWizard off) + **"Keep the last N processing sessions"** spinbox (`processing_archive_keep`, 0 renders as "all") + **"Processing tools"** → one path row **per registered tool** (`launch.tool_ids()`, so a new workflow gets an override with no dialog change; `external_app_paths.<id>`, override for `launch.find_app`; placeholder shows the auto-detected path; #19) + **"Finished-image hints"** editable keyword fields (finished / intermediate) → `hints.set_hints` (#17) + **Import** → "Import per-sub JPG previews" checkbox → `import_sub_previews` (#25) + theme + **Updates** → "Check for updates on launch" → `updates.set_check_enabled` + **AI assistant** → Connection details… (any MCP client) · Set up Claude Desktop… · Disconnect · "save plans straight to Plans/" (`assistant_direct_save`). **The settings column scrolls and every explanatory label wraps** — the dialog outgrew a laptop screen, and both overflows showed up as text with a line sliced off rather than an obviously-too-small window (vertical: Qt squeezes wrapped labels below `heightForWidth`; horizontal: one *unwrapped* label's single-line width becomes the dialog's minimum width). `test_no_explanatory_text_is_cut_off` guards both. (Goal management lives in Overview → **Manage goals**.) |
| `publish_dialog.py` | **Publish / share** dialog (item 8a, off the Library menu): section checkboxes + global "exclude journals" + target picker (`publish.PUBLISHERS`, "(soon)" for disabled) + a **Repository field + Uploads mode combo under GitHub Pages** (`owner/repo` or git URL, persisted `publish_github_repo`; replace ↔ incremental, persisted `publish_github_deploy_mode`, default replace — both live only while that target is checked) + a **gallery-level combo** under Image galleries (finished / +device stacks / all; `publish_gallery_level`, default finished) + site-title + output-folder chooser → threaded `_PublishWorker` running `publish.run_publish` behind modal progress+Cancel (stage labels via the worker `status` signal — "Rendering site…"/"Uploading to GitHub…" — the bar resets per stage; a user cancel closes quietly, and the engine kills the git push so teardown can't beach-ball); **Save** persists every choice without publishing; "Open folder" (+ "Open site" with the pages URL after a GitHub Pages deploy) on success |
| `backup_dialog.py` | **Back up Library** dialog (item 10, Library menu): destination **pre-seeded from the saved setting** (Browse overrides ad-hoc; a run saves it back), which now accepts a folder **or `s3://bucket/prefix`** (#93) + snapshot-status line + Automation/retention group (auto on · interval · **Back up now** beside the toggle · keep-N snapshots (default all) · min-free-GB (default 100); no age-based "older than N days" policy — it would wipe history after a gap in use) → threaded `_BackupWorker` running `backup.create_snapshot` behind modal progress+Cancel; bottom buttons are **Save**/**Cancel** (Save persists settings without running a backup) + **Restore…**; "Open folder" on success (suppressed for a bucket — a button that silently does nothing is worse than none). **Cloud half:** typing `s3://` reveals a **Cloud storage** group (endpoint URL · region · access key id · secret) and a **Back up:** scope combo. `_sync_cloud_visibility` reflects everything knowable from the destination *string* immediately — format forced to pooled + disabled, its own `CLOUD_FORMAT_NOTE` (the pooled blurb concatenated said "stored once, named by its contents" twice and promised a browsable `latest/` copy, which is the one thing object storage can't do), min-free disabled — because a bucket **is not probed until Test connection**, so anything the probe would fix is on screen until then. That button, not `editingFinished`, is what probes: a probe needs the credentials to make it, and the only way to give them to it is to save them, so an automatic probe would write the user's keys to the keyring as a side effect of leaving a field. The **secret is never populated from the keyring**, not even masked — empty means "keep what's saved" (else opening the dialog to change the interval would wipe it), and the placeholder tracks the *current* access key id so switching ids can't imply the old secret came along. `_fit_height` re-fits when the group appears (a layout that doesn't fit is squeezed, not scrolled — the overlapping-spin-boxes lesson) |
| `restore_dialog.py` | **Restore from backup** dialog (item 10): snapshot picker (by date) + a checkable file **tree** (from the snapshot manifest) + restore target (**extract to a folder** default, or **into the store** behind a create-vs-overwrite conflict preview + confirm) + **Verify integrity** (`backup.verify`); threaded `_Worker` (shared by verify + restore) behind modal progress+Cancel |
| `about_dialog.py` | **About M110** dialog (UI Phase 4 branding; Help menu, `AboutRole` so macOS folds it into the app menu — **and the nav-column brand mark**): theme-recolored logo + tagline ("Complete the catalog.") + version (`importlib.metadata`) + **update status** + Uranometria credit + Apache-2.0 line. The status line answers the question the version line provokes: `showEvent` fires `start_update_check()` on **every** appearance (never `__init__` — workers start on explicit actions, which is also what keeps offscreen tests off the network; `check_updates=False` suppresses it), reusing `update_notice.UpdateCheckWorker` with **`record=False`** so an About peek never consumes the daily launch throttle, and running regardless of the launch-check preference (same as Help → Check for updates…). States: `CHECKING` → `CHECK_FAILED` / `UP_TO_DATE` / "Version X is available — Download" (link to the release). `done()` **waits** the worker before teardown (the export-dialog SIGSEGV) |
| `error_report.py` | **global error handling + crash/report flow** (the beta crash-reporting arc). `install_excepthook(app)` (called in `main()`) replaces PySide6's abort-on-uncaught-slot-error with: log the traceback, show `ErrorReportDialog` ("M110 hit a problem", copyable report + prefilled GitHub new-issue via `issue_url`), and **return without aborting**. Worker-thread exceptions marshal to the GUI thread (`_Dispatcher` queued signal); re-entrancy-guarded. `build_report(exc_info=)` = env (version/OS/Qt/data-root/log) + traceback + log tail. Same dialog (non-crash) backs **Help → "Report a problem…"**. `REPO_URL` is the one knob to change when the public repo name is settled |
| `first_run_dialog.py` | **first-launch welcome / data-folder prompt** (onboarding). `run_first_run_if_needed()` (called by `main()` before the window): when `config.is_first_run()` (no env, no saved pref, no store at the default), shows `FirstRunDialog` (branded welcome + a data-folder field pre-filled with the default + Browse + "Get started") → persists the choice (`save_data_root`) + bootstraps (`ensure_data_root`); cancel falls back to the default. Persisting the pref means no re-prompt next launch; a returning user (existing default store) is never prompted |
| `theme/` | **design system** (UI Phase 0; `m110/ui/theme/`). `tokens.py` = light+dark semantic palette (`LIGHT`/`DARK` `Tokens`; roles like `window`/`surface`/`text_secondary`/`accent`/`status_deep`) + `SPACE`/`RADIUS`/`FONT_SIZE` scales + `active()`/`set_active`. `qss.build_qss(tokens)` generates the app-wide stylesheet. `manager.ThemeManager` applies it + **follows the OS appearance** (`QStyleHints.colorScheme()`, live via `colorSchemeChanged` on Qt≥6.8 else focus-in `refresh_system`) with a persisted `ui_theme` override. `fonts.py` bundles **JetBrains Mono** (`fonts/*.ttf`, OFL) + `mono_font()`. Façade: `install(app)` (in `main()`), `set_mode`, `active_tokens`, `status_color`/`muted_color`/`ink_color`, plus the brand helpers `app_icon`/`logo_pixmap`/`logo_icon`. `brand.py` = theme-aware branding (UI Phase 4): `logo_pixmap(height, color)` recolors the bundled `brand/m110-logo.svg` ink — any near-black `fill` (style **or** attribute form) → the target color, then applies an **alpha dilation** (`LOGO_STROKE_WIDTH`, viewBox units — Qt's SVG renderer silently ignores strokes on this complex path, so weight is added by dilating the rendered ink, not an SVG stroke) so hairlines read when scaled — then tight-crops (fast path = path bounds; fallback = transparent-pixel autocrop, so a **drop-in replacement SVG needs no code changes** as long as it's black ink on transparent). Wordmark reads in light **and** dark; the nav-rail mark recolors on `ThemeManager.changed`. `app_icon()` composes the ink (deep sepia) on a **fixed parchment tile**, inset ~80% of the canvas (dock-icon grid) — app/dock icons intentionally **don't** follow the theme; `tools/gen_app_icon.py` exports `brand/app-icon.png` for packaging. (A warm-sepia `accent` was tried in Phase 4 but **reverted** — the accent stays the neutral blue.) **Control metrics are tuned against native macOS** (measured styled-vs-unstyled in a real cocoa app, not guessed): inputs 26px / nav-rail rows 28 / table rows 23 / headers 29, with buttons and combos deliberately left at 30 because they were *already* under the platform's 32. The two `min-height: 20px` literals (buttons, inputs) are **anti-clipping floors, not sizing** — written as literals precisely so retuning a `SPACE` token can't move them; `tests/test_theme_qss.py` guards both. `QTableView::item` padding is paired with `widgets.CELL_WIDGET_PAD_*` and must change with it. **New UI code pulls color/spacing from tokens — never hardcode hex.** Programmatic (non-QSS) colors repaint via a page `restyle()` on `ThemeManager.changed`; muted labels use the `QLabel[muted="true"]`/`[caption="true"]` QSS rules |

---

### Conventions & rules

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
  `M110_DATA_ROOT` + the `config.*` globals + `SETTINGS_FILE` + `APP_CONFIG_DIR` at a
  throwaway dir for the whole run** — so even a `QThread` worker that leaks past its
  per-test `monkeypatch` (which once corrupted a live `library.toml`) can never read/write
  `~/Documents/M110` **or `~/.m110`** (the log lives there, and the crash report embeds
  its tail — an unsealed log made `test_error_report` fail whenever the developer's own
  app had crashed). Keep per-test `seed_root` + the MainWindow `_ready = False`
  guard anyway (defense in depth).
- **The manual-test harness is part of the change, like the docs.** An engine
  rename or a removed function must be carried through **`tools/make_test_corpus.py`**
  (and `create_test_harness.sh`) in the *same* commit. That generator builds the
  store `./create_test_harness.sh` launches the app against, so it is the only way
  the [`TESTING.md`](TESTING.md) GUI flows get exercised at all — but it lives
  outside the package, so a break there doesn't fail anything until a human sits
  down to run a manual test and gets a traceback instead of an app. That is exactly
  how `media.scan()` (removed in the media-first-class work) survived in the
  generator for a whole release cycle. `tests/test_make_test_corpus.py` now **runs
  the real generator** (~1s into a temp dir) rather than checking that the names it
  calls still exist: the same change also turned `media.scan`'s dicts into
  `MediaItem` dataclasses, and a symbol-existence check waves that straight through.
  When a feature lands, also ask what the corpus must **contain** for a tester to
  see it — the Media work shipped video posters, recursive discovery and the
  sidecar clean-up against a corpus holding one bare `.mp4`.
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
  loose-`.py` reconstruction hid this (the parsetab existed as a file there). Optional
  **sky map** = `uranometria`, deliberately **not** declared in `pyproject.toml` (not on
  PyPI; a direct-URL requirement would poison any future upload, extras included) — so
  each build job `pip install`s it *explicitly*, and the three specs
  `collect_data_files("uranometria")`. Optional **cloud backup** = `s3` extra
  (boto3 + keyring), pulled in by `build`; the specs also `collect_data_files` for
  **boto3/botocore**, because botocore carries its whole API surface as *data* and loads
  a service model at client-creation time — modules-without-data raises
  `DataNotFoundError` the first time a frozen app touches a bucket (the astropy parsetab
  shape, #75). boto3 is deliberately **not** in `dev`: `S3Backend`'s conformance tests run
  against an injected fake client, so the suite proves the adapter with no AWS SDK and no
  network. **Both halves are load-bearing**: skip the install
  and that installer silently has no Map view; skip the data and the frozen app **crashes
  at launch** — `uranometria.catalog` reads its constellation JSON at import, and the
  Library builds the Map view inside `CatalogPage.__init__` (0.3.0-beta.1). Data only, no
  `collect_submodules` — `uranometria.annotate` imports the excluded matplotlib. Dev =
  pytest (+ astroquery for `tools/gen_caldwell.py`). Declared in `pyproject.toml`.

---

### Testing

```bash
pytest -q                 # all
pytest -q tests/test_ingest.py
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # (won't render, but imports/constructs)
```

1568 tests, all fixture-based. The **UI is driven offscreen with pytest-qt**
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

### Roadmap

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

### Gotchas / lessons learned

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
- **The macOS `.app` must set `LSBackgroundOnly: False` explicitly.** PyInstaller's
  `BUNDLE` inherits `console` from the `COLLECT`, which inherits it from its EXE args
  **last-one-wins** — and ours is the `console=True` MCP server (which cannot become
  windowed: the Windows GUI subsystem has no stdio). PyInstaller reads that as
  "console app" and stamps `LSBackgroundOnly=True`, so LaunchServices registers M110 as
  `type="BackgroundOnly"`: **no menu bar, no Dock icon, not in Force Quit**, window
  can't take focus properly. The user `info_plist` is merged *over* the defaults, so the
  explicit key is the fix. Bit 0.3.0-beta.1/b2; invisible in b1 only because that build
  crashed first. Diagnose this class with `lsappinfo list | grep -A6 space.m110.M110`
  (`type=`) and `plutil -p <app>/Contents/Info.plist` — not by reading the spec, which
  looks innocent. Any future console EXE added to the bundle re-arms it.
- **A backup destination that can't hardlink silently stored a full copy per night.**
  The mirrored format dedups by `os.link`ing to the previous snapshot; where that
  fails it byte-copies *everything*, correctly but at N× the size — and the only
  signal was a `hardlinks: false` field in a manifest that didn't exist until after
  the first run (issue #92). Two lessons baked in: (a) **probe the capability up
  front and say what you found** (`backup.probe_destination`, run on a worker — a
  dead SMB mount blocks `os.stat` indefinitely, and the old status line did this
  inline on every keystroke); (b) when a destination leaves no good option, **change
  behavior and tell the user**, don't degrade quietly. Pooled storage is that
  behavior. Corollary for testing: a link-less filesystem can't be faked well in
  pytest — monkeypatching `os.link` covers the code path, but the release drill is a
  real FAT32 disk image (see TESTING.md §2.5a; §2.5b runs a local MinIO for the
  cloud path, which needs no account).
- **Pooled backup objects are mode 0444, and that bites on Windows.** A `latest/`
  entry is a hardlink to its object — same inode — so an in-place edit there would
  rewrite content every snapshot sharing it references; read-only is the guard.
  But Windows refuses to delete a read-only file, so GC/`unlink_rel`/overwrites must
  `chmod` first (`backends/local._chmod_writable`). Won't show up on macOS or Linux
  CI. Restored files are explicitly chmod'd back to 0644 — a restore that hands the
  user read-only files is its own bug.
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
- **Measure a styled control against the platform before "fixing" its size.** A
  "the UI looks clunky" report is a measurement question, and the answer is often
  not where it feels like it is. Recipe: **one real cocoa `QApplication`**, build the
  widgets twice — once with `theme.install(app)` and once with
  `app.setStyleSheet("")` — and diff `sizeHint()`. Same style, same font, only the
  sheet differs. Doing that found the opposite of the report: `QPushButton` and
  `QComboBox` were already **2px under** native macOS (30 vs 32) and the body font is
  *byte-identical* to `QFontDatabase.systemFont(GeneralFont)` at 13.0pt — while the
  real bloat was text inputs (30 vs 21), the nav rail (36 vs 17), table rows (27 vs
  19) and headers (33 vs 21). Two follow-ons worth knowing: macOS deliberately draws
  `QToolButton` at 10pt and `QHeaderView` at 11pt, so a blanket
  `QWidget { font-size }` silently upsizes exactly those; and a QSS `min-height`
  sizes the **content** box, so it is the anti-clipping floor and cutting *padding*
  can never narrow the text band.
- **Styling any property of a widget hands its WHOLE rendering to the stylesheet —
  sub-controls included.** Set one colour on a `QSpinBox` and QMacStyle stops drawing
  it, so the native stepper degrades to two ~2px dots; add `::up-button`/
  `::down-button` rules without `::up-arrow`/`::down-arrow` images and you get an
  empty compartment, which looks *more* broken. Sub-controls travel with their
  arrows (`theme/icons/chevron-{up,down}.svg`, one neutral grey because QSS has no
  `currentColor`). We can't have themed colours *and* the native stepper; the colours
  win because dark mode needs them.
- **A dialog's reject button says "Cancel" only when it can undo something.** Default
  it to **Close**, and switch to Cancel (with Save enabled) only while there are
  unsaved edits — see `backup_dialog._sync_exit_buttons`. That dialog persists its
  settings inside "Back up now" *before* the run, so after a manual backup "Cancel"
  was simply untrue: `reject()` only closes the window. Track dirty from
  `textChanged`, **not** `textEdited` — `textEdited` skips programmatic writes, and
  Browse sets the field with `setText()`, so a corrected path left Save greyed out.
- **`&` in a widget label is a mnemonic marker.** Qt eats it and underlines the next
  character, so `QGroupBox("Automation & retention")` renders as "Automation
  retention". Write `&&`. Guarded across `m110/ui/**` by a source scan in
  `tests/test_ui_widgets.py`.
- **Never build a `QIcon` from a file path for a fixed-size icon — it distorts, and
  only for some formats.** `QIcon(str(path))` painted at `setIconSize(160, 160)`
  **fills** the square, ignoring aspect ratio. Measured on a real 1080x1920 lunar
  capture: the Moon's bounding box is `749x745` (aspect **1.005**) in the source and
  `111x62` (aspect **1.790**) through QIcon — squashed by exactly 1920/1080, which is
  how "the Moon is an oval" got reported. The trap is that it is **format-dependent**:
  the JPEG handler advertises `ScaledSize`, so Qt asks it to decode straight to the
  target size and it obeys literally; PNG advertises no such support, so Qt loads
  full-size and scales `KeepAspectRatio` — *correctly*. The same line is right for a
  PNG and wrong for a JPEG, and every Seestar/Dwarf still is a JPEG, so testing with a
  synthetic PNG "proves" the bug absent. Always go through `widgets.ThumbnailLoader`
  (off-thread, center-crop-then-scale, mtime-keyed cache) or `detail._square_icon`;
  `QIcon(pixmap)` is fine, since the caller has already done the work. Regression-test
  the **subject's** shape, not the pixmap's — asserting the pixmap is 160x160 *passes*
  on the broken code. `tests/test_thumbnail_aspect.py` measures a synthetic circle's
  roundness and AST-scans `m110/ui` for `QIcon(<path>)`.
- **A callback body isn't evaluated until it's clicked — so a missing import in one
  passes every test that only *builds* the page.** `detail.py` imports *names* from
  `m110.ui.widgets`, never the module, so a lambda calling `widgets.stack_in_stackingwizard(...)`
  raised `NameError` the first time a user pressed the button; the helper it reached
  then read `config`, which `widgets.py` binds nowhere, and `launch`, which it imports
  only inside a *different* function. Three undefined names, zero test failures, and
  a crash dialog in the user's hands. Constructing a widget proves its constructor
  runs and nothing more. Two guards, complementary on purpose
  (`tests/test_ui_button_wiring.py`): an AST pass over `m110/ui/**` flags any name
  *read* that is bound nowhere in the file (deliberately scope-blind — over-generous,
  so anything it flags is real), and a test that **actually clicks the button** and
  asserts what it did, which is the only thing that catches "imported, but in another
  function". Both were verified to fail against the real bug before being kept — a
  guard nobody has seen fail is a guess. Whenever you add a button, click it in a test.
- **A grid/list page can look right offscreen and still be broken — the delegate
  never paints.** `test_ui_pages` constructs pages and asserts model state, so a
  `TileDelegate.paint` that raises (a helper accidentally spliced into the middle of
  it) sailed through the whole suite; the offscreen *render* is what surfaced it, as
  a `NameError` recursing through every `rowCount`/`paint` override. When touching a
  delegate, render the window to a QPixmap — see the screenshot recipe below — rather
  than trusting green tests.
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
- **An ad-hoc GUI script must isolate `SETTINGS_FILE`/`APP_CONFIG_DIR`, not just
  `M110_DATA_ROOT`.** Settings live at **`~/.m110/settings.json` — outside the data
  root**, so pointing `M110_DATA_ROOT` at a scratch dir does *nothing* to protect
  them. `tests/conftest.py` seals both (that's what `_seal_live_store` is for), but a
  throwaway script run by hand — or by a subagent — inherits no such seal, and any
  code path that reaches `config.save_setting` writes the developer's real
  preferences. This is not hypothetical: an audit script constructed a
  `BackupDialog` and called its `_persist_settings("/tmp/typed")` to check a button
  state, and **overwrote the user's real backup destination** — silently disabling
  their backups until they noticed. Constructing a dialog is enough to be dangerous:
  dialogs read settings on open and write them on any save-shaped action. Before
  running one:
  ```python
  import tempfile, pathlib
  from m110 import config
  scratch = pathlib.Path(tempfile.mkdtemp())
  config.SETTINGS_FILE = scratch / "settings.json"     # NOT under the data root
  config.APP_CONFIG_DIR = scratch / "app_config"       # the log lives here too
  ```
  Prefer driving the *engine* over constructing UI when a question can be answered
  without a widget, and prefer a pytest case (already sealed) over a scratch script.
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
  **A third form, and the sharpest: dropping the reference in the worker's OWN
  result slot.** Our workers emit `done`/`failed`/`probed` from *inside* `run()`, so
  the slot executes on the GUI thread while the thread is still finishing. Clearing
  `self._worker` there with a bare `deleteLater()` leaves a live QThread parented to
  the dialog with nobody holding it; closing the dialog then runs
  `QObjectPrivate::deleteChildren()` over it. That is a **qFatal — "QThread:
  Destroyed while thread is still running" → SIGABRT**, not the SIGSEGV above, and
  `error_report`'s excepthook can never see it because `abort()` isn't an exception.
  Note *how* it hides: it doesn't bypass the `_stop_worker` teardown guard, it
  **defeats** it — that guard tests `is not None`, and the reference was already
  cleared, so the protection reads as present and does nothing.
  **Every** drop of a worker reference goes through **`widgets.drain_worker(w)`**
  (wait → `deleteLater` → return `None`), and
  `tests/test_ui_modal_safety.py` greps every `_finish_*`/`_stop_*` method in
  backup/restore/publish/export for it — the shape has to be asserted because the
  failure aborts the interpreter instead of failing an assertion. The reason that
  scan exists: `export_dialog` found and fixed this **locally**, comment and all, and
  the other three dialogs kept the unsafe copy for months. A slow destination (a
  `/Volumes` share) turns the race from rare into routine.
- **Never rebuild a page from under a nested event loop — and never open one from
  inside an item-view handler.** A modal dialog (`.exec()`) or a popup menu runs a
  **nested** event loop, and a `deleteLater()` issued *inside* one takes effect as that
  loop iterates — i.e. while the C++ handler that opened it is still on the stack. So
  the 0.3.0b3 SIGSEGV: the detail gallery called `ImageViewer(...).exec()` straight from
  `itemDoubleClicked` (emitted from inside `QAbstractItemView::mouseDoubleClickEvent`),
  the window-focus auto-sync finished inside the viewer's loop, `_on_refresh_done`
  `reload()`ed every page, `DetailPane._clear()` deleted the gallery — and Qt resumed
  the double-click handler on freed memory. Two rules now, both in `widgets.py`: anything
  that tears widgets down checks **`modal_loop_active()`** first (the shell parks the
  rebuild and retries — `MainWindow._apply_refresh`), and anything opening a modal/menu
  from an item-view signal goes through **`defer()`** / **`connect_context_menu()`**.
  Deferred openers must work off a **snapshot** of their data, since a rebuild may land
  in the gap. Don't try to pytest the crash itself — a regression **segfaults** the
  interpreter (exit 139) instead of failing an assertion, taking the whole run with it;
  assert the *policy* (`tests/test_ui_modal_safety.py`) and run the manual
  `tools/repro_modal_uaf.py buggy|fixed` when touching this. Diagnosing the class from a
  crash report: a live worker thread next to a mouse-handler frame is the signature.
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

### Repo layout

```
m110/            engine package (+ ui/ subpackage, seed/ data)
tests/                  pytest suite (fixture-based)
tools/                  dev utilities (release.py → one-command release cutter, incl. the `docs` phase;
                        build_docs.py → renders docs/*.md + CHANGELOG.md into the versioned
                        site at site/docs/<tag>/ + latest/ (nav order comes from docs/README.md's
                        own link list, so a new page just appears; a .md link to a repo file we
                        don't publish becomes a GitHub link AT THAT TAG rather than a 404);
                        make_test_corpus.py → synthetic manual-test store;
                        smoke_mcp.py → drive the assistant MCP server over real
                        pipes with no AI client, to tell "server broken" apart
                        from "client can't find it";
                        drill_backup_s3.py → TESTING §2.5b against a REAL MinIO it
                        starts itself (57 checks, ~5 s): the one thing the suite's
                        fake client and the no-network boto3 tests can't prove is a
                        real S3 implementation — path-style behind a custom endpoint,
                        real LIST pagination, real error shapes, a server killed
                        mid-upload. Needs a minio binary, hence a tool not a test;
                        repro_modal_uaf.py → the modal/nested-loop use-after-free,
                        pre- vs post-fix (segfaults by design, so not a pytest case))
packaging/              native installers: common/ (shared PyInstaller entry shims —
                        GUI + m110-mcp + m110-stack, one Analysis, three EXEs +
                        astropy hook override) · macos/ (.app→sign/notarize→.dmg) ·
                        linux/ (onedir→AppDir→AppImage) · windows/ (onedir→.ico→Inno Setup)
site/                   m110.space landing page + **docs/<tag>/** versioned user guide
                        (static; Cloudflare Pages, deploy dir = site/ — so rendered docs must be
                        committed, which is why the release `docs` phase runs before `commit`)
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

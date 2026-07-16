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
the deferred half of item 2) and the Checkpoint C assistant (item 4) remain open.

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

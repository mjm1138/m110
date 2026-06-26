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

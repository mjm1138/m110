# Bugs & Improvements

Open issues + the improvement backlog. **Completed items are archived in
[`DONE.md`](DONE.md)** (with a concise fixed-bugs log); this file tracks only
what's still open. Larger items map to [`ROADMAP.md`](ROADMAP.md) phases.

Legend: `[ ]` open · `[~]` partially done

---

## Processing & curation UX  *(→ ROADMAP item 7)*

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

- [ ] **#28 — Siril prep is confusing (per-filter layout + stale dirs).** (Bug D from the
  M27 investigation.) The single↔multi-filter sandbox layout is hard to follow: a target
  that becomes "multi-filter" grows `siril/<FILTER>/lights/` job dirs, but an earlier
  single-filter prep's `siril/lights/` (and any orphaned filter dir) is **not cleaned up**,
  so the user can open a stale folder with a partial sub set (exactly what happened on M27:
  stale `siril/lights/` had 461 while the live `siril/LP/lights/` had all 1223). Improvements:
  (a) reconcile/clean orphan job dirs when the filter composition changes (carefully —
  never nuke an in-progress run); (b) surface which sandbox dir is current (next-steps.md
  already names it, but the stale dir shouldn't linger); (c) reconsider whether per-filter
  split should be **opt-in** — a Seestar user is effectively single-filter (LP or none), so
  the split mostly adds confusion. Edge case today (one object shot with mixed filter
  settings), but the stale-dir cleanup is the generally-useful piece.

- [ ] **#17 — Intermediate / finished file hinting.** The naming patterns for
  intermediate and finished images are built on Mike's particular habits, and are
  probably not generalizable. Two enhancements can help:
  - ✅ **Preference pane hint set (done — `feature/finished-hints`).** The
    finished/intermediate vocabulary is now a single user-editable keyword set in
    `m110/hints.py` (defaults `processed/final/finished` + `starless/starmask`),
    edited in Preferences → "Finished-image hints", persisted in `settings.json`
    (`finished_hints`), read live. The three former hardcoded copies
    (`siril._classify`, `ingest._is_finished_raster`, `build_images._is_intermediate_fit`)
    now draw from it — a stranger can add their own keywords instead of silently
    misclassifying.
  - ✅ **Gallery + curation done** (`feature/finished-gallery`). The detail pane splits
    into **Finished** / **Working files** groups with right-click **Set as hero** /
    **Mark as finished** / **Mark as working**. Per-image overrides persist in journal
    frontmatter (`finished_extra`/`working_extra`; `objects.get_curation`/`set_curation`);
    galleries derive from tier + overrides. Terminology settled on "finished"/"working".
  - ✅ **Hero-render cache fixed** (shipped with the above). `build_images._render_hero`
    now keys on source **identity** (a `renders/hero/<slug>.src` sidecar = source
    rel-path + `img_hash`), not mtime — so picking an **older** image as hero re-renders
    instead of leaving a stale hero. `rebuild_hero(slug)` re-renders one hero
    synchronously for the interactive action.
  - *Open question (deferred):* a "favorites" designation alongside "hero" (multiple
    favorites display) — not needed for beta.
- [ ] **#18 — Advanced processing prep.** Create Siril (and other workflow) working
  directories populated with lights from **disparate sources** (see #16) and
  **disparate objects** (e.g. combine m81 + m82 + "m81 m82" as a mosaic), via hardlinks
  (only processing/intermediate files cost disk). Custom workspaces must be easily
  discoverable by name on the filesystem. Also support custom **split** workflow
  directories, like the LP / no-filter splits created automatically today.
- [ ] **#19 — Open In… / Process in…** (cross-platform launch is the main risk.)
  Right-click an **image** → "Open In…" a compatible processing/viewing app (Finder-
  style). Right-click an **object** → "Process in…" (Siril/PixInsight/…) which opens
  the tool, creating/selecting the appropriate working directory first (or a custom one
  per #18). Pure **guide**, not control.

## Import

- [~] **#16 — Robust, layout-flexible, multi-source import.** **6a–6c shipped**
  (any-directory recursive scan, FITS-header classification + layout registry,
  holding-area manual assign — see [`ROADMAP.md`](ROADMAP.md) item 6 / [`DONE.md`](DONE.md)).
  **Open: 6d — lazy device-under-target** — record device/source per session; introduce
  the optional `Images/<target>/<device>/` path level (+ a `.store_version` bump + a
  `migrate.py` step) **only when a 2nd device appears** (flat = default device). A device
  registry keyed to planning device-profiles (`planning_config.load_device`). Deferred
  until a real 2nd telescope exists. **Note (verified 2026-07-07):** the per-unit scope id
  is in **FITS only** — `TELESCOP = S50_<8hex>` (e.g. `S50_15e7e390`); the S50 `.jpg` EXIF
  carries model/firmware but **no** unit id. So device attribution must key off FITS
  `TELESCOP`; a JPEG-only import can't tell two same-model scopes apart. See
  [`DATA_MODEL.md`](DATA_MODEL.md) → "Import & multi-source / multi-telescope".
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
- [ ] **Full import triage toolkit**  *(→ ROADMAP item 9).* Deeper tools for files the
  classifier can't place — FITS header inspector, in-app viewer/annotator, **plate-solving**
  to recover pointing. Extends the #26 holding area; pulls in a plate-solver dependency,
  so deferred until real-world messy imports demand more than manual assign.

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
- [ ] **#40d — Restore has no store-version gate.** `backup` records `store_version` in each
  snapshot manifest and `.store_version` isn't denylisted, so a **full** restore brings back the
  old stamp and `migrate` re-runs on next launch (self-healing ✓). But `restore_dialog` offers a
  **per-file checkable tree** and neither dialog reads `store_version` — so a **partial** restore
  can put a pre-v4 `library.toml` back under a v4 stamp, where migration won't re-run. The #40c
  splitter hardening means this no longer causes an under-count (the pair still splits), but the
  stale pseudo-object rows would linger until manually removed. Worth a version-mismatch warning
  on restore (and/or forcing `.store_version` to be restored with `library.toml`).

## Planning / prioritization

- [x] **#3 — Manual Pin/Deprioritize priorities** *(the self-contained slice of ROADMAP
  item 1; `feature/manual-pins`, term renamed from "Mute" in `feature/deprioritize-rename`).*
  Ships ahead of the scorer so the Summary **Priority targets** view has a reason to exist
  for a fresh user (empty `priorities.toml`). Per-store `pins.toml` (`m110/pins.py`, survives
  regeneration; legacy `"mute"` value read-mapped) + right-click **Pin/Deprioritize** on
  Library, Goals, **and the Priority-targets rows** with a ▲/▼ marker; pinned objects surface
  in Priority targets (deprioritized excluded) with an empty-state prompt. Today's slice:
  **pin = always shown, deprioritize = hidden** — no season/rank logic until the scorer
  composes over it (numeric nudge + `computed rank + overrides` deferred with the engine).
- [~] **#21 — Auto-prioritizer / target scoring.** Promoted to **ROADMAP item 1**
  (a deterministic, testable scoring engine to replace the hand-edited/LLM-edited
  `priorities.toml`; dependency: multi-catalog goals, item 5 ✓). The vision: priorities
  derive from active **goals** + **season** (an in-goal object about to go out of season
  outranks one just rising) + an optional **per-type weight** preference + a "many new
  targets" vs "deep stacks" strategy toggle. *The scoring weights + which knobs surface
  in a priorities preference pane are still **TBD** — see the scoring model + the
  Astronomy-prototype findings in ROADMAP item 1 (glow-mask dark-site awareness,
  urgency×completion coupling, combined-frame captures).*
*Session-planner items (#40–44) are phased in [`PLANNING_ROADMAP.md`](PLANNING_ROADMAP.md).*

- [ ] **#40 — Non-overlapping, 10-min-aligned sequence** *(→ PLANNING_ROADMAP Phase 4).*
  Object sessions **cannot overlap**; the Seestar SSC tool requires start/end times on
  **10-minute increments**. Replace the current overlapping "best times" with a real
  sequence. **General logic (v1):**
  1. Highest-priority object visible right at astronomical dark = object 1. Desired
     duration = astro-dark span ÷ target count, unless it reaches deep-stack status
     with a shorter duration.
  2. Highest-priority object visible at the end of object 1's capture = object 2.
  3. …at the end of object 2's capture = object 3, and so on.
  4. If two equal-priority objects are visible for a window, pick the one closer to
     **setting**; sequence the other afterward.
  Later versions improve the logic (e.g. grouping objects by sky region).
- [ ] **#41 — Schedule output format** *(→ PLANNING_ROADMAP Phase 4.2).* Output is a
  sequence schedule; each target row = object name, altitude at start, start time,
  duration, filter, **moon impact** (with a plain-language explanation of what that
  means — see #36). Object 2 start = object 1 start + duration (don't model
  slew/focus time).
- [ ] **#42 — Target-count control** *(→ PLANNING_ROADMAP Phase 4.1).* Way too many
  targets proposed (8, overlapping). Add a user selection for **how many targets** —
  arbitrary up to the number of visible targets, **default 4**.
- [ ] **#43 — Date-picker broken** *(→ PLANNING_ROADMAP Phase 5).* Date selection is
  broken: most calendar days are labeled with ellipses, and the selected date renders
  greyed-out.
- [ ] **#44 — LLM session-planner skill foundation** *(→ PLANNING_ROADMAP Phase 6;
  post-release follow-on).* Lay the foundation for an M110-native session-planner
  skill over the deterministic engine — consult the `astro-session-planner` skill +
  `scripts/`/`workflows/` in ~/Astronomy and work from there. This is the point where
  an LLM plugs in (explains/tunes/narrates; the engine stays the source of truth).

*Findings from the 2026-07-13 prioritizer/planner review below — reasoning in
[`prioritizer-review.md`](prioritizer-review.md).*

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
- [ ] **#36 — Moon model is wrong (planner header).** On `2026-07-18` the plan reported
  "Moon: 0% lit, down at dusk (−17°)"; actual Boulder values are **~24% illuminated (waxing
  crescent, 4 days after the Jul 14 new moon), +5° at dusk, setting ~23:00**. Two bugs: (a) **illumination is wrong** (reported 0% — dangerous,
  it greenlights broadband on what could be a moon-up night); (b) the moon is described by a
  single **dusk snapshot** with a wrong altitude (timezone/eval-instant smell) when it must be
  **per-slot** across the night. Also the `Moon°` separation column is printed even when the
  moon is **below the horizon** (no impact) — gate it on moon-altitude, and make "moon impact"
  filter-aware (LP narrowband is near-immune). This is the correctness half of the #193 ask to
  *explain* moon impact.
- [ ] **#37 — Start-altitude ceiling (~78°) ignored in slot selection.** The `2026-07-18` plan
  put 4/8 targets at best-time altitudes over the ceiling (M29 88°, Sh2-112 84°, Sh2-115 83°,
  M39 82°) — the Seestar app rejects captures that *start* above ~78°. Pick a start on the
  rising side below ~75°, or after the target descends back through ~75°. The logic already
  exists in Astronomy `scripts/sky.py` (the `^` over-ceiling flag).
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
- [ ] **#38b — Reference magnitude audit (B-mag leakage) + coverage backfill.** Some
  SB-floored entries are **data errors**, not faint targets: `seed/objects.toml` lists the
  **Helix (NGC 7293) at mag 13.5** (real V ≈ 7.3) and NGC 4945 at 14.4 (real ≈ 9.3) — Simbad
  B-mag/photographic leakage from the build-time fetch. `SB_FLOOR = 0.3` keeps bad data from
  burying a showpiece, but the fix is in `tools/gen_catalogs.py`: prefer V-mag explicitly,
  flag suspect rows, and re-run the backfill (coverage gaps today: 145 missing magnitudes,
  41 missing sizes of 450). Build-time only; runtime stays offline.
- [x] **#39 — Combined-folder under-count in the prioritizer.** *(PLANNING_ROADMAP Phase 1.2,
  `feature/session-planner`.)* `prioritize.build_contexts` now rolls each combined/mosaic
  capture folder's integration up into its constituent **catalog members** (reusing
  `scan_sessions.folder_to_slugs`) and drops the synthetic combined slug from scoring.
  Verified on the live store: `m81` → 1870 min (126 solo + 1744 pair), `m82` → 1757 min
  (13 + 1744), `m81-m82` dropped (was 126/13/1743 fragments with `obs:null`). Scope was
  **prioritizer-only** by decision — see #40b for the engine-wide rollup.
- [ ] **#40b — Combined-folder rollup in the *engine* (processing queue + Library).**
  `build_totals`/`build_processing` still key on `by_folder`, so genuinely-separate on-disk
  folders (`M81`, `M82`, **and** `M81 M82`) surface as **three rows** in the Processing queue
  and three objects in the Library — the small solo captures (M81 126 min, M82 13 min) read as
  "not processed / new". #39 fixed only the prioritizer; extending the family rollup into
  `build_totals`/`build_processing` (a combined folder subsumes its members' solo folders)
  would collapse the queue + Library to one target family. Needs a rule for how a solo folder
  folds into a combined one. *(Superseded in framing by #40c — see there: the queue showing one
  row per capture **target** is correct; the real defect is upstream.)*

## Publishing  *(→ ROADMAP item 8)*

- [ ] **#27 — Publishing follow-ups** (8a landed — local static-site export). Targets/
  refinements that build on the `publish/` engine + registry: (a) a **GitHub Pages
  deploy** target (git/`ghp-import` push to `gh-pages`, repo from settings, image-cache
  preservation) — the registered-disabled `github-pages` placeholder; (b) **Netlify /
  S3·CloudFront / WordPress·Ghost** targets; (c) **per-list (goal) publish flags** (8a
  ships per-object `publish` + per-journal `private` only); (d) **cross-publish image-cache
  reuse** (8a regenerates web derivatives each run; the publish analogue of #14); (e)
  optional **auto-publish on refresh**. `publish.PUBLISHERS` + `PublishOptions` are the
  stable seams; each target is an adapter.
**Other Publishing Targets**: Astrobin, Cloudynights, Other fora?

## UI niceties (backlog)

- [x] **Empty-state guidance** *(done — `feature/onboarding`).* A fresh store (nothing
  captured) shows a **welcome + "Import images…" CTA** on the Summary landing page
  (`go_to_import` → Import page) instead of empty tables, and the Library stat row shows
  an "empty — Import or add an object" hint. The seed `priorities.toml` now ships **empty**
  so a stranger doesn't inherit hand-authored targets.
- [x] **First-launch data-folder prompt** *(done — `feature/onboarding`).* `FirstRunDialog`
  (`config.is_first_run()` + `ui/first_run_dialog.py`) prompts for a data folder on a genuine
  first launch, persists it, and never re-prompts a returning user.
- [ ] **Surface skipped files** after an import ("N already present, skipped") — copies
  are already skip-if-present + partial-safe, so this is just reporting.

## Open questions

- *(None open.* The royalty-free-images question is **answered** — the decision
  (CDS hips2fits survey cutouts + curated CC-BY heroes; 8-bit sRGB JPEG specs; a
  reference-image tier + attribution) is captured in [`DATA_MODEL.md`](DATA_MODEL.md)
  "Reference images for uncaptured objects" and scheduled as a **UI Phase 2** item in
  [`UI_ROADMAP.md`](UI_ROADMAP.md).)*

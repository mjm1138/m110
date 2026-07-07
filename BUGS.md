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
- [ ] **#25 — Optional import of per-sub `.jpg` previews.** The Seestar saves a full-size
  `.jpg` preview beside every `.fit` sub in a `_sub` folder; these are recognized-and-
  ignored on import today. *Enhancement:* a preference (default **off**) to import them —
  into `Images/<target>/lights/` or a dedicated `previews/` subdir. Cheap (the
  `_classify_seestar_dir` `_sub` branch already enumerates the folder's non-FITS content);
  decide the destination + gallery interaction first.
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
- [ ] **Full import triage toolkit**  *(→ ROADMAP item 9).* Deeper tools for files the
  classifier can't place — FITS header inspector, in-app viewer/annotator, **plate-solving**
  to recover pointing. Extends the #26 holding area; pulls in a plate-solver dependency,
  so deferred until real-world messy imports demand more than manual assign.

## Planning / prioritization

- [x] **#3 — Manual Pin/Mute priorities** *(the self-contained slice of ROADMAP item 1;
  `feature/manual-pins`).* Ships ahead of the scorer so the Summary **Priority targets**
  view has a reason to exist for a fresh user (empty `priorities.toml`). Per-store
  `pins.toml` (`m110/pins.py`, survives regeneration) + right-click **Pin/Mute** on
  Library & Goals rows with a ▲/▼ marker; pinned objects surface in Priority targets
  (mutes excluded) with an empty-state prompt. Standalone for now — the scorer will
  compose over it (numeric nudge + `computed rank + overrides` deferred with the engine).
- [~] **#21 — Auto-prioritizer / target scoring.** Promoted to **ROADMAP item 1**
  (a deterministic, testable scoring engine to replace the hand-edited/LLM-edited
  `priorities.toml`; dependency: multi-catalog goals, item 5 ✓). The vision: priorities
  derive from active **goals** + **season** (an in-goal object about to go out of season
  outranks one just rising) + an optional **per-type weight** preference + a "many new
  targets" vs "deep stacks" strategy toggle. *The scoring weights + which knobs surface
  in a priorities preference pane are still **TBD** — see the scoring model + the
  Astronomy-prototype findings in ROADMAP item 1 (glow-mask dark-site awareness,
  urgency×completion coupling, combined-frame captures).*

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

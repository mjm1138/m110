# Bugs & Improvements

Open issues + the improvement backlog. **Completed items are archived in
[`DONE.md`](DONE.md)** (with a concise fixed-bugs log); this file tracks only
what's still open. Larger items map to [`ROADMAP.md`](ROADMAP.md) phases.

Legend: `[ ]` open · `[~]` partially done

---

## Processing & curation UX  *(→ ROADMAP item 7)*

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
- [ ] **Full import triage toolkit**  *(→ ROADMAP item 9).* Deeper tools for files the
  classifier can't place — FITS header inspector, in-app viewer/annotator, **plate-solving**
  to recover pointing. Extends the #26 holding area; pulls in a plate-solver dependency,
  so deferred until real-world messy imports demand more than manual assign.

- [ ] **#40d — Restore has no store-version gate.** `backup` records `store_version` in each
  snapshot manifest and `.store_version` isn't denylisted, so a **full** restore brings back the
  old stamp and `migrate` re-runs on next launch (self-healing ✓). But `restore_dialog` offers a
  **per-file checkable tree** and neither dialog reads `store_version` — so a **partial** restore
  can put a pre-v4 `library.toml` back under a v4 stamp, where migration won't re-run. The #40c
  splitter hardening means this no longer causes an under-count (the pair still splits), but the
  stale pseudo-object rows would linger until manually removed. Worth a version-mismatch warning
  on restore (and/or forcing `.store_version` to be restored with `library.toml`).

## Planning / prioritization

- [~] **#21 — Auto-prioritizer / target scoring.** The scoring engine **shipped**
  as ROADMAP item 1 Checkpoint A (`m110/prioritize.py`: goals + season urgency +
  completion×strategy + per-type weights + tonight feasibility + pins; strategy
  toggle + weight spinboxes on the Planning pane — see [`DONE.md`](DONE.md), incl.
  the archived scoring-model design + Astronomy-prototype findings). *Still open:*
  the **session-time controls + night presets** (the second tuning tier) and the
  other refinements listed under ROADMAP → "Session-planning follow-ups".
*Session-planner items (#40–44) are phased in [`PLANNING_ROADMAP.md`](docs-archive/PLANNING_ROADMAP.md).*

- [ ] **#44 — LLM session-planner skill foundation** *(→ PLANNING_ROADMAP Phase 6;
  post-release follow-on).* Lay the foundation for an M110-native session-planner
  skill over the deterministic engine — consult the `astro-session-planner` skill +
  `scripts/`/`workflows/` in ~/Astronomy and work from there. This is the point where
  an LLM plugs in (explains/tunes/narrates; the engine stays the source of truth).

*Findings from the 2026-07-13 prioritizer/planner review below — reasoning in
[`prioritizer-review.md`](docs-archive/prioritizer-review.md).*

- [ ] **#38b — Reference magnitude audit (B-mag leakage) + coverage backfill.** Some
  SB-floored entries are **data errors**, not faint targets: `seed/objects.toml` lists the
  **Helix (NGC 7293) at mag 13.5** (real V ≈ 7.3) and NGC 4945 at 14.4 (real ≈ 9.3) — Simbad
  B-mag/photographic leakage from the build-time fetch. `SB_FLOOR = 0.3` keeps bad data from
  burying a showpiece, but the fix is in `tools/gen_catalogs.py`: prefer V-mag explicitly,
  flag suspect rows, and re-run the backfill (coverage gaps today: 145 missing magnitudes,
  41 missing sizes of 450). Build-time only; runtime stays offline.
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

- [~] **#27 — Publishing follow-ups** (8a landed — local static-site export). Targets/
  refinements that build on the `publish/` engine + registry: (a) ✅ **GitHub Pages
  deploy** *(done 2026-07-15, `feature/publish-ghpages` — see DONE.md)*: system-git
  force-push of the rendered site to `gh-pages` (`m110/publish/ghpages.py`), repo from
  the dialog/settings; (b) **Netlify /
  S3·CloudFront / WordPress·Ghost** targets; (c) **per-list (goal) publish flags** (8a
  ships per-object `publish` + per-journal `private` only); (d) **cross-publish image-cache
  reuse** (8a regenerates web derivatives each run; the publish analogue of #14); (e)
  optional **auto-publish on refresh**. `publish.PUBLISHERS` + `PublishOptions` are the
  stable seams; each target is an adapter.
- [ ] Publishing: User should have the option to add a copyright notice to published images
- *(2026-07-15 live-library test findings, rounds 1+2 — deploy progress bar,
  no-save-without-publish, push timeout, cancel→beach-ball/orphaned push,
  working-files upload bloat, stale-output-never-torn-down, three-level gallery
  selection, GitHub-setup docs, processing-page/app alignment — all fixed on
  `feature/publish-ghpages` before merge; see DONE.md.)*
**Other Publishing Targets**: Astrobin, Cloudynights, Other fora?

## UI niceties (backlog)

- [ ] **Surface skipped files** after an import ("N already present, skipped") — copies
  are already skip-if-present + partial-safe, so this is just reporting.

## Open questions

- *(None open.* The royalty-free-images question is **answered** — the decision
  (CDS hips2fits survey cutouts + curated CC-BY heroes; 8-bit sRGB JPEG specs; a
  reference-image tier + attribution) is captured in [`DATA_MODEL.md`](DATA_MODEL.md)
  "Reference images for uncaptured objects" and scheduled as a **UI Phase 2** item in
  [`UI_ROADMAP.md`](UI_ROADMAP.md).)*

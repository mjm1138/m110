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

- [ ] **#17 — Intermediate / finished file hinting.** The naming patterns for
  intermediate and finished images are built on Mike's particular habits, and are
  probably not generalizable. Two enhancements can help:
  - A **preference pane** to explicitly list intermediate and finished filename
    hints, populated by a default set built on current preferences.
  - An addition to the object view: below the gallery of "finished" images, a gallery
    of "unfinished" images, with right-click actions to **promote** unfinished →
    finished, **demote** finished → unfinished, and **set hero**.
  - *Open questions:* Are "finished"/"unfinished" the right terms? Should there be a
    "favorites" designation alongside/instead of "hero"? How would multiple favorites
    display?
  - ⚠️ **When adding an in-app "set as hero" action, fix the hero-render cache.**
    `build_images._render_hero` currently skips regeneration when
    `dst.stat().st_mtime >= src.stat().st_mtime` — it keys on the source's mtime,
    not on *which* source. Today that's safe because imported renders are written
    with a fresh (now) mtime, so a newly-picked hero is always newer than the prior
    `hero/<slug>.jpg`. But picking an **existing, older** gallery image as hero
    would leave the stale hero (and thus stale Library grid tiles + list-view row
    thumbnails, which are both hero-backed). The fix: invalidate on the source
    **identity** (frontmatter `hero:` value / source path), not just mtime.
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
  until a real 2nd telescope exists.
- [ ] **#25 — Optional import of per-sub `.jpg` previews.** The Seestar saves a full-size
  `.jpg` preview beside every `.fit` sub in a `_sub` folder; these are recognized-and-
  ignored on import today. *Enhancement:* a preference (default **off**) to import them —
  into `Images/<target>/lights/` or a dedicated `previews/` subdir. Cheap (the
  `_classify_seestar_dir` `_sub` branch already enumerates the folder's non-FITS content);
  decide the destination + gallery interaction first.
- [ ] **#26 — Holding-area identification aids.** The 6c holding-area panel lets you
  assign object + kind but offers no help *figuring out* what a held file is (now lists
  filenames on hover, but no more). *Enhancements (overlap ROADMAP item 9):* (a)
  **reveal the file location** — a "Reveal in Finder" / "Open folder" action and/or the
  `Inbox/<folder>` path in the panel; (b) a **preview/inspector** — thumbnail for images,
  a FITS-header view (OBJECT/IMAGETYP/FILTER/RA/DEC via `ingest.frame_info`); (c)
  **suggested identity** — for FITS with RA/DEC reuse #12 pointing (`frame_radec` +
  nearest-catalog); headerless → plate-solving (item 9). Start with (a) + the FITS-header
  inspector — most of what's needed is already in `frame_info`. There should be an option to discard a file in the Inbox holding area, with a confirmation modal.
- [ ] **Full import triage toolkit**  *(→ ROADMAP item 9).* Deeper tools for files the
  classifier can't place — FITS header inspector, in-app viewer/annotator, **plate-solving**
  to recover pointing. Extends the #26 holding area; pulls in a plate-solver dependency,
  so deferred until real-world messy imports demand more than manual assign.

## Planning / prioritization

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

## UI niceties (backlog)

- [ ] **Empty-state guidance.** When the Library is all-uncaptured (fresh data root),
  show a hint like "Import from your Seestar to get started" to orient new users.
- [ ] **First-launch data-folder prompt** — a one-time "choose your data folder" prompt
  rather than silently defaulting to `~/Documents/M110`.
- [ ] **Surface skipped files** after an import ("N already present, skipped") — copies
  are already skip-if-present + partial-safe, so this is just reporting.

## Open questions

- *(None open.* The royalty-free-images question is **answered** — the decision
  (CDS hips2fits survey cutouts + curated CC-BY heroes; 8-bit sRGB JPEG specs; a
  reference-image tier + attribution) is captured in [`DATA_MODEL.md`](DATA_MODEL.md)
  "Reference images for uncaptured objects" and scheduled as a **UI Phase 2** item in
  [`UI_ROADMAP.md`](UI_ROADMAP.md).)*

# Bugs and Improvements
Record bugs and improvements here under the appropriate area.

Legend: `[x]` fixed · `[ ]` open · `[~]` partially done

## Ingest Dialog

### Bugs
- [x] **Bug**: Copy modal doesn't close after file copies.
  *Fixed (cf1ebd0).* Root cause: after a copy the dialog auto-**rescanned** the
  source, which popped a *second* (slow, over-SMB) scan modal — so it looked like
  the copy modal never closed. Removed the auto-rescan; the progress dialog is now
  closed + `deleteLater`'d explicitly (`autoClose`/`autoReset` off). After ingest
  the plan clears and the summary invites a manual **Rescan**.
- [x] **Bug**: Hitting cancel on Ingest window after file copy crashes app.
  *Fixed (cf1ebd0).* Root cause: closing the dialog while a `QThread` worker was
  still running destroyed a running thread (hard crash). Close/Cancel now cancel
  and `wait()` for any running worker before teardown (`_stop_worker` wired into
  `reject()` and `closeEvent()`); finished workers are `deleteLater`'d.
- [x] **Bug**: No images displayed for any object, including those with Seestar
  Stacks. *Fixed (30f4639).* Root cause: ingested Seestar stacks were `.fit`-only
  and `build_images` only thumbnailed *viewable* (raster) files → **zero**
  thumbnails/heroes generated. Now: thumbnails/heroes render from FITS stacks too
  (percentile stretch), the gallery shows any image with a thumbnail, and ingest
  also copies the device's preview `.jpg/.png` from stack folders.
  ⚠️ **Re-run Refresh (Ctrl+R) once** to generate thumbnails for data ingested
  before this fix.
- [x] **Bug**: Processed NGC 6992 but the app has not picked up the processed
  images. (Unrelated to the earlier catalog gap — same object, different cause.)
  *Fixed.* Root cause: **over-aggressive intermediate exclusion**, not caching.
  The Naztronomy/Siril deliverable bakes the steps it went through into its name
  (`NGC_6992_…_spcc_processed.png` / `.fit`), but `siril._classify` vetoed any
  name containing a pipeline-step token (`_spcc`/`_crop`/`_stretch`/`_og`), so the
  finished render+stack were treated as intermediates → `has_unimported_output`
  returned False and the **Import finished work** entry never appeared. *Fix:* only
  star **layers** (`starless`/`starmask`) are an outright veto; step tokens no
  longer disqualify a file (a `.fit` still needs a `processed/final/finished`
  hint to count as a stack, so bare `_spcc.fit`/`_og.fit` stay excluded). Same
  correction applied to `build_images._is_intermediate_fit` (a final-hinted FITS
  is no longer skipped for thumbnailing). Tests:
  `test_siril.test_scan_finished_keeps_pipeline_step_tokens_in_final_name`,
  `test_build_images.test_is_intermediate_fit_honors_final_hint`.
  
- [x] **BUG**: **Edit object journal entry should trigger refresh in Journal view**. If I add notes to an object and return to the Journal view, the new content doesn’t appear until I do a manual refresh. *Done — saving Object Notes emits `DetailPane.saved` → `CatalogPage.notes_saved` → the shell reloads the other views (lightweight, no scan/derive/render). `test_ui_pages.test_object_notes_edit_wraps_and_signals_reload` + `test_catalog_page_reemits_notes_saved`.*
- [x] **BUG**: **Text doesn’t wrap at view width in the “Editing Journal” view** (edit window showed a horizontal scroll bar). *Done — the Object Notes editor uses `QPlainTextEdit.WidgetWidth` wrap instead of `NoWrap`.*

### UI
- [x] **UI**: Copy modal should say "Copying Files" / show progress.
  *Done (cf1ebd0).* Now "Copying files…" / "Moving files…" with a determinate bar.
  - [x] **UI** Catalog view: Sorting on the season column should sort by date month starting with January. Year-round goes at the bottom. *Done — `catalog.season_sort_key` (first month Jan→Dec; Year-round/empty last), via `_NumItem`.*
  - [x] Detail view: Gallery is truncated; can’t see a full frame. *Done — dropped the 190px cap (taller, scrolls); full frames via the viewer below.*
  - [x] Detail view: Clicking on a thumbnail doesn’t do anything, should launch an image viewer view with nav buttons to view other images in the gallery of the detail view. *Done — double-click opens `ui/image_viewer.ImageViewer` (full-res for rasters via a new `images.json` `full` field; FITS falls back to the thumb) with Prev/Next + ←/→ + Esc.*
  - [x] Detail view: Hero image should scale to be viewable in the current view *Done — `ui/image_viewer.ScalableImage` fits the pane width and rescales on resize (capped height).*
  - [x] Detail view: Journal entry renders as poorly formatted text. It should render the markdown correctly including line breaks, and limit width to the view width *Done — `objects.journal_to_markdown` strips editor-only HTML comments and preserves single line breaks; `QTextBrowser` wraps to the pane width.*

#### Follow-up fixes (detail view)
- [x] **Crash / duplicate buttons / persistent Save+Cancel.** Re-rendering the
  detail pane (selection, **or auto-refresh on window resize/focus**) piled up
  stale **Edit / Prepare / Save+Cancel** buttons, and clicking a stale one
  **segfaulted** on teardown (PySide `QListWidgetItem` double-free). *Fixed:*
  `DetailPane._clear` now **recurses into sub-layouts** (`addLayout` items were
  detached but their child widgets never deleted); the gallery no longer stores
  Python objects on `QListWidgetItem`s (parallel list instead — avoids the
  teardown double-free). Regression test: `tests/test_ui_detail.py`.
- [x] **Image viewer opened too large / couldn't resize vertically / no corner
  grab.** The scalable image pinned the dialog's min-height to the (huge) scaled
  image height. *Fixed:* `ScalableImage` gains a `fit="both"` mode (viewer scales
  into the available box in both dimensions, claims no min size); the viewer opens
  at ≤80% of screen and is freely resizable.

### Improvements (proposed — see Feedback below)
- [x] **#9**: Group the preview by object (object · #frames · MB) instead of one
  row per frame. *Done — `ingest.group_ops` aggregates by source folder; ops carry
  `size_bytes` (stat'd on the scan worker). Preview shows Object · Kind · Files ·
  Size · → Destination, with a running total size in the summary.*
- [x] **#10**: Allow selecting which objects to import (default: all). *Done —
  per-row checkboxes (default all) + Select all/none; the summary updates live and
  ingest applies only the checked groups (autoprep then runs for those targets).*
- [x] **#11**: Import & display *everything* off the Seestar (stacks, planetary,
  scenery, …). *Done.* Ingest of stacks (+previews) and media already worked; the
  display gap is now filled by the **Media page** (`ui/pages/media.py` over
  `media.scan()`): per-category sections of `Media/<Category>_photo|_video/` —
  photo galleries (double-click → image viewer) + video rows (Open → OS player).
- [x] **#12**: **Smart-ingest name normalization + pointing verification.** *Done.*
  Device folder names can't be trusted (firmware saved "M81 M82" into an `M81`
  dir; SSC makes case-variant `m82` dirs). Built on the #9/#10 grouped preview:
  (a) **canonicalization** — `ingest.canonical_target` folds a source name onto a
  single destination via alias → existing-folder casing → catalog id (so
  `m82`→`M82` at scan time); (b) **pointing check** — `annotate_pointing` reads
  `RA`/`DEC` from one sample frame per group and compares to the catalog position
  (bundled `seed/coords.csv`, generated via Simbad → offline at runtime); >0.15°
  shows a **`⚠ … → M82?`** badge + a **remap dropdown** that `retarget`s the
  group before confirm; (c) a per-store **alias table**
  (`.m110_internal_data/ingest_aliases.toml`) that the remap can write via
  "remember". Degrades to "unverified" where coords/frames are missing.
- [x] **#15**: **Working folders self-heal on refresh.** Processing-prep used to
  fire only on ingest, so objects that arrived another way (migrated/copied,
  not via the device) never got a `siril/` sandbox — and there was no way to
  trigger prep for what's already in the store (the temptation was to fake it via
  Inbox). *Done:* `processing.prepare_missing()` runs on every refresh (and via a
  **"Prepare working folders"** menu action) — it creates only the **absent**
  sandboxes for the enabled workflow(s) and never rewrites an existing one
  (protects hand-edited presets + in-progress runs). Ingest still does the full
  prep (links new lights + refreshes the preset) for freshly-ingested targets.
- [~] **#16**: **Import — robust, layout-flexible, multi-source** *(6a–6c landed
  2026-06-26/27; 6d open → ROADMAP item 6).* **6a shipped:** ingest renamed **Import**,
  promoted to a top-level nav page, any-directory recursive scan
  (`ingest.scan_directory_plan`), copy semantics + content-aware collision handling,
  Favorites/Recent-places source picker. **6b shipped:** FITS-header classification
  (`ingest.frame_info`), calibration frames route to `darks/`/`flats/`/`biases/`, new
  kinds (`dark`/`flat`/`bias`/`siril-stack`/`finished`), header-wins-over-folder, and the
  **layout-recognizer registry** (`ingest.LAYOUTS`: seestar · m110-store — incl. the
  `~/Astronomy/Images` precursor · raw-fits · asiair-disabled) shown in the preview;
  own-content-tree never re-imported. **6c shipped:** **nothing silently ignored** — a
  sweep routes every unclaimed content file (headerless FITS, stray images; junk/`*_thn.`
  excluded) into the `Inbox/` **holding area** (`kind="unassigned"`), surfaced in an
  always-visible **Holding area panel** with per-folder object+kind **manual assign**
  (`ingest.scan_holding`/`assign` → move into the content tree; alias-learning). Inbox is
  no longer a user-facing source. Inbox originally recognized exactly one shape — the Seestar export (`<obj>_sub/`
  of `Light_*.fit`, `<obj>/` of `Stacked_*`, `*_photo`/`*_video`) and silently finds
  nothing for any other structure (M110 *store* folders, another telescope's layout, a
  flat pile of FITS, calibration frames). The build: (a) **recognize multiple known
  layouts** (Seestar, ZWO ASIAIR, raw FITS trees, already-M110-store folders → "belong
  in Images/, not the queue") and say which it detected; (b) **classify by FITS header**
  (`OBJECT`/`IMAGETYP`/`FILTER`/`RA`/`DEC`) over folder names, so unstructured dumps and
  calibration frames sort (pairs with #12's pointing logic); (c) when it can't classify,
  **holding area + manual assign** rather than ignoring; (d) a device/format **registry**
  mirroring the processing-workflow registry. **Resolved decisions:** point at **any
  directory** (recurse) — the special-cased Inbox/Seestar *sources* go away (directory
  chooser + Favorites/Recent places); **copy, don't rename**, with content-aware
  collision handling (checksum/header → duplicate-skip vs. distinct-suffix); top-level
  **Import nav page**; and the open "how do lights from different sources land in the
  store?" question → **lazy device-under-target** (flat = default device; the
  `Images/<target>/<device>/` level + `.store_version` bump only when a 2nd device
  appears; source recorded in session metadata meanwhile). The deeper **triage toolkit**
  (header inspector, viewer/annotator, plate-solving) is split out as ROADMAP item 9.

- [x] **#22**: **Siril autoprep race → `SameFileError`** *(fixed 2026-06-26, with #16
  6a).* When the import worker's `run_autoprep` and the shell's focus-triggered
  `prepare_missing` built the *same* new `siril/` sandbox concurrently, one pass linked
  a file in the gap between the other's `exists()` check and `os.link`, so the loser
  fell back to `copyfile` on the same inode → `SameFileError`. (Surfaced because Import
  became a **non-modal page** — the old modal dialog blocked that refresh.) Fix:
  `siril._link_or_copy` is now idempotent (`FileExistsError` → no-op; copy fallback only
  when dst is absent), and `main._do_refresh` skips while `ImportPage.is_busy()`.
  Regression test in `test_siril.py`.
- [x] **#23**: **Messier catalogue shipped only 108/110** *(fixed 2026-06-26).* `M40`
  (Winnecke 4, a double star) and `M73` (NGC 6994, a 4-star asterism) were dropped
  because they don't resolve in Simbad. Authored by hand in `seed/objects.toml`
  (coords/type/mag/size, season derived) + added to `seed/catalogs/messier.toml`
  membership, so Goals progress reads /110. Fits the app's "Complete the catalog" ethos.
- [x] **#24**: **Goals page redundant object label "M51 (m51)"** *(fixed 2026-06-26).*
  `pages/goals.py::_object_table` fabricated `{"id": slug}` (the lowercase slug), so
  `object_identifiers` appended it after the catalog designation. Now resolves each row
  from the real Library/reference entry → just "M51".

- [ ] **#17**: **Intermediate and finished file hinting** The naming patterns for intermediate and finished images are built on Mike’s particular habits, and are probably not generalizable. Two enhancements can help with this:
	- [ ] A preference pane to explicitly list intermediate and finished filename hints, populated by a default set build on current preferences
	- [ ] An addition to the object view: below the gallery of “finished” images, have a gallery of “unfinished” images. Introduce a right-click actions for images to:
		- [ ] promote an unfinished image to finished
		- [ ] demote a finished image to unfinished
		- [ ] specify an image as the hero image
	
	Questions to go along with #17: Are “finished” and “unfinished” the right terms? Should there be a “favorites” designation along with/instead of a “hero” designation? How would multiple favorites be displayed?
	
- [ ] **#18**: **Advanced processing prep** As a user, I should be able to create Siril (and other workflows) working directories that I can populate with lights from disparate sources (see #16) and disparate objects (e.g. if I want to combine lights from m81, m82, and m81 m82 as a mosaic). It would use hard links to the original lights so the only disk space cost would be processing and intermediate files. Custom workspaces would need to be easily discoverable by name on the filesystem. I should also be able to create custom split workflow directories, similar to the splits that are automatically created for LP and no-filter lights of the same object.
- [ ] **#19**: **Open In...** This might be hard to keep cross platform. As a user, I should be able to right click on an image and have an “Open In” option to open the image file in compatible processing/viewing apps, similar to how it works in MacOS Finder. When selecting an object (as opposed to an image) there should be a right-click option to “process in...” that would open the processing tool (Siril, Pixinsight, whatever), creating an appropriate working directory first if necessary, and setting the working directory in the app to the selected object’s appropriate working subdirectory (or optionally a custom working directory as in #18)
- [ ] **#25**: **Optional import of per-sub `.jpg` previews.** The Seestar saves a full-size `.jpg` preview beside every `.fit` sub in a `_sub` folder. As of `0fb76d3` (the 6c fix) these are recognized-and-ignored on import — a `_sub` folder imports only its `.fit` lights, and the per-sub JPGs aren't held or copied. No obvious use case (the stack folder keeps the real preview, and 100s of redundant sub-previews would bloat the store), but some users might want them. *Enhancement:* a preference (default **off**) to import the per-sub previews — e.g. into `Images/<target>/lights/` alongside the subs, or a dedicated `previews/` subdir. Cheap to add (it's the `_classify_seestar_dir` `_sub` branch in `ingest.py`, which already enumerates the folder's non-FITS content). Decide the destination + whether it interacts with the gallery before building.
- [ ] **#26**: **Holding-area identification aids.** The 6c holding-area panel lets you assign object + kind, but offers no help *figuring out* what a held file is, and no indication of where the files physically live. *Enhancements (overlaps ROADMAP item 9, the import-triage toolkit):* (a) show/reveal the file location — a "Reveal in Finder" / "Open folder" action on a held group (the files sit in `Inbox/<folder>/`), and/or surface the `Inbox/<folder>` path in the panel; (b) a quick **preview/inspector** — thumbnail for images, a FITS-header view (OBJECT/IMAGETYP/FILTER/RA/DEC via `ingest.frame_info`) for FITS, so the user can identify before assigning; (c) **suggested identity** — for FITS with RA/DEC, reuse the #12 pointing logic (`frame_radec` + nearest-catalog) to propose an object; for headerless files, defer to plate-solving (item 9). Start with (a) + the FITS-header inspector — cheapest, and most of what's needed is already in `frame_info`.
- [x] **#20**: **Data Model** *(highest priority — done.)* Documented the data model in **[`DATA_MODEL.md`](DATA_MODEL.md)** (canonical): principles/invariants,
  entity hierarchy, a per-file **data catalog** (location · format · derivation ·
  mutability+enforcement · persistence · retention), mutability & retention
  policy, versioning/migration, an embedded **Mermaid data-flow diagram**, and
  *designed-for-future* seams settled with the user — **Objects + list defs**
  (many-to-many catalog/goals, item 5), **device-under-target** multi-telescope
  (#16), planning **profiles** + a `Plans/` output axis (items 1–2), and a
  **files + swappable SQLite-index** substrate seam. `CLAUDE.md` (Conventions) and
  `README.md` now point at it and require data-model changes to be recorded there
  (on-disk changes bump `.store_version` + add a `migrate.py` step). #14
  (render-orphan prune) is the first concrete retention task it formalizes.
  - [~] **#21**: **Auto-prioritizer** *(promoted → ROADMAP item 1, "Auto-prioritizer
    / target scoring"; dependency: multi-catalog goals, item 5.)* The vision of the priorities table in ~/Astronomy is that it’d be a hand-edited list of priorities that gets used for session planning, but the reality is I just have an LLM edit the list based on season and vaguely stated goals. We should be able to put some logic around it. User has a priorities preference pane where they rank object types (optional) to give them more weight when selecting targets. Beyond that priorities would be based on goal(s) (which catalogs/lists are being pursued) and season. An object that’s part of an active goal that is about to go out of season would be a higher priority than an object that’s just coming in to season, and so on. Some brainstorming on these rules would be good. User would also select a general preference for “capture as many new targets as possible” vs. “build deep stacks”.
    *Scoring model sketched in ROADMAP; **scoring weights + which knobs surface in
    the priorities preference pane are still TBD** (to refine next session).*

---

## Feedback (on the UI & Enhancement notes)

**#9 — Group preview by object. Strongly agree; this is the next thing I'd build.**
The per-frame table is the source of several problems at once: it's slow to
populate (1,500+ `QTableWidgetItem`s), unreadable, and made the modal churn worse.
An object-grouped view (`M101 · 314 frames · 6.1 GB · → FITS/M101/lights`) is far
clearer and faster. One implementation note: to show **MB** I need to `stat()`
each source file during the scan — fine, but it must stay on the scan worker
thread (statting 1,500 files over SMB on the UI thread would re-freeze things).
I'd add a `size_bytes` to the ingest op, summed per object.

**#10 — Select objects to import (default all). Agree, and it pairs naturally with
#9.** Once rows are per-object, a checkbox column (with select-all/none) is easy,
and ingest just filters the op list to the checked objects. This is genuinely
useful: re-pull one object, skip a half-captured night, or split a huge first
import into chunks. Recommend doing #9 + #10 in one pass.

**#11 — "Manage and display everything off the Seestar." Half done; the rest is a
display surface.** Ingest already *captures* more than the Library shows:
- Seestar stacks → `Seestar_stacks/<obj>/` (now incl. preview JPGs) ✓
- Lunar/planetary/scenery media → `Images/<Category>_photo|_video/` ✓ (copied)
But the **Library only renders catalog (Messier/NGC) objects**, so media and
non-catalog content are invisible. Closing this needs a new view — e.g. a "Media"
/ "Other" section or tab with lunar/planetary/scenery galleries (and video
thumbnails). That's its own increment, bigger than #9/#10; worth scoping after the
Library MVP. (Planetary from the ETX/ASI662 would also land here eventually.)

**Other UI observations (mine):**
- **Pre-copy summary.** Before a big copy, show total size + rough time so the
  user knows a 12 GB pull is coming. (Depends on #9's size data.)
- **Resumability is already good** — copies skip-if-present and are partial-safe
  (atomic temp+rename), so a cancelled/failed ingest can just be re-run. Worth
  surfacing in the UI ("N already present, skipped").
- **Empty-state guidance.** When the Library is all-uncaptured (fresh data root),
  a hint like "Ingest from your Seestar to get started" would orient new users.
- **First-launch.** Consider a one-time "choose your data folder" prompt rather
  than silently defaulting to `~/Documents/M110`.

---

## Data Store / File Organization

### Improvements (proposed)

- [x] **#13**: **Human-friendly data-store layout (architectural).** *Done
  (2026-06-10; tests green, pending commit).* The old data root mixed concerns
  and exposed app internals, so a human browsing `~/Documents/M110` couldn't tell
  content from machine state — and could break it. The old top level was three
  dirs that didn't map to how a user thinks: `data/` (catalog/sessions/derived
  **plus** the human-authored journals), `Images/` (content, but with jargon
  subfolder names — `FITS`, `Seestar_stacks`, `From the scope`, `Finished
  Images` — and the ingest staging area among real content), and `site/` (an
  opaque leftover name from the old static-site generator). The fix was
  architectural, not cosmetic.

  **What shipped — a two-axis store (version 2):**
  - **`Objects/` (catalog-object axis) and `Images/` (capture-target axis) kept
    distinct.** Objects and capture targets are **many-to-many** (one `M81 M82`
    capture feeds two catalog objects), so conflating them into one
    "per-object folder" can't work cleanly — splitting the axes resolves it and
    leaves room for future top-level siblings (e.g. `Session Plans/`).
  - **Internals hidden.** All machine state moved into a hidden
    **`.m110_internal_data/`** (with a "don't touch" README anyway).

    ```
    ~/Documents/M110/
      Objects/<catalog id>/          (Objects/M101/, named by catalog id; slug→id)
        journal.md                   per-object notes (+ future per-object artifacts)
      Images/<target>/               (= the old object_dir)
        lights/  stacks/  seestar-stacks/  finished/
      Media/<Category>_photo|_video/ non-catalog media
      Inbox/                         ingest staging (was "From the scope")
      .m110_internal_data/           hidden app internals + README
        catalog.toml  priorities.toml  sessions.jsonl  processing_overrides.toml
        derived/                     generated rollups
        renders/                     thumbnails + hero/<slug>.jpg (was site/img)
        .store_version               = 2
    ```

  - **Siril vs Seestar stacks stay distinct** (`stacks/` + `seestar-stacks/`) to
    preserve gallery labels and hero-tier order.
  - **Journals keyed by catalog id** (`Objects/M101/journal.md`), resolved via
    the catalog (fallback: slug). Folder names are **relocated as-is, not
    normalized** — case/space cleanup remains **#12**.

  **How it landed:**
  - New `m110/migrate.py` (`migrate_store`): in-place, **idempotent**,
    version-stamped, same-fs renames, resume-safe, never destructive; called from
    `config.ensure_data_root()`. Covered by `tests/test_migrate.py`.
  - `scan_sessions`/`build_derived` now read `config.*` **dynamically** (retired
    import-time path binding). Behavior-compat with the Astronomy byte-for-byte
    goldens was **consciously retired** for this store; re-validated against the
    repo's own fixtures. Per-target paths via
    `config.{target,lights,stacks,seestar_stacks,finished}_dir()`.
  - Done **before 0.1e/0.1f** so journal editing + processing-prep build against
    the final layout (no double migration).

- [ ] **#14**: **`build_images.render_images` never prunes orphaned renders.**
  *Logged 2026-06-18 from the Astronomy session (engine-parity audit).* When a
  source image changes (reprocess, new mtime/size → new `img_hash` → new
  thumbnail/full filename), the **old** derivative is left behind in
  `.m110_internal_data/renders/`. `render_images` only *writes* derivatives +
  `images.json`; there's no cleanup pass, so the renders cache grows unbounded
  over time. Gallery correctness is unaffected (`images.json` references current
  hashes), so this is **disk hygiene, not a display bug** — low priority.
  - **Fix pattern:** port Astronomy's `build_site._cleanup_orphaned_images` —
    after rendering, compute the active hash set from the rendered manifest and
    `unlink` any `renders/*.{jpg,png}` (and hero sidecars) whose stem isn't
    active. (Astronomy `scripts/build_site.py`.)
  - **Note on the parent bug:** the Astronomy *dry-run* mis-reported phantom
    thumbnail create/remove counts because it had a **second, drifting** copy of
    `img_hash`/discovery. **M110 is not exposed to that** — it has a single
    `img_hash` (already the correct `mtime+size+v5` formula) and one
    `discover_images`, and no dry-run predictor. Only the cleanup gap above
    carried over.
  - **Re the NGC 6992 "processed images not picked up" bug (now fixed):** ruled
    out — that turned out to be **classification** (`siril._classify` vetoing
    step-token names like `_spcc_processed`), not the render cache. The
    `make_thumb`/`make_full` skip-cache is content-hash keyed (`mtime+size+v5`),
    so a reprocessed file gets a fresh hash → fresh derivative; it does not
    suppress regeneration. #14 remains purely the orphan-cleanup disk-hygiene gap.

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
- [ ] **#9**: Group the preview by object (object · #frames · MB) instead of one
  row per frame.
- [ ] **#10**: Allow selecting which objects to import (default: all).
- [~] **#11**: Import & display *everything* off the Seestar (stacks, planetary,
  scenery, …). *Ingest* of stacks (+previews) and media (`*_photo`/`*_video`)
  already works; the gap is a **display surface** for non-catalog media.
- [ ] **#12**: **Smart-ingest name normalization + pointing verification.** Field
  evidence (June 2026) shows device folder names can't be trusted: a Seestar
  firmware regression saves the custom object "M81 M82" into an `M81` directory
  (same pointing, wrong name — silently mis-credits the data), and SSC creates
  case-variant dirs (`m82`), forking an object across folders. At ingest preview:
  (a) case-fold incoming names against existing folders + catalog and propose the
  canonical destination; (b) read `RA`/`DEC` from a sample frame and compare to
  the catalog position — >0.15° mismatch gets a "pointing ≠ name" badge and a
  remap dropdown so the user fixes it *before* confirm; (c) support a per-store
  alias table for known quirks. Pairs naturally with #9/#10 (grouped, selectable
  preview rows). This is exactly the kind of correctness work a GUI ingest can do
  that raw device copying can't.

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

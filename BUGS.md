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

# Changelog

All notable user-facing changes to M110 are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/) once it
reaches 1.0. Until then (pre-`0.1.0`), the detailed engineering history of how and
why each subsystem shipped lives in [`DONE.md`](DONE.md); this file summarizes the
changes a **user** would notice, per release.

## [Unreleased]

## [0.2.0-beta.1] - 2026-07-15

### Added
- **Plan a night.** On the Planning page, pick a night, choose how many **targets**
  (default 4), and M110 builds a real observing **schedule** — back-to-back,
  non-overlapping slots on 10-minute boundaries, each with a start time, duration,
  altitude at start, filter, and moon impact. The highest-priority target that's up at
  astronomical dark goes first; each next target starts when the previous one ends;
  targets about to leave the season go before ones that will keep. Durations adapt:
  a target that reaches *deep stack* sooner gets a shorter slot, and the schedule
  keeps filling until dawn rather than stranding dark hours. Reorder or drop slots
  (the schedule re-chains instantly), then **save a field guide** — a clean, printable
  plan you can browse and view right in the app.
- **Altitude timeline.** The plan is drawn as an altitude-vs-time chart: each target's
  curve across the dark window, the **moon's track** while it's up, your device's
  **start ceiling**, and the scheduled slots as colored time bands.
- **The schedule respects your telescope.** Smart scopes like the Seestar refuse to
  *start* a capture too close to the zenith (~78° for the S50) — proposed start times
  now stay safely below that ceiling, catching high targets on their rising or setting
  side instead. Dwarf devices get a softer quality guideline. Short "last-chance"
  slots on a setting target are flagged **⚠** so you can keep or drop them knowingly.
- **Smarter ranking.** Catalog completion oddities that aren't imaging targets (M40 —
  a double star; M73 — an asterism) no longer claim dark-sky time, and very faint,
  diffuse targets are down-weighted by surface brightness — a showpiece outranks a
  stretch target on a small scope.

### Fixed
- **Moon information is now trustworthy.** The plan header describes the whole night
  ("29% lit · up at dusk (+6°) · sets 23:05"), not one misleading snapshot; the
  per-target **Moon** column only shows a separation while the moon is actually up
  ("—" once it sets) and grades its impact by phase, proximity, and your filter
  (narrowband is largely immune). Also fixed a bug that could print a moon separation
  roughly double the real value.
- **Plans can no longer be saved under the wrong date.** Changing the night or the
  location clears the stale plan (regenerate for the new night); a saved field guide
  is always stamped with the night its astronomy was computed for.
- **The date picker works.** The calendar popup showed "…" instead of most day
  numbers and greyed out the selected date; day numbers, weekday names, and the
  selection now render properly in both light and dark themes — and the "Night:"
  field itself is no longer near-unreadable in dark mode.

### Changed
- Field guides now note both dates: when the plan was generated and which night it's
  for. Season labels are no longer printed beside a dated recommendation (they read
  as contradictory).

### Removed
- The published website's *Priority Targets* section. It was driven by the old
  hand-edited priorities file, which the automatic ranking replaces.

## [0.1.0-beta.3] - 2026-07-14

### Added
- **Planning page + location profiles.** A new **Planning** pane in the nav rail is
  the home for session planning. It starts with a **location selector**, your
  **priority targets**, and a **Manage site profiles** section where you can create,
  edit, and delete observing-site profiles — coordinates, elevation, timezone, and an
  imported horizon (`.hrz`) skyline — with an optional online **place-name lookup** to
  fill in coordinates. This is the foundation the automatic prioritizer and session
  planner build on next.
- **Automatic priority ranking.** The Planning page now ranks your targets for you —
  by goal membership, how soon the season closes, how much integration they still need
  (type-aware: nebulae need far more than clusters), and how well they sit tonight from
  your site. A **Strategy** toggle (capture-many ↔ go-deep) and **tuning weights** re-rank
  instantly; **Pin/Deprioritize** still compose on top. The heavy sky math runs once a
  day in the background.
- **Light-dome estimate for a site.** In a site profile, **Compute light-dome…**
  estimates your local light-pollution "glow" — how high the sky is washed out toward
  nearby towns in each direction — from a bundled worldwide town dataset and your
  location (optionally calibrated by a Bortle number). Planning uses it to favor
  targets away from your brightest horizons. The result is saved with the profile and
  can be hand-edited.
- The **user guide** is now linked from the app's Help menu and the website.

### Fixed
- **Combined captures count for both objects.** A two-object capture folder (like
  `M81 M82`) now credits its integration to *both* catalog objects, and no longer
  creates a phantom "M81 M82" object in your Library (existing libraries are cleaned
  up automatically on first launch — the library format steps to v4). The Processing
  queue's first column is now honestly labelled **Target**: a combined capture and a
  solo capture of the same object are separate stacks to process, not duplicates.
- **Import preview checkboxes render on every row** on macOS (clicks toggled them
  correctly, but only the current row's checkbox was visible).

## [0.1.0-beta.2] - 2026-07-12

### Added
- **Update notifications.** M110 checks GitHub for a newer release on launch (about
  once a day) and shows a quiet, dismissible banner when one is available, with
  **Download** and **Skip this version**. Check anytime via **Help → Check for
  updates…**, or turn the launch check off in **Preferences → Updates**. The check
  degrades silently when you're offline and sends no data.
- **Holding area: assign many files at once.** Select multiple rows in the holding
  area and assign them all to the same object and kind in one step, instead of one row
  at a time.

### Fixed
- **Import now scans every subfolder, consistently.** Some capture folders nested more
  than one level deep could be missed depending on how you started the import. The
  importer now walks the whole folder tree the same way from every entry point, and shows
  a clear summary after scanning — how many objects and files it found, and how many files
  it couldn't identify (which go to the holding area for you to assign). A detailed scan
  log is also written to help diagnose future import surprises.
- **Holding area: assign files to any object name.** The Object field accepts any
  name you type — including an object not yet in your library (a new entry is created
  when you assign) — but it looked like a fixed drop-down. It now clearly reads as
  type-or-pick, with a placeholder and search-as-you-type.
- **Window can be resized narrower.** A few long description lines didn't wrap, which
  forced the main window to a wide minimum it wouldn't shrink below (most noticeable on
  the empty-library Overview). Those lines now wrap, so the window resizes down normally.

## [0.1.0-beta.1] - 2026-07-10

First public beta.

### Added
- **DwarfLab Dwarf 3 support.** Import recognizes the Dwarf 3's on-device layout —
  raw subs, in-app stacks, and startrails (routed to Media) — and derives sessions
  from the FITS headers, so capture tracking works the same as it does for a Seestar.
- **Overview page.** A single dashboard of collapsible sections — goal progress,
  priority targets, integration time & recent sessions, category progress, and goal
  management — each remembering whether you left it open or closed.
- **Media, in the Library.** A Deep sky / Media toggle switches the Library between
  your catalog objects and your lunar / planetary / scenery / startrails media.
- **Feed view.** A reverse-chronological, photo-blog-style view of your objects, as a
  third Library view alongside List and Grid.
- **Processing: "Ready to import"** — objects with finished Siril output waiting to be
  pulled in are grouped at the top of the Processing queue.
- **Backups** — hardlinked, dated snapshots of your library to an external
  destination, with retention and one-click restore.
- **Publishing** — export a selective static website of your collection to a folder.
- Continuous integration runs the test suite on every push and pull request
  (Python 3.11 + 3.14); contributor docs (`CONTRIBUTING.md`, Code of Conduct, security
  policy, issue/PR templates).
- Import: **live scan progress** shows the current folder and a running file count, so
  a slow scan over a network share clearly shows progress.

### Changed
- **Simpler navigation** — the nav rail is now four pages: **Library · Overview ·
  Import · Processing**. The Library is home and opens as a thumbnail grid.
- The holding area splits a mixed import folder into one row **per detected object**,
  so each can be assigned independently.

### Fixed
- **First launch no longer shows "Sync failed"** on a brand-new (empty) library.
- **Processing accuracy** — objects whose finished stack lives among their working
  files now show the correct "In stack" frame count and a correct "+ new" backlog
  (previously blank / inflated). The Overview integration table no longer shows blank
  cells for some objects.
- No longer crashes on **Windows** first launch (engine text files are read/written as
  UTF-8, not the OS locale encoding).
- Import: **Cancel** now interrupts a scan mid-folder; no longer crashes on Linux when
  a background sync finishes while the window is hidden.
- Table sizing throughout Overview / Processing / object detail no longer truncates a
  row or leaves dead space.

### Removed
- The separate **Summary, Goals, Sessions, Journal,** and **Media** nav pages — all
  folded into the Library and Overview (see *Changed*).

---

<!--
Release entries look like:

## [0.1.0-beta.1] - 2026-07-XX
### Added / Changed / Fixed / Removed
- ...

Keep the newest release at the top, under [Unreleased]. Move Unreleased items
into a dated, versioned section when you cut a release.
-->

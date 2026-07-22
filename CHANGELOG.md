# Changelog

All notable user-facing changes to M110 are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/) once it
reaches 1.0. Until then (pre-`0.1.0`), the detailed engineering history of how and
why each subsystem shipped lives in [`DONE.md`](DONE.md); this file summarizes the
changes a **user** would notice, per release.

## [Unreleased]

### Fixed
- **A stack of just one object no longer stands in for a combined target.** If you shoot a
  pair together — an `M81 M82` folder, say — and one of your stacks covers only *one* of
  them, M110 no longer treats it as the pair's latest stack. It was measuring that stack's
  frame count against everything you'd ever captured of the pair, which produced a wildly
  inflated "rejected" percentage. M110 now reads the object name recorded inside the file by
  the telescope, and prefers a stack that covers the whole target.
- **The Processing page was reading the wrong stack, so "In stack", "+ new" and rejection %
  could be badly off.** When an object had more than one stack on disk, M110 picked the one
  with the newest *file date* — but copying a file updates its file date, so a stack you
  re-copied recently could look newer than the one you actually made last. On one target in
  testing this showed **In stack 118 frames (0:39)** when the real latest stack had **393
  (2:23)**, and claimed **417 new frames waiting** when only 123 were. M110 now picks the
  stack by the date **written inside the file by the stacker**, which is what it was already
  using to decide which frames count as new. If you've been seeing a reprocess backlog that
  didn't look right — or targets stuck on "out of date" that you know you'd already
  reprocessed — this was why. **Your numbers will change after the next refresh, and some
  targets may correctly drop to "up to date".** Nothing on disk is touched; only the
  reported figures change.

## [0.2.0-beta.7] - 2026-07-21

### Added
- **Export finished images sized for web sharing.** Right-click any image in an object's
  gallery — or the hero image — or use the new **⤓ Export…** button in the full-screen
  image viewer, then **Export for sharing…** to save a copy under a size limit you set (for
  Reddit's 20 MB cap, say), or with **No maximum**. It preserves as much quality as it can:
  by default it stays **lossless** (a finished 16-bit PNG typically drops well under 20 MB
  just by converting to 8-bit, at full resolution) and only reduces resolution if it has to;
  or pick **Keep full resolution** for a high-quality JPEG. A standard Save dialog opens with
  a suggested name like `M42-20mb-20260721.png` that you can rename, and lets you choose
  where the file goes.
- **Three "Popular" goal lists, curated by popularity and matched to your gear.** New
  bundled goals you can turn on from **Overview → Manage goals**: **Popular: Deep (S50)** —
  small, faint, detailed targets that suit the S50's deeper aperture and narrow field;
  **Popular: Widefield (S30 Pro / Dwarf 3)** — big showpiece nebulae that need a wide frame
  (North America, Veil, Heart & Soul, Andromeda…); and **Popular: Bright & Easy (S30 / Dwarf
  Mini)** — bright, forgiving crowd-pleasers that reward a short session. Each list spans all
  four seasons and reaches well beyond Messier. To support them, four iconic targets were
  added to the object reference: the **Pelican**, **Horsehead**, and **Elephant's Trunk**
  nebulae, and the second half of the **Double Cluster** (NGC 884).

### Changed
- **Importing a Siril project keeps your Naztronomy preset.** If the folder you import
  already contains a `naztronomy_smart_scope_presets.json`, M110 carries it into that object's
  processing sandbox instead of generating a fresh default — so your saved stacking settings
  come across with your data. (Part of importing existing Siril projects — issue #57.)
- **Processing prep now sets up your calibration frames too.** When an object has darks,
  flats, or biases, M110 links them into the Siril working folder right beside the lights (at
  no extra disk space) and turns on the matching options in the generated Naztronomy preset, so
  the script calibrates by default. Previously only lights were set up, so an imported project's
  calibration frames were left behind. (Groundwork toward importing existing Siril projects —
  issue #57.)
- **Import recognizes existing Siril project folders.** If you already keep your captures in
  Siril-style project folders — `M51/lights`, `M51/darks`, `M51/flats`, `M51/biases` — you can
  point import at the folder that holds them and M110 pulls each project in as one object,
  without you reorganizing anything. A stack or finished image Siril left loose beside those
  folders now lands in the right place (`stacks/` / `finished/`) instead of the holding area; a
  `M63_sub` folder imports as **M63**; and a folder of loose subs named after a catalog object
  (with no `lights/` subfolder) is recognized by its name. (Thanks to @devonjones — issue #57.)
- **Overview's "Priority targets" no longer says the prioritizer is "coming."** The
  automatic target ranking has shipped — it lives on the **Planning** page. The
  caption on Overview now explains that this section shows the targets you've
  *pinned*, and points to Planning for the automatic ranking.

### Fixed
- **"Import finished work" now finds the stacks and renders you've sorted into folders
  yourself.** If you saved your Siril stack into a `stacks/` folder and your finished image
  into a `finished/` folder — instead of leaving them loose for M110 to sort — import used
  to pick up only files whose *names* contained a word like "processed" or "final." A
  plainly-named `.fit` stack was skipped, and often only the `.jpg` came through. M110 now
  trusts the folder: anything in `stacks/` is treated as a stack and anything in `finished/`
  as a finished image, whatever it's named. (Thanks to @devonjones — issue #85.)
- **Checkboxes and radio buttons are visible in dark mode.** Their empty (unchecked)
  boxes and circles were drawn by the native macOS control style and came out almost
  invisible against the dark background, so some options were hard to spot — for
  example in Preferences, the Publish and Backup dialogs, and the new export dialog.
  They now have a clear outline in both light and dark themes.
- **No more rare crash when quitting while thumbnails are still loading.** M110 decodes
  gallery/row thumbnails on background threads; if you quit the app while one was still
  in progress, the decode could run as the window tore down and crash. The app now waits
  for in-flight thumbnail work to finish first. (This also fixes intermittent
  test-suite failures in CI, which were the same race.)

## [0.2.0-beta.6] - 2026-07-19

### Changed
- **"Enrich online" is no longer offered when only the filter is unset.** The capture
  *filter* was counted as missing metadata, so objects that otherwise had everything would
  still offer online enrichment and then report "nothing to add" — because no catalog knows
  which filter you shot with. Filter is no longer treated as a fillable gap, so enrichment
  is only offered when there's actually a field a lookup could provide.

### Fixed
- **Planning and priority ranking work in the installed app.** In the packaged builds they
  failed with *"astronomy engine unavailable"* (the ranking) or no usable plan — because the
  astronomy library (astropy) wasn't fully bundled: its unit-parser tables were missing, so the
  very first calculation at startup errored out. Those files are now included, and planning,
  tonight's observability, and the priority ranking all compute again. (Thanks to @devonjones —
  issue #75.)
- **"Enrich online" / "Look up online" work in the installed app (for real this time).**
  Beta 5 bundled the Simbad lookup library (astroquery), but it still failed to start because
  the same astropy pieces above were missing **and** astropy's version record wasn't included
  (astroquery reads it at launch). Both are now bundled, so online enrichment actually runs.
  (Thanks again to @devonjones — issue #74.) If online lookup ever fails again, M110 now writes
  the underlying reason to its log so it can be diagnosed instead of just showing "not available."
- **Online lookups no longer crash with an "int too large" error on Windows.** Once enrichment
  ran, a Windows-specific quirk in how Simbad results were fetched (a large ID value that
  Windows couldn't handle) made every lookup fail with *"OverflowError: Python int too large to
  convert to C long."* M110 now fetches results in a way that avoids that value entirely, so
  Enrich online and Add-object lookups work on Windows too. (Thanks to @devonjones.)
- **The About box shows the version you actually installed.** Installing a new beta *over* an
  older one on Windows could leave the old version's record behind, so Help → About reported an
  earlier beta (some users saw 0.1.0-beta.1). The Windows installer now fully replaces the app
  on upgrade, and M110 reads its version from the running code rather than a leftover record —
  so the number is always right. (If you hit this, a clean reinstall also fixes it.)
- **Unavailable right-click menu options now look disabled instead of dead.** When a
  menu entry doesn't apply — e.g. **Fill in missing metadata** / **Enrich online** on an
  object that already has complete details — it's now clearly greyed out, rather than
  looking normal but doing nothing when clicked. (A styling gap meant disabled items in
  M110's menus kept full-strength text; they're now dimmed like disabled buttons.)

## [0.2.0-beta.5] - 2026-07-19

### Fixed
- **A re-processed image with the same filename is no longer silently lost on import.**
  When you *Import finished work* and a file has the **same name** as one already in
  `finished/` (or `stacks/`), M110 used to skip it — and then the cleanup step swept your
  new version into the sandbox's `archive/` folder, so an improved re-process could seem to
  vanish. Now: if the incoming file is **identical** it's skipped (a true duplicate), but if
  it's **different** it's imported alongside the old one under a numbered name (e.g.
  `M42-2.png`), so nothing is lost. The import preview shows exactly what will happen.
- **"Enrich online" and "Look up online" now work in the installed app.** These
  Simbad lookups (fill in an object's type/magnitude/size/coordinates, or look up a new
  object you're adding) depend on a library (astroquery) that the packaged builds weren't
  shipping — so clicking them just showed an error telling you to `pip install` something,
  which isn't possible in an installed app. The packaged macOS/Windows/Linux builds now
  bundle it, so online enrichment works out of the box. (Thanks to @devonjones for the
  report — issue #64.) If a build ever still lacks it, the message now says so plainly
  instead of pointing at an impossible install command.
- **The Sessions "Mount" column now shows your real EQ / Alt-Az mode.** It used to be a
  guess based on a fixed calendar date, which was only ever right for the developer's own
  telescope — everyone else's sessions could be mislabeled. M110 now reads the actual mode
  recorded in each capture's file (both Seestar and Dwarf 3 record it), and only falls back
  to a date guess for older files that predate that recording.
- **Planning tells you the truth when it can't run.** If the astronomy calculations fail
  to start, *"Plan a night"* now says the astronomy engine isn't available (and records the
  details in the log for a problem report) instead of the misleading *"No astronomical
  darkness for that night here"* — which now appears only when it's actually true (a
  high-latitude summer night with no real darkness). The priority-ranking status likewise
  says when it's running in a **degraded** mode rather than reporting "up to date". This
  makes a broken-astronomy situation obvious instead of silent.
- **Session planning works in the installed app again.** In the packaged builds (macOS,
  Windows, and Linux), the whole Planning pane was quietly broken: **"Plan a night"**
  always reported *"No astronomical darkness for that night here"* even in the middle of
  summer, and **Recompute** finished almost instantly and produced only a generic ranking
  (no season/tonight information, nothing hidden as "not up tonight"). The cause was that
  the astronomy library M110 uses (astropy) wasn't being bundled completely — one of the
  physical-constants modules it loads on demand was left out, so every sky calculation
  failed silently. All of astropy is now bundled, and planning computes real twilight,
  moon, and observability again. (Running from source was never affected.)

## [0.2.0-beta.4] - 2026-07-18

### Fixed
- **"Process in Siril" no longer crashes Siril's scripts (macOS).** Launching Siril from
  the packaged M110 app could make Siril's Python scripts abort on startup with a "two sets
  of Qt binaries" error — M110 was leaking the location of its own bundled Qt to Siril, and
  Siril's scripts (which use their own Qt) loaded both at once. M110 now hands Siril a clean
  environment, so its scripts run normally.

## [0.2.0-beta.3] - 2026-07-17

### Added
- **Process in Siril, in one click.** Right-click an object (or use the button on its
  detail page, or right-click a row on the Processing page) → **Process in Siril** and
  M110 launches Siril already pointed at that object's working folder — no more browsing
  to the right directory yourself. M110 finds Siril automatically in the usual place;
  if it's installed somewhere else, set the path under *Preferences → Processing tools*.
  When Siril can't be found, M110 offers to open the working folder instead. **Quit Siril
  when you finish an object** — M110 sets the working directory only as Siril starts, so
  if Siril is already open it won't switch to the next object's folder. (See the
  [processing guide](docs/processing.md).)
- **"Open in…" for gallery images.** Right-click any image on an object's page to **Open
  in default app** (your usual image viewer/editor) or **Reveal in file manager**.
- **"Reveal working folder" on an object.** The object detail pane now has a button that
  opens that object's Siril processing folder (`Images/<target>/siril/`) directly — so
  you can set Siril's *working directory* to the right place instead of hunting for it.

### Fixed
- **Windows: the app no longer crashes on launch.** The Windows build was missing the
  time-zone database that the planning features rely on, so it quit immediately with a
  `zoneinfo` / `tzdata` error before the window ever appeared. The database is now bundled
  in the build. (Thanks to @devonjones for the report — issue #56.)
- **Processed images saved in the wrong folder are now picked up.** If you set Siril's
  working directory to the object folder (`Images/<target>/`) instead of its `siril/`
  sub-folder, your finished renders and stacks used to be invisible to *Import finished
  work*. M110 now also scans the object folder as a fallback, so that easy mistake no
  longer strands your processing output.
### Changed
- **Priority targets now default to what's actually up tonight.** The Planning page's
  priority list has a new **"Visible tonight"** checkbox (on by default) that hides
  objects out of season for tonight — so winter/spring targets like M44, M97, or M42 no
  longer sit near the top of a July list. Uncheck it to see the full ranking when you're
  planning a future date.
- **"Plan a night" respects the Targets number.** The night sequencer now schedules
  roughly the number of targets you ask for, gives each one its **full slot** rather than
  cutting a primary short, and **never schedules a slot under 30 minutes** — no more
  10-minute stubs that a slew and autofocus would eat whole.

### Added
- **Weight object types in your priority ranking.** Planning → *Tuning weights* gains
  **Galaxies / Globular clusters / Open clusters / Nebulae** controls — turn galaxies and
  nebulae up and clusters down (or vice-versa) to shape what gets prioritized in a
  cluster-heavy catalog like Messier.

## [0.2.0-beta.2] - 2026-07-15

### Added
- **Publish straight to GitHub Pages.** *Library → Publish / share* can now deploy your
  site to a GitHub repository instead of only writing a folder you host yourself. Enter
  your repository as `owner/repo`; M110 uses the `git` and GitHub sign-in you already
  have, so no passwords or tokens are handled by the app. Your site lands at
  `https://<owner>.github.io/<repo>/`, and the success dialog links straight to it.
  Uploads happen in the background with real progress, and **Cancel** stops them
  cleanly. See the new **[Publishing guide](docs/publishing.md)** for the one-time
  repository and SSH setup.
- **Choose how uploads work.** *Replace the site each time* (the default) keeps the
  repository small forever but re-uploads everything on each publish; *Upload only what
  changed* makes re-publishing a large gallery take seconds, at the cost of keeping
  every superseded image in the repository's history.
- **Save your publish settings without publishing.** Change what's included, the site
  title, or the destination, and keep it for next time — no export required.

### Changed
- **Published galleries now show your finished images only**, by default. Working files
  (Siril stacks and other by-products) no longer go on the public site — they were the
  bulk of its size and upload time. A control under *Image galleries* lets you publish
  **finished + your telescope's in-app stacks**, or **everything**, if you'd rather.
  Images you've marked *finished* by right-clicking always publish.
- **The published Processing page now mirrors the app's** — a *Ready to import* group at
  the top, no clutter from fully-processed targets, and the same Target / Rejected /
  Latest stack / Notes columns you see in the window.

### Fixed
- **Re-publishing removes what you've excluded.** Unchecking a section or narrowing your
  galleries used to leave the old pages and images behind in the output folder — and if
  you were deploying them, they kept getting uploaded even though nothing linked to them.
  The published site now always mirrors your current selections.
- **The Processing queue sorts by "+ new" first**, so the targets with the most
  unstacked frames are on top — and when you pick a different sort, it now survives
  clicking away from M110 and back.
- **The update check works on a clean install.** A dependency it needs at runtime wasn't
  declared, so in a fresh environment the check could silently do nothing.

### Security
From an internal threat-model review of M110's real attack surface — the files you
import. Full assessment in
[`docs-archive/SECURITY_ASSESSMENT.md`](docs-archive/SECURITY_ASSESSMENT.md).
- **A crafted capture file can no longer write outside your data folder.** An object name
  read from a FITS `OBJECT` header (fully attacker-controlled in a hand-made file), or a
  source folder name, flowed into the destination path unsanitized. Object names are now
  reduced to a single safe path segment, and the importer — the only code that writes
  into your library — hard-refuses any operation resolving outside your data folder.
- **Pillow raised to 12.3 or newer**, clearing five advisories flagged by `pip-audit`.
  M110 decodes untrusted images with Pillow; those specific issues were in code paths
  M110 doesn't use, but the old floor allowed years-old builds.
- **Image decompression bombs are capped.** Rendering now refuses absurdly large images
  (over 300 megapixels — far beyond any real frame or mosaic) instead of trying to
  allocate them.

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

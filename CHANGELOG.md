# Changelog

All notable user-facing changes to M110 are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/) once it
reaches 1.0. Until then (pre-`0.1.0`), the detailed engineering history of how and
why each subsystem shipped lives in [`DONE.md`](DONE.md); this file summarizes the
changes a **user** would notice, per release.

## [Unreleased]

## [0.3.0-beta.5] - 2026-08-18

### Added
- **You can now set aside subs you don't want stacked, without deleting them.**
  Move any frames you don't want — clouds, trails, bad focus — from an object's
  `lights/` folder into a folder called `rejected/` beside it (create it yourself;
  M110 won't make one for you). From then on those frames are out of the picture:
  they aren't linked into the Siril working folder, they stop counting toward the
  object's integration time and session totals, and — the part that makes this
  worth doing instead of deleting — **M110 won't copy them back off your telescope
  the next time you import.** Previously the only way to keep a bad sub out of a
  stack was to delete it, and the next import brought it straight back.

  The frames themselves are never touched: M110 only ever reads the names in
  `rejected/`, and removes the *link* to them from the working folder. If you
  reject frames for an object you've already prepped, the working folder is
  tidied up on the next sync. Change your mind by moving the files back.

  This is the groundwork for the planned Lights Table, where you'll be able to
  review and flag subs from inside the app instead of in a file manager.
  (Thanks to @devonjones — [#110](https://github.com/mjm1138/m110/issues/110).)
- **The Media library now has List and Grid views, like the rest of the Library.**
  Media used to be a plain stack of sections; it now gets the same treatment as
  your deep-sky objects — a grid of thumbnails with a tile-size slider, or a
  sortable list with a detail panel showing a large preview, the capture date,
  size and dimensions, plus Open, Reveal and Export buttons. There's a category
  filter, a Photos/Videos switch and a search box, and your choice of view is
  remembered.
- **Videos have thumbnails.** Your telescope saves a preview frame next to every
  clip, and M110 now uses it, so videos look like their contents instead of a
  filename. A small ▶ marks them apart from photos. Videos still open in your
  usual player — M110 doesn't play them itself.
- **Processed work stored alongside your videos is now visible.** Stacked lunar
  results saved into a video folder — including whole subfolders of output from
  tools like AutoStakkert — were invisible before, because Media only looked for
  video files in a video folder and never looked inside subfolders. It now shows
  every photo and video it finds, wherever it sits. FITS results get a rendered
  preview like everything else.
- **Tools → Clean up imported sidecars** removes the small duplicate thumbnails
  and `.avi.idx`/`.avi.txt` files that earlier imports copied into your Media
  folder. It shows you exactly what it will delete, nothing is selected until you
  choose it, and thumbnails a video depends on are never offered — they're the
  only preview frame those clips have.
- **Double-click the hero image to open it full-size.** The big image at the top of
  an object's detail pane now opens in the image viewer just like a gallery
  thumbnail does — and it opens *at that image*, so Prev/Next carry on through the
  object's other pictures from there. Previously the hero was the one image you
  couldn't click on to see it larger.
- **The menus have been reorganised into File, View, Library, Tools and Help.**
  Previously almost everything lived under a single "Library" menu — including
  Preferences, backups and publishing — which read oddly on Windows and Linux, and
  there was **no Exit command at all** outside macOS. Import and Publish now sit under
  File, backups and Preferences under Tools, and File → Exit closes the app. On macOS
  nothing moves out from under you: About, Preferences and Quit stay in the M110
  application menu where they belong.
- **A View menu switches panes from the keyboard** — Ctrl+1 to Ctrl+5 (Cmd on macOS)
  jump straight to Library, Overview, Planning, Import or Processing.
- **About M110 now tells you whether an update is waiting.** Open it and it checks in
  the background, then shows either "You're up to date" or the newer version with a
  Download link. It re-checks each time you open it, and never counts against the
  daily launch check.

### Changed
- **Working out your priority targets is about 10× faster** — on a Messier-sized
  list it went from roughly 23 seconds to under 3. This is the calculation behind
  the Planning page's target ranking, which runs in the background the first time
  you open Planning each day and whenever you press **Recompute**. M110 was working
  out sunset and sunrise separately for *every single target*, over and over, even
  though the sky gets dark at the same time no matter what you're pointing at. It
  now works each night out once. Same numbers, same rankings — just far less waiting.
  The saving grows with the size of your goal lists: the more targets you track, the
  more repeated work this removes.
- **The interface is tighter and closer to the way Mac apps look.** Text fields,
  drop-downs, the navigation rail down the left, table rows and the List/Grid/Feed
  buttons all carried more padding than macOS uses, which made everything feel
  chunky and fitted less on screen. They've been measured against the real system
  controls and trimmed — a table shows more rows, the nav rail is slimmer, and
  headers use the smaller text macOS uses for them. Buttons and the body text were
  measured too and left alone: they already matched the system. Spin boxes also get
  their up/down arrows back — they'd been reduced to a pair of dots.
- **The M110 mark has moved to the bottom of the sidebar**, just above the status bar,
  and **clicking it opens About** — so the version and update status are one click
  away from anywhere in the app. The sidebar now reads as a single panel, with its
  divider running the full height of the window.
- **The status bar no longer leads with a captured/total count.** The Library page
  already shows that tally in context; in permanent chrome it was noise. The status
  bar now shows where your data lives, plus whatever an in-progress operation
  (syncing, backing up) has to say.
- **Saved field guides are now managed by right-click instead of a row of buttons.**
  Double-click a guide to open it, or right-click for **View**, **Reveal in file
  manager** and **Delete** — the same way object actions already work everywhere
  else in M110. The three buttons in every row are gone: *View* only repeated the
  double-click, and *Delete* sat a few pixels from it looking exactly the same.
  The list is quieter and the titles get the space back.
- **The backup window's "Cancel" button now says "Close" unless you've changed
  something.** After running a backup, "Cancel" suggested it would undo the backup
  you'd just taken; it never could. It now reads "Cancel" only while you have
  unsaved changes, and **Save** is greyed out when there's nothing to save.
- **The placeholder observing site is now a named landmark.** A brand-new data
  folder starts with its location set to Boulder Public Library, Colorado,
  rather than an unlabelled set of coordinates — so it's obvious it's a
  placeholder waiting for your own site. Set yours in **Planning → Manage site
  profiles**; existing data folders are untouched.
- **The AI-assistant connection now uses the current version of the MCP standard
  library.** M110 had been held on the previous major version, which upstream now
  only patches for security. Nothing changes in how you connect an assistant, what
  it can see, or what it can do — the tools, skills and the read-only guarantees
  are identical, and existing client configurations keep working unchanged. Two
  small improvements came with it: skill documents are now correctly labelled as
  Markdown when an assistant reads them, and a mistaken tool argument produces a
  clearer message naming the tool and the argument.

### Fixed
- **Lunar and planetary photos were squashed in the Media view — the Moon showed
  as a wide oval.** Media thumbnails were being stretched to fill a square instead
  of keeping their proportions, so a tall 1080×1920 frame was flattened by nearly
  half. Planets were hit the same way; the subject was just small enough that it
  was hard to tell. Thumbnails now keep their shape.
- **Every lunar and planetary photo appeared twice in Media.** Imports were
  copying in the small preview thumbnail your telescope writes beside each photo,
  and Media listed it as a separate picture — so each shot showed up once
  full-size and once as a small, soft duplicate. Those duplicates are no longer
  imported or listed, and the clean-up tool above removes the ones already there.
- **The List/Grid buttons drifted apart in the Media view.** In Media they were
  drawn as two detached buttons with a gap between them, instead of the single
  joined control they are everywhere else — the pair was being stretched to the
  width of the four-button deep-sky version.
- **The close button on a media file's details showed an empty box.** The ✕ was
  squeezed out of a button too narrow to hold it. It's now the same flat ✕ the
  object detail panel uses.
- **The ✕ on an object's details did nothing in Map view.** Closing the panel
  worked in List and Grid but not on the sky map, where the panel stayed open
  with the object still ringed on the chart.
- **The Library's list and detail panels no longer butt into the divider between
  them.** Both sides of the divider — and the **Play · Reveal · Export** buttons
  under a media file's details, which sat hard against it — now have a little
  breathing room, in the Media and deep-sky views alike.
- **Buttons in table rows were cut off.** Most visibly in Planning → *Saved field
  guides*, where the row read "View · Revea · Delete" with the tops and bottoms of
  the buttons shaved off, at any window size. The same thing was happening more
  subtly elsewhere: the Import holding area's **Discard** button was a few pixels
  short, and the object pickers in both import previews were squeezed vertically.
  Rows are now measured against the controls they actually contain, so nothing is
  clipped — and the holding area's columns size themselves rather than relying on
  fixed widths that went stale whenever a label changed.
- **"Reveal in file manager" on a saved field guide opened the file instead.** It
  handed the guide to whatever app opens Markdown rather than showing you the
  `Plans/` folder.
- **M110 could quit unexpectedly when you closed the backup window.** If the
  window was still checking the destination — likely on an external drive or a
  network share, where that check takes a moment — closing it crashed the app
  outright rather than just closing. The same fault was present in the restore,
  publish and export windows when closing one just as its operation finished.
- **The backup window could refuse to save a corrected destination.** If you fixed
  the backup folder with **Browse…**, the **Save** button stayed greyed out, and the
  only way to enable it was to change some unrelated setting as well. Picking a
  folder now counts as a change, as it always should have.
- **The backup window can no longer erase your backup folder.** Saving with the
  destination box empty used to write the empty value straight over the folder you'd
  configured — silently leaving you with no backups. An empty box is now treated as
  "not entered" and your saved folder is kept.
- **The backup window opened too short, squashing the settings together.** The
  three retention fields overlapped each other by a few pixels, and the window
  couldn't show what it contained. It now opens at the size it actually needs, and
  those three fields line up in a column instead of each sitting at its own
  position.
- **The numbers in the backup window were cut off.** In *Back up Library*, the
  backup interval, "keep newest" and "keep at least … GB free" fields showed their
  values with the tops and bottoms of the digits sliced away — "100" was barely
  readable. They're now given enough room, in that window and anywhere else a
  crowded layout could have squeezed an input field.
- **A missing "&" in the backup window.** The *Automation & retention* section
  heading read "Automation  retention".

## [0.3.0-beta.4] - 2026-08-11

### Added
- **Backups now work properly on destinations that can't share files between
  backups** — many network drives, appliance NASes and exFAT disks. Previously M110
  stored a *complete copy* of your library on every single backup there, without
  saying so. It now recognises such a destination and switches to **pooled backups**,
  which store each file once and give each backup a small index of what it contained:
  the same "only what changed" saving, without needing anything special from the
  drive. As before, every backup can be restored on its own, at any age — there's no
  chain of older backups to keep intact.

  On destinations that *can* share files, nothing changes: **mirrored backups stay
  the default**, because a backup that's simply your files in dated folders can be
  restored with no software at all, and that's worth keeping. You can pick either
  from the backup window, and switching never strands backups you already have —
  both kinds stay listable, verifiable and restorable side by side.

  Because a pooled backup stores files under content-derived names, it also writes
  its own way back out, next to the data: a browsable copy of the newest backup
  (where the destination allows it), an `INDEX.tsv` listing every file in plain text,
  and a `restore.py` that rebuilds your files with nothing but a standard Python
  install — no M110 needed. See the [backup guide](docs/backup.md).

### Changed
- **The backup window now tells you what your destination can do, before you back up.**
  Some destinations — exFAT drives, certain network shares and appliance NASes — can't
  share files between backups, which means every backup stores a *full copy* of your
  library instead of just what changed. M110 could only mention this after a backup had
  already run. It now checks when you pick the folder and says either "Unchanged files
  are shared between backups" or warns that every backup will be a full copy, along with
  how much room is left. The restore list marks any backup that was stored as a full copy.

### Fixed
- **M110 could crash while you were looking at an image.** If a background sync
  finished while an image viewer or a right-click menu was open, M110 rebuilt the page
  underneath it and quit with a segfault the moment you closed the viewer. The most
  likely way to hit it: come back to a window you'd left in the background (which
  starts a sync), double-click a thumbnail, and browse for a while. Syncs now wait for
  any open dialog or menu to close before refreshing the page, and viewers and menus
  no longer open in a way that lets a refresh pull the ground out from under them.
- **The backup window could hang while you typed a destination path.** It re-read the
  whole backup folder on every keystroke; on a slow or disconnected network share that
  froze the window. It now checks once, after you finish typing or pick a folder.
- **The "keep at least this much free space" retention rule deleted too much.** Once
  the destination dropped below the threshold, a single pass queued *every* backup but
  the newest for deletion instead of removing them one at a time until there was
  enough room. It now frees space incrementally and stops as soon as the threshold is
  met.

## [0.3.0-beta.3] - 2026-07-30

### Fixed
- **The Mac app launched with no menu bar** (and no Dock icon, and no entry in Force
  Quit): the packaged bundle was marked as a *background* app. That flag was set
  automatically because M110 ships a second, headless executable — the assistant's
  connector, which by nature has to be a console program — and the packaging tool
  applied its console setting to the whole app. Affected 0.3.0-beta.1 and
  0.3.0-beta.2 on macOS; b1 crashed before a window appeared, so b2 is where it
  became visible.

## [0.3.0-beta.2] - 2026-07-30

### Fixed
- **0.3.0-beta.1 wouldn't start.** The packaged app crashed on launch with a
  `FileNotFoundError` about `constellations.json`: the installer carried the sky-map
  chart library's code but not the star and constellation data it loads, and because
  the Library draws the map while the window is being built, that failure took the
  whole app down before it appeared. The data is now bundled. Two follow-ons so this
  can't be fatal again: the sky map now reports *any* problem loading its chart
  library as "the map is unavailable" — the same graceful path as not having it
  installed — instead of letting the error escape, and the Linux and Windows
  installers now ship the chart library too (0.3.0-beta.1 had it on macOS only, so
  the Map view was simply absent there).

## [0.3.0-beta.1] - 2026-07-30

### Added
- **A sky map in the Library.** A fourth view — List · Grid · Feed · **Map** — plots your
  collection on a star chart, so you can see where everything you've shot actually sits and
  which parts of the sky are still empty. Markers use the same colors as the status chips
  elsewhere (green for a deep stack, amber for an initial capture), so a season's work reads
  at a glance. Click an object to open it; scroll to zoom, drag to pan, double-click to
  reset. Search and the catalog filter narrow the map exactly as they narrow the list, and a
  northern/southern toggle appears only if you've shot something far enough south to need
  one. **Filter to a goal and the rest of that list joins the chart in grey**, so you can
  see your progress against it — the gaps are the point. Hovering an object shows its hero.
  If a filter matches nothing you still get the sky, with a line saying why it's bare
  rather than an empty panel. Objects with no known coordinates — combined capture targets like `M42_mosaic`, or
  anything unidentified — are listed under the chart rather than quietly left off it.

  **With thanks to [Devon Jones](https://github.com/devonjones)**, who wrote
  [Uranometria](https://github.com/devonjones/uranometria) — the open-source star-atlas
  library that draws these charts — proposed the integration, and shaped the library to fit
  M110. The charts you see are his work; M110 supplies the objects and paints the markers.
  Uranometria is credited in **Help → About M110**, and is an optional component: without it
  the Map view explains what to install rather than failing.

- **The assistant can hand you a saved plan.** Ask it to plan a night and then save
  the field guide, and M110 shows a "from the assistant" bar with a Review button —
  accept, and the plan lands in your Plans folder like any other. Changes it suggests
  (a pinned target, a tuning tweak) queue up the same way, so you no longer have to
  copy-paste anything out of a chat.

  Applying a suggestion re-checks it against your library *as it is now*. If you've
  shot, imported and refreshed since it was suggested, M110 tells you what changed and
  shows the updated ranking before you commit.

  **The assistant still can't change your library.** It can only ever *add* a file to
  one staging folder — it cannot modify or delete anything you made, and nothing takes
  effect until you accept it. If you'd rather skip the review step for plans,
  Preferences → AI assistant has a toggle to let them save directly.
- **Connect Claude to M110.** Preferences → *AI assistant* → **Connect Claude Desktop**
  wires your existing Claude Desktop (or Claude Code) to your library. You can then ask
  it things like "what should I shoot tonight?", "why is M101 ranked above M13?", or
  "critique my M51" — and it answers from *your* data: your site, your horizon and light
  dome, your capture history, your priority ranking. It can also show you the night's
  schedule and hand you a field guide.

  Two things worth knowing. **It cannot change your library**: it can look, and *suggest*
  changes — new tuning weights, a pinned target, a journal entry — but it cannot alter or
  delete your files, your library, or your settings. The most it can do is add a file to
  one staging folder, and nothing takes effect until you accept it. Suggestions come with
  the ranking M110 itself computes for them, so you can see the effect before deciding,
  and you apply them in the app. And **your data goes to whoever you connect**: object notes, capture
  history and image data are sent to whatever AI model that client uses. M110 tells you
  this before it writes anything, and Disconnect removes it again.

  You bring your own client and your own account — M110 never handles an API key.

### Changed
- **The Library's catalog filter lists the catalogs you've set as goals**, rather than every
  catalog M110 ships. Picking one you weren't working and getting an empty view was a dead
  end — and since most Messier objects also belong to one of the Popular lists, the full list
  was mostly noise. Turn a catalog on under **Overview → Manage goals** to filter by it.
- **The security policy now describes what actually leaves your machine.**
  [`SECURITY.md`](SECURITY.md) lists every network call M110 makes and when it runs,
  covers the AI assistant (what a connected client can see, and the narrow limits on
  what it can write), and is straight about publishing to GitHub Pages uploading your
  images. It previously described a version of M110 that only ever exported to a local
  folder.
- **Enrich online explains what it sends.** The confirmation now says it sends each
  object's name to Simbad, instead of referring to an "optional `online` extra" —
  packaged builds already include it, so that was jargon that told you nothing about
  the privacy question you were being asked.

### Fixed
- **Mosaic folders and catalog-number folders now count toward the right object.** A capture
  folder named for *how* you shot it (`M42_mosaic`, `NGC 7000_mosaic`) or by a catalog number
  (`C 6`) was being treated as an object in its own right instead of as frames of M42, NGC
  7000, and NGC 6543 — so those captures got a placeholder Library entry with no coordinates,
  no catalog details, and no place on the sky map. Worse, it was self-sustaining: once the
  placeholder existed, the folder kept matching it. M110 now strips the capture decoration
  and resolves catalog numbers through catalog membership. **Your integration times and
  session counts for the affected objects will change after the next refresh** — those frames
  now count where they belong. **The old placeholder entries are cleaned up for you** on the
  next refresh: an entry that no capture folder points at any more, whose name resolves to
  another object in your Library, and that you haven't written notes on, is removed — it was
  an empty duplicate of the object that now holds its captures. Anything you annotated, and
  anything nothing took over (a genuinely off-catalog target), is left alone. Only the
  Library index is touched; no captures, renders or journals are moved or deleted.
- **A mosaic no longer inflates an object's integration time.** Frames shot as a mosaic
  can't be stacked with a single-frame capture of the same object, so adding the two
  together claimed a depth no single stack had — and could push an object to **Deep Stack**
  when neither framing got there on its own. An object's integration is now its plain
  capture, with any mosaic listed beside it on the object page as tracked separately. An
  object you've *only* ever shot as a mosaic still counts that mosaic as its capture, and
  combined targets like `M81 M82` are unaffected — those frames really do contain both
  objects. **Some integration times will drop after the next refresh**; nothing on disk
  changes, and the hours are still shown, just not added together.

- **A mosaic of something off-catalog is filed under the object, not the framing.** Importing
  `Foo_mosaic` for a target M110 doesn't recognise created an object called "Foo_mosaic" — so a
  later plain capture of Foo became a *second* object, splitting one target's frames in two.
  The object is now "Foo", however you framed it.
- **Markarian's Chain can be charted and planned.** As a chain of galaxies rather than a
  single object it has no catalogued position, so it had none — which kept it off the sky
  map and out of session planning. It now carries a hand-set centre (the midpoint of the
  chain, between M84 and NGC 4477), approximate by nature but enough to point at.

### Removed
- **The bundled Siril/Seestar workflow playbooks have been removed** pending replacements
  written against citable sources. They were never actually shown anywhere in the app —
  M110 selected which ones applied to a target but never displayed them — so nothing you
  used has gone away. They were withdrawn rather than edited because they had drifted into
  being personal notes rather than a guide: they carried the author's name and location,
  referenced a developer-only document, assumed one specific observing site's conditions
  without saying so, and one of them was a dated weather forecast. Your Siril working
  folders are unaffected and still get their `next-steps.md`.

## [0.2.0-beta.8] - 2026-07-22

### Fixed
- **"Reveal in file manager" on a `.fit` now shows the `.fit`.** Because M110 can't display
  a FITS directly, gallery tiles show a generated preview of it — and Reveal, Open, and
  Export were all acting on that preview instead of the real file. Reveal opened M110's
  internal renders folder, and **Export for sharing quietly exported the small preview
  rather than re-rendering the FITS at full resolution**. All three now act on the actual
  file. (Takes effect after the next automatic refresh, i.e. your next launch.)
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

# UI critique — pre-1.0 (2026-11-17)

Two critiques ahead of the 1.0 UI pass: **(1) Apple HIG**, covering what is visible,
where it lives, and what the menus hold; **(2) aesthetics**, compared with photo and
astronomy software. The decisions from the follow-up interview are in
[`UI_ROADMAP.md` → "1.0 redesign"](../UI_ROADMAP.md); the identity mocks are in
[`ui-1.0/`](ui-1.0/).

**Method.** I rendered every rail page, the object detail pane, the List and Feed
views, and four dialogs (Preferences, About, Backup, Publish) on the real **cocoa**
platform, in both themes. The renders used the live store read-only (`_ready = False`,
with `HOME` and the settings file pointed at a temp dir). I then read the menu, context-menu and
shortcut wiring in `m110/ui/`. Screenshots are in the session scratchpad (not
committed). Severity: **P1** = would be cited as "not a Mac app" / a real usability
gap; **P2** = polish a reviewer would notice; **P3** = nice to have.

---

## Part 1 — Apple HIG

### 1.1 Where every surface lives today

| Surface | Sidebar | Menu bar | Keyboard | Only other route |
|---|---|---|---|---|
| Library (Grid/List/Feed/Map) | ✅ | View › Library | ⌘1 | view modes: segment only |
| Media | — | — | — | "Deep sky · Media" segment inside Library |
| Journal (Feed) | — | — | — | segment; page titles itself "Journal" |
| Sky map | — | — | — | segment |
| Object detail pane | — | — | — | select a tile/row |
| Overview | ✅ | View › Overview | ⌘2 | |
| All sessions log | — | — | — | **button on Overview only** |
| Planning (+ site profiles, field guides) | ✅ | View › Planning | ⌘3 | |
| Import | ✅ | View › Import, File › Import… | ⌘4, ⌘I | |
| Processing | ✅ | View › Processing | ⌘5 | |
| Devices | ✅ | View › Devices | ⌘6 | |
| Preferences | — | App menu (hoisted from Tools) | ⌘, | |
| Back up / Restore | — | Tools | — | Restore also in Backup dialog |
| Publish / share | — | File | — | |
| Assistant proposals | — | — | — | **banner only** (invisible when hidden) |
| MCP connection details | — | — | — | Preferences button only |
| Image viewer / Export | — | — | — | double-click, context menu, viewer button |
| Integration goal | — | — | — | detail-pane button |
| Pin / deprioritize / remove / set hero / mark finished | — | — | — | **context menus only** |
| Process in Siril / AstroWizard / StackingWizard / Import finished work / Reveal | — | — | — | **detail-pane buttons only** |

### 1.2 Menu bar

- **P1 · No Edit menu.** Every Mac app has one: Undo/Redo, Cut/Copy/Paste, Select
  All, **Find (⌘F)**. Text fields still copy and paste because Qt handles the keys inside
  the widget, but nothing works at the app level. ⌘F doesn't focus the Library search,
  there is no Undo for "Remove from Library" or an unpin, and macOS has nowhere to
  put Emoji & Symbols or Dictation.
- **P1 · No Window menu.** Qt doesn't add one, so the app has no Minimize (⌘M), no Zoom,
  no Enter Full Screen (⌃⌘F) and no window list. That last one matters because the image viewer is its
  own window. The main window has no **⌘W** either (the viewer does).
- **P1 · Object commands live only in context menus and pane buttons.** HIG treats
  a context menu as a *shortcut* to commands that also exist in the menu bar, never
  as their only home. About fifteen per-object verbs are invisible until you right-click.
  Proposal: an **Object** menu (Lightroom's "Photo" menu is the analogue) that
  is enabled on selection: Open/Show Detail · Set Goal… · Pin / Deprioritize ·
  Process in Siril ▸ · Send to AstroWizard… · Stack in StackingWizard… · Import
  Finished Work… · Export for Sharing… (⇧⌘E) · Reveal Working Folder in Finder (⇧⌘R) ·
  Remove from Library (⌘⌫).
- **P2 · The View menu holds only pages.** It's missing the things a View menu holds:
  *as List / Grid / Feed / Map*; Deep sky / Media; **Show/Hide Sidebar (⌃⌘S)**;
  **Show/Hide Inspector** (the detail pane, ⌥⌘I); tile Zoom In/Out (⌘+/⌘−); Enter
  Full Screen.
- **P2 · Mixed placement.**
  - *Tools* is a Windows convention. Back Up / Restore are file/data operations
    (File menu on Mac, and fine there on Windows too).
  - *Prepare working folders* in Tools contradicts the house rule "processing-prep is
    automatic — no manual Prepare button." Either drop it or rename it as a repair
    action ("Rebuild Working Folders").
  - *Check for Updates…* lives in the **app menu** on macOS (the Sparkle convention);
    `ApplicationSpecificRole` hoists it.
  - Preferences: check that the hoisted item reads **Settings…** on macOS 13+.
- **P2 · Inconsistent labels.** The menu says "Fill missing metadata…"/"Enrich online…"
  while the context menu says "Fill in missing metadata"/"Enrich online" (different
  wording, and the ellipsis comes and goes). "Publish / share…" should be "Publish…". Mac menus use title case
  ("Add Object…", "Back Up…").

### 1.3 Sidebar

- **P2 · Text-only, flat, fixed.** Mac sidebars pair a symbol with each label, group items
  under section headers, and can be resized and collapsed. This one is 130–160 px
  fixed, has no icons, and View has no Hide Sidebar.
- **P2 · Top-level collections are hidden in segments.** Media and Journal are
  peers of the Library, but they sit behind a segment and a view toggle. Photos
  and Lightroom put collections in the sidebar. A grouped sidebar would show the whole app at once:
  - **Library:** Deep Sky · Media · Journal
  - **Workflow:** Import · Processing
  - **Observing:** Planning · Devices
  - Overview, as home, sits at the top.
- **P1 (a11y) · Selected item contrast.** White on the dark accent `#5a93e6` is
  **3.1:1**, below AA for 13 px text. The same fill is used for selected segments.

### 1.4 Window chrome, toolbar, status bar

- **P1 · No toolbar; controls are stacked in the content area.** Above the Library grid sit
  four rows of chrome: scope segment and view segment, Catalog combo, Search, then the stat line. That
  is about 200 px. On a Mac the view switcher, scope and **search field** belong in a unified
  toolbar (`setUnifiedTitleAndToolBarOnMac` + `QToolBar`), and the title should name the
  current place ("Library — 65 objects").
- **P2 · The status bar permanently shows the absolute data-root path.** Mac apps rarely
  keep a status bar, the path is noise, and it leaks into every screenshot. Use the status bar only for transient
  progress, or drop it, and show the path in Settings and About.
- **P2 · The search field isn't a search field.** It has no magnifier glyph, no clear button, isn't wired
  to ⌘F, and the Journal view adds a *second* search box of its own.

### 1.5 Pages, controls, copy

- **P2 · Page headers are inconsistent.** Library and Devices have no title. Overview,
  Import and Processing use a 20 px bold title. Planning uses a small semibold "Session
  Planning" plus a description. The names drift from the sidebar: Processing vs "Processing
  Queue", Planning vs "Session Planning", Feed vs "Journal". Pick one rule. Ideally the
  window/toolbar title carries the name and content titles go away.
- **P2 · Tables.** Headers are centered (Mac: aligned with their column; numbers right-aligned). Overview and Planning
  numbers are left-aligned and proportional, so columns don't line up, while Processing uses
  right-aligned mono, which is inconsistent. Truncation loses identity: the Processing Target column shows "NG…",
  the Devices Model column "ZWO Seestar …", and the Library tile caption is *always*
  cut off ("4:16 · …"). Library List and Processing scroll horizontally at the default
  window size.
- **P2 · Planning's "#" column has gaps** (1, 2, 4, 5 … 28, 38) under "Visible
  tonight". It shows the global rank but reads as a bug. Label it "Rank" or renumber.
- **P2 · Dialogs.**
  - **Preferences** is one long scrolling sheet of explanatory paragraphs that applies on Close.
    The HIG Settings window uses toolbar tabs (General · Processing · Tools · Backup ·
    Assistant · Appearance), applies changes immediately and has no Close/OK.
  - **Backup** is about 1000 pt tall with a large empty lower half. Its primary actions are
    styled as inline hyperlinks ("Set up local backup…"), its tab selector floats mid-dialog,
    and it shows Restore… / Close / (disabled) Save. It belongs as a Settings pane plus
    File › Back Up Now.
  - **No default button is visibly marked** (accent fill, Return). Group-box titles end in colons
    ("Processing workflows you use:").
- **P2 · Empty states.** Import shows two empty tables, column headers and five disabled
  buttons before anything happens, plus a "Holding area" frame that reads "Nothing held."
  Show one empty state with one primary action (Choose Source… / a detected telescope)
  and reveal the tables when there's data.
- **P3 · Copy.** "Planning plans for this telescope." (Devices); "Integ" / "Of goal" headers;
  "Deep Stack" / "Deep" / "deep" used interchangeably.
- **P3 · Notes duplicate the title.** The journal's markdown H1 ("M81 — Bode's Galaxy") renders
  as a second, larger title inside the Notes box, directly under the pane title.

---

## Part 2 — Aesthetics

**Comparison set.** Photo: Lightroom Classic, Capture One, Apple Photos, Pixelmator
Pro / Darkroom (Mac-native polish). Astronomy: SkySafari and Stellarium (consumer
polish), AstroBin and Telescopius (web galleries and planning), and the anti-references
the roadmap already names: PixInsight, N.I.N.A., ASIStudio.

**What's working.** The photographs carry the app. A grid of real stacks is
beautiful, and the restraint (no gradients, no decoration) is the right instinct.
Status pills pair text with color. The hand-inked wordmark has real character. The bones are
good; the issues are hierarchy and voice.

### 2.1 Dark mode: why it feels "too dark"

The base isn't darker than macOS's own (`#1e1f22` ≈ macOS `#1e1e1e`). The problem is that
**the ladder is too short**:

| token | hex | L* |
|---|---|---|
| window | `#1e1f22` | 11.8 |
| surface | `#26282c` | 16.1 |
| surface_alt | `#2b2e33` | 18.8 |
| raised | `#303338` | 21.1 |
| border | `#3a3d42` | 25.7 |

Four surface levels span about 9 L\*, so everything reads as one black slab. Separation then
falls to 1 px borders, which is why the app is boxes within boxes: tables in framed sections
in framed panels. Three more things push it toward "developer tool" rather than "photo tool":

1. **Cool blue cast.** The grays carry a blue tint (`#1e1f22`, `#26282c`), the
   GitHub/VS Code look.
2. **The status colors are GitHub Primer's dark palette** (`#3fb950`, `#58a6ff`,
   `#d29922`, `#e5534b`). That is the main reason it reads as a dev tool.
3. **Inverted figure/ground.** Lightroom and Capture One use **mid-dark neutral
   panels** and put images on a separately controlled, usually darker, well. That way the
   photo is the brightest and most saturated thing on screen. Here the grid well (`surface`) is
   *lighter* than the window, so the night-sky thumbnails sit in a gray-black box.

**Direction:**
- Use neutral grays (or a whisper of warmth that matches the parchment brand).
- Raise the chrome to roughly L\* 18–24, with ≥ 5 L\* between levels.
- Give images a darker **well** (~L\* 8–10).
- Use far fewer borders. Let surface steps do the separating.

### 2.2 Typography: correct but voiceless

- One family (system UI) and effectively two weights. The scale (11/12/13/15/20) has
  steps too small to read as hierarchy: 13 vs 15 barely registers.
- **No typographic voice.** The brand is an *astronomer's notebook* (hand-inked
  wordmark, parchment icon), and nothing in the type says so. The UI and the brand look
  like two products.
- **Mono is used inconsistently.** Durations are mono in Processing and Devices and proportional
  in Overview and Planning. Mono should be reserved for genuinely technical strings (filenames,
  FITS cards, RA/Dec). Use system **tabular numerals** for every number column.

**Direction:**
- A bundled OFL **serif display face** for object and page titles (Source Serif 4,
  Newsreader, Literata or Fraunces are candidates). It evokes star atlases and observing
  handbooks: designation in a strong weight, common name in italic.
- Keep SF (system) for UI chrome.
- Tracked small-caps section labels, as Lightroom does for panel headers.
- A wider scale: 11 · 13 · 15 · 17 · 22 · 30.

### 2.3 The signature visual is missing

The tagline is *Complete the catalog*, but the Overview shows completion as a table
row ("49/110 (44.5%)"). Make **a 110-cell Messier board** the hero. Each cell is a
thumbnail when captured, tinted by Deep, in-progress or Initial status, and an empty
slot when missing; it works for any goal list. No comparator has this, and it is the
one image that sells M110 in a screenshot. Overview overall is three stacked tables with no
visualization. Progress bars, rings or sparklines would turn it into a dashboard.

### 2.4 Grid and detail

- **The grid doesn't justify.** Columns leave a ragged gap on the right (6 tiles plus
  dead space; 3 plus a large gap with the detail pane open). Lightroom, Photos and AstroBin fill the row.
- **Captions are loud and always truncated.** Two lines of text, a saturated pill on each
  of 65 tiles, and the line is cut off. Option: the designation overlaid bottom-left on a
  subtle gradient, status as a small badge, and details on hover or at larger tile sizes.
- **Detail hero.** A portrait image sits centered with wide gutters. Let it fill the pane width on a
  dark well. Show the metadata as an aligned key/value grid, not a sentence of
  `·`-separated facts.

### 2.5 Color and accent

- **Blue means two things.** The accent `#5a93e6` marks "selected" (nav, segments,
  checkboxes, slider), and `status_progress` blue marks "in progress toward goal". On the grid,
  "76% of goal" pills look like selection. Give progress its own hue, or change the accent.
- **Accent choice is still open** (UI_ROADMAP). Options: follow the macOS system accent (HIG-native),
  or a brand accent. A brass/amber ink that fits the notebook brand was tried as sepia and
  read poorly, so a more saturated amber is worth one more try.

### 2.6 Iconography

There are no icons anywhere. Buttons are text, and a few use unicode stand-ins ("⤓ Export…", "ⓘ
Info", "‹ Prev"). One consistent bundled icon set (an SF Symbols-like line set such as Lucide,
Phosphor or Tabler, as SVG recolored from tokens) in the sidebar, toolbar and image
viewer is probably the **single highest polish-per-hour change** available.

### 2.7 Domain opportunity: night mode

SkySafari, Stellarium and most capture tools offer a **red night-vision theme**. It is used
at the telescope, which is exactly when Planning and field guides are open. With the token
system, a third `Tokens` instance (plus a red tint on images) is cheap, and it is a
differentiator photo tools don't have.

### 2.8 Light mode

Light mode is clean but generic. White wells make dark astro thumbnails look like holes punched
in the page. Consider keeping image wells neutral-dark in both themes; Lightroom and
Capture One never put photos on white.

---

## Highest-leverage moves (my ranking, before the interview)

1. Re-cut the dark palette: neutral, a longer ladder, a darker image well, fewer borders, non-Primer status hues.
2. Add the Edit, Window and Object menus, and fill out View. This closes the P1 HIG gaps cheaply.
3. Add a unified toolbar (view switcher, scope, search) and drop the status-bar path.
4. Add an icon set and a grouped sidebar with Media and Journal promoted.
5. Typography: serif display face, tabular numerals, a wider scale, one page-header rule.
6. Make the Messier board the Overview hero.
7. Restructure Settings into tabs, with Backup as a pane.
8. Add a night-vision theme.

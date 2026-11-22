# M110 — UI Look & Feel Roadmap

A design-system-first plan to evolve M110's UI from "functional PySide6" to a
polished, image-forward **professional photo tool**. Authored from a 2026-06-29
interview with the user; this is the canonical UI design plan (referenced from
[`ROADMAP.md`](ROADMAP.md)). Engineering roadmap items stay in `ROADMAP.md`; this
file owns *look & feel*.

---

## Vision

> "Lightroom for smart telescopes" — and it should **feel** like a pro photo tool.

- **Reference points:** **Lightroom Classic** + **Capture One** (neutral dark-gray
  chrome, panels, list/grid, efficient density, disciplined typography). **Apple HIG**
  aware (native-feeling controls, system fonts, light+dark) but **not** reproducing
  Apple Photos' consumer softness, and **not** the over-dense/esoteric feel of astro
  tools (PixInsight/N.I.N.A./ASIStudio).
- **Image-forward:** the astrophotos are the point — heroes scale gracefully,
  thumbnails appear wherever objects do, galleries read like a contact sheet.
- **Professional, efficient, calm:** restrained accent, consistent spacing, aligned
  numbers, no decoration for its own sake.
- **Minimal main-window chrome (a core principle, 2026-07-01).** A common failing of
  astro software is a cluttered, control-dense interface. M110 pushes hard the other
  way: the **main window's** primary views (**Library · Overview · Planning · Import ·
  Processing · Devices** — the rail after the 2026-07 IA cleanup, with Planning added
  post-beta and **Devices** promoted from a Tools dialog on 2026-10-21 because users own
  several telescopes and per-object integration targets will be per device) carry as **few visible controls as possible**, presented
  **unobtrusively but legibly** — prefer one control with one clear meaning over several
  redundant ones; prefer a sensible default over a toggle nobody switches; don't let a
  control's show/hide relocate its neighbours. Complexity is allowed to grow in
  **special-purpose / editing surfaces** (the object detail pane, processing-queue
  management, dialogs, a future assistant) where the extra density earns its keep.
  *Examples of this in practice:* the Library list/grid switch is a **single** toggle
  (its "off" state is list view — no second icon); the grid's zoom slider sits in a thin
  status-strip row so toggling it can't shove other controls; a "Captured only" checkbox
  was **removed** rather than kept "just in case" (reintroduce as a preference only if a
  real need surfaces).

## Decisions (from the interview)

| Dimension | Decision |
|---|---|
| Aesthetic | Pro photo tool (Lightroom/Capture One), HIG-aware, not consumer-cute, not astro-esoteric |
| Theme | **Light + dark, follow system** + manual override |
| Priorities | **Visual polish** + **imagery presentation** |
| Scope | **Adopt a design system** (tokens + components first) |
| Tech | **Tokens module + hand-rolled QSS** — own it outright, no new theming dependency |
| Typography | **System UI font** for chrome + **bundled monospace** for technical data (FITS values, RA/Dec, filenames, integration); tabular/aligned numerals |
| Imagery | Library **list/grid toggle** (object-grid first); more **compact** object-page galleries; **responsive hero scaling** (fit well, not just bigger); upgraded **fullscreen viewer**; **thumbnails everywhere** |
| Grid scope | **Object-grid first** (one tile per object), built so a cross-object image browser can follow |
| Sequencing | **Foundation first** (tokens + theming + restyle), then imagery |
| Branding | **Shipped (Phase 4)** — hand-inked "M110" wordmark (theme-recolored), parchment app/dock icon, About dialog. *Astronomer's-notebook* aesthetic. Accent stays the neutral blue for now (a sepia accent was tried + reverted — read poorly) |

## Architecture & principles

- **Engine stays Qt-free.** All theming lives under `m110/ui/` (proposed
  `m110/ui/theme/`). No `PySide6` imports leak into engine modules.
- **Single source of truth for style = tokens.** A Python tokens module defines the
  palette + scales; a generator emits the app QSS for the active theme. Widgets stop
  hard-coding colors/sizes (today's `widgets.status_label`/colors, ad-hoc stylesheets,
  inline sizes migrate to tokens).
- **Reuse what exists:** `widgets.py` (`NumItem`, `status_label`/colors, `make_table`),
  `detail.py` (`DetailPane`), `image_viewer.py` (`ScalableImage`, `ImageViewer`), and
  the renders cache (`config.RENDERS_DIR` thumbs + `HERO_DIR` heroes, `images.json`).
  These are the seams the refresh should build on, not replace wholesale.
- **Performance:** thumbnail loading in lists/grids must be **async + cached** (never
  block the UI thread); lazy-render off-screen tiles.
- **Accessibility:** target legible contrast in **both** themes; don't encode status by
  color alone (chip text + color).
- **Testable:** keep visual logic thin and test with pytest-qt (theme applies, toggle
  switches palettes, grid model/delegate, viewer state); add golden-image coverage
  where feasible (mirrors `tests/test_render_golden.py`).

---

## Tweaking theme colors (where to edit)

**All colors live in one file: [`m110/ui/theme/tokens.py`](m110/ui/theme/tokens.py).**
Edit the hex values in the **`LIGHT`** and **`DARK`** `Tokens(...)` instances. Each field
is a *semantic role* (`window`, `surface`, `text_primary`, `text_secondary`, `accent`,
`status_deep`, `status_initial`, `selection_bg`, …) used app-wide — change one hex and
that role recolors everywhere (QSS + the status pills + muted labels), no other file to
touch. `accent` is the single brand swap-point; `SPACE`/`RADIUS`/`FONT_SIZE` (same file)
tune spacing/rounding/type scale.

- **See a change:** relaunch M110, or just toggle **Preferences → Appearance** (the theme
  re-applies live). For quick experimentation, `python -c "from m110.ui import theme; ..."`
  isn't needed — editing the hex + relaunching is enough.
- **Two palettes:** set the light value in `LIGHT` and the dark value in `DARK` (they're
  independent; mind contrast in both).
- **What maps where:** `qss.build_qss()` consumes these roles for the stylesheet;
  `widgets.StatusPillDelegate` / `theme.status_color()` read `status_deep`/`status_initial`;
  `QLabel[muted="true"]` uses `text_secondary`.

---

## Phases

### Phase 0 — Design tokens + theming foundation  *(the design system)* — **done 2026-06-29**
The de-risking foundation everything else builds on. **Shipped:** `m110/ui/theme/`
(`tokens` light+dark semantic palette + scales · `qss.build_qss` · `manager.ThemeManager`
follow-system + manual override + live re-apply · `fonts` bundled **JetBrains Mono** +
`mono_font()` · façade `install/set_mode/active_tokens/status_color/muted_color`).
Installed in `main()`; **Preferences → Appearance** (System/Light/Dark, live);
`widgets.py` status/muted colors + the ~15 inline `#8b949e` labels migrated to tokens
(`QLabel[muted="true"]`/`[caption="true"]`); journal editor uses the bundled mono. Tests:
`test_theme_{tokens,qss,manager,fonts}.py` + a catalog restyle check (299 pass).
**Decisions resolved:** accent = neutral desaturated blue token (brand swap-point);
mono = JetBrains Mono (OFL, bundled); Qt floor stays **6.6** with feature-detected
`colorSchemeChanged` + focus-in fallback for follow-system.

Original scope (as built):
- **`theme/tokens.py`** — semantic tokens with **light + dark** values: surfaces
  (window/surface/raised), text (primary/secondary/disabled), `accent` (neutral for
  now), borders/dividers, **status colors** (deep-stack / initial / none / processing
  states), focus ring; a **spacing** scale (4/8-based), **radius**, **type scale**,
  elevation. One place to later swap in a brand accent.
- **`theme/qss.py`** — generate the app-wide QSS string from tokens for a given theme
  (tables, headers, buttons, inputs, search fields, menus, nav rail, progress dialogs,
  scrollbars, tooltips, chips).
- **`theme/manager.py`** — apply QSS + `QPalette`; **detect system appearance**
  (`QStyleHints.colorScheme()`, Qt ≥ 6.5; we target PySide6 ≥ 6.6) and follow it, with
  a **manual override** (System / Light / Dark) persisted in settings; **live re-apply**
  on change (no restart). Add the toggle to `preferences.py`.
- **Typography** — set the application UI font to the system UI font; bundle one
  monospace (license-clean, e.g. JetBrains Mono / IBM Plex Mono) as package-data + a
  helper to apply it to numeric/code/data cells (RA/Dec, integration, filenames). Wire
  tabular numerals.
- **Migrate** `widgets.status_label`/colors to tokens so chips are theme-aware.

*Exit:* the existing app looks coherent in light **and** dark, toggling live, with no
structural changes yet.

### Phase 1 — Restyle existing surfaces  *(apply the system)* — **done 2026-06-30**
Apply tokens across the current pages; no new views.
- **Landed (2026-06-30):** **status pill chips** (`widgets.StatusPillDelegate` — tinted
  rounded chip from the theme `status_*` color, sort-safe) on the Library Status column;
  **alternating row colors** on all shared tables; **uniform page padding** (token-driven
  margins on the page stack); removed the redundant **Import toolbar button** (nav rail +
  `Ctrl+I` remain); **tabular numerals** — right-aligned bundled-mono numeric columns
  (`widgets.make_numeric`) on the catalog / sessions / processing tables; **nav-rail
  polish** (object-named `#navRail`: accent-rounded selected item, hover, right divider,
  padding). Headings already use theme-aware `<h2>`/`<h3>` rich text (inherit palette).
- **Also landed (final slice):** `DetailPane` refinement — the captured status renders
  as a tinted **pill** matching the table (`detail._status_pill`), a muted stats line,
  and consistent section spacing/margins; **dialog spacing** pass (token margins/spacing
  on Preferences / Publish / Add-object) + dropped the redundant "Preferences saved"
  modal (BUGS #59 — only a restart notice when the data folder changes). Header
  sort-indicator already renders natively (the ▲/▼ caret), so no extra work.
- **Responsive hero**: `ScalableImage` already scales aspect-correct + non-upscaling +
  height-capped — revisit only if heroes need more presence per real use.

### Phase 2 — Imagery: thumbnails everywhere + viewer upgrade  *(core done 2026-07-01; reference-images item below still open)*
- **Thumbnails in rows** *(done 2026-07-01)* — Library / Sessions / Processing (and
  their search-filtered views) show a small hero thumbnail on the Object row, backed by
  the existing renders cache (`objects.hero_path`), decoded **async** off the UI thread
  and memo-cached by (path, size, mtime) so re-sorts/rebuilds don't redecode. Landed as
  `widgets.ThumbnailLoader` (QThreadPool + QImageReader decode) + `widgets.RowThumbnails`
  (per-page row↔slug↔icon-item bookkeeping, reset on every table rebuild). The decode
  crops a **center square** (side = half the frame width, clamped to frame height) before
  scaling down — smart-scope frames put the subject dead-center, and a full-frame squash
  read as noise at icon size (user feedback 2026-07-01); the crop reads better but is still
  size-limited at ~20px row icons — **acceptable for rows, revisit at Phase 3's larger grid
  tile size**, which reuses this same loader/crop.
- **Fullscreen viewer upgrade** *(done 2026-07-01)* — `image_viewer.ZoomableImage`
  (a `QScrollArea`-based replacement for the viewer's old fit-only `ScalableImage`)
  adds continuous **zoom** (Fit / 100% / ±, 0.05–8×) and **click-drag pan** once
  content exceeds the viewport (event-filter on the viewport, the standard Qt
  pattern). `ImageViewer` gained a zoom toolbar (Fit/100%/−/+/live %), a toggleable
  themed **metadata overlay** (Source/Date/Size always; Integration when the image
  matches a processing-queue `latest_processed` stack; Filter only when every
  session for the object agrees on one — never guessed across a mixed-filter
  object), and keyboard polish (Home/End jump, `+`/`-`/`0`/`1`/`I`). Item shape is
  backward compatible (`(name, path)` tuples still work, e.g. the Media page —
  the Info toggle just doesn't appear without `meta`). "Smoother transitions" was
  deliberately scoped to **zoom always resets to Fit on navigate** (no animated
  crossfade — low payoff for the effort here) so Prev/Next never lands on an
  inherited zoomed crop of the next image. Metadata content lives in
  `detail._gallery_meta()` (keeps `image_viewer.py` app-data-agnostic); sourced
  from `derived.totals_by_slug()[slug]["filters"]` and the `processing` queue's
  `stack_meta` — no new derived-data fields needed.
- **Compact object-page gallery** *(done 2026-07-01)* — the `DetailPane` gallery
  (`detail.show_object()`) drops from 160px letterboxed icons to a **120px
  center-cropped-square** contact sheet (`detail._square_icon()` — same crop
  instinct as row thumbnails, but `side = min(w, h)` rather than the row
  icons' aggressive half-width crop, since a ~120px tile has room to keep more
  of the frame). `setGridSize()` + `setUniformItemSizes(True)` fix the
  ragged-row alignment a long filename used to cause; filenames now elide
  (`Qt.ElideMiddle`) to one line with the full name as a tooltip — keeps
  CLAUDE.md's "show real filenames" without letting them break the grid.
- **Reference images for uncaptured objects** *(decided 2026-06-30)* — populate
  thumbnails/heroes for objects the user hasn't shot, from **CDS hips2fits** survey
  cutouts by RA/Dec (SDSS/DSS2, cached offline) + curated **ESA/Hubble/ESO (CC BY)**
  heroes, **clearly badged as survey/reference (not a capture)**, with per-image
  attribution rendered on the object page. New reference-image tier + attribution
  storage — see **[`DATA_MODEL.md`](DATA_MODEL.md)** "Reference images for uncaptured
  objects". (Also lets the user build an in-app image library from their own collection
  — export 8-bit sRGB JPEG ~1600px; keep 16-bit masters in their archive.)

### Phase 3 — Library list/grid toggle  *(object-grid)* — **done 2026-07-01**
- A **grid view** of the Library: one **tile per object** (hero thumbnail + id/name +
  status chip + integration), **zoomable** tile size, toggling with the current table;
  shares the existing **search / catalog filter / captured-only** state and routes to
  the same `DetailPane`.
- Built as a **reusable image-grid component**, `m110/ui/image_grid.py` — `TileItem`
  (plain dataclass) + `TileModel(QAbstractListModel)` + `TileDelegate
  (QStyledItemDelegate)`, with zero imports from `m110.catalog`/`objects`/`derived` so
  a future cross-object image browser (Phase 4+) can reuse it for a different dataset.
  `CatalogPage` (`pages/catalog.py`) adapts Library rows into `TileItem`s and hosts both
  views in a `QStackedWidget`, toggled by two `QToolButton`s + a `QSlider` (80–220px,
  persisted via `config.get_setting`/`save_setting`, same precedent as the theme-mode
  setting). Filtering narrows the model's data (`QListView` has no `setRowHidden`
  equivalent — a proxy model would be premature for a few-hundred-row list), with an
  explicit selection-preserve/restore step across each reset so typing in the search
  box doesn't silently drop the grid's selection. Thumbnails reuse `widgets.
  ThumbnailLoader` (extended with a `crop="square"` option — tiles are big enough to
  keep more of the frame than the row-icon crop) and the status chip reuses a
  `paint_status_chip()` helper extracted from `StatusPillDelegate`.

### Phase 4 — Branding pass  *(done 2026-07-03)*
- **Logo:** the uploaded hand-inked `m110-logo.svg` "M110" wordmark, moved into the
  package (`m110/ui/theme/brand/`). A new `theme/brand.py` **recolors the ink to the
  active theme's text color** at render time (`logo_pixmap` — SVG fill-swap + tight crop
  via `QSvgRenderer.boundsOnElement`) so it reads in both light and dark; placed at the
  **top of the nav rail** (re-renders on theme change).
- **App/dock icon:** `brand.app_icon()` composes the ink on a **fixed parchment tile**
  (rounded, aged-paper gradient) at the standard sizes; set as the window/dock icon.
  `tools/gen_app_icon.py` exports a PNG master for future Developer-ID packaging.
- **About dialog:** Help → About M110 (`about_dialog.py`) — themed logo, tagline
  ("Complete the catalog."), version, license.
- **Accent:** a warm ink/sepia accent was tried to match the logo but **reverted** — it
  read poorly; the accent stays the **neutral blue** for now (still a one-token swap in
  `tokens.py` if revisited).

### Phase 5 — Navigation IA cleanup  *(done 2026-07; pre-public-launch)*
Decided once, before launch, to avoid re-teaching users a moved layout. The rail went
from **8 panes → 4**: **Library · Overview · Import · Processing**.
- **Library is home** — lands there by default, in **grid** mode; a fresh empty store
  lands on Overview (welcome/CTA).
- **Overview** = the former **Summary + Goals** merged into one pane of **collapsible
  sections** (`widgets.CollapsibleSection`, the macOS disclosure pattern; open/closed
  state persists per user). Goal *progress* is the hero; goal *setup* is demoted to a
  collapsed "Manage goals" section.
- **Media** → a **Deep sky · Media segment** at the top of the Library (embeds `MediaPage`).
- **Journal** → a third **List · Grid · Feed** view of the Library (embeds `JournalPage`).
- **Sessions** → a "View all sessions…" dialog on Overview (per-object sessions already
  live in the object detail pane). The Library stat strip gained total integration hours.

### Phase 6 — Shell chrome pass  *(done 2026-08-12)*
Four small corrections to the shell itself, once the pages had settled.
- **The brand mark moved to the foot of the nav column** (Phase 4 put it at the *top*
  of the rail, where it competed with the nav items for the eye's first landing spot).
  It's now a quiet anchor just above the status bar — and it earns its place by being
  **clickable → About**, which puts version + update status one click from anywhere.
  The **surface and divider moved from `#navRail` to `#navColumn`** so the column reads
  as one panel: a rail-owned border stops where the list stops, which was invisible with
  the mark above it and obvious with the mark below.
- **About gained a live update line** — it re-checks on every appearance (`record=False`,
  so it never eats the daily launch throttle) and says "You're up to date" or offers the
  newer version. The version line provoked the question; the dialog now answers it.
- **The status bar dropped its `n/n captured` prefix** — the Library's own stat row
  already shows that tally *in context*; in permanent chrome it was noise competing with
  the data-root path and the operation messages that actually change.
- **Menus reorganised to File · View · Library · Tools · Help.** The old Library+Help
  pair only read acceptably on macOS, where the `MenuRole`s hoist About/Preferences into
  the app menu; on Windows and Linux it filed Preferences under "Library" and offered
  **no way to quit at all**. One structure covers all three — the roles still do the
  hoisting, so there's no `sys.platform` branch to drift. A **View** menu (Ctrl+1–6)
  came with it, giving the rail keyboard access it never had.

### 1.0 redesign — decisions (interview 2026-11-17)

Before the project leaves beta, a full look-and-feel pass. Inputs:
[`docs-archive/UI_CRITIQUE_2026-11.md`](docs-archive/UI_CRITIQUE_2026-11.md) (HIG and
aesthetic critiques, measured on cocoa renders) and the identity mocks in
[`docs-archive/ui-1.0/`](docs-archive/ui-1.0/) (**A** was chosen). These decisions
**supersede** the Typography, Branding/accent and Density rows above.

| Dimension | Decision |
|---|---|
| Identity | **A · notebook-tinged pro.** Lightroom/Capture One structure with the astronomer's-notebook brand layered on. |
| Dark palette | **Warm graphite, mid-gray panels, a darker image well.** A longer luminance ladder (≥ 5 L\* between levels), far fewer 1 px borders, no GitHub-Primer hues. Images are the brightest thing on screen. |
| Light palette | **Warm paper chrome**, matching the parchment icon. Grids, heroes and the viewer **keep a dark image well**. |
| Night vision | **Third theme, ships in 1.0:** red on black with dimmed images. Toggled from View and Settings. |
| Accent | **Brass/ink amber** (≈ `#d9a648` on dark). Text on the accent must meet AA (today's white-on-blue is 3.1:1). |
| Status hues + names | **Deep** (sage) · **n%** (slate; no longer collides with the accent) · **Initial** (terracotta). The same three words everywhere, with "Deep" explained once in tooltips/help. |
| Typography | **Newsreader** (OFL, bundled) for object names, page/inspector titles and notes, with lining numerals forced for designations. **System font** for chrome. Tracked small-caps section labels. Tabular numerals in every number column. JetBrains Mono only for genuinely technical strings. Wider scale: 11 · 13 · 15 · 17 · 22 · 30. |
| Icons | **Lucide** (ISC, bundled SVG, recolored from tokens) in the sidebar, toolbar, buttons and viewer. Replaces unicode stand-ins. |
| Platform | **Mac-first, others adapt.** HIG structure on every OS, with platform-correct labels via `MenuRole`s. |
| Sidebar | **Grouped, with icons and live counts.** Overview · *Library:* Deep Sky, Media, Journal · *Workflow:* Import, Processing · *Observing:* Planning, Devices. Media and Journal leave the Library segments. Resizable and collapsible (View › Hide Sidebar). |
| Landing | **Overview**, with the catalog board. |
| Overview | Hero = the **"Complete the catalog" board**: one cell per goal-list object (110 for Messier) showing a thumbnail when captured, tinted by status, empty when missing. The tables underneath become compact progress bars and lists. |
| Toolbar | **Unified toolbar.** Place title + subtitle (e.g. "Deep Sky · 65 objects · 316.8 h"), view switcher, catalog picker and a real search field (⌘F). Replaces the stacked control rows. |
| Status bar | **Kept, transient only:** empty except during sync, backup and import. The data-root path moves to Settings › General and About. |
| Menus | **Edit** (Undo/Redo with real Undo for Remove from Library and pin changes, Copy, Select All, Find ⌘F) · **Window** (Minimize, Zoom, Full Screen, window list) · **Object** (every per-object verb, enabled on selection) · **View** gains view modes, Hide Sidebar and Hide Inspector · Back Up/Restore move to **File** · the **Tools menu is dropped**. Context menus become shortcuts to menu commands, never their only home. Title-case labels and consistent ellipses. |
| Settings | A **Mac Settings window**: toolbar tabs General · Processing · Tools · Backup · Assistant · Appearance. Changes apply instantly and there is no Close button. **The Backup dialog becomes the Backup tab**, plus File › Back Up Now. Prose shrinks to one line plus help text. |
| Grid tiles | **Overlay captions:** designation bottom-left (serif) and status dot + label bottom-right on a gradient. **Justified** grid, never truncated. Details on hover and in the inspector. |
| Density | **Compact** rows (~24–28 px, vs ~45 today) with no toggle. |
| Delivery | **Phased betas**, below. |

#### Phase 7 — Foundation  *(first beta)* — ✅ landed 2026-11-17 (`claude/ui-foundation-a5685c`)
- ✅ Re-cut `tokens.py`: warm dark, warm-paper light, night-vision red; an image-well role; AA on-accent text; new status hues. `tests/test_theme_contrast.py` checks AA + the ladder numerically for all three palettes. *Change from the plan, at the user's review:* the **light** theme's well is a medium warm gray (`#5c5852`, L\* 38 — the lightest that keeps light captions AA), not near-black, which read as a hole in the paper.
- ✅ Bundle Newsreader and Lucide (`NOTICE`; package-data globs, no spec change needed — **validated in a real PyInstaller build**: fonts + SVGs collected and rendering in the frozen app); type scale; tabular numerals.
- ✅ Menus: Edit/Window/Object/View; File takes Back Up/Restore; drop Tools; Undo stack.
- ✅ Toolbar with search (⌘F) — as a header bar in an expanded title-bar band, not `QToolBar` (see the resolved decision below); status bar transient-only.
- ✅ Grouped sidebar (icons, counts, collapsible); Media/Journal promoted; Overview lands.
- ✅ Compact density; one page-header rule; status names everywhere.

Left for Phase 8 (noticed while doing 7) — all three closed in Phase 8 · A: the traffic
lights sat at the title bar's own height, ~10 px above the header bar's centre line
(moving them needs AppKit, not Qt); table number columns were right-aligned but their
headers weren't; the Overview could briefly show the old tables under a modal that
opens while a sync rebuilds it.

#### Phase 8 — Pages  *(follow-up betas, before 1.0)*
Shipped as six PRs, in order: **A** tables + Phase 7 carry-overs · **B** grid tiles +
inspector · **C** Overview board · **D** Import empty state · **E** Settings window ·
**F** night vision + 1.0 exit audit. Every critique **P1** already closed in Phase 7,
so Phase 8 closes P2s; F re-audits P1s and AA. The only goldens are the engine render
goldens (thumbnail/hero), which Phase 8 doesn't touch; pages are checked by structural
tests and cocoa before/after screenshots instead of UI pixel goldens (offscreen Fusion
can't validate macOS painting and renders differently per machine).

- ✅ **A · Tables + carry-overs** (`feature/ui-p8-tables`). Every header aligns with
  its column (`widgets.AlignedHeader`, installed by `compact_table`, reads the cells'
  alignment); number cells right-aligned + tabular on every page; right-aligned
  columns never stretch as the last section; identity columns size to contents
  (`keep_identity_column`) and row thumbnails reserve their width up front, so no
  "NG…"; Devices list drops its Model column; Planning "#" → **Rank**. Carry-overs:
  **traffic lights centred** — feasible after all, via an empty unified `NSToolbar`
  (pyobjc, `m110/ui/macos_chrome.py`), so AppKit lays out a 52 pt band and centres the
  buttons itself; **stale Overview tables** under a modal fixed (`widgets.clear_layout`
  hides before `deleteLater`; post-sync modals `defer`red).
- ✅ **B · Grid tiles + inspector** (`feature/ui-p8-grid-inspector`). Tiles are the
  image (center-cropped, rounded) with the title bottom-left on a well-coloured scrim
  and a status dot + label bottom-right; subtitle → tooltip; the label drops before
  the title elides; selection is a brass outline (`image_grid.TileDelegate`, shared
  by Deep Sky and Media — Media in the system font, middle-elided). **Justified**:
  `image_grid.JustifiedGridView` fits `width // (target + gap)` columns and widens the
  cells to fill the row, against Qt's own wrap bounds (viewport − reserved scrollbar);
  thumbnails decode at the tile's device-pixel size. **Inspector** in mock A's order:
  hero `fit="cover"` edge to edge · serif title + facts · Integration card (total,
  status-hued bar, "Deep · goal 4 h on S50") · DETAILS key/value grid (capture facts,
  then the old "Object details") · PROCESSING (Process in Siril = accent) · Notes
  without the leading H1 (`objects.strip_title_heading`; also the Journal feed) ·
  gallery · goals · Processing status · Sessions. Lucide `x` close button.
- ✅ **C · Overview catalog board** (`feature/ui-p8-overview-board`). Engine
  `goals.board(gid, by_slug)` → every member in catalog order as `{slug, label,
  state: missing|initial|progress|deep, progress}`, scope-aware (agrees with
  `build_goals`); `board_counts`. `m110/ui/catalog_board.py`: `CatalogBoard` (one
  painted widget, `heightForWidth`, justified cells; hero thumbnails, a status-hued
  foot bar filling to the goal, empty well slots; hover tooltip; click → deferred
  `object_activated`), `GoalBar` (deep + captured segments), `StatusBarDelegate`
  (mini bar + label). The Overview leads with the board (section titled with the
  goal; "11 / 110 captured · 1 deep · 10%", legend, a goal picker when >1 active,
  saved as `overview_board_goal`); Goals = bar rows; the integration table's Status
  is a mini bar. An empty store shows the board too.
- ✅ **E · Settings window** (`feature/ui-p8-settings`). `preferences.SettingsWindow`:
  a non-modal, single-instance top-level (`MainWindow._show_settings(pane)`), a pane
  bar of icon-over-label buttons (General · Processing · Tools · Backup · Assistant ·
  Appearance; Lucide, `#settingsBar`/`#settingsTab` QSS), title = pane, fixed 600 pt
  wide and fitted to each pane's height (capped at 85% of the screen, then it
  scrolls), last pane remembered (`settings_pane`). Instant apply everywhere, no
  OK/Save/Close (⌘W = Close Window, now an application shortcut). Prose → one line +
  caption per group. Data folder: read-only path + *Change…*, saved at once with an
  inline restart note. **Backup folded in:** `backup_dialog` → `backup_pane.BackupPane`
  (summary without links · Local drive | Cloud segment · Restore… / Back Up Now);
  every slot field persists on commit (`_SlotPanel._commit`), a destination only
  when valid. File › **Back Up Now** queues every configured slot through the
  background backup queue (none configured → Settings › Backup); File › Back Up… is
  gone. "Preferences → …" copy → "Settings › …" app-wide.
- ✅ **D · Import empty state** (`feature/ui-p8-import-empty`). `ImportPage` is a
  `QStackedWidget`: a start page (glyph, serif "Import captures", one line, **one
  primary action** — *Import from Seestar — <volume>* when mounted, else *Choose
  Folder…*; *Choose Another Folder…* beside a device; up to three recent places
  as quiet `link` buttons) and the scan page (path + *Change Source…*, the
  preview, the action row with Import as the default). A scan with no rows, a
  cancel, a failure or an import that empties the source returns to the start
  page with a note. The holding area is shown only while something is held. The
  Source combo + Browse… are gone (the start page is the picker).
- Tables: aligned headers, right-aligned tabular numbers, no identity-losing truncation; Planning "#" → Rank.
- Night-vision theme wired to View and Settings.

**1.0 exit:** every P1 in the critique closed, AA contrast in all three themes, goldens refreshed.

### Phase 4+ — Later  *(deferred)*
- **Cross-object image browser:** a Lightroom-catalog-style view of every render/stack
  across the whole collection (not grouped by object) — a bigger feature + data work;
  the Phase 3 grid component is its foundation.

---

## Open decisions (resolve as phases start)

- ~~**Accent color**~~ — *resolved 2026-11-17:* brass/ink amber (1.0 redesign above).
  The Phase 4 sepia read poorly because it was desaturated, so tune for saturation and AA.
- ~~**Bundled mono typeface**~~ — JetBrains Mono shipped (Phase 0).
- ~~**Density default**~~ — *resolved 2026-11-17:* compact, no toggle.
- ~~**Unified toolbar fidelity in Qt**~~ — *resolved 2026-11-17 by prototype:*
  `setUnifiedTitleAndToolBarOnMac` + `QToolBar` in Qt 6 draws the toolbar *below* a
  separate native title strip (light when the app is dark), and every embedded
  widget paints its own background — two bars, not one. Chosen instead:
  `Qt.ExpandedClientAreaHint` (+ `NoTitleBarBackgroundHint`, Qt ≥ 6.9, macOS only)
  with a full-height sidebar under the traffic lights and our own header bar in the
  title row (`m110/ui/toolbar.py`), as in Finder/Photos. Off macOS the platform title
  bar stays and the header bar is the first row.
- ~~**Undo scope**~~ — *resolved for Phase 7:* Remove from Library and pin/deprioritize
  overrides (every route). Candidates for later: Include in Publishing, Set as Hero,
  Mark as Finished/Working, integration goals.
- **Qt floor:** confirm `QStyleHints.colorScheme` behavior on the PySide6 6.6 baseline
  (and whether to require 6.8 for `setColorScheme` to *force* a theme cleanly).

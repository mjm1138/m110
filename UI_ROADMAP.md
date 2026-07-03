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
  way: the **main window's** primary views (Summary · Goals · Library · Processing ·
  Sessions · Journal · Media) carry as **few visible controls as possible**, presented
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
| Branding | **Shipped (Phase 4)** — hand-inked "M110" wordmark (theme-recolored), parchment app/dock icon, warm-ink/sepia accent, About dialog. *Astronomer's-notebook* aesthetic |

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
- **Accent:** swapped the single accent token from neutral blue to **warm ink/sepia**
  (light `#8a5a2b`, dark `#c69a6b`) — the notebook aesthetic; affects selection/focus/
  links app-wide via `qss.build_qss`.
- **About dialog:** Help → About M110 (`about_dialog.py`) — themed logo, tagline
  ("Complete the catalog."), version, license.

### Phase 4+ — Later  *(deferred)*
- **Cross-object image browser:** a Lightroom-catalog-style view of every render/stack
  across the whole collection (not grouped by object) — a bigger feature + data work;
  the Phase 3 grid component is its foundation.

---

## Open decisions (resolve as phases start)

- ~~**Accent color**~~ *(resolved — Phase 4)*: shipped a **warm ink/sepia** brand accent
  (light `#8a5a2b`, dark `#c69a6b`) to match the astronomer's-notebook logo, superseding
  the neutral-blue-vs-system-accent question.
- **Bundled mono typeface** + its license (JetBrains Mono / IBM Plex Mono / Iosevka).
- **Density default:** comfortable vs. compact rows (and whether to expose a density
  toggle) — Capture One/Lightroom lean compact.
- **Qt floor:** confirm `QStyleHints.colorScheme` behavior on the PySide6 6.6 baseline
  (and whether to require 6.8 for `setColorScheme` to *force* a theme cleanly).

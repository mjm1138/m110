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
| Branding | **Neutral now, brand later** (restrained neutral/system accent; logo + app icon deferred) |

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

## Phases

### Phase 0 — Design tokens + theming foundation  *(the design system)*
The de-risking foundation everything else builds on.
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

### Phase 1 — Restyle existing surfaces  *(apply the system)*
Apply tokens across the current pages; no new views.
- Nav rail, page headers/section headers, the shared tables
  (row height, alternating rows, header treatment, sortable affordance, **status as
  pill chips**, right-aligned tabular numbers), `DetailPane` header/meta block,
  buttons/inputs/search, dialogs (Ingest/Import/Publish), menus, status bar.
- **Responsive hero**: tune `ScalableImage`/detail layout so heroes fill their pane
  gracefully (aspect-correct letterboxing, sensible max sizes), per "better scaling,
  not just larger."
- Consistent spacing/padding/margins pass throughout.

### Phase 2 — Imagery: thumbnails everywhere + viewer upgrade
- **Thumbnails in rows** — Library / Sessions / Processing / search results get a small
  hero/representative thumbnail (a `QStyledItemDelegate` or icon column) backed by the
  renders cache, loaded **async**. Objects become visually identifiable at a glance.
- **Fullscreen viewer upgrade** (`image_viewer.py`) — zoom/pan, **fit / 100%**, a
  **metadata overlay** (filter, integration, date, filename from sessions/derived),
  keyboard-nav polish, smoother transitions.
- **Compact object-page gallery** — denser, better-aligned contact-sheet grid in the
  detail pane.

### Phase 3 — Library list/grid toggle  *(object-grid)*
- A **grid view** of the Library: one **tile per object** (hero thumbnail + id/name +
  status chip + integration), **zoomable** tile size, toggling with the current table;
  shares the existing **search / catalog filter / captured-only** state and routes to
  the same `DetailPane`.
- Build it as a **reusable image-grid component** (model + delegate + zoom) so a future
  cross-object image browser can reuse it.

### Phase 4+ — Later  *(deferred)*
- **Branding pass:** signature accent, logo, app/dock icon, naming/typography
  treatment (swap the neutral accent token).
- **Cross-object image browser:** a Lightroom-catalog-style view of every render/stack
  across the whole collection (not grouped by object) — a bigger feature + data work;
  the Phase 3 grid component is its foundation.

---

## Open decisions (resolve as phases start)

- **Accent color** for the neutral phase: a restrained desaturated blue token vs.
  **following the macOS system accent** — pick in Phase 0.
- **Bundled mono typeface** + its license (JetBrains Mono / IBM Plex Mono / Iosevka).
- **Density default:** comfortable vs. compact rows (and whether to expose a density
  toggle) — Capture One/Lightroom lean compact.
- **Qt floor:** confirm `QStyleHints.colorScheme` behavior on the PySide6 6.6 baseline
  (and whether to require 6.8 for `setColorScheme` to *force* a theme cleanly).

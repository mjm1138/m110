# M110 — Roadmap

Canonical roadmap for M110: the north star, the foundational decisions, what has
shipped, and what remains. **Shipped work is summarized in the status table and
archived in [`DONE.md`](DONE.md)** (how and why each piece landed — item numbers
there match their original slot here); this file carries detail only for **open**
work. Open bugs / smaller improvements live in [`BUGS.md`](BUGS.md).

**North star:** "Lightroom for smart telescopes" — one native-feeling app to
catalog, track, ingest, and process-prep a smart-telescope deep-sky collection.

---

## Status at a glance

| # | Milestone | Status | Detail |
|---|---|---|---|
| — | **MVP v0.1 — "the Library"** (catalog, ingest, rendering, processing-prep, two-axis store) | ✅ shipped | [`DONE.md`](DONE.md) |
| 0 | **Navigation IA** — 5-pane rail (Library · Overview · Planning · Import · Processing) | ✅ shipped | [`DONE.md`](DONE.md), [`UI_ROADMAP.md`](UI_ROADMAP.md) |
| — | **UI design system** — tokens, light/dark theming, restyled surfaces, branding | ✅ shipped | [`DONE.md`](DONE.md), [`UI_ROADMAP.md`](UI_ROADMAP.md) |
| 1 | **Session planning** — site profiles + light-dome glow, deterministic prioritizer, night planner + sequencer, field guides | ✅ shipped *(follow-up refinements open [↓](#1--session-planning-follow-ups-non-blocking-refinements))* | [`DONE.md`](DONE.md) Checkpoints A/B + tuning arc; [`docs-archive/PLANNING_ROADMAP.md`](docs-archive/PLANNING_ROADMAP.md) |
| 5 | **Library, catalogs & goals** — multi-list tracking, 6 bundled catalogs, custom goals | ✅ shipped *(catalog growth open [↓](#5--catalog-growth))* | [`DONE.md`](DONE.md) |
| 6 | **Import** — any-directory recursive scan, header classification, holding area, Dwarf 3 | ✅ 6a–6c + Dwarf 3 shipped *(6d open [↓](#6d--multi-device-device-under-target--dwarf-remainders))* | [`DONE.md`](DONE.md) |
| 8 | **Publishing** — selective static-site export + publisher registry + GitHub Pages deploy | ✅ 8a + GitHub Pages shipped *(more targets open [↓](#8--publishing-remaining-targets))* | [`DONE.md`](DONE.md) |
| 10 | **Library backup** — hardlinked snapshots, verify, selective restore, auto-backup | ✅ shipped | [`DONE.md`](DONE.md) |
| 7 | **Processing & curation UX** | 🔶 #17 hinting + curation gallery shipped; #18/#19 open [↓](#7--processing--curation-ux-remainder) | [`DONE.md`](DONE.md), [`BUGS.md`](BUGS.md) |
| 4 | **In-app assistant** (bring-your-own LLM) — MCP server over a read-only tool registry | ✅ M0 shipped *(M1 in-app transport + safe-writes open [↓](#4--in-app-assistant-bring-your-own-llm--m0-shipped))* | [`DONE.md`](DONE.md) |
| 2 | **Plan-file generation** (SSC / NINA device schedules) | ⬜ open | [↓](#2--plan-file-generation-device-schedules) |
| 11 | **Lights Table** (bulk sub inspection/culling) | ⬜ open | [↓](#11--lights-table) |
| 12 | **Sky map** (uranometria integration — Library Map view + publish page) | ⬜ open — **upstream dependency landed** ([uranometria 0.11.0](https://github.com/devonjones/uranometria/pull/22)); M110 side next | [↓](#12--sky-map-uranometria-integration) |
| 13 | **Image annotation** (plate-solved object overlays; needs ASTAP) | ⬜ open — scoped, agreed with upstream ([#98](https://github.com/mjm1138/m110/issues/98)) | [↓](#13--image-annotation-plate-solved-object-overlays) |
| 9 | **Import triage toolkit** (header inspector, plate-solving) | ⬜ deferred | [↓](#9--full-import-triage-toolkit-deferred) |
| 3 | **Equipment monitor** | 💤 deprioritized (vision revised) | [↓](#3--equipment-monitor-deprioritized) |

---

## Foundational decisions

- **Distribution:** open-source, **Developer-ID direct distribution** (notarized
  `.dmg` / Homebrew cask), **not** the Mac App Store. The sandbox can't
  orchestrate the workflow, and the audience is open-source-native.
- **Tech:** **PySide6**, one cross-platform codebase, over a **headless Python
  engine** imported in-process (no API server for the MVP). A native SwiftUI Mac
  wrapper is a *deferred* option the engine boundary keeps open (it would
  reintroduce a FastAPI layer for a separate-process client).
- **Processing model:** **prepare-and-guide, not control.** The app arranges
  files into Siril's expected layout and emits Siril-ready configs + guidance;
  it does **not** drive Siril/StarNet directly (avoids the maintenance tax of
  wrapping volatile CLIs).
- **Data:** the app **owns its own data store** (default `~/Documents/M110`),
  decoupled from any other project; it seeds a starter catalog and generates its
  own derived data and image renders. The data model is documented and canonical
  in **[`DATA_MODEL.md`](DATA_MODEL.md)**.

> **UI look & feel** is planned separately in **[`UI_ROADMAP.md`](UI_ROADMAP.md)** —
> it cross-cuts the milestones below.

---

## Remaining milestones

In build-priority order. Numbers are each item's **original slot** (stable across
this file, [`DONE.md`](DONE.md), and [`BUGS.md`](BUGS.md)).

### 4 — In-app assistant (bring-your-own LLM) — *M0 shipped*

Put the LLM value proven out in this project — **session planning, image
analysis, workflow coaching** — over the user's own data. This is **"Checkpoint C"
of the session-planning arc**: it layers on the deterministic prioritizer +
planner. The assistant *proposes* toggles / weights / plans and *explains* the
ranking; the engine still computes, and never yields authorship of the priority
list.

**Why M110 is unusually well-positioned.** The three things that make an LLM
genuinely useful here, the app already holds in structured form:
- **Context** — catalog, priorities, capture status, per-object journals, and
  the site / equipment / obstruction profile.
- **Tools** — the engine's real computations (twilight / moon / transit-altitude
  / obstruction; derived rollups; image access).
- **Knowledge** — procedures for using the above well. Shipped as skills; the
  *workflow playbooks* half (drizzle / PSF / colour) is the gap — the bundled
  set was withdrawn and needs re-authoring before the coaching leg can ship
  (see **Open**, below).

So "skilling" the model is mostly wiring: **data → context, engine functions →
tools, docs → reference.**

#### The phasing was inverted (2026-07, with the user)

The original plan was A0 in-app chat → … → A4 *(optional)* MCP server. That
front-loads the **least** agent-agnostic work: credentials, provider adapters,
streaming, and a chat pane all had to land before a single grounded answer was
possible. Building the MCP server **first** inverts it — MCP *is* the provider
abstraction, so agent-agnosticism costs nothing, and the user gets value from
the client they already have. Revised phasing:

- **M0 — tool registry + skills + stdio MCP server. ✅ shipped.**
- **M1 — in-app HTTP transport over the same registry, plus a confirm-gated
  safe-write allowlist** (journal append, pins, save field guide, save
  strategy/weights). The proposal envelope is already designed as this seam.
- **M2 — *(optional)* in-app chat**: provider adapters, key handling in the OS
  keychain, cost controls, local models. Only if BYO-client proves insufficient;
  the MCP topology may make it permanently unnecessary.

#### Open

- **M1** — the in-app transport and the safe-write allowlist.
- **Processing coach**, deferred: the bundled guidance corpus was withdrawn (see
  [`BUGS.md`](BUGS.md) #45) and replacements need authoring against citable
  sources before the *coaching* leg can ship.
- Cost controls and a model picker belong to whichever client the user brings —
  revisit only if M2 happens.


### 2 — Plan-file generation (device schedules)

Emit **machine** plan files from the night plan the sequencer already computes
(`planning.plan_night` / `sequence_plan` — the human-readable half, the field
guide, shipped with Checkpoint B): **SSC schedule JSON** (port the existing
Astronomy generator), **NINA Advanced Sequences** (schema capture pending),
possibly INDI/Ekos. Validate against a real device before shipping.

### 1 — Session-planning follow-ups (non-blocking refinements)

The arc is release-ready (see the tuning arc in [`DONE.md`](DONE.md)); these are
the noted refinements, none blocking:
- **Two-tier tuning — session-time controls + night presets.** Live,
  non-destructive re-rank knobs on the Planning surface: Filter (broadband/NB),
  Available time, Brightness limit, Short-window threshold, Moon (auto/ignore) —
  hard filters + soft nudges over the persistent strategy/weights, with saved
  **presets** ("Backyard NB night", "Dark-site galaxy hunt"). Toggles never
  mutate the saved strategy. *Deferred knobs:* sky-quadrant constraint,
  framing/FOV (needs equipment), transparency, novelty/staleness.
- **Trajectory-aware altitude.** Weight which side of its seasonal arc a target
  is on: past-peak-and-falling (closing opportunity) outranks
  rising-toward-peak at the same altitude (sign+slope of dark-window peak
  altitude a few nights out — a finer partner to `nights_to_close`).
- **Per-object integration target.** A user-set override of the type-default
  deep threshold (object detail carries it; badge + scorer read it), and a
  **v2 surface-brightness basis** (mag + size) refining the per-type table.
- Data/robustness follow-ups tracked in BUGS: **#38b** (reference V-mag audit),
  **#40b/#40d**. (#44, the assistant foundation, shipped with item 4 M0.)

### 11 — Lights Table

A view with tools to quickly examine large numbers of .fits files. Should be a
direct view of files, with autostretch (not looking at derived jpgs). Users can
flag files with clouds, satellite/aircraft trails, and other imperfections. User
can delete the file on disk with confirmation, or just mark it so it won't be
hardlinked into workflow (e.g. "Siril") directories. Future versions might
support batched background extraction, plate solving, SPCC, or maybe image
analysis (find frames with satellite trails, find frames with low star count,
etc).

### 12 — Sky map (uranometria integration)

Plot the collection on a star-atlas chart: **where** in the sky everything you've
shot actually is, and how much of a goal list is still empty. Proposed in issue
**#98** by **Devon Jones**, who wrote and offered
[**uranometria**](https://github.com/devonjones/uranometria) — a chart library
built with this sort of integration in mind. This section is the scoping write-up **for
Devon to review** before we open a PR against his repo.

**Why it earns a slot.** M110 already knows every fact a chart needs (coords,
capture status, integration, goal membership, hero images) and today renders them
only as tables and tiles. A chart is the one view that answers "what's *left*"
spatially — Overview's goal percentages become a picture of the sky filling in.

#### Licensing & dependency assessment ✅

- **Code: Apache-2.0**, identical to ours. No friction.
- **Bundled data** is permissive-with-attribution: OpenNGC (CC-BY-SA-4.0), the
  Sharpless catalog via VizieR, d3-celestial stars + constellation lines (BSD-3),
  Marcellus / IBM Plex Mono (OFL). Share-alike attaches to the *database*, not to
  M110's code — no viral effect. Devon already stamps attribution into the
  generated page footer, which matters because publishing a chart to a user's
  GitHub Pages site *is* redistribution.
- **Our obligation:** `NOTICE` entries once we bundle it into frozen builds —
  the same precedent as the GeoNames CC-BY-4.0 data in `glow.py`.
- **Deps:** `click` + `pyyaml` only for the chart half. (The `annotate` extra —
  astropy/astroquery/matplotlib + an external ASTAP install — is out of scope
  here; see *Not in scope* below.)
- **Distribution — end users get it bundled either way.** Frozen builds have no
  pip, so the `build` extra pulls the dependency into the build venv and
  PyInstaller freezes it in. Exact precedent: astroquery, bundled for the same
  reason (issue **#64** — "a frozen app user can't add the extra themselves").
  uranometria additionally ships package **data** (`data/*.csv`, `.json`,
  `.tsv`, base64 font assets), so the three specs need
  `collect_data_files("uranometria")` — PyInstaller won't pick those up on its own.
- **Not on PyPI yet — a source-install wrinkle, not a blocker.** M110 doesn't
  publish to PyPI today (the release pipeline builds installers and attaches them
  to a GitHub Release), so a `git+https://` direct reference in `pyproject.toml`
  would work right now. It would, however, become a landmine on any future PyPI
  upload — direct-URL references are rejected anywhere in the metadata, including
  in extras. Cleanest path: keep the git URL **out** of `pyproject.toml`, install
  it explicitly in the build step, and switch to a normal
  `skymap = ["uranometria>=…"]` extra once it's published.
- **Optional import regardless.** `try: import uranometria / except ImportError`
  is the house pattern (`publish/` → `PublishDepsMissing`, `online` →
  `OnlineLookupError`), so a lean source install still runs — the Map view just
  hides itself. That stays true even after the extra exists.

#### Upstream dependency: ✅ **landed** (2026-07-30)

The SVG mode below was written by us and **merged upstream** as
[uranometria#22](https://github.com/devonjones/uranometria/pull/22), released in
**0.11.0**. The shipped API differs from the proposal in one way: it returns
**one entry per hemisphere** rather than taking a `hemisphere=` kwarg, which
reuses uranometria's own `need_north`/`need_south` derivation untouched — and
matches this item's Map view, where the N|S toggle only appears when southern
objects exist.

```python
charts, warnings = uranometria.render_svg(config, palette=…, font_family=…)
# [{"hemisphere": "north", "svg": "<svg xmlns=…>…</svg>",
#   "objects": [{"uid": 0, "id": "mk-0", "disp": "M31", "image": "heroes/m31.jpg",
#                "x": 612.4, "y": 388.1,
#                "label": {"dx": 16, "dy": 4, "anchor": "start"}}]}]
```

Verified end to end before merge: QtSvg renders the document correctly (dominant
disc color `#0A0F24`, **zero** black samples, every marker within 14 px of its
reported position), the interactive HTML page is **pixel-identical** (0 of
1,260,000 pixels differ), and a round-trip of M110's own 41-object library
produces one northern disc with no warnings and every marker inside the disc.
`uranometria.chart.MARKER_R` is the hit-test radius; `id="mk-N"` survives into
the markup so `QSvgRenderer.boundsOnElement` is an exact alternative.

Still not on PyPI (Devon's account recovery is weeks out), so the
build-step install described above stands until it is.

#### The rendering constraint — verified, and the change we made

`packaging/*/M110.spec` **deliberately excludes** `QtWebEngineCore` /
`QtWebEngineWidgets`. Embedding uranometria's interactive HTML would mean adding
a Chromium (~150–300 MB per bundle) plus a separately-signed
`QtWebEngineProcess` helper for notarization. Not worth one view.

Rendering the chart's SVG natively with `QtSvg` is the answer, but the SVG as
emitted today won't survive it. Probed against M110's own PySide6:

- **QtSvg ignores the entire `<style>` cascade** — not just CSS custom
  properties. A `.dot { fill:#00FF00 }` rule with a *literal* color still
  rendered black.
- Markers are positioned purely in CSS (`page.py`: `.marker { transform:
  translate(var(--tx),var(--ty)) }`, with `--tx/--ty` in each marker's `style`
  attribute), so under QtSvg **every marker collapses onto the origin**.
- **Presentation attributes render correctly**: `fill=`, `transform=`,
  `text-anchor`, `font-size` all work.

So the ask is narrow — an SVG mode that emits presentation attributes instead of
the CSS cascade. Everything else in `chart.py` is already shaped for it:
`project()` is module-level pure math, the viewBox is a fixed `0 0 1000 1000`,
`Chart.markers` already carries computed `x/y`, and label collision-avoidance
(`place_label`) runs in Python, not JS — so static SVG loses nothing on layout.

What shipped, in the terms above:

- `palette` — a 15-key dict (`sky/deep/star/grid/equator/aster/conname/accent/…`
  plus `ecliptic` and the star tints). We inject M110 theme tokens, so the chart
  follows light/dark instead of being fixed dark. A **gain** over the HTML version.
- each chart's `objects` — every marker's final `(x, y)` in the viewBox plus
  label offset / id / image. The important one: without it we'd re-derive
  positions and duplicate the marker layout. With it, native hit-testing is exact.
- `font_family` — the page embeds Marcellus / IBM Plex Mono as woff2 data URIs,
  which QtSvg can't load, so we pass a family we register ourselves (we already
  bundle JetBrains Mono via `ui/theme/fonts.py`).

Non-breaking: `page.py` keeps the CSS mode. The attributes are emitted
*unconditionally* — a CSS rule always outranks a presentation attribute, so the
interactive page renders identically and there is one code path, not two.

#### In-app scope — Library → **Map** view

The Library page already stacks List / Grid / Feed over one shared
`_current_items()` filter pipeline, so **Map is a 4th segment button**, not a new
nav pane (item 0's minimal-chrome rule). It inherits search, the catalog filter,
and captured-only for free; clicking a marker is just `select_object`, which
drives the existing `DetailPane` in the same splitter — exactly how Grid behaves.
The grid's zoom slider row (`_zoom_row_widget`) is the precedent for the map's
own zoom control.

```
┌───────────┬──────────────────────────────┬───────────────────────────┐
│ Library   │ [Deep sky|Media]  [List|Grid|Feed|▮Map]                  │
│ Overview  │ (search)          [Messier ▾]│  M51                      │
│ Planning  │ 46 captured · 12 deep · 128h │  Whirlpool Galaxy         │
│ Import    │      ╭────────────────╮      │  ┌─────────────────────┐  │
│ Processing│    ·  ·   ◉M101  ·  ✦ │      │  │      hero image     │  │
│           │   ✦  ◉M81   ·   ○  ·  │      │  └─────────────────────┘  │
│           │    ·   ·  ◉M51  ·   ✦ │      │  [Deep] 6.2 h · 4 sessions│
│           │      ╰────────────────╯      │  Type        Galaxy       │
│           │ [N|S]        Zoom ──── ⟲     │  Season      Mar–May      │
│           │ ◉ deep  ◎ captured  ○ goal   │  RA/Dec  13h29m · +47°11′ │
└───────────┴──────────────────────────────┴───────────────────────────┘
```

Interaction is native, and maps onto UI we already own — nothing is lost by
dropping the JS:

| uranometria HTML/JS | M110 native |
|---|---|
| scroll-zoom, drag-pan, dbl-click reset | `QGraphicsView` + `QGraphicsSvgItem` (precedent: `image_viewer.ZoomableImage`) |
| click marker → photo lightbox | hit-test `placed` → the existing `ImageViewer` (full-res, with the export / curation menu) |
| searchable object sidebar | the Library *is* that |
| markers counter-scale on zoom | `ItemIgnoresTransformations` on marker items |

**Use cases, phased:**

- **12a — "Where is my collection?"** *(core)* Every filtered Library object
  plotted; click → select → detail pane. Hemisphere toggle only when the set
  actually reaches past dec −35° (uranometria's own threshold).
- **12b — Goal progress as a picture.** Marker style by capture depth —
  uncaptured goal member (dashed outline) / captured (ring) / deep (filled).
  Sources already exist: `goals.goal_members`, `derived` totals,
  `build_derived.deep_threshold` (type-aware: galaxies 240 min, nebulae 360).
  The header's catalog filter scopes the map to one goal list.
- **12c — Season context** *(cheap, phase 2)*. A polar chart's RA axis **is** the
  season axis (`catalog.season_from_ra`) — shade the current season's RA wedge.
- **12d — Tonight's plan on the sky** *(phase 2, honest scoping)*. Highlight the
  sequenced targets on the Planning page, numbered by slot. **Complements, does
  not replace, `NightTimeline`**: these charts are whole-sky and epoch-agnostic —
  no horizon, no altitude, no time axis, so they answer "where am I pointing",
  not "how high, and for how long". The timeline stays the planner's main view.
- **12e — Publish a sky map page** *(independent of everything above)*. Use
  `generate()`'s **full interactive HTML** as a page on the static site — a
  browser is the right viewer there, so we keep search, the lightbox, and
  annotations for free. Slots into `publish/` as one more section checkbox;
  heroes are already emitted as web derivatives, and `select.publishable_slugs` /
  `journal_visible` already decide what's shareable.

**Not in scope here.** The `annotate` half is tracked separately as
[item 13](#13--image-annotation-plate-solved-object-overlays) — it shares the
library but nothing else: different trigger, different surface, different
external dependency.

**Data mapping.** Pass **fully-specified entries** (label + `ra_deg`/`dec_deg`
from `library.toml` + hero path + color), never bare designations — Devon
documents this as the host-app pattern and it keeps generation offline and
deterministic. It also sidesteps the real edge cases in a live library: entries
like `M42_mosaic`, `NGC 7000_mosaic`, `Unknown`, `Markarian's Chain`, and
`Kochab` would otherwise fail catalog lookup or hit the online Sesame resolver.
`constellation` is the one field we don't store; it's optional.

**Settled with Devon** (issue #98, 2026-07-30). The API shape was approved, we
wrote the PR, and it merged upstream in 0.11.0. PyPI is a goal on his side but
gated on account recovery, so M110 installs from git until then. Verified on real
data: this item's 12a/12b are now purely M110-side work with no upstream blocker.

### 13 — Image annotation (plate-solved object overlays)

Plate-solve a stack and label **everything actually in the frame** — the target,
its companions, the IC/NGC neighbours nobody mentions, named bright stars with
magnitude and distance, keyed field stars. The second half of
[uranometria](https://github.com/devonjones/uranometria) (issue **#98**),
promoted out of [item 12](#12--sky-map-uranometria-integration) because it shares
only the library: different trigger, different surface, different external
dependency.

**Why it's worth its own slot.** Most tools show you the headline object and stop
— a typical M110 frame contains several catalogued objects that never get named
anywhere in the app. Annotation is the feature that turns "here's my picture of
M51" into "…and here are NGC 5195, the IC companions, and the mag-9 star at
lower left, at 480 pc." It also feeds the journal and anything published.

**Library API** (host-integration path, already documented upstream):

```python
model = build_model(stack, allow_online=True, solve_kwargs={"ra_hours":…, "dec":…})
write_model(model, sidecar)                 # cache: solve once, re-render forever
```

Plus `render_png` / `render_html` for export. `AstapError` on solver failure;
per-object lookup misses degrade to warning strings.

#### What this actually costs us

- **In-app dependency delta: zero.** `build_model` needs astropy + astroquery,
  and packaged builds **already bundle both** (issue #64). Pillow ships too.
  Only `render_png` wants **matplotlib**, which the specs deliberately
  `exclude` — so we don't use his PNG renderer in-app.
- **The model JSON is the integration seam** — the same lesson as item 12's SVG.
  It carries per-object **pixel** coordinates, so M110 paints the overlay itself
  with `QPainter` in `image_viewer.py`, themed and zoom-aware, reusing the pan/zoom
  we already have. No Chromium, no matplotlib, no second rendering stack.
- **The real dependency is external: [ASTAP](https://www.hnsky.org/astap.htm)**
  plus a local star database (D20 for ~1° fields). That's a Siril-shaped
  prepare-and-guide problem, and `launch.py` already solves its shape: extend the
  `_TOOLS` registry + `find_app` (user override → OS-standard locations → `None`),
  add ASTAP binary + star-DB path fields to Preferences → *Processing tools*
  beside Siril's, and hide the action with an install hint when it's missing —
  the same degradation as Siril's `LaunchError` → reveal-the-folder fallback.
- **Solving is slow** → `QThread` worker behind a modal progress dialog with a
  working Cancel, per the house rule.

#### Gotchas to design around

- **Pixel frame.** The model's `solved.pixel_frame` is `"fits0"` (FITS row order)
  for FITS sources and `"raster0"` (top-down) for JPEG/PNG. Our overlay must flip
  y only when the model and the displayed raster disagree — `build_images._open_image`
  normalises both kinds into one QPixmap, so the flip decision belongs at the
  overlay layer, not the decode layer. Getting this wrong mirrors the annotations
  vertically, which looks *almost* right — the worst kind of bug.
- **Solve the star-rich stack, not a starless render.** Upstream says so
  explicitly, and we can enforce it for free: `hints.is_intermediate_name`
  already recognises `starless` / `starmask`, so those tiles simply don't offer
  the action.
- **Online vs offline.** Field-star identity comes from CDS (VizieR Gaia DR3
  for magnitudes/distances, Tycho-2 designations, SIMBAD named stars).
  `allow_online=False` degrades to bundled-catalog DSOs only — wire it to the
  same expectation as `catalog.enrich_online`: offline is a first-class mode,
  not an error.
- **Sidecar placement.** `<image>.annotations.json` beside the source (e.g.
  `Images/<target>/stacks/<stack>.fit.annotations.json`) is upstream's convention
  *and* what the sky-map lightbox auto-discovers. Additive, so no
  `.store_version` bump — but it's a new file in the content tree and needs a
  **[`DATA_MODEL.md`](DATA_MODEL.md)** entry.

#### Phasing

- **13a — Solve + cache** *(engine, Qt-free)*. `m110/annotate.py`: ASTAP
  discovery, `build_model` with a pointing hint from the object's known RA/Dec
  (upstream notes it speeds the solve), sidecar write, staleness check. Feed the
  hint from `catalog.load_coords` — we always have it, so we never solve blind.
- **13b — Native overlay** *(the payoff)*. An **Annotations** toggle in
  `ImageViewer`: markers + leader labels painted with `QPainter`, a searchable
  side panel of identified objects with SIMBAD / Wikipedia links, colour-coded by
  class. Right-click a gallery tile → **Annotate…**.
- **13c — Export.** Annotated PNG / standalone HTML via upstream's renderers, for
  sharing. Runs out-of-process or gated on an optional extra, so matplotlib stays
  out of the bundle.
- **13d — Publish.** Ship the sidecar with the site so the published gallery —
  and [item 12e](#12--sky-map-uranometria-integration)'s sky-map lightbox — shows
  the overlay. This is where 12 and 13 compound: a chart of your collection where
  every photo is fully labelled.

**Strategic bonus: it unlocks [item 9](#9--full-import-triage-toolkit-deferred).**
That item's deferred triage toolkit lists plate-solving as the way to recover
headerless frames, and the holding area's `ingest.identify_holding` currently
guesses identity from the `OBJECT` header or nearest-catalog-by-RA/Dec. A real
solver behind one shared seam turns that guess into an answer. Build the ASTAP
integration once; both items draw on it.

### 7 — Processing & curation UX (remainder)

(BUGS **#18/#19**; the #17 configurable finished/intermediate hinting + the
Finished/Working curation gallery **shipped** — see [`DONE.md`](DONE.md).)
- *Advanced/custom workspaces* (#18) — named, on-disk-discoverable Siril (and
  other) working dirs that combine lights from disparate sources (#16) and
  **multiple objects** (mosaics, e.g. M81 + M82 + "M81 M82"), via hardlinks;
  custom split workflows. Introduces a workspace entity not bound to one target.
- *Open In… / Process in…* (#19) — OS-level "open this image in <app>" and
  "process this object in <Siril/PixInsight/…>" (creating/selecting the working
  dir first). Pure **guide**, not control — fits the processing philosophy;
  cross-platform launch is the main risk.

### 8 — Publishing: remaining targets

8a (local static-site export + the publisher registry) and the **GitHub Pages
deploy** (2026-07-15) shipped; the registry (`publish.PUBLISHERS` +
`PublishOptions`) is the stable seam — each new target is an adapter. The
follow-up list is BUGS **#27**: Netlify / S3·CloudFront / WordPress·Ghost,
per-list publish flags, cross-publish image-cache reuse, auto-publish on
refresh; possibly Astrobin/forum exports.

**Sharing / Export arc.** Promoting share/export toward a top-level feature.
- ✅ **Image export for web sharing** — a size-budgeted single-image exporter
  (`webexport.py` + `ui/export_dialog.py`; right-click a gallery tile / the hero /
  the image viewer's ⤓ Export…). A max-size (or No-maximum) control + a
  quality-preserving ladder (lossless PNG → downscale, or full-res JPEG), native OS
  save panel with a `[Object]-[maxsize]-[date]` name. See [`DONE.md`](DONE.md).
- ⏭ **Destination model + a "Share" nav pane** *(next)* — replace the single
  publish config with a list of named **destinations** (each = publisher + its own
  scoped `PublishOptions`), so different data can go to different targets, and lift
  the publish dialog into a managed pane (destinations list + batch image export +
  publish history). Deferred as a separate, larger change.

### 5 — Catalog growth

More bundled catalogs from `next_catalog_lists.md` — **Herschel 400**, **Arp**,
**Lunar 100**, AL Double Star (data-generation in `tools/gen_catalogs.py`;
build-time only, runtime stays offline).

- ✅ **Popular device lists** (2026-07-20) — three hand-curated goal lists chosen for
  community popularity and matched to gear by field-of-view fit + aperture reach:
  `popular-deep-s50`, `popular-widefield` (S30 Pro / Dwarf 3), `popular-bright`
  (S30 / Dwarf Mini), each ~48 targets spanning all four seasons and reaching well
  beyond Messier. Added Pelican (IC 5070), Horsehead (IC 434), Elephant's Trunk
  (IC 1396) + NGC 884 to the object reference to support them. Curated, not generated.

### 6d — Multi-device: device-under-target + Dwarf remainders

Record device/source per session; introduce the optional
`Images/<target>/<device>/` path level only when one target is actually shot on
a **2nd device** (flat = default device). A device registry keyed to planning
device-profiles (`planning_config.load_device`). This is the phase that bumps
`.store_version` + adds a `migrate.py` step. See [`DATA_MODEL.md`](DATA_MODEL.md).

Dwarf 3 core support **shipped 2026-07-09** (see [`DONE.md`](DONE.md)); the
remaining device-source gaps collect here:
- **`DWARF_DARK/` / `CALI_FRAME/` routing** → darks / calibration tiers.
- **`Restacked/` (Mega Stack)** → the device-stack tier.
- **TIFF subs** (a Dwarf 3 capture option; today only FITS subs are handled).
- **`shotsInfo.json` sidecar** — RA/DEC + target + exposure/gain + IR-filter +
  stacking stats per session folder; a rich metadata source for the pointing
  check and session facts.
- **Volume auto-detection** — probe a mounted volume/dir for
  `Astronomy/DWARF_RAW` (the analogue of the Seestar `MyWorks` probe).
- **Dwarf II validation** against a real capture dump.

### 9 — Full import triage toolkit *(deferred)*

Extends item 6's holding area with deeper tools for files the header/layout
classifier can't place: a **FITS header inspector**, an in-app **image
viewer/annotator** for headerless frames, and **plate-solving** to recover
pointing (→ object) when no usable `OBJECT`/`RA`/`DEC` exists. Deferred — pulls
in a plate-solver dependency; only worth it once real-world messy imports demand
more than manual assign (the #26 identification aids cover the common cases).

### 3 — Equipment monitor *(deprioritized)*

Originally: an Alpaca monitor/author *companion* to a headless Pi field stack
(SSC / PINS / INDI) — kept a thin companion, never a hardware-control
reimplementation (owning hardware control means owning every "it disconnected
at 2am" report).

I'm revising this vision to *maybe* just a live-view window and/or incoming
frame viewer similar to a tethered camera experience in studio photography
workflows. And putting a very low priority on it.

---

## Shipped

One line each; the full how-and-why lives in **[`DONE.md`](DONE.md)** (skim it
when extending an existing subsystem).

- **MVP v0.1 — "the Library"** — 0.1a–0.1f, own data root + bootstrap, the
  image-rendering port, the two-axis store (#13), the processing-prep round-trip.
- **0 — Navigation IA** — the 5-pane nav rail after the pre-launch 8→4 cleanup
  (Overview merged Summary+Goals; Media/Journal/Sessions absorbed into Library);
  Planning added post-beta.
- **UI design system** — theme tokens + QSS, follow-OS light/dark, restyled
  surfaces, branding/logo, JetBrains Mono.
- **1 — Session planning** — Checkpoint A (site profiles, light-dome glow
  auto-map, deterministic prioritizer + tuning UI), Checkpoint B (night planner,
  sequencer, `NightTimeline`, field guides under `Plans/`), and the release
  tuning arc (two ground-truth reviews; [`docs-archive/`](docs-archive/)).
  Design history + prototype findings archived in DONE.md.
- **5 — Library, catalogs & goals** — Object/Catalog/Goal/Library concepts,
  six bundled catalogs, custom goals, Simbad enrichment, Library-=-collection.
- **6 — Import (6a–6c)** — any-directory recursive scan, FITS-header
  classification + layout registry, holding area + manual assign + identification
  aids; **DwarfLab Dwarf 3** end-to-end (2026-07-09).
- **8a — Publishing** — Qt-free `publish/` engine + registry, selective static-
  site export with privacy controls.
- **10 — Library backup** — hardlinked dated snapshots, checksum verify,
  selective restore, retention, opt-in auto-backup.
- **7 (part) — #17 finished/intermediate hinting + curation gallery** — the
  user-editable hint vocabulary + Finished/Working groups with per-image
  curation.

---

## Decisions & open items

| Item | Status |
|---|---|
| License | ✅ **Apache-2.0** (decided 2026-06-04; see `LICENSE` / `NOTICE`) |
| Public name | ✅ **M110** (decided 2026-06-04). Tagline: *Complete the catalog.* Package import id `m110`. |
| External presence (pre-release) | Follow-ups: domain (`m110.app` — verify at registrar), GitHub org (`m110` username taken → `m110app` / `messier110`), and an explicit "smart telescope / deep-sky catalog tracker" subtitle for discoverability. Per the name writeup. |
| Native SwiftUI Mac wrapper on the same engine | deferred option |
| Port `build_site`'s Jinja static-site rendering | **not** ported as the app's UI (the app *is* the UI; only the image pipeline was ported). Its capability **returns, generalized, as the Publishing phase** (item 8) — optional, selective, multi-target export |
| Cross-platform packaging (notarize / Homebrew cask / Windows / Linux) | future |
| Rendering HTML in-app (QtWebEngine) | ❌ **no** — the packaging specs exclude `QtWebEngineCore`/`QtWebEngineWidgets` on purpose; a Chromium adds ~150–300 MB per bundle plus a separately-signed helper for notarization. In-app visuals render natively (`QtSvg` / `QPainter`); HTML output belongs in the browser or on a published site (item 12) |

---

## Guiding principles (so scope stays sane)

- **Phase ruthlessly; control last.** This vision is really five products
  (track / process-prep / plan / generate / control) in increasing risk order.
  Ship the Library, resist the equipment-control siren.
- **Don't wrap volatile external tools** more than necessary — prepare-and-guide
  over direct control; the maintenance tax of chasing Siril/SSC/NINA changes is
  real.
- **Generalization is a project.** Today's config still assumes one observer's
  site/obstructions/equipment; productizing means abstracting that — budget for
  it, don't underestimate it.

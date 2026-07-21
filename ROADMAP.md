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
| 1 | **Session planning** — site profiles + light-dome glow, deterministic prioritizer, night planner + sequencer, field guides | ✅ shipped *(follow-up refinements open ↓)* | [`DONE.md`](DONE.md) Checkpoints A/B + tuning arc; [`docs-archive/PLANNING_ROADMAP.md`](docs-archive/PLANNING_ROADMAP.md) |
| 5 | **Library, catalogs & goals** — multi-list tracking, 6 bundled catalogs, custom goals | ✅ shipped *(catalog growth open ↓)* | [`DONE.md`](DONE.md) |
| 6 | **Import** — any-directory recursive scan, header classification, holding area, Dwarf 3 | ✅ 6a–6c + Dwarf 3 shipped *(6d open ↓)* | [`DONE.md`](DONE.md) |
| 8 | **Publishing** — selective static-site export + publisher registry + GitHub Pages deploy | ✅ 8a + GitHub Pages shipped *(more targets open ↓)* | [`DONE.md`](DONE.md) |
| 10 | **Library backup** — hardlinked snapshots, verify, selective restore, auto-backup | ✅ shipped | [`DONE.md`](DONE.md) |
| 7 | **Processing & curation UX** | 🔶 #17 hinting + curation gallery shipped; #18/#19 open ↓ | [`DONE.md`](DONE.md), [`BUGS.md`](BUGS.md) |
| 4 | **In-app assistant** (bring-your-own LLM) | ⬜ open — **next major milestone** | ↓ |
| 2 | **Plan-file generation** (SSC / NINA device schedules) | ⬜ open | ↓ |
| 11 | **Lights Table** (bulk sub inspection/culling) | ⬜ open | ↓ |
| 9 | **Import triage toolkit** (header inspector, plate-solving) | ⬜ deferred | ↓ |
| 3 | **Equipment monitor** | 💤 deprioritized (vision revised) | ↓ |

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

### 4 — In-app assistant (bring-your-own LLM) — *next major milestone*

Put the LLM value that's proven out in this project — **session planning, image
analysis, workflow coaching** — *inside* the app, grounded in the user's own
data. This is **"Checkpoint C" of the session-planning arc**: it layers over the
deterministic prioritizer + planner — the assistant *proposes* session toggles /
weights / plans and *explains* the ranking, but the engine still computes (it
never authors the priority list). Foundation noted in BUGS **#44** (consult the
`astro-session-planner` skill in ~/Astronomy).

**Why M110 is unusually well-positioned.** The three things that make an LLM
genuinely useful here, the app already holds in structured form:
- **Context** — catalog, priorities, capture status, per-object journals, and
  the site / equipment / obstruction profile.
- **Tools** — the engine's real computations (twilight / moon / transit-altitude
  / obstruction; derived rollups; image access).
- **Knowledge** — the workflow playbooks (drizzle / PSF / colour / planning).

So "skilling" the model is mostly wiring: **data → context, engine functions →
tools, docs → reference.** The app is the ideal host because it owns all three;
the LLM stops guessing and starts calling real functions over real data.

**Architecture (Qt-free `m110/assistant/`):**
- `credentials` — API keys in the OS keychain (`keyring`), never plaintext;
  per-provider.
- `providers/` — adapters behind one interface (chat + tools + vision +
  streaming). **Claude first** (Anthropic Messages API: tool use, image input,
  **prompt caching** for the large static context, streaming). Design the seam
  for OpenAI / local (Ollama) later.
- `context` — assemble the system payload from app data + playbooks, with cache
  markers on the static parts.
- `tools` — expose engine functions as LLM tools: altitude / twilight / moon,
  priorities, object lookup, captured list, workflow-doc fetch, image fetch
  (vision), propose-plan, save-critique/journal. Grounds answers in real
  computation, not guessed numbers.
- UI — a dockable Assistant chat plus context-seeded entry points
  ("Plan tonight", "Critique this image", "How should I process this?").

**The three features:** *planning* (assistant + planning tools + priorities →
a plan, exported via the plan-file phase); *image analysis* (vision + the
object's render/stack + processing metadata → a critique saved to the journal);
*coaching* (grounded Q&A over the playbooks + the object's current state).

**MCP angle (design toward it).** Expose the engine's tools+data as an **MCP
server**: the in-app assistant becomes an MCP client, and the *same* server
lets a user point their own external Claude / Claude Code at M110's data and
tools. Standards-based, future-proof, keeps the assistant thin.

**Cross-cutting.** BYO-key (user's account, user pays); model picker (Haiku for
cheap coaching, Sonnet/Opus for planning/analysis); prompt caching for cheap
repeat calls; clear disclosure that data/images go to the chosen API, with a
**local-model option** for privacy/offline; prefer tool-computed facts over
model guesses; needs a network entitlement (fine for Developer-ID).

**Phasing:** A0 contextualised chat (BYO Claude key, cached context, no tools)
→ A1 tool use (real planning + grounded answers) → A2 vision (image critique)
→ A3 provider abstraction + cost controls + local models → A4 (optional) MCP
server / agentic multi-step (Claude Agent SDK).

**Dependencies / risk.** The planning engine + data model it builds on are
shipped. Risks: provider-API churn; user cost surprises (mitigate: caching +
model choice + a token/cost readout); hallucination (mitigate: ground in
tools/data, cite sources); and scope — keep it "an LLM over the existing
engine," not a bespoke agent framework.

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
  **#40b/#40d**, **#44** (assistant foundation, → item 4).

### 11 — Lights Table

A view with tools to quickly examine large numbers of .fits files. Should be a
direct view of files, with autostretch (not looking at derived jpgs). Users can
flag files with clouds, satellite/aircraft trails, and other imperfections. User
can delete the file on disk with confirmation, or just mark it so it won't be
hardlinked into workflow (e.g. "Siril") directories. Future versions might
support batched background extraction, plate solving, SPCC, or maybe image
analysis (find frames with satellite trails, find frames with low star count,
etc).

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
  (`webexport.py` + `ui/export_dialog.py`; right-click a gallery tile / the image
  viewer's ⤓ Export…). Reddit/Discord/Custom budgets, quality-preserving ladder
  (lossless PNG → downscale, or full-res JPEG), native OS save panel. See
  [`DONE.md`](DONE.md).
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

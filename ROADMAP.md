# M110 — Roadmap

Canonical roadmap for M110: the north star, the foundational decisions,
the MVP build order, and what comes after. (Long-form rationale for the
decisions lives in the sibling Astronomy project's `workflow_app_plan.md`; this
file is the standalone, authoritative status.)

**North star:** "Lightroom for smart telescopes" — one native-feeling app to
catalog, track, ingest, and process-prep a smart-telescope deep-sky collection.

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
  own derived data and image renders.

---

## MVP (v0.1) — "the Library"

| Step | Status | What |
|---|---|---|
| 0.1a | ✅ | engine package + read functions (config, catalog, derived, objects) |
| 0.1b | ✅ | read-only Library: capture-status table (natural M/NGC sort) + object detail/gallery |
| 0.1c | ✅ | in-app **Refresh** (threaded) — ported scan_sessions + build_derived |
| —    | ✅ | **Own data root** (`~/Documents/M110`) + bootstrap/seed + Preferences + Seestar mount detection |
| —    | ✅ | **Image rendering** port (build_images: thumbnails / heroes / images.json, cached) |
| 0.1d | ✅ | **Ingest** — preview-then-confirm; sources: staging (move) + mounted Seestar `MyWorks` (copy); threaded + cancellable |
| 0.1e | ⬜ | **inline journal editing** — edit `data/objects/<slug>.md` in-app |
| 0.1f | ⬜ | **processing-prep** — arrange Siril folder layout (incl. per-filter split), emit Naztronomy preset JSON, surface workflow guidance |

---

## Later phases (post-MVP)

1. **Session planning** — port the positional math (twilight / moon /
   transit-altitude / obstruction / start-altitude ceiling) into `planning.py`;
   build a planning surface; emit the session-plan document.
2. **Plan-file generation** — SSC schedule JSON (port the existing generator),
   NINA Advanced Sequences (schema capture pending), possibly INDI/Ekos.
3. **Alpaca equipment control** — a monitor/author *companion* to a headless Pi
   field stack (SSC / PINS / INDI). Last and riskiest; keep it a thin companion,
   not a hardware-control reimplementation. Owning hardware control means owning
   every "it disconnected at 2am" report.

---

## Decisions & open items

| Item | Status |
|---|---|
| License | ✅ **Apache-2.0** (decided 2026-06-04; see `LICENSE` / `NOTICE`) |
| Public name | ✅ **M110** (decided 2026-06-04). Tagline: *Complete the catalog.* Package import id `m110`. |
| External presence (pre-release) | Follow-ups: domain (`m110.app` — verify at registrar), GitHub org (`m110` username taken → `m110app` / `messier110`), and an explicit "smart telescope / deep-sky catalog tracker" subtitle for discoverability. Per the name writeup. |
| Native SwiftUI Mac wrapper on the same engine | deferred option |
| Port `build_site`'s Jinja static-site rendering | intentionally **not** ported (the app is the UI; only the image pipeline was ported) |
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

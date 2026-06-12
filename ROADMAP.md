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
| —    | ✅ | **Two-axis data store** (BUGS #13) — `Objects/` (catalog axis) + `Images/` (capture-target axis), hidden `.m110_internal_data/`, in-place idempotent migration. Landed *before* 0.1e/0.1f so both build on the final layout |
| 0.1e | ✅ | **inline journal editing** — Edit/Save/Cancel the raw `Objects/<id>/journal.md` in the detail pane (table + actions lock while editing) |
| 0.1f | ✅ | **processing-prep round-trip** — prepare a contained `Images/<target>/siril/` sandbox (literal `lights/` hardlinks + Naztronomy preset by frame count + guidance), set up **automatically on ingest**; then **import finished work** (renders→`finished/`, stack→`stacks/`, hero pick) and clean the sandbox up. Detail-pane entry points |

---

## Later phases (post-MVP)

1. **Session planning** — port the positional math (twilight / moon /
   transit-altitude / obstruction / start-altitude ceiling) into `planning.py`;
   build a planning surface; emit the session-plan document.
   *Head start (June 2026):* the Astronomy repo now has the tested, config-driven
   engine to port — `scripts/{sky,horizon,make_ssc,planning_config}.py` +
   `tests/test_planning.py` (site/device TOML profiles, zoneinfo DST, moon model,
   horizon-mask obstruction). **Decision: horizon input is Stellarium/NINA-style
   `.hrz` files** (whitespace az/alt pairs; our CSV also accepted) — **theo.rocks**
   (mobile web app: pan the phone around the skyline, export `.hrz`) is the
   recommended capture tool for M110 users; the parser already consumes its output.
2. **Plan-file generation** — SSC schedule JSON (port the existing generator),
   NINA Advanced Sequences (schema capture pending), possibly INDI/Ekos.
3. **Alpaca equipment control** — a monitor/author *companion* to a headless Pi
   field stack (SSC / PINS / INDI). Last and riskiest; keep it a thin companion,
   not a hardware-control reimplementation. Owning hardware control means owning
   every "it disconnected at 2am" report.

4. **In-app assistant (bring-your-own LLM).** Put the LLM value that's proven out
   in this project — **session planning, image analysis, workflow coaching** —
   *inside* the app, grounded in the user's own data.

   **Why M110 is unusually well-positioned.** The three things that make an LLM
   genuinely useful here, the app already holds in structured form:
   - **Context** — catalog, priorities, capture status, per-object journals, and
     the site / equipment / obstruction profile (the `config` generalization seam).
   - **Tools** — the engine's real computations (twilight / moon / transit-altitude
     / obstruction once the planning module lands; derived rollups; image access).
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

   **Dependencies / risk.** Builds on the planning module + data model, so it
   comes *after* those. Risks: provider-API churn; user cost surprises (mitigate:
   caching + model choice + a token/cost readout); hallucination (mitigate: ground
   in tools/data, cite sources); and scope — keep it "an LLM over the existing
   engine," not a bespoke agent framework.

5. **Goal / catalog selection — multi-list tracking.** Today the catalog and
   priorities are built around a single implicit goal: the Messier list. Once
   that's well underway, generalize so a "goal" is a named catalog (Messier,
   Caldwell, RASC Finest NGC, Herschel 400, Sharpless subset, Arp Peculiar
   Galaxies, Lunar 100, Double Star Club, ...) with its own object list,
   progress tracking, and dashboard/list view. Objects can belong to multiple
   catalogs (e.g. the Veil Nebula is both a non-Messier addition *and* Caldwell
   C33/C34), so this is membership/tagging, not a strict partition. Default goal
   ships as Messier; users add other goals from a built-in library of catalog
   definitions (or import their own). See the sibling Astronomy project's
   `next_catalog_lists.md` for the candidate lists and rationale behind each.

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

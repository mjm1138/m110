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
  own derived data and image renders. The data model is documented and canonical
  in **[`DATA_MODEL.md`](DATA_MODEL.md)** — item 5 (multi-catalog goals), #16
  (multi-telescope), and the planning phases build to the seams it defines.

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

0. **Site-parity multi-page UI** *(done)* — bring the app to functional
   parity with the published static site's pages. Left **nav rail + stacked
   pages**, Summary as the landing page, one shared Object detail reachable from
   every object link. **Phase 1 done:** shell + **Summary** + **Processing**
   (Catalog = the relocated Library). **Phase 2 done:** **Sessions** (sortable log   + search) + **Journal** feed (reverse-chron object cards by latest image
   activity); `derived.load_sessions()` added.
   **Phase 3 done:** Object view enriched (per-object Processing + Sessions tables + Catalog-details block) + Catalog parity (Size/Filter columns, search box,
   captured/deep/total stat row). **Site-parity multi-page UI complete.** All
   backed by existing derived data; only `derived.load_sessions()` was net-new.
   **Plus a Media page** (BUGS #11) — browses non-catalog `Media/` (photos →
   viewer, videos → OS player) via a new Qt-free `media.scan()`.

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

   **Auto-prioritizer / target scoring** (BUGS **#21**; dependency: item 5).
   Replace the hand-edited `priorities.toml` (today delegated to an ad-hoc LLM
   edit) with a **deterministic, testable scoring engine** that ranks targets from
   the data the app already holds + the planning math above. Build it as engine
   logic (the assistant, item 4, can later *explain/tune* it — not author a TOML).
   Score = weighted sum of:
   (a) **active-goal membership** (which catalogs/lists are being pursued; weight
   by goal rank); (b) **seasonal urgency** — rises as the remaining observable
   window narrows, so *closing soon* ≫ *mid-season* ≫ *just rising*; out-of-season
   excluded; (c) **completion vs. a strategy toggle** — *"capture many new targets"*
   favours uncaptured/under-threshold objects, *"build deep stacks"* favours
   started-but-shallow ones; (d) optional **per-type weights** (user pref);
   (e) **tonight feasibility** (transit altitude in dark hours, moon
   separation/illumination, horizon obstruction) to turn a season ranking into a
   tonight shortlist; (f) **manual overrides** (pins/excludes + the current
   `track=false` campaign entries). Natural output: a season-level goal backlog +
   a tonight's-targets shortlist (which feeds the plan-file generator, item 2).
   *Scoring weights + which knobs surface in a priorities preference pane: TBD —
   to refine.*

   **Findings from the Astronomy prototype (reviewed 2026-06-22)** — the
   `scripts/prioritize.py` prototype ran and generated a real `priorities.toml`.
   What the review surfaced for the M110 port:
   - **Location/dark-site awareness is the biggest gap.** With strategy=new the
     top picks were low-southern objects (M16/M17 @34–36°, M9/M107 @32–37°) —
     exactly the targets the hand list reserves for dark-site trips; from a
     Bortle-5 backyard at that altitude they're poor. "Tonight feasibility" (e)
     is deliberately *not* a ranking factor, so nothing demotes a trip-only
     target for a home night.
     - **Chosen direction: a "glow mask" — an azimuth-dependent quality floor
       layered on the physical horizon.** The season/observability gate already
       reads the `.hrz` horizon mask; add a parallel light-pollution layer so the
       effective usable floor per azimuth = `max(physical_obstruction,
       glow_floor)`. A city dome (e.g. Denver to the SE) becomes a ~30° floor in
       that arc while the open N stays at 10° — correctly demoting low-toward-city
       targets without touching low-away-from-city ones (a flat altitude floor
       can't make that distinction). Lives in the **site profile**, so a dark-site
       trip uses a different/empty glow mask and trip-only targets rank high there,
       low at home. Should be **filter-aware** (narrowband/LP punches through light
       pollution, so a softer floor for ON/LP targets than broadband — same
       principle as the moon decision).
     - *Data sources (for a v2 auto-derived mask):* the **World Atlas of Artificial
       Night Sky Brightness** (Falchi 2016; zenith Bortle/SQM scalar for a
       lat/lon) for the site-class tag, and **VIIRS Day/Night Band** radiance
       (NOAA/EOG, public domain) for *where* the domes are → project nearby
       sources to az/alt with a scattering falloff. Bundle/cache like
       `seed/objects.toml` to stay offline. *v1:* a hand- or semi-auto `glow.hrz`
       sibling + a stored Bortle/SQM — cheap and immediately useful.
   - **The season gate hard-drops short-window targets.** `season_min_hours`
     (1.5h above min-alt, unobstructed, minus a pre-dawn hour) gates out objects
     that only get 30–70 min of clean time from the home horizon mask
     (M109, M53, the Veil before late summer). Defensible, but it silently omits
     targets the user *does* grab opportunistically. Prefer a graded "short
     window" signal over a binary out-of-season drop; expose the threshold.
   - **Hand metadata is fragile.** Folder→object mapping and custom
     strategy/target live only on the generated priority entries, so an object
     cycling out of the ranking loses them. Prototype patched this with a
     one-time-archive fallback, but the real fix is a **stable metadata source**
     (catalog fields or a per-object overrides file) the generator reads, never
     the generated artifact itself.
   - **Resolve by canonical coords, not display id.** "Veil Nebula (E)" doesn't
     resolve; prototype now falls back to the slug ("ngc-6992" → "NGC 6992").
     The port should resolve via the catalog object's coords directly.
   - **Filter must be derived from type** (emission/planetary → LP, else IRCUT);
     prototype now does this — keep it first-class in the port.
   - **Strategy mode = the night's character.** new vs deep flips the list;
     near-complete close-outs (M57/M12/M56) sink to the bottom under "new". The
     toggle deserves prominence (and a deep/close-out night is a distinct mode
     from a breadth night).

   **Fixed in the Astronomy prototype 2026-06-22 (re-decide on port).** These
   are being developed in the live `~/Astronomy` workflow first because it has
   the most complete real data; the M110 port may land the same intent
   differently:
   - **Urgency × completion coupling.** Deep mode kept finished targets and let
     seasonal urgency pump their score — a done object "closing in 7d" outranked
     a genuine close-out (M81 1834/240 above the M12 close-out). Fix: scale raw
     window-urgency by the completion factor (`u = u_raw × c`), so finished
     targets (c→0) get no urgency credit while under-goal close-outs (c=1) keep
     it. Verified: M81/M82, M97, M108, M13, M5 dropped to the bottom; M57/M12/
     M10/M56 stayed high. **Port note:** this couples two factors that the
     weights table treats as independent — clean for now, but if the port adds
     more factors, consider whether urgency should instead be a *gate*
     (zeroed once complete) or a separate "finish-before-it-sets" signal
     distinct from "new-target seasonal urgency."
   - **Combined-frame captures (`[[combine]]`).** M81+M82 are imaged in one FOV
     under the `M81 M82` folder; the scorer ranked the catalog slugs m81/m82
     separately, each defaulting to 240 min (→ the 1834/240 artifact) and
     splitting one target into two rows. Fix: a `combine` group in
     `priority_prefs.toml` (canonical id + members + folder + shared target) is
     ranked as ONE entry off the folder's integration; members are skipped.
     (M108/M97 is the other framed pair — add when it next matters.) **Port
     note:** M110's two-axis store already separates Objects from capture
     targets (Images/<target>), so the *capture target* may be the natural
     ranking unit there — combine grouping might fall out of the data model
     rather than needing an explicit prefs list. Decide against the store, not
     by copying this TOML shape.
2. **Plan-file generation** — SSC schedule JSON (port the existing generator),
   NINA Advanced Sequences (schema capture pending), possibly INDI/Ekos.
3. **Alpaca equipment control** — a monitor/author *companion* to a headless Pi
   field stack (SSC / PINS / INDI). Last and riskiest; keep it a thin companion,
   not a hardware-control reimplementation. Owning hardware control means owning
   every "it disconnected at 2am" report.
   
   I’m revising this vision to *maybe* just a live-view window an/or incoming frame viewer similar to a tethered camera experience in studio photography workflows. And putting a very low priority on it.

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

5. **Library, catalogs & goals — multi-list tracking + arbitrary objects.**
   Today everything is one implicit list (Messier). Generalize into four clear
   concepts:
   - **Object** — an astronomical target with intrinsic reference data (coords,
     type, magnitude, size). Season is **derived** from coords + site, not stored.
   - **Catalog / List** — a curated, named, **app-bundled, immutable** reference
     set (Messier, Caldwell, RASC Finest, Herschel 400, Sharpless, Arp, Lunar 100,
     …). Ships with the app.
   - **Goal** — a catalog the user is *actively pursuing* (selection over catalogs,
     with progress tracking + a dashboard/list view).
   - **Library** — the user's **personal corpus**: every object in their store —
     catalog members they track **plus arbitrary/captured additions**. Mutable,
     per-user. (Lightroom's "Library.") Objects are many-to-many with catalogs (the
     Veil is a non-Messier add *and* Caldwell C33/C34) — membership, not partition.

   **Phase 5a (done):** foundation — per-store `catalog.toml` → **`library.toml`**
   (v2→v3 store migration); bundled data split into an **object reference dataset**
   (`seed/objects.toml`, id → coords/type/mag/size) + **catalog membership lists**
   (`seed/catalogs/*.toml`; Messier ships). A fresh Library seeds from the
   reference. Nav "Catalog" → "Library". No new user-facing behavior yet.
   **5b (next):** Goals — active-catalog selection + per-goal progress/dashboard;
   more bundled catalogs; the fresh-Library-=-Messier-only decision.
   **5c:** the add-arbitrary-object + enrich flow below.

   **Add arbitrary objects + auto-enrich.** A user can add any object to their
   Library; the app fills the data fields via a cascade (generalizes
   `catalog.add_captured_objects`):
   1. **Bundled reference** (covers catalog objects — instant, offline, complete);
   2. else **online lookup by name** — **astroquery** (Simbad/VizieR) for
      type/mag/size/coords. *(c): bundled-first, astroquery as enrichment, mainly
      for objects outside any supported catalog.* New optional dependency; network.
   3. else **embedded coordinates** — FITS `RA`/`DEC` or the filename pointing data
      (reuses ingest #12); type stays "unknown" for the user to complete.
   4. **Season is always derived** from the resolved coords (no lookup).

   Default goal ships as Messier; users add other goals from the bundled catalog
   library (or import their own). See the sibling Astronomy project's
   `next_catalog_lists.md` for candidate lists.

6. **Ingest evolution — robust, layout-flexible, multi-telescope** (BUGS **#16**).
   Today's Inbox recognizes only the Seestar export shape. Grow to: recognize
   multiple known layouts (Seestar, ZWO ASIAIR, raw FITS trees, already-M110-store
   folders), **classify by FITS header** (OBJECT/IMAGETYP/FILTER/RA/DEC) over
   folder-name conventions (pairs with #12's pointing logic), manual-assign the
   unrecognized rather than silently ignoring, and a device/format **registry**
   mirroring the processing-workflow registry. Lands the **device-under-target**
   layout from [`DATA_MODEL.md`](DATA_MODEL.md) so frames differentiate by source.
   Foundational for everything multi-scope; scope after the ingest/processing UX
   settles.

7. **Processing & curation UX** (BUGS **#17/#18/#19**). Generalize processing-prep
   past one user's habits and add curation:
   - *Configurable finished/intermediate hinting* (#17) — a preference-driven hint
     set (replacing today's hardcoded `_classify` patterns, the source of the
     NGC 6992 miss) + a per-object **finished vs. unfinished** gallery with
     right-click promote/demote/set-hero. Persists a curation designation (data-model
     impact — see DATA_MODEL future directions).
   - *Advanced/custom workspaces* (#18) — named, on-disk-discoverable Siril (and
     other) working dirs that combine lights from disparate sources (#16) and
     **multiple objects** (mosaics, e.g. M81 + M82 + "M81 M82"), via hardlinks;
     custom split workflows. Introduces a workspace entity not bound to one target.
   - *Open In… / Process in…* (#19) — OS-level "open this image in <app>" and
     "process this object in <Siril/PixInsight/…>" (creating/selecting the working
     dir first). Pure **guide**, not control — fits the processing philosophy;
     cross-platform launch is the main risk.

8. **Publishing / sharing.** Let users publish their collection to the web — the
   generalized successor to the Astronomy `build_site` static site (which M110
   intentionally did *not* port as its own UI). **Selective**: choose what goes
   public — catalog, goals/lists, the Summary dashboard, processing queue, object
   pages, journal entries, galleries/heroes — with privacy controls (e.g. exclude
   private journals; per-object/per-list publish flags). **Pluggable targets** via
   a publisher **registry** (mirroring the processing-workflow / device registries):
   **GitHub Pages first** (static-site export, like today's site), then other
   CMS/hosting platforms (Netlify, S3/CloudFront, WordPress/Ghost via API, …).
   Qt-free `publish/` engine renders selected derived data + journals + renders into
   the chosen artifact; the UI just picks sections + target + triggers it.
   *Sequencing:* high personal value (it replaces the site the user relies on today)
   and shares rendering concerns with phase 0 (same sections) — reasonable to pull
   forward once the multi-page UI and multi-list (item 5) are in place.

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

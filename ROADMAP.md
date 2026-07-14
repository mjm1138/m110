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

## MVP (v0.1) — "the Library" *(complete)*

0.1a–0.1f shipped, plus the own-data-root + bootstrap, the image-rendering port, the
two-axis data store (BUGS #13), and the processing-prep round-trip. Full breakdown
archived in **[`DONE.md`](DONE.md)**.

---

## Later phases (post-MVP)

> **UI look & feel** is planned separately in **[`UI_ROADMAP.md`](UI_ROADMAP.md)** —
> a design-system-first refresh toward a professional, image-forward photo tool
> (tokens + hand-rolled QSS, light/dark follow-system, Library list/grid, thumbnails
> everywhere, upgraded viewer). Cross-cuts the pages below.

0. **Navigation IA** *(done; refined pre-launch)* — a left nav rail + stacked pages
   with one shared Object detail. A pre-public-launch cleanup **slimmed the rail 8→4**:
   **Library · Overview · Import · Processing** (a 5th **Planning** pane landed
   post-beta with item 1's Checkpoint A). The Library (grid) is the landing
   home; **Overview** merges the former Summary dashboard + Goals management into
   collapsible sections; **Media / Journal / Sessions** were absorbed into the Library
   (a Deep-sky/Media scope, a List/Grid/Feed view segment, and the detail pane).
   Details in **[`DONE.md`](DONE.md)** and **[`UI_ROADMAP.md`](UI_ROADMAP.md)** (Phase 5).

1. **Session planning** — port the positional math (twilight / moon /
   transit-altitude / obstruction / start-altitude ceiling) into `planning.py`;
   build a planning surface; emit the session-plan document.
   > **Tuning arc complete (2026-07-14) — release-ready.** All five phases of
   > **[`PLANNING_ROADMAP.md`](PLANNING_ROADMAP.md)** landed on
   > `feature/session-planner`: single ranked source (`priorities.toml` retired) +
   > combined-folder rollup + feasibility gate · per-slot moon model · per-device
   > start-altitude ceiling · the night **sequencer** (non-overlapping 10-min
   > schedule, count control, night fill, marginal-slot ⚠) · calendar/date-edit UI
   > fixes + timeline overlays. Verified twice against independent astropy ground
   > truth (the 2026-07-13 [`prioritizer-review.md`](prioritizer-review.md) and the
   > 2026-07-14 [`PLANNING_BUGS.md`](PLANNING_BUGS.md) harness review + re-review).
   > Remaining follow-ups are non-blocking: BUGS #38b (reference V-mag audit),
   > #40d (restore version gate), #44 / Phase 6 (LLM skill foundation).
   **Foundation landed (2026-06-26):** the Qt-free engine is ported —
   `m110/planning.py` (`twilight` / `moon_summary` / `transit_altitude` + the
   seasonal/tonight `observability()` gate returning `{observable, hours_clear,
   transit_alt, nights_to_close, season}`) over `m110/planning_config.py` (site/
   device **profiles** in `.m110_internal_data/profiles/`, `default.toml` seeded
   idempotently) + `m110/horizon.py` (`.hrz`/CSV mask + the **glow**-layer
   `effective_floor` = `max(physical, glow)`). Coords reuse `catalog.load_coords`,
   season `catalog.season_from_ra`. The glow seam is wired but **empty** (filled by
   the next light-dome session). *Still open here:* a planning **UI surface**, the
   **plan-file** emit (item 2), and the **auto-prioritizer** scorer below.
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

   **Decided design (2026-07-03) — build plan.** Fleshed out with the user;
   supersedes the "TBD" note where it conflicts. The prioritizer and the session
   planner (item 2) are one interdependent arc — the planner *consumes* the
   prioritizer and both need the same site/glow foundation — shipped as **three
   checkpoints** so value lands incrementally, with the assistant (item 4) as a
   follow-on that layers over the deterministic tools.

   - *Foundation — a **Planning** view + site profiles.* ✅ **Shipped**
     (`feature/planning-profiles`): a new top-level **Planning** nav pane (5th pane;
     location profiles are conceptually subordinate to planning, so they live here,
     not a standalone pane) with a **location selector**, a **Priority targets** table
     (pins-only until the scorer lands), and a **Manage site profiles** section over
     the `SiteProfileEditor`. `planning_config` gained writers (`save_site` /
     `delete_profile` / `import_horizon_mask` / `active_profile` / `set_active_profile`
     / `load_active_site`) + an optional online `geocode` (Nominatim, degrades
     offline). Named **site profiles** (Home, Dark-site A…) carry coordinates/
     elevation, timezone, and an imported **`.hrz` horizon** (theo.rocks); the active
     one is persisted (`active_site_profile` setting). Prioritizer + planner read the
     selected site. The **light-dome layer** (next) and the scorer fill in on top.
     **Equipment inventory is deferred** out of this arc (the profile carries only what
     the scorer needs; multi-device stays #16-6d).
   - *Light domes — bundled offline auto-map (v1).* ✅ **Engine shipped**
     (`feature/glow-automap`, `m110/glow.py`). Build the azimuth-dependent glow floor
     from a **bundled public-domain populated-places dataset** (GeoNames): find towns
     within a radius (~50 mi, adjustable), compute each town's **bearing** + a **glow
     intensity** via Walker's Law (skyglow ∝ population × distance⁻²·⁵), map each to a
     dome (peak floor altitude + angular half-width; brighter/closer ⇒ taller/wider),
     and take the **upper envelope** as `glow_floor(az)`. Store it in the site profile
     (`<profile>.glow.hrz`, inspectable + hand-editable); calibrate via an optional
     observed **Bortle** anchor. Fills the `[glow]` seam; composes as
     `max(physical, glow)` via `horizon.effective_floor`; **filter-aware** (a softer
     `NARROWBAND_FACTOR` floor). Authored from the Planning → Manage site profiles
     editor ("Compute light-dome…"); the scaling constants are calibration defaults to
     tune against known sites.
     - **Dataset = GeoNames `cities1000`** (population ≥ 1000), produced by
       `tools/gen_geonames.py` → `m110/seed/geonames/cities1000.tsv.gz` (CC-BY 4.0,
       attributed in `NOTICE`). **Decided: NOT `cities15000`** — skyglow domes are
       dominated by *nearby* towns of a few thousand, so a 15k floor would silently
       drop the sources that matter most to rural / dark-site users and biases against
       the sparser southern hemisphere (the Reddit audience is global, both
       hemispheres). `cities1000` is global with signed lat/lon, and the Walker/bearing
       math is hemisphere-agnostic. `cities500` is a drop-in if finer granularity is
       wanted; **VIIRS** radiance is the uniform-global **v2** precision upgrade if the
       populated-places heuristic proves uneven anywhere.
   - *Deep-stack threshold — type-aware (shipped `feature/prioritizer`).* The
     "when is it deep?" threshold is now **per object type** (`build_derived
     .deep_threshold` / `DEEP_MIN_BY_TYPE`, calibrated to S50 experience: a **90-min
     SNR floor** for clusters/globulars/unlisted, planetaries 180, galaxies 240,
     emission/Sharpless/reflection/dark **360**), since required integration scales
     with surface brightness — a flat 60 min falsely marked faint nebulae done and
     ignored the sensor-noise floor. **Shared** between
     the status badge and the prioritizer's completion factor so they always agree.
     *Planned:* a **user-set integration target per object** (a per-object override of
     the type default; the object detail carries the target, the badge + scorer read
     it), and a **v2 surface-brightness** basis (magnitude + size) refining the
     per-type table.
   - *Scoring — two refinements to the (a)–(f) sum above.* **Trajectory-aware
     altitude:** beyond *how high* an object peaks in tonight's dark window, weight
     *which side of its seasonal arc it's on* — the dark-window peak rises to a best
     then declines over the weeks, so an object **past peak and falling** (closing
     opportunity) is bumped over one **rising toward peak** (can wait) at the same
     altitude; compute as the sign+slope of dark-window peak altitude sampled a few
     nights out (a finer partner to `nights_to_close`). **Graded short-window:** the
     prototype's hard `season_min_hours` gate becomes a scored/threshold knob so
     opportunistic short windows aren't silently dropped.
   - *Two-tier tuning (on the Planning surface).* **Persistent strategy** (saved
     baseline): a **strategy slider** capture-many ↔ go-deep; **per-object-type
     weights**; goal ranking; deep-stack threshold. **Session-time controls** (live,
     non-destructive re-rank): **Site**, **Filter (broadband/NB)**, **Available
     time**, **Brightness limit**, **Short-window threshold**, **Moon (auto/ignore)**
     — a mix of hard **filters** (exclude) and soft **nudges** (re-weight). **Night
     presets** save a toggle combo ("Backyard NB night", "Dark-site galaxy hunt",
     "Quick 1-hour"). Model: `ranked = score(persistent_weights) → filtered/
     re-weighted by session_toggles`; toggles never mutate the saved strategy
     (presets are the explicit save path). *Deferred knobs:* sky-quadrant
     constraint, framing/FOV (needs equipment), transparency, novelty/staleness.
   - *Manual overrides.* ✅ **Shipped** (`feature/manual-pins`, the beta slice):
     **Pin ▲ / Deprioritize ▼** on object rows in **Library** (right-click + ▲/▼ marker),
     **Goals** (right-click on membership rows), and **Summary** (pins surface in
     Priority targets, deprioritized excluded, empty-state, + right-click Pin/Deprioritize
     on the rows themselves), stored in a stable per-store `pins.toml` (`m110/pins.py`)
     that **survives regeneration** — resolving the "hand metadata is fragile" finding
     below. *Still to come with the scorer:* the **in-season / rank ordering** (today a
     pin is simply always shown), the optional **numeric nudge**, and composing
     `computed rank + overrides = final order` (today overrides act standalone).
   - *Build order — three shippable checkpoints:*
     - **A — Profiles + Prioritizer** ✅ **Shipped** (`feature/planning-profiles` →
       `glow-automap` → `prioritizer`): Planning pane + site profiles → light-dome
       auto-map → `m110/prioritize.py` scorer + overrides → priority UI (ranked table +
       strategy toggle + per-factor weights, live re-rank of a once/day-cached compute).
       *Follow-ups noted below:* trajectory-aware altitude, per-object integration
       targets, surface-brightness thresholds, and the two-tier session controls.
     - **B — Session Planner** *(field-guide slice shipped `feature/session-planner`)*:
       the **Plan a night** surface (pick site + night → per-target time windows via
       `planning.night_track`/`plan_night` → an auto-ordered plan (sets-soonest first)
       with include/reorder controls + a **`NightTimeline`** altitude chart) and the
       **field-guide emit** (`m110/fieldguide.py` → printable Markdown, saved under the
       `Plans/` axis, browsable/viewable in-app via `QTextBrowser.setMarkdown`). *Still
       open here:* **device plan-files** (SSC schedule JSON / NINA — item 2) once the
       schema/generator is ported + validated on a real device.
     - **C — Assistant** *(item 4; follows)*: the LLM layers over A+B's deterministic
       tools (proposes toggles/weights/plans; the engine still computes).

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
       `seed/objects.toml` to stay offline. *v1 (decided):* a **bundled GeoNames
       auto-map** (Walker's-Law domes within a radius) + optional Bortle/SQM anchor +
       manual override — see "Decided design" above; VIIRS is the v2 upgrade.
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
   *inside* the app, grounded in the user's own data. **This is "Checkpoint C" of
   the item-1 arc: a follow-on that layers over the deterministic prioritizer +
   planner** — the assistant *proposes* session toggles / weights / plans and
   *explains* the ranking, but the engine still computes (it never authors the
   priority list). Ships after A/B.

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

5. **Library, catalogs & goals — multi-list tracking + arbitrary objects** *(done; catalog library still growing)*.
   Four concepts shipped — **Object** / **Catalog/List** / **Goal** / **Library** (the
   user's mutable corpus = captured/annotated collection). Phases 5a–5d landed (per-store
   `library.toml`, bundled reference + catalog lists, the Goals nav page with custom
   goals, Simbad enrichment, the Library-=-collection reframe). **Six catalogs ship**
   (Messier, Caldwell, RASC Finest, Best-of-Sharpless, Bennett, Lacaille). Full detail
   in **[`DONE.md`](DONE.md)**. The **Manage goals** section (Overview) groups its
   catalog picker into collapsible **All-sky / Northern / Southern / Custom** sections, each catalog
   with a description caption + a "Learn more" link (per-catalog `hemisphere` +
   `source_url` in `seed/catalogs/*.toml`, surfaced via `goals.list_goals`).
   *Remaining (growth, not blocking):* more bundled catalogs
   from `next_catalog_lists.md` — **Herschel 400**, **Arp**, **Lunar 100**, AL Double Star
   (data-generation in `tools/gen_catalogs.py`).

6. **Import — robust, layout-flexible, multi-source** *(6a–6c done 2026-06-26/27;
   6d deferred)* (BUGS **#16**). Point the importer at **any directory**, recurse,
   recognize the source, classify by **FITS header**, preview/select/confirm, and route
   unrecognized files to a **holding area + manual assign** — **copy** by default
   (source untouched). **6a–6c shipped** (Import nav page + any-directory recursive scan;
   header-based classification + the `ingest.LAYOUTS` registry; the holding area) —
   full detail in **[`DONE.md`](DONE.md)**.

   - **DwarfLab Dwarf 3 support** *(done 2026-07-09, `feature/dwarf3-ingest`)*. A second
     device validated end-to-end against real Dwarf 3 output. Fixed two `.fit`-only
     assumptions that made Dwarf `.fits` captures invisible (`config.is_light_frame`
     diverted every sub to `working_files/`; `scan_sessions` skipped `.fits` + parsed
     Seestar-only filenames → zero sessions): a shared `config.FIT_EXTS` now covers
     `.fit`/`.fits` engine-wide, and `scan_sessions` is **header-driven** (`DATE-OBS`/
     `EXPTIME`/`FILTER`, Seestar filename as a fast path). Added a `dwarf` layout
     recognizer (`ingest._classify_dwarf_dir`) routing on-device session folders (subs →
     `lights/`, `stacked-16_*` + `stacked.jpg` → the `seestar-stacks/` device-stack tier,
     startrails → `Media/Startrails_{video,photo}/`, `Thumbnail/`/aux ignored), and
     `_usable_object` so an `OBJECT` of `''`/`Unknown` goes to the holding area instead of
     a literal target. No `.store_version` bump. Tests in `tests/test_ingest_dwarf.py`.

   - **6d — Lazy device-under-target + source differentiation** *(open, deferred)*.
     Record device/source per session; introduce the optional `Images/<target>/<device>/`
     path level only when a **2nd device** appears (flat = default device). A device
     registry keyed to planning device-profiles (`planning_config.load_device`). This is
     the phase that bumps `.store_version` + adds a `migrate.py` step — defer until a real
     2nd device exists. See [`DATA_MODEL.md`](DATA_MODEL.md).

   The **full import triage toolkit** (FITS header inspector, viewer/annotator,
   plate-solving) is split out as **item 9** (pulls in a solver dependency).

7. **Processing & curation UX** (BUGS **#17/#18/#19**). Generalize processing-prep
   past one user's habits and add curation:
   - *Configurable finished/intermediate hinting* (#17) — ✅ **hint set done**
     (`feature/finished-hints`): a preference-driven, user-editable keyword set
     (`m110/hints.py`, edited in Preferences) replaces the hardcoded `_classify`
     patterns (the source of the NGC 6992 miss); the three consumers (siril import,
     ingest loose-render, build_images hero-tier) all draw from it. ✅ **Gallery done too**
     (`feature/finished-gallery`): the detail pane splits into **Finished / Working files**
     groups with right-click **promote/demote/set-hero**, persisting per-image curation in
     journal frontmatter (`finished_extra`/`working_extra`) + the **hero-render
     identity-cache fix** (set-hero to an older image now re-renders). See DATA_MODEL
     "Image curation state".
   - *Advanced/custom workspaces* (#18) — named, on-disk-discoverable Siril (and
     other) working dirs that combine lights from disparate sources (#16) and
     **multiple objects** (mosaics, e.g. M81 + M82 + "M81 M82"), via hardlinks;
     custom split workflows. Introduces a workspace entity not bound to one target.
   - *Open In… / Process in…* (#19) — OS-level "open this image in <app>" and
     "process this object in <Siril/PixInsight/…>" (creating/selecting the working
     dir first). Pure **guide**, not control — fits the processing philosophy;
     cross-platform launch is the main risk.

8. **Publishing / sharing** *(first slice done 2026-06-29 — local static-site export)*.
   Let users publish their collection to the web — the generalized successor to the
   Astronomy `build_site` static site (which M110 intentionally did *not* port as its
   own UI). **Selective**: choose what goes public — catalog, the Summary dashboard,
   processing queue, object pages, journal entries, galleries/heroes — with privacy
   controls (exclude journals globally or per-object `private`; per-object `publish`
   opt-out). **Pluggable targets** via a publisher **registry** (mirroring the
   processing-workflow / device registries): then other CMS/hosting platforms
   (Netlify, S3/CloudFront, WordPress/Ghost via API, …). Qt-free `publish/` engine
   renders selected derived data + journals + renders into the chosen artifact; the
   UI just picks sections + target + triggers it.

   - **8a — Static-site export + registry** *(done 2026-06-29)*. Qt-free `m110/publish/`
     package: a publisher **registry** mirroring `processing.WORKFLOWS` (`static-site`
     available; `github-pages`/`netlify` placeholders), a Jinja2 site renderer, the
     testable selection/privacy core, per-object `publish` flag + journal `private`, and
     a **Library → Publish / share…** dialog. Detail in **[`DONE.md`](DONE.md)**.
   - *Deferred (BUGS #27):* GitHub Pages / git-push deploy, Netlify/S3/CMS targets,
     per-list publish flags, cross-publish image-cache reuse, auto-publish on refresh.

9. **Full import triage toolkit** (extends item 6's holding area). Deeper tools for
   files the header/layout classifier (6b) can't place: a **FITS header inspector**,
   an in-app **image viewer/annotator** for headerless frames, and **plate-solving**
   to recover pointing (→ object) when no usable `OBJECT`/`RA`/`DEC` exists. Builds on
   the 6c holding area + manual-assign UI. Deferred — pulls in a plate-solver
   dependency; only worth it once real-world messy imports demand more than manual
   assign.

10. **Library Backup** *(v1 done 2026-07-02)* — incremental backups to a user-defined
    destination + selective restore + retention. Qt-free engine `m110/backup.py` writes
    **hardlinked dated snapshots** (`rsync --link-dest` semantics in pure Python): each
    snapshot is a full, browsable tree, but files unchanged since the previous snapshot
    (all the immutable raws) are hardlinked, so incrementals cost only the changed bytes
    (verified: a 2nd no-change snapshot of the test store added **0 new bytes**). Scope is
    a **denylist** — everything under the store except regenerable derived data
    (`derived/`, `renders/`, `sessions.jsonl`) and the `siril/` working sandboxes — so new
    authored data is captured automatically. Each snapshot carries a **checksum manifest**
    for integrity/bit-rot verification. **Restore** defaults to extracting selected paths
    to a chosen folder (never touches the live store); restoring back into the store is
    available behind a create-vs-overwrite conflict preview + confirm. **Retention**
    (keep-N snapshots, default all / min-free-GB, default 100) prunes whole oldest snapshots, explicitly,
    never the last one. UI: Library → **Back up…** / **Restore…** (`backup_dialog.py` /
    `restore_dialog.py`, mirroring the publish worker/progress pattern) + an opt-in
    **auto-backup** (opt-in, background, unobtrusive): fires at **launch** when the last
    snapshot is older than the interval (default **12h**), *and* on an **hourly tick** that
    runs a **daily 02:00** snapshot while the app stays open (so a long-running session still
    gets daily backups, not just launch ones) — the interval doubles as a min-age guard so a
    fresh launch backup doesn't re-fire at 02:00 (`due_for_auto_backup` / `due_for_scheduled_backup`).
    Both share one cancel-on-quit worker; an interrupted snapshot is atomic (`*.incomplete` →
    rename, swept on next run) so quitting mid-backup never corrupts. It's an external-output
    feature (writes outside `<data_root>`) → no `.store_version` impact. *Deferred:* cloud/remote
    destinations, multiple destinations (3-2-1).

11. **"Lights Table"** A view with tools to quickly examine large numbers of .fits files. Should be a direct view of files, with autostretch (not looking at derived jpgs). Users can flag files with clouds, satellite/aircraft trails, and other imperfections. User can delete the file on disk with confirmation, or just mark it so it won't be hardlinked into workflow (e.g. "Siril") directories. Future versions might support batched background extraction, plate solving, SPCC, or maybe image analysis (find frames with satellite trails, find frames with low star count, etc)

12. **DwarfLab (Dwarf II / Dwarf 3) import support** *(beta-reach; extends item 6).*
    Add a second smart-telescope source alongside the Seestar so M110 reaches the #2
    smart-telescope community (DwarfLab owners on r/seestar-adjacent forums + the Smart
    Telescope Underworld Discord). This is **additive** — a new entry in the
    `ingest.LAYOUTS` registry + a `_classify_dwarf_dir()` classifier, mirroring the
    Seestar path; **no `.store_version` bump** (device stays flat per the 6d deferral —
    record device per-session, don't introduce `Images/<target>/<device>/` until someone
    actually shoots one target on both scopes).

    **What the public docs already give us** (help.dwarflab.com "Files Stored in DWARF
    3 / DWARF 2"): an `Astronomy/` root with well-documented subfolders —
    `DWARF_RAW/` (per-session light-frame folders), `DWARF_DARK/`, `CALI_FRAME/`,
    `Restacked/` (Mega Stack), `STARTRAILS/`, `Solving_Failed/`. Per-session folders are
    self-identifying: `DWARF_RAW_<TARGET>_EXP_<n>_GAIN_<n>_<YYYY-MM-DD-HH-MM-SS-FFF>`, so
    the **object name is parseable from the folder name** (cleaner than needing headers).
    Each session folder holds the raw subs (FITS *or* TIFF — user choice on Dwarf 3), the
    stacked outputs (8-bit JPG, 16-bit PNG, 16-bit FITS single+stacked), `*_thumbnail`
    files, and a **`shotsInfo.json`** sidecar carrying RA/DEC + target + exposure/gain +
    IR-filter status + stacking stats (a rich structured metadata source; also feeds the
    #12 RA/Dec pointing check).

    **Proposed mapping:** `DWARF_RAW_<target>_…/` subs → `Images/<target>/lights/`; the
    in-folder stacked FITS/PNG → `stacks/` (or a `dwarf-stacks/` tier analogous to
    `seestar-stacks/`); `DWARF_DARK/` → darks; `CALI_FRAME/` → calibration; ignore
    `Solving_Failed/`, thumbnails, JPG previews. Importer 6a's any-directory recursive
    scan means a Dwarf user can already point M110 at their SD card before auto-detection
    exists — the classifier is the real work; **auto-detection** is a small add (probe a
    volume/dir for `Astronomy/DWARF_RAW`, the analogue of the Seestar `MyWorks` probe).

    **Two gaps to close with one real capture dump before shipping** (not blockers):
    (1) the **exact raw-sub filename/extension** — the session folder mixes single subs
    *and* the stacked FITS, so the classifier must tell them apart (Seestar solves this
    via the `Light_*` prefix); (2) **whether individual subs carry RA/DEC/OBJECT in the
    FITS header**, or only the stack — if subs lack pointing, fall back to the folder name
    / `shotsInfo.json` for object + pointing (still fully workable). *Action:* recruit a
    Dwarf II/3 owner from the same forums to share a real `Astronomy/` dump to confirm
    both. Cross-ref: item 6 (import), 6d (multi-device), BETA.md §3.

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

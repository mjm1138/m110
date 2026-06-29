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

0. **Site-parity multi-page UI** *(done)* — nav rail + stacked pages (Summary ·
   Catalog · Processing · Sessions · Journal · Media), Summary as the landing page,
   one shared Object detail reachable from every object link. Plus the Media page
   (BUGS #11). Details in **[`DONE.md`](DONE.md)**.

1. **Session planning** — port the positional math (twilight / moon /
   transit-altitude / obstruction / start-altitude ceiling) into `planning.py`;
   build a planning surface; emit the session-plan document.
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

5. **Library, catalogs & goals — multi-list tracking + arbitrary objects** *(done; catalog library still growing)*.
   Four concepts shipped — **Object** (intrinsic reference data; season derived),
   **Catalog/List** (bundled, immutable membership sets), **Goal** (a catalog being
   actively pursued, with progress), **Library** (the user's mutable corpus =
   captured/annotated collection). Phases 5a–5d landed: per-store `library.toml`,
   the bundled object reference + catalog lists, the Goals nav page (select/create/
   edit custom goals), reference + online (Simbad) enrichment, and the
   Library-=-collection reframe. **Six catalogs ship** (Messier, Caldwell, RASC
   Finest, Best-of-Sharpless, Bennett, Lacaille). Full detail in **[`DONE.md`](DONE.md)**.
   *Remaining (growth, not blocking):* more bundled catalogs from
   `next_catalog_lists.md` — **Herschel 400**, **Arp**, **Lunar 100**, AL Double Star
   (data-generation in `tools/gen_catalogs.py`).

6. **Import — robust, layout-flexible, multi-source** *(6a–6c done 2026-06-26/27;
   6d deferred)* (BUGS **#16**; ingest →
   *Import*). Today's ingest is fixed to two special-cased sources (the `Inbox/`
   staging area it *moves* from, a mounted Seestar `MyWorks` it *copies* from) and
   classifies purely by **folder-name convention** (`<obj>_sub/` → lights, `<obj>/`
   of `Stacked_*` → seestar-stacks, `*_photo`/`*_video` → media); a one-level scan
   that **silently ignores** anything else (a flat FITS pile, a ZWO ASIAIR tree, an
   arbitrary directory, calibration frames). The "Lightroom for smart telescopes"
   target: **point the importer at any directory**, recurse, recognize the source,
   classify by **FITS header**, present the familiar select/deselect preview, and
   give unrecognized files a **holding area + manual assign** instead of dropping
   them. **Copy** by default (leave the source alone), preserving original filenames.

   **Decided** (2026-06-26): rename **Ingest → Import** (user-facing strings, nav,
   menu/shortcut; engine module `ingest.py` keeps its internal names). Promote to a
   **top-level Import nav page**. The special-cased Inbox/Seestar *sources* go away —
   they're just directories you browse to (a **directory chooser + Favorites/Recent
   places** makes `/Volumes/Seestar`, `~/Astronomy/Images` one click); `Inbox/` is
   repurposed on-disk as the **holding area / import queue**. **Lazy
   device-under-target** for source differentiation (see [`DATA_MODEL.md`](DATA_MODEL.md)):
   flat `Images/<target>/` stays the implicit **default device**, the
   `Images/<target>/<device>/` level appears only when a 2nd device shows up — no
   forced migration. Phases:

   - **6a — Import view + any-directory source** *(done 2026-06-26)*. Top-level
     **Import** nav page (the old modal Ingest dialog superseded; `Ctrl+I`/toolbar
     repointed to it). Directory chooser + **Favorites/Recent places** (the
     special-cased Inbox/Seestar source entries removed; recents persist in settings,
     a mounted Seestar + the Inbox auto-appear). **Recursive** `ingest.scan_directory_plan`
     walks an arbitrary tree (Seestar-shaped folders found at any depth). Always
     **copy** (source untouched), preserving filenames, with content-aware **collision
     handling** in `apply_ops` — on a dest name clash a **checksum/size** compare →
     *duplicate*→skip vs. *distinct*→minimal `_N` suffix (replaces skip-by-name-only;
     header compare wasn't needed). Preview/select/confirm + pointing-remap unchanged.
     Classification is still **folder-name** based — header-based sorting is 6b.
   - **6b — Header-based classification + layout registry** *(done 2026-06-27)*.
     Classification now reads the FITS header (`ingest.frame_info` →
     OBJECT/IMAGETYP/FILTER/RA/DEC, header-only via `fits.getheader`) so unstructured
     dumps sort and **calibration frames** (`IMAGETYP=DARK/FLAT/BIAS`, folded from
     ZWO/INDI variants by `_normalize_imagetyp`) route to `darks/`/`flats/`/`biases/`
     (new `config.{darks,flats,biases}_dir`). New op **kinds** `dark`/`flat`/`bias`/
     `siril-stack`/`finished` join `light`/`stack`/`media`; **header wins** over folder
     name (a stray DARK in `_sub` → `darks/`). A **layout-recognizer registry**
     (`ingest.LAYOUTS`, mirrors `processing.py`'s workflow registry) names the detected
     source per group — **seestar** (folder conventions), **m110-store** (the
     `~/Astronomy/Images` precursor: `FITS/<obj>/{lights,darks,…,stacks}`, `Finished
     Images/<obj>`, `Seestar_stacks/<obj>`; `process/`+`siril/` sandboxes skipped),
     **raw-fits** (loose FITS header-sorted), and **asiair** (registered-disabled
     placeholder). The app's own `Images/` content tree is never re-imported into
     itself (`_in_own_store`). The Import preview shows the kind + detected layout
     (tooltip). Pairs with #12's pointing logic (`frame_radec`).
   - **6c — Holding area + manual assign** *(done 2026-06-27)*. **Nothing is silently
     ignored:** `_classify_dir` now **sweeps** every unclaimed content file (headerless
     FITS, stray images/video — junk/hidden/`*_thn.` excluded via `_is_content_file`)
     into the repurposed `Inbox/` **holding area** as `kind="unassigned"` ops. The
     Import view gained an always-visible **Holding area panel** (a vertical splitter
     below the scan preview) listing held files grouped per source folder with an
     editable **Object** dropdown + a **Kind** dropdown (`ASSIGNABLE_KINDS`) + **Assign**;
     `ingest.assign(group, object, kind)` rebuilds the group as **move** ops and
     `apply_ops` moves them out of `Inbox/` into the content tree (`Images/<obj>/<kind>`
     or `Media/`), with the same alias-learning prompt (`ingest.add_alias`). Engine
     adds `scan_holding`/`holding_count`/`assign`; `Inbox/` is no longer a user-facing
     *source*. Off-catalog assigns just create `Images/<obj>/…` (the refresh
     auto-adds them to the Library).
   - **6d — Lazy device-under-target + source differentiation.** Record device/source
     per session; introduce the optional `Images/<target>/<device>/` path level only
     when a 2nd device appears (flat = default device). A **device registry** keyed to
     planning device-profiles (`planning_config.load_device` is the existing seam).
     This is the phase that bumps `.store_version` + adds a `migrate.py` step — defer
     until a real 2nd device exists.

   Foundational for everything multi-scope; 6a–6c have no hard gate (build on #12
   pointing, #9/#10 grouped+selectable preview, the two-axis store). The **full import
   triage toolkit** — FITS header inspector, in-app viewer/annotator for headerless
   files, plate-solving — is deferred to its own later item (pulls in a solver
   dependency).

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

   - **8a — Static-site export + registry** *(done 2026-06-29)*. New Qt-free
     `m110/publish/` package: a publisher **registry** (`PUBLISHERS`, `run_publish`,
     `enabled_target_ids`) mirroring `processing.WORKFLOWS` — `static-site` available,
     `github-pages`/`netlify` registered-disabled placeholders. `site.py` (ported from
     `build_site.py`) renders Jinja2 templates → a user-chosen **local folder** from
     the existing derived JSON + `build_images` derivatives + journals; `select.py` is
     the testable selection/privacy core; `images.py` reuses `build_images` for web
     thumb/full derivatives. Per-object `publish` flag (`catalog.set_publish_flag`,
     right-click in the Library) + journal `private` frontmatter. **Library → Publish /
     share…** dialog (section/target/output pickers) runs on a threaded worker behind a
     modal progress+Cancel. Optional `publish` extra (jinja2 + markdown; degrades via
     `PublishDepsMissing`).
   - *Deferred:* GitHub Pages / git-push deploy target, Netlify/S3/CMS targets,
     per-list publish flags, cross-publish image-cache reuse, auto-publish on refresh.

9. **Full import triage toolkit** (extends item 6's holding area). Deeper tools for
   files the header/layout classifier (6b) can't place: a **FITS header inspector**,
   an in-app **image viewer/annotator** for headerless frames, and **plate-solving**
   to recover pointing (→ object) when no usable `OBJECT`/`RA`/`DEC` exists. Builds on
   the 6c holding area + manual-assign UI. Deferred — pulls in a plate-solver
   dependency; only worth it once real-world messy imports demand more than manual
   assign.

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

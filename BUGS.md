# Bugs & Improvements

Open issues + the improvement backlog. **Completed items are archived in
[`DONE.md`](DONE.md)** (with a concise fixed-bugs log); this file tracks only
what's still open. Larger items map to [`ROADMAP.md`](ROADMAP.md) phases.

Legend: `[ ]` open · `[~]` partially done

---

## Processing & curation UX  *(→ ROADMAP item 7)*

- [x] **Import misses output saved outside the sandbox** (done — `feature/reimport-object-root`).
  If Siril's working directory was set to `Images/<target>/` instead of its `siril/`
  sub-folder, the run's renders/stacks landed loose in the object dir and *Import finished
  work* never saw them (`siril._sandbox_outputs` only walked `siril/`). Fix:
  `siril._root_outputs` also scans the object dir (skipping the managed tiers, raw inputs,
  and the sandbox itself), and `has_unimported_output`/`scan_finished` draw from both via
  `_finished_outputs`. Paired with a **"Reveal working folder"** button on the object
  detail pane (opens `Images/<target>/siril/` so Siril's working dir is set to the right
  place) and a bolder callout in the sandbox `next-steps.md`. A lightweight down-payment on
  the object-side "Process in…" of **#19**; the full launcher is still open.

- [x] **#85 — Import ignores stacks/renders the user sorted into folders themselves**
  (done — `feature/import-tier-classify`). *Import finished work* only recognized a `.fit`
  as a stack/deliverable when its **filename** carried a "finished" hint
  (`processed`/`final`/…), so output the user (or Siril) saved into `siril/stacks/` and
  `siril/finished/` subfolders with plain names (`M_27_…_og.fit`, `M_27_…_2026-07-21.fit`)
  was dropped — only the `.jpg` came through. Fix: **directory wins** — `siril._classify`
  now takes the managed tier a file sits under (at any depth, sandbox *or* object root) and
  classifies by it (`stacks/` → stack, `finished/` → deliverable; no filename hint, and the
  intermediate/star-layer veto is not applied — the user filed it there on purpose),
  falling back to the filename vocabulary only for *loose* files. The `stacks/`/`finished/`
  tiers are now scanned too, with a `p == dest` guard in `_finished_outputs` so files
  already correctly in place don't flood the preview. (Thanks to @devonjones.)

- [ ] **#28 — Siril prep is confusing (per-filter layout + stale dirs).** (Bug D from the
  M27 investigation.) The single↔multi-filter sandbox layout is hard to follow: a target
  that becomes "multi-filter" grows `siril/<FILTER>/lights/` job dirs, but an earlier
  single-filter prep's `siril/lights/` (and any orphaned filter dir) is **not cleaned up**,
  so the user can open a stale folder with a partial sub set (exactly what happened on M27:
  stale `siril/lights/` had 461 while the live `siril/LP/lights/` had all 1223). Improvements:
  (a) reconcile/clean orphan job dirs when the filter composition changes (carefully —
  never nuke an in-progress run); (b) surface which sandbox dir is current (next-steps.md
  already names it, but the stale dir shouldn't linger); (c) reconsider whether per-filter
  split should be **opt-in** — a Seestar user is effectively single-filter (LP or none), so
  the split mostly adds confusion. Edge case today (one object shot with mixed filter
  settings), but the stale-dir cleanup is the generally-useful piece.

- [ ] **#17 — Intermediate / finished file hinting.** The naming patterns for
  intermediate and finished images are built on Mike's particular habits, and are
  probably not generalizable. Two enhancements can help:
  - ✅ **Preference pane hint set (done — `feature/finished-hints`).** The
    finished/intermediate vocabulary is now a single user-editable keyword set in
    `m110/hints.py` (defaults `processed/final/finished` + `starless/starmask`),
    edited in Preferences → "Finished-image hints", persisted in `settings.json`
    (`finished_hints`), read live. The three former hardcoded copies
    (`siril._classify`, `ingest._is_finished_raster`, `build_images._is_intermediate_fit`)
    now draw from it — a stranger can add their own keywords instead of silently
    misclassifying.
  - ✅ **Gallery + curation done** (`feature/finished-gallery`). The detail pane splits
    into **Finished** / **Working files** groups with right-click **Set as hero** /
    **Mark as finished** / **Mark as working**. Per-image overrides persist in journal
    frontmatter (`finished_extra`/`working_extra`; `objects.get_curation`/`set_curation`);
    galleries derive from tier + overrides. Terminology settled on "finished"/"working".
  - ✅ **Hero-render cache fixed** (shipped with the above). `build_images._render_hero`
    now keys on source **identity** (a `renders/hero/<slug>.src` sidecar = source
    rel-path + `img_hash`), not mtime — so picking an **older** image as hero re-renders
    instead of leaving a stale hero. `rebuild_hero(slug)` re-renders one hero
    synchronously for the interactive action.
  - *Open question (deferred):* a "favorites" designation alongside "hero" (multiple
    favorites display) — not needed for beta.
- [ ] **#18 — Advanced processing prep.** Create Siril (and other workflow) working
  directories populated with lights from **disparate sources** (see #16) and
  **disparate objects** (e.g. combine m81 + m82 + "m81 m82" as a mosaic), via hardlinks
  (only processing/intermediate files cost disk). Custom workspaces must be easily
  discoverable by name on the filesystem. Also support custom **split** workflow
  directories, like the LP / no-filter splits created automatically today.
- [~] **#19 — Open In… / Process in…** (cross-platform launch is the main risk.)
  **Core shipped** (`feature/reimport-object-root`). Right-click an **object** (Library,
  Processing page, or the detail-pane button) → **"Process in Siril"** launches Siril with
  the object's working directory set (`siril -d <sandbox>`; a chooser when the sandbox is
  split per-filter). Right-click a gallery **image** → **"Open in default app"** /
  **"Reveal in file manager"**. Pure **guide**, not control — M110 starts the tool and gets
  out of the way. Cross-platform launch lives in the Qt-free `m110/launch.py`: settings
  override (`external_app_paths`) → OS-standard locations (macOS `/Applications/Siril.app`,
  Linux `siril`/`siril-cli` in PATH, Windows Program Files) → graceful reveal-folder
  fallback; the path is settable in *Preferences → Processing tools*. **macOS must launch
  via `open`** (`_launch_macos`), not a direct `Popen`: Siril's bundled Python is
  hardened-runtime + library-validated, so it only spawns when Siril is its own *responsible
  process* — a child-process launch left M110 responsible and Siril SIGKILLed its own Python
  ("unable to spawn python" / "version check failed"). Trade-off: `open --args -d` sets the
  working dir only on a **cold start** (ignored if Siril is already open — a small UX gap; a
  future `open -n` new-instance option could close it if Siril tolerates concurrent
  instances). **Open:** (a) a
  configurable multi-app list for the image "Open In…" submenu (only default-app + reveal
  today); (b) PixInsight/DSS/APP as launchable targets (registered in `processing.WORKFLOWS`
  but not yet in `launch._TOOLS`); (c) custom/combined workspaces per #18. **Verify on real
  Linux/Windows** — auto-detect paths are coded but only exercised on macOS + in tests.

## Import

- [~] **#16 — Robust, layout-flexible, multi-source import.** **6a–6c shipped**
  (any-directory recursive scan, FITS-header classification + layout registry,
  holding-area manual assign — see [`ROADMAP.md`](ROADMAP.md) item 6 / [`DONE.md`](DONE.md)).
  **Open: 6d — lazy device-under-target** — record device/source per session; introduce
  the optional `Images/<target>/<device>/` path level (+ a `.store_version` bump + a
  `migrate.py` step) **only when a 2nd device appears** (flat = default device). A device
  registry keyed to planning device-profiles (`planning_config.load_device`). Deferred
  until a real 2nd telescope exists. **Note (verified 2026-07-07):** the per-unit scope id
  is in **FITS only** — `TELESCOP = S50_<8hex>` (e.g. `S50_15e7e390`); the S50 `.jpg` EXIF
  carries model/firmware but **no** unit id. So device attribution must key off FITS
  `TELESCOP`; a JPEG-only import can't tell two same-model scopes apart. See
  [`DATA_MODEL.md`](DATA_MODEL.md) → "Import & multi-source / multi-telescope".
- [x] **#57 part B3 — preserve an imported Naztronomy preset** (`feature/import-siril-preset`).
  Completes #57: `ingest._claim_siril_preset` detects a `naztronomy_smart_scope_presets.json`
  in an imported Siril project (project root or a `presets/` subdir; object gated on naming a
  known catalog object) and routes it into that object's `siril/presets/` (new `siril-preset`
  kind), so autoprep **preserves** the user's preset instead of generating a fresh default (a
  non-default preset already survives `apply_prep`). With #57 part A (`feature/import-siril-projects`)
  and part B (`feature/import-siril-sandbox`), an existing Siril project imports its frames,
  reproduces in the `siril/` sandbox with calibration hardlinked, and keeps the user's preset.
- [~] **#57 part B — calibration-aware Siril sandbox** (`feature/import-siril-sandbox`).
  Prep was lights-only, so an imported Siril project's darks/flats/biases never reached the
  `siril/` sandbox and couldn't be used. Now `siril.plan_prep`/`apply_prep` **hardlink**
  `darks/`/`flats/`/`biases/` into the sandbox root (shared across filters; free, like lights)
  and flip the Naztronomy preset's matching toggles when present; `is_default_preset` reads the
  toggles back so a calibration-on default is still re-tunable; the calibration tiers join
  `_ARCHIVE_KEEP` so an import doesn't sweep them away. **Still open (B3):** detect a
  `naztronomy_smart_scope_presets.json` in the imported project and carry it into
  `siril/presets/` (preserved instead of regenerated) — that half is ingest-coupled and belongs
  with #57 part A (`feature/import-siril-projects`, PR #88).
- [~] **#57 — Import folders already set up for Siril.** Point import at existing Siril
  project folders and have the frames pulled in without reorganizing the source. **(A)
  recognition landed** (`feature/import-siril-projects`): the scanner recognizes a Siril/M110
  **project root** (a folder that *contains* lights/darks/flats/biases) and routes the loose
  files Siril left beside those folders — a stacked `.fit` → `stacks/`, another
  processing-product `.fit` → `working_files/`, a finished render → `finished/` — instead of
  stranding them in the holding area; a `<obj>_sub` folder imports under the object's real id
  (`M63`, not `M63_sub`); and a folder of loose subs with no `lights/` subdir routes by the
  folder name **when it names a known catalog object** (a generic/session-named folder still
  goes to holding). **(B) follow-up (open):** reproduce the project in the
  `Images/<target>/siril/` sandbox — hardlink darks/flats/biases alongside the lights (prep is
  lights-only today) and preserve an imported `naztronomy_smart_scope_presets.json` rather than
  regenerating it.
- [ ] **Full import triage toolkit**  *(→ ROADMAP item 9).* Deeper tools for files the
  classifier can't place — FITS header inspector, in-app viewer/annotator, **plate-solving**
  to recover pointing. Extends the #26 holding area; pulls in a plate-solver dependency,
  so deferred until real-world messy imports demand more than manual assign.

- [ ] **#40d — Restore has no store-version gate.** `backup` records `store_version` in each
  snapshot manifest and `.store_version` isn't denylisted, so a **full** restore brings back the
  old stamp and `migrate` re-runs on next launch (self-healing ✓). But `restore_dialog` offers a
  **per-file checkable tree** and neither dialog reads `store_version` — so a **partial** restore
  can put a pre-v4 `library.toml` back under a v4 stamp, where migration won't re-run. The #40c
  splitter hardening means this no longer causes an under-count (the pair still splits), but the
  stale pseudo-object rows would linger until manually removed. Worth a version-mismatch warning
  on restore (and/or forcing `.store_version` to be restored with `library.toml`).

## Library & metadata enrichment

- [ ] **Metadata enrichment: discoverability + smarter sources.** Today the offline
  reference fill is effectively automatic (a capture → `add_captured_objects` pulls full
  reference metadata), and online (Simbad) enrichment is a deliberate **explicit** action —
  it makes external network calls, so it's kept off the deterministic offline refresh path
  (also: many faint targets genuinely have no Simbad mag/size, so an auto-on-refresh pass
  would re-query them forever without a "tried, got nothing" cache). Grew out of the #64
  discussion. **No behavior change wanted now** — backlog of improvements:
  - **Surface objects that need enrichment.** You currently discover gaps only by
    right-clicking one object at a time (the greyed-out-menu confusion was a symptom — now
    fixed to always-selectable). Make it first-class: a Library filter / badge / count for
    "has metadata gaps," so a user can see *which* objects to enrich and enrich them in bulk
    without hunting object-by-object.
  - **Prefer a common name over the bare catalog id.** When a well-known common name exists
    (e.g. "Hercules Cluster" for M13, "Ring Nebula" for M57), surface it alongside/instead of
    the Library id in labels — sourced from the reference/Simbad during enrichment.
  - **Plate-solve as a last resort.** When name/designation lookup can't identify or position
    an object, plate-solve a frame to recover identity/coordinates — a tier below reference →
    Simbad. Overlaps the import-triage plate-solver (see "Full import triage toolkit" under
    **Import**); share the dependency.
  - *(Optional, low-risk):* also run the offline `fill_all_missing_metadata()` on refresh so
    pre-existing / off-catalog entries self-heal from the bundled reference without a manual
    step (network still stays explicit). Reference-data quality itself is tracked separately
    under **Planning / prioritization** (the Simbad-magnitude item).

## Planning / prioritization

- [~] **#21 — Auto-prioritizer / target scoring.** The scoring engine **shipped**
  as ROADMAP item 1 Checkpoint A (`m110/prioritize.py`: goals + season urgency +
  completion×strategy + per-type weights + tonight feasibility + pins; strategy
  toggle + weight spinboxes on the Planning pane — see [`DONE.md`](DONE.md), incl.
  the archived scoring-model design + Astronomy-prototype findings). *Still open:*
  the **session-time controls + night presets** (the second tuning tier) and the
  other refinements listed under ROADMAP → "Session-planning follow-ups".
  - ✅ **Priority-list tuning (2026-07-17 in-app review, `feature/prioritizer-tuning`).**
    Three fixes surfaced planning a real July night — detail in [`DONE.md`](DONE.md):
    - **"Visible tonight" toggle** (default on) filters the ranking to targets actually
      up tonight (`prioritize.filter_visible_tonight` — hides `observable is False`, keeps
      unknown/degraded). Fixes out-of-season Messiers (M44/M97/M3/M35/M36…) floating into
      the top on goal+completion while the scorer only *softly* graded observability.
    - **Sequencer honors `count`.** `sequence_plan` no longer trims a primary to hit its
      deep-stack target (each chosen object runs its **full slot** — overshoot beats
      seeding a marginal one) and **drops any slot < `MIN_SLOT_MIN` (30 min)** — no
      10-minute stubs. The `deep_remaining` duration cap was removed.
    - **Per-type weight controls** — Planning → *Tuning weights* exposes Galaxies /
      Globular / Open clusters / Nebulae multipliers (`prioritize.TYPE_GROUPS`; the engine
      already applied `type_weights`).
*Session-planner items (#40–44) are phased in [`PLANNING_ROADMAP.md`](docs-archive/PLANNING_ROADMAP.md).*

- [ ] **#44 — LLM session-planner skill foundation** *(→ PLANNING_ROADMAP Phase 6;
  post-release follow-on).* Lay the foundation for an M110-native session-planner
  skill over the deterministic engine — consult the `astro-session-planner` skill +
  `scripts/`/`workflows/` in ~/Astronomy and work from there. This is the point where
  an LLM plugs in (explains/tunes/narrates; the engine stays the source of truth).

*Findings from the 2026-07-13 prioritizer/planner review below — reasoning in
[`prioritizer-review.md`](docs-archive/prioritizer-review.md).*

- [ ] **#38b — Reference magnitude audit (B-mag leakage) + coverage backfill.** Some
  SB-floored entries are **data errors**, not faint targets: `seed/objects.toml` lists the
  **Helix (NGC 7293) at mag 13.5** (real V ≈ 7.3) and NGC 4945 at 14.4 (real ≈ 9.3) — Simbad
  B-mag/photographic leakage from the build-time fetch. `SB_FLOOR = 0.3` keeps bad data from
  burying a showpiece, but the fix is in `tools/gen_catalogs.py`: prefer V-mag explicitly,
  flag suspect rows, and re-run the backfill (coverage gaps today: 145 missing magnitudes,
  41 missing sizes of 450). Build-time only; runtime stays offline.
- [ ] **#40b — Combined-folder rollup in the *engine* (processing queue + Library).**
  `build_totals`/`build_processing` still key on `by_folder`, so genuinely-separate on-disk
  folders (`M81`, `M82`, **and** `M81 M82`) surface as **three rows** in the Processing queue
  and three objects in the Library — the small solo captures (M81 126 min, M82 13 min) read as
  "not processed / new". #39 fixed only the prioritizer; extending the family rollup into
  `build_totals`/`build_processing` (a combined folder subsumes its members' solo folders)
  would collapse the queue + Library to one target family. Needs a rule for how a solo folder
  folds into a combined one. *(Superseded in framing by #40c — see there: the queue showing one
  row per capture **target** is correct; the real defect is upstream.)*

## Session analytics / capture diagnostics

- [ ] **#45 — Per-session capture diagnostics (why is rejection high?).** Analyse an
  incoming session's sub timestamps to explain the yield the app already shows. Grounded in
  a read-only proof of concept over real data (4,799 subs parsed in ~20 ms) + the
  2026-07-18 discussion; corrected framing below (an earlier draft had two facts wrong).

  **The signal is nearly free.** `scan_sessions` already parses the Seestar filename's
  `…-<YYYYMMDD>-<HHMMSS>.fit` and *discards the time*. Keeping it gives per-sub timestamps
  with zero new I/O for Seestar; the Dwarf/header path already reads `DATE-OBS`.

  **Two acceptance gates, not one** — name them distinctly:
  1. **Capture gate** — the Seestar/Dwarf reject frames *in real time* and **don't save
     them** ("Save Every Frame" does **not** save the rejected ones — community-confirmed).
     So gaps in the *saved* cadence are the real-time-drop signal, and **number-of-saved-FITS
     vs altitude/declination is a valid metric** (a community experiment used exactly this).
     This is the altitude-sensitive gate and the one M110 doesn't measure yet.
  2. **Stack gate** — `STACKCNT`/`LIVETIME` rejection at integration. **Already computed**
     by `build_processing`.
     The prize is the **loss ledger** joining both: `expected (cadence×window) → saved
     (capture gate) → stacked (stack gate)`.

  **Metrics (Tier 1, cheap, filename-only for Seestar):** first/last light; real cadence &
  per-frame overhead (median inter-frame Δ − exposure); **capture acceptance = saved ÷
  expected**; duty cycle (integration ÷ wall-clock span); gap-size histogram (**small
  single-frame drops** = per-frame quality rejection, attributable to a precise altitude;
  **large gaps** = interruptions — meridian/azimuth flip, refocus, clouds — *not* per-frame
  rejections); contiguous capture blocks; largest-gap clock times.

  **Altitude / declination correlation (Tier 2, astropy, lazy):** for each *saved* sub we
  know its exact altitude (timestamp + coords + observer), so compute **acceptance per
  altitude band** directly — no need to guess a dropped frame's time (that earlier
  "can't know the altitude of a rejected frame" claim was wrong: the gap is bounded by the
  saved frames on either side and altitude varies <~0.25°/min, so drops *are* attributable
  to well within any band). **Self-contained on Seestar** — its header carries `SITELAT`/
  `SITELONG` alongside `RA`/`DEC`/`DATE-OBS`, so altitude needs no site profile; **Dwarf
  headers lack `SITELAT`/`SITELONG`**, so Dwarf altitude falls back to the active site
  profile. Expect a **mount-mode-dependent shape**: alt-az field rotation ∝ 1/cos(alt) →
  worst near zenith (users report 90–95% rejection >75°); EQ mode nulls that, leaving
  declination-drift + low-altitude airmass. **`mount_mode` now comes from the header
  `EQMODE` card** (the `fix/mount-mode-eqmode` change), so the analysis can split on it
  honestly.

  **Gotchas:** (a) analyse per **observing night**, not calendar date — the PoC's date
  bucketing fused two nights into a bogus 1,149-min "gap"; split on any multi-hour gap.
  (b) Dwarf `DATE-OBS` is *"end of exposure"* vs Seestar's start — offset by one exposure
  when computing cadence. (c) Tier-3 header-only extras (`FOCUSPOS` focus drift, `CCD-TEMP`/
  `DET-TEMP`, gain) need a per-sub header read → opt-in.

  **Home:** fold `session_stats` into `scan_sessions` (Tier 1, on refresh; store the summary,
  not raw timestamps); surface in the `DetailPane` Sessions table; reuse `NightTimeline` for
  the Tier-2 altitude-vs-time chart with gaps overlaid. Companion to the `build_processing`
  rejection number.

## Publishing  *(→ ROADMAP item 8)*

- [~] **#27 — Publishing follow-ups** (8a landed — local static-site export). Targets/
  refinements that build on the `publish/` engine + registry: (a) ✅ **GitHub Pages
  deploy** *(done 2026-07-15, `feature/publish-ghpages` — see DONE.md)*: system-git
  force-push of the rendered site to `gh-pages` (`m110/publish/ghpages.py`), repo from
  the dialog/settings; (b) **Netlify /
  S3·CloudFront / WordPress·Ghost** targets; (c) **per-list (goal) publish flags** (8a
  ships per-object `publish` + per-journal `private` only); (d) **cross-publish image-cache
  reuse** (8a regenerates web derivatives each run; the publish analogue of #14); (e)
  optional **auto-publish on refresh**. `publish.PUBLISHERS` + `PublishOptions` are the
  stable seams; each target is an adapter.
- [ ] Publishing: User should have the option to add a copyright notice to published images
- *(2026-07-15 live-library test findings, rounds 1+2 — deploy progress bar,
  no-save-without-publish, push timeout, cancel→beach-ball/orphaned push,
  working-files upload bloat, stale-output-never-torn-down, three-level gallery
  selection, GitHub-setup docs, processing-page/app alignment — all fixed on
  `feature/publish-ghpages` before merge; see DONE.md.)*
**Other Publishing Targets**: Astrobin, Cloudynights, Other fora?

## Backup & restore  *(→ ROADMAP item 10)*

- [ ] **Surface the destination's hardlink capability in the backup UI.** `create_snapshot`
  probes the **destination** filesystem (`backup._supports_hardlinks`, `backup.py:238`) and
  silently falls back to byte-copying *every* file when links aren't supported — so on an
  exFAT/appliance/rclone-mounted destination each nightly snapshot is a **full copy** of the
  library and the user has no way to know. Show the probe result in `backup_dialog` (and per
  snapshot in the restore picker, the manifest already records `hardlinks`): "unchanged files
  are shared between snapshots" vs "every snapshot stores a full copy". Cheap, independent of
  the storage rework below, and it's the first thing to check on a #92-style report — SMB2/3
  *does* support hardlinks and most Samba-based NASes (Synology, TrueNAS) honor `os.link`, so
  a given NAS user may already be fine.

- [ ] **#92 / #93 — network + offsite backup destinations (content-addressed storage).**
  Two linked requests from @devonjones: incremental backup to a NAS where the hardlink
  approach may not apply (#92), and direct-to-S3 offsite backup with a configurable endpoint
  so B2/R2/Wasabi work too (#93). #93 is correctly gated on #92 — both are the same seam.

  **Don't build full/incremental chains.** The tape-era model (a full every N days,
  incrementals between) is what makes this feel non-trivial, and it buys the bad properties:
  restores that need an intact chain, retention that can't drop a full until its dependents
  expire, and a corruption blast radius spanning days. That's the state engine to avoid.

  **Content-addressed snapshots are incremental by construction, with no chain state** — and
  the existing engine is most of the way there, since each snapshot already writes a
  `{rel: {size, mtime, sha256}}` manifest. Promote that sha256 from metadata to address:

  ```
  <dest>/M110-Backups/<store>/
    objects/ab/cd/abcdef…             immutable, named by sha256 of contents, mode 0444
    snapshots/<ts>.json               today's manifest, essentially unchanged
    state.json
  ```

  Dedup moves from the filesystem (hardlink to the prior snapshot → needs POSIX links) to the
  application (object already exists → needs only exists/put), which is what makes it work over
  SMB, S3, and anything else. Every snapshot stays independently restorable (no chain replay),
  retention becomes "delete a manifest, then sweep objects no manifest references" — a refcount
  over data we already have, not a dependency graph — and `verify` gets *stronger*: an object's
  name is its checksum, so the store is self-validating.

  Details that matter:
  - **Source hash cache** keyed on `(path, size, mtime, inode)`, kept locally in `~/.m110`
    (must survive destination switches), or a 500 GB library gets rehashed nightly. A cache
    miss costs a rehash, never corruption — strictly safer than today's reuse test, where a
    matching size+mtime silently hardlinks possibly-stale bytes.
  - **Keep hardlinks where they work.** A `latest/` tree beside `objects/`, relinked each run
    with entries hardlinked *into* the object store, preserves the browsable
    "my backup is just my files in Finder" property for free (no duplicated bytes). Where the
    FS can't link (S3, exFAT) it's simply absent and the backup is still correct — browsability
    becomes a *capability of the destination*, not a *mode of the product*. One format, one
    restore path, one test surface.
  - **Backend seam** = put/get/exists/list/delete, mirroring `publish.PUBLISHERS`:
    `LocalBackend` (dir — DAS or NAS mount) and `S3Backend` (boto3 with `endpoint_url`, so
    B2/R2/Wasabi fall out free) write the *same layout*. Follow the `online`-extra pattern —
    optional `s3` extra, graceful "not installed" error from source, bundled in packaged
    builds. Credentials go in **keyring**, not `settings.json` (the PyInstaller specs already
    collect keyring for astroquery).
  - **Destinations become a list.** `backup_destination` is a single setting; offsite implies
    plurality (local NAS nightly + S3 weekly, different retention each). This — not the storage
    format — is the real UI change: destination rows with per-row scope, schedule, retention.
    Format is *derived from the probed destination*, never a user-facing mode; same instinct as
    `launch.find_app` and the hardlink probe: detect, don't ask.
  - **Per-destination scope tier**, because S3 economics demand it: lights are ~99% of the bytes,
    and plenty of users will want offsite to mean journals + `finished/` + `stacks/` for a couple
    of dollars a month with the raws staying on the NAS. Without it the first sync runs for a week.

  **Alternative considered — shell out to `restic`.** Precedent exists (`publish/ghpages.py` drives
  the system git), and restic already is CAS + dedup + prune + S3-with-custom-endpoint + SFTP +
  rclone, delivering both issues nearly free. Costs: bundling/notarizing a ~25 MB Go binary per
  platform, a hard external dependency on the *data-safety* feature, and an opaque repo the user
  can't browse without restic. Preference is to build it natively — the delta is small (manifest,
  retention, verify, restore UI, cancel/progress, atomic-write discipline all exist) and it keeps
  the no-external-binary property exactly where it matters most. Hold restic in reserve if S3
  retry/multipart correctness turns ugly.

  **Sequencing** (each step stands alone and ships something): (1) surface the hardlink probe
  (above); (2) storage v2 — content-addressed objects + snapshot manifests + GC retention,
  `LocalBackend` only (closes #92; the hardlinked `latest/` keeps the browsable tree); (3)
  destinations list + per-destination scope/schedule/retention; (4) `S3Backend` + keyring
  credentials (closes #93). Note **#40d** (restore has no store-version gate) is orthogonal and
  still open either way.

## Packaging & release

- [ ] **`hdiutil create` is deprecated (macOS 27).** `packaging/macos/make_dmg.sh:26`
  builds the DMG with `hdiutil create -volname … -srcfolder …`; macOS 27 warns
  *"'hdiutil create -volname -format …' is deprecated. Please use 'diskutil image
  create from/blank --volumeName --format …' instead."* Cosmetic today — the DMG builds,
  signs, and notarizes fine (0.2.0-beta.2 shipped through it), and deprecated ≠ removed.
  **Don't switch naively:** `diskutil image create` needs a very recent macOS while
  `hdiutil` works everywhere, and although the DMG is built locally by the maintainer
  today, `.github/workflows/release.yml` documents moving the macOS build into CI as a
  later step — GitHub's macOS runners lag OS versions, so a hard switch would build here
  and break there. The safe form is a version/capability guard that falls back to
  `hdiutil` (verify the result still codesigns + passes
  `spctl -a -t open --context context:primary-signature`). Act when Apple actually
  removes `hdiutil`, or when the macOS-in-CI move happens — whichever comes first.

- [ ] **`release.py` smoke phase can watch the wrong run.** `tools/release.py`'s `smoke`
  sleeps 12s after `gh workflow run`, then takes the newest `workflow_dispatch` run —
  falling back to a **completed** one if the new dispatch hasn't registered yet. With
  older successful `workflow_dispatch` runs in the list (there are some on
  `deps/artifact-actions`), a slow dispatch would make the script report "smoke build
  green" without having smoke-tested anything — defeating the phase's whole purpose
  (catching a broken pipeline *before* the tag exists). It picked correctly during
  0.2.0-beta.2, so this is latent, not observed. Fix: pin the run by `createdAt` after
  the dispatch (or match `headBranch == main` + a not-completed status), rather than
  "newest of that event".

## UI niceties (backlog)

- [ ] **Surface skipped files** after an import ("N already present, skipped") — copies
  are already skip-if-present + partial-safe, so this is just reporting.

## Open questions

- *(None open.* The royalty-free-images question is **answered** — the decision
  (CDS hips2fits survey cutouts + curated CC-BY heroes; 8-bit sRGB JPEG specs; a
  reference-image tier + attribution) is captured in [`DATA_MODEL.md`](DATA_MODEL.md)
  "Reference images for uncaptured objects" and scheduled as a **UI Phase 2** item in
  [`UI_ROADMAP.md`](UI_ROADMAP.md).)*

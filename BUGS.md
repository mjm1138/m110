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

- [ ] **A misfiled stack (disjoint `OBJECT`) is still read as the target's.** Sibling of the
  partial-stack rule shipped in `feature/stack-object-match` (see DONE.md). That rule demotes
  a stack whose `OBJECT` names a *strict subset* of a combined target's objects; a stack
  whose `OBJECT` is **unrelated** to the target (an M51 stack sitting in the M71 folder) is
  deliberately left alone, because a disjoint name is more likely to mean "we can't resolve
  this name" than "this file is misfiled" — demoting on it risks discarding a perfectly good
  stack whose OBJECT is spelled in a form `folder_to_slugs` doesn't recognize. Worth
  revisiting alongside a **general "this file doesn't belong here" surface**: the same signal
  would catch the misfiled *lights* case too (the `M81 M82` folder's 2026-06-03/04 sessions
  are M81-only captures by header, which is how the stray stack arose in the first place).
  Related: `Images/M81/` has 327 lights and no `stacks/` tier at all, so it reads
  `not_processed` while its stack lives in the combined folder. Needs a user-facing
  reconcile/"move to the right target" flow, not a silent rule.

- [ ] **Directory precedence outranks the stack `DATE` — should it?** Follow-up to the
  mtime→`DATE` selection fix (`feature/stack-date-selection`, see DONE.md).
  `read_latest_stack_metadata` still sorts root/`stacks/` ahead of `working_files/`
  *unconditionally*, so a genuinely newer stack that only exists in `working_files/` loses
  to an older canonical one. Live case **M106**: `stacks/` holds a 748-frame stack
  (`DATE` 2026-06-01) while `working_files/` holds a 945-frame one (`DATE` 2026-06-19) —
  the page reads **In stack 748, "+ new" 225, out_of_date**, where letting DATE win would
  read **945, "+ new" 0, up_to_date**. Both are defensible: the precedence encodes "a
  canonical stack is more trustworthy than a processing product the lights-guard diverted",
  and there's already a separate **Ready to import** flag for un-imported work — so "In
  stack" arguably means *integrated*, not *newest that exists anywhere*. But M106's
  `ready_for_import` is `False`, so today nothing tells the user the 945-frame stack exists.
  Decide: (a) keep precedence, and surface un-imported stacks some other way; (b) let DATE
  win outright and demote directory to a tiebreak; (c) keep precedence only when the
  canonical stack is *not older* than the working_files one. Needs a call on what "In stack"
  means before changing behavior.

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
- [ ] **#18 — Advanced processing prep (custom workspaces).** Create Siril (and other
  workflow) working directories populated with lights from **disparate sources** (see #16)
  and **disparate objects** (e.g. combine m81 + m82 + "m81 m82" as a mosaic), via hardlinks
  (only processing/intermediate files cost disk). Custom workspaces must be easily
  discoverable by name on the filesystem. Also support custom **split** workflow
  directories, like the LP / no-filter splits created automatically today.

  **The blocker is that everything is target-scoped.** `siril.plan_prep(target)` derives
  its whole world from `Images/<target>/`, and the sandbox lives at
  `Images/<target>/siril/`. A workspace spanning M81 + M82 + "M81 M82" has no honest home
  there — parking it under one member lies about provenance and breaks the archive/import
  logic. But the shape underneath already generalises: `PrepPlan` is "N `PrepJob`s, each a
  dir with `lights/` + a preset", and `apply_prep` just executes hardlink ops. So the hinge
  is small — **`plan_prep(frames, dest)` with a thin target-scoped wrapper** preserving
  today's behaviour. A user-defined split (by device, exposure, or hand-picked) is then just
  a different grouping key producing the same `PrepJob` list as the automatic per-filter split.

  **On disk — a new *visible* axis** (satisfies "discoverable by name"), parallel to
  `Images/` and `Plans/`:

  ```
  Workspaces/<name>/
    workspace.toml        manifest: member objects, per-frame provenance, grouping rule,
                          compat verdict — makes the sandbox reproducible and routable
    lights/               hardlinks (per-job subdirs when split)
    darks/ flats/ biases/ hardlinked calibration
    presets/ next-steps.md
    finished/ stacks/     results
    archive/<ts>/         past runs (same never-delete posture as the target sandbox)
  ```

  Additive like `Plans/` was, so `ensure_data_root` creates it idempotently with **no
  `.store_version` bump** — but `workspace.toml` is a new file format and needs a
  [`DATA_MODEL.md`](DATA_MODEL.md) entry. *Open:* where results land for a multi-object
  workspace. The store already models objects↔targets many-to-many across two axes, and a
  workspace is a third (*processing*) axis with the same property — long term, outputs live
  in the workspace and each member's gallery joins them via the manifest. First cut: import
  into a designated primary target's `finished/` and record the association, with the
  manifest shaped so the join is a later addition, not a migration.

  **"Can these lights actually be combined?" — grade, don't gate.** Define a `FrameProfile`
  fingerprint (geometry, bayer pattern, pixel scale, filter, exposure, gain, temp, device,
  mount mode, pointing) and classify the set:
  - *Hard blockers* (one sequence is impossible): differing `NAXIS1/2`, differing
    `BAYERPAT`, incompatible bit depth. Siril needs identical frame geometry, and
    demosaicing with the wrong pattern silently wrecks colour.
  - *Split, don't block:* different filter (today's per-filter jobs), different device or
    pixel scale — separate jobs, combine at the stack level.
  - *Warn but allow:* mixed exposure/gain, wide temperature spread, EQ vs Alt-Az. All
    stackable; all change the noise model.
  - *Pointing decides the **mode**, not pass/fail.* Derive FOV from
    `FOCALLEN`/`XPIXSZ`/`NAXIS` and compare frame centres: within ~½ FOV → **single stack**;
    separated but adjacent → **mosaic** (exactly the M81 + M82 + "M81 M82" case this item
    names); unrelated → incompatible. The engine should return "these are a mosaic", not
    "these failed".

  Verified against real headers (live store + the Dwarf test dump): S50 = 1080×1920, GRBG,
  2.9 µm @ 250 mm → **2.39 ″/px, 0.72°×1.28°** (matches the S50's published FOV, so the
  derivation is sound); Dwarf 3 wide = 1920×1080, RGGB, 2.9 µm @ 6.7 mm → **89 ″/px**. Those
  two can never share a sequence, and the fingerprint says so from headers alone.

  **Don't re-read thousands of headers.** `scan_sessions` already does **one header read per
  session segment** for `EQMODE` — extend that same read to capture the profile and persist
  it in `sessions.jsonl`, so compatibility computes instantly from derived data. Composes
  with **6d**: `TELESCOP` carries the per-unit id (`S50_15e7e390`) device attribution needs.

  **Two traps to design against.**
  - *Calibration matching is a correctness bug, not a warning.* The sandbox hardlinks one
    shared `darks/` at the root (#57 part B); that's quietly wrong once frames span
    different gain/exposure/temp. A mixed workspace must match calibration per job or refuse it.
  - *Dwarf frames report `RA`/`DEC` as `0.0`* when pointing is unset (and omit `CCD-TEMP`).
    Treat as **unknown**, never as "pointing at the origin", or the overlap math will
    confidently place them in Cetus.

  **Fix first: `siril.filter_of` is a filename regex** (`_(LP|IRCUT|UV|DARK)_<timestamp>.fit`;
  everything else → `OTHER`). It works for a Seestar-only target and breaks the moment a
  workspace mixes sources — the Dwarf's `FILTER` is an empty string and its filenames don't
  match at all. Per the house rule (header truth > filenames) it should read `FILTER` like
  `scan_sessions._session_key` does, with the filename as fast path only. This decides job
  splits, so it lands before workspaces.

  **Phasing.** (1) `FrameProfile` + classifier in the engine off an extended
  `sessions.jsonl` — Qt-free, testable, and useful alone (it can flag mixed-source targets
  that already exist). (2) Generalise `plan_prep` to a frame list. (3) `Workspaces/<name>/`
  + manifest + create/edit flow, with a **preflight report** in the dialog (contributing
  sources, a verdict chip per group, the resulting job split, blockers that can't be checked
  past) — same preview-then-confirm posture as ingest. (4) Import-back to member objects,
  then the many-to-many gallery join. Unblocks **#19(c)**.
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

- [x] **`canonical_target` ignores catalog designations — a Caldwell-named capture forks
  its own folder** (done — `fix/canonical-target-designations`). Reported 2026-08-01 from
  the live store. The Seestar writes the folder
  name from whichever catalog the target was picked out of in the app, so the 2026-08-01
  Veil session landed as `C 34` while the same object's five earlier sessions are under
  `NGC 6960`. Result: two sibling `Images/` folders for one object, and processing-prep
  offers a *choice* between the two light sets instead of one 696-frame target.
  **Root cause:** `ingest.canonical_target` resolves alias → existing `Images/<dir>` casing
  → catalog `id`/slug casing → normalized name. It never asks catalog membership, so a
  designation from a non-primary catalog can't fold onto the primary id.
  **The resolution already exists and is already used elsewhere** —
  `scan_sessions.folder_to_slugs` calls `catalog.designation_index()` /
  `_normalize_designation()` for exactly this case ("A folder named by a *catalog number*
  (`C 6`) names an object the reference keys by its primary designation (ngc-6543)").
  That's why the derived layer is *already correct*: `sessions.jsonl` maps `C 34` →
  `ngc-6960` and `C 22` → `ngc-7662` today. Only the on-disk folder is forked, which is
  why the symptom is invisible in totals and only bites at prep time.
  **Fix:** insert a designation-index lookup into `canonical_target`, between the existing-
  `Images/`-dir check and the catalog id/slug check — resolve the incoming name to a slug
  via `designation_index()`, then return that slug's primary `id` (its folder, if one
  exists). Ordering matters: the existing-dir check must stay first so an established
  folder keeps its spelling; the designation lookup then catches the *new* alternate
  designation before it can mint a second folder.
  Shipped as `catalog.slug_for_designation()` — now the single entry point for "what
  object is this name?", used by both `canonical_target` and `folder_to_slugs` (which had
  its own inline copy) so the two axes can't drift apart again.
  **The fix is prospective only** — it stops new forks, it doesn't heal existing ones. All
  three live cases were repaired by hand on 2026-08-02: `C 34` merged into `NGC 6960`
  (182 + 514 lights), and `C 6` / `C 22` renamed to `NGC 6543` / `NGC 7662` (folder rename
  + sandbox `next-steps.md` paths + folding the orphan `Objects/C 6/journal.md`'s `hero:`
  pin into the live `Objects/NGC 6543/` one). Frame **filenames** were deliberately left as
  captured (`Light_C 6_…`): sessions key off the folder, and the `hero:` pin matches a raw
  filename, so renaming files would have churned ~1,400 of them and broken the pin for
  nothing. The store is clean; what's missing is the tooling to do this without a shell —
  next item.

- [ ] **No user-facing way to merge or rename a capture target.** Fallout from the
  designation fix above: repairing an already-forked or misnamed `Images/<target>/` is a
  hand `mv` today. Two shapes, one surface: **merge** two targets (move `lights/` +
  `seestar-stacks/`, fold the journal + hero frontmatter, drop the stale `siril/` sandbox,
  re-scan) and **rename** one onto its primary designation (`C 6` → `NGC 6543`, absorbing
  the orphan journal stub). Same surface the misfiled-stack item under *Processing &
  curation UX* wants for "this file doesn't belong here" — worth designing once.
  Requirements learned from doing all three by hand (2026-08-02):
  - **Merge** must tolerate a `siril/` sandbox whose `lights/` are **hardlinks** into the
    folder being emptied — dropping the sandbox is safe, the inodes survive via the
    destination, but a naive "delete source dir" ordering *looks* like it destroys frames.
  - **Rename** must rewrite the absolute paths baked into `siril/next-steps.md`, and must
    not blow away in-progress per-filter sandboxes (`siril/IRCUT`, `siril/LP`) or the
    `siril/archive/` — re-running prep to regenerate the file is not an acceptable
    substitute when a Siril job is mid-flight.
  - Both must **fold the journal**, not just pick one: the orphan carried the `hero:` pin
    while the live stub carried the proper `name:`.
  - Both should refuse (or warn hard) when Siril's current working directory is inside the
    folder being moved.

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

- [x] **#44 — LLM session-planner skill foundation** *(done — `feature/assistant-mcp`,
  ROADMAP item 4 M0).* Shipped as a Qt-free tool registry + a `plan-a-night` skill over
  the deterministic engine, served through a stdio MCP server. The engine remained the
  source of truth: the skill forbids hand-assembling a schedule, because the sequencer
  handles slot packing, setting times, the start-altitude ceiling and moon impact
  together. Not seeded from the `astro-session-planner` skill in ~/Astronomy — that
  corpus needs the same PII/staleness review that got `m110/guidance/` withdrawn
  (see #45); the M110 skill was written fresh against the shipped tools.

- [ ] **#45 — Author replacement processing guidance.** The bundled
  `m110/guidance/*.md` playbooks were **removed** (`chore/remove-stale-guidance`)
  rather than patched: two opened with `**Observer:** Mike | **Boulder, CO**`, three
  cross-referenced `CLAUDE.md` (a document users don't ship and a model can't read),
  `seestar_s50_imaging_guide.md` was a *dated March 2026 Boulder weather forecast*
  rather than a guide, and Boulder-specific seeing (2–3″) was baked unlabelled into
  the drizzle and PSF recommendations. They were also **already invisible** —
  `PrepPlan.guidance` was computed but never rendered anywhere, so nothing user-facing
  changed. Replacements should be written against citable Siril 1.4.x sources, carry no
  personal identifiers, label any site-specific number as an example, and contain no
  dated forecasts. **Prerequisite for** the assistant's deferred *processing-coach*
  skill (ROADMAP item 4) and for any future in-app guidance surface.

- [x] **Priority computation took ~23 s on a Messier-sized list** *(done — `perf/twilight-cache`)*.
  Profiled, not guessed: **91% of the runtime was `planning.twilight`**, recomputed per
  target. `observability` calls `_clear_hours` up to 22× per target (tonight + the
  `nights_to_close` forward grid, `SEASON_GRID_DAYS=7` out to `SEASON_HORIZON_DAYS=150`),
  and *each* call recomputed twilight — **535 calls for 22 distinct nights, 24× redundant**,
  with tonight's alone computed 110 times (once per target, identical every time). Twilight
  depends only on (site, date); it has nothing to do with the target, so the cost was
  O(targets × nights) for no reason — and got worse the more goal lists you activate.
  Fixes: (a) **memoize** — `_twilight_cached`, keyed on the four `Site` fields the math
  reads (lat/lon/elev/tz) + date + step, with the cached function taking *only* those so it
  can't grow a dependency outside the key; a profile edit changes the key, so a stale hit
  isn't possible. (b) **batch the `Time` construction** — `Time([to_utc(t) for t in times])`
  built one astropy `Time` per 5-minute step (204,664 `Time.__init__` calls, ~10 s a run);
  `_utc_times` does the identical conversion in one. (c) the second `get_sun` transform over
  the post-dusk tail was **redundant** — those samples are a slice of the ones already
  transformed, so dawn is read out of the existing array. **23 s → 2.4 s cold (9.5×),
  1.4 s warm.** Verified byte-identical against the old implementation over **488 nights ×
  4 sites** (incl. 49 no-astro-dark nights at 64°N and a southern site): zero mismatches;
  the existing June/December twilight goldens still pass. Guarded by five tests in
  `test_planning.py`, incl. one asserting that ranking *more* targets adds **zero**
  twilight computation. Remaining ~1.4 s is thin — ERFA `epv00`/`pnm06a` for the per-target
  transforms plus a one-time IERS table parse; vectorizing the target transform across
  targets or astropy's `ErfaAstromInterpolator` would chip at it, judged not worth the
  complexity.

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

- [x] **Surface the destination's hardlink capability in the backup UI**
  *(done 2026-08-02, `fix/backup-destination-probe`)*. `create_snapshot` probed the
  destination filesystem and silently byte-copied *every* file when links weren't
  supported — so on an exFAT/appliance/rclone-mounted destination each nightly snapshot
  was a **full copy** of the library and the user had no way to know. The old status line
  could only warn *after* a snapshot existed (it read `hardlinks` back out of the newest
  manifest), which is the wrong moment. Now: a public, Qt-free
  `backup.probe_destination(path) → DestinationInfo` (exists / writable / hardlinks /
  free bytes / snapshot count + newest) answers the question **before the first backup**,
  creating nothing and leaving no probe files behind; `backup_dialog._ProbeWorker` runs it
  on a QThread and the status line says "Unchanged files are shared between backups" vs
  "⚠ This destination can't share files between backups — every backup stores a full
  copy." The restore picker labels each snapshot `· full copy` when its manifest says so
  (mixed histories happen — a share remounted with different capabilities). Also fixed the
  latent freeze this replaced: `_refresh_status` ran `list_snapshots()` **on the GUI
  thread on every `textChanged` keystroke**; it now fires on `editingFinished`/Browse and
  memoizes per path. First thing to check on a #92-style report — SMB2/3 *does* support
  hardlinks and most Samba-based NASes (Synology, TrueNAS) honor `os.link`, so a given NAS
  user may already be fine.

- [x] **#92 — pooled (content-addressed) backups for destinations that can't hardlink**
  *(done 2026-08-02, `feature/backup-pooled-storage`)*. @devonjones backs up to a NAS,
  where "the linking approach doesn't necessarily work across a network" — and where
  mirrored snapshots therefore stored a **full copy of the library every night**, silently.
  Shipped as a *second* format rather than a replacement: **mirrored stays the default
  wherever hardlinks work**, because a snapshot that restores in Finder with no software
  at all is worth keeping for everyone it works for. A destination that fails the link
  probe resolves to **pooled** and the app persists that (`backup_format`); both formats
  stay listable/verifiable/restorable at the same destination — provably disjoint
  namespaces (mirrored dirs parse as timestamps, `objects/`/`snapshots/`/`latest/` never
  will), so no flag day and no conversion. What landed:
  `backup/backends/` (put/get/exists/list/delete seam + `LocalBackend`/`MemoryBackend`,
  registry-shaped like `publish.PUBLISHERS`), `pooled.py` (objects addressed by sha256,
  self-contained gzipped manifests, **written last** so *a manifest exists ⇒ every object
  it names exists* — which is also why a cancelled first sync resumes for free),
  `hashcache.py` (sqlite in `~/.m110`, keyed `(path,size,mtime_ns,inode,dev)`; a miss is
  always safe, and a stale hit is caught by cross-checking the stored object's size),
  `recovery.py` (the browsable `latest/` hardlink tree, `INDEX.tsv`, a mirrored
  `latest-manifest.json.gz`, and a stdlib-only `restore.py` written *into* the backup root
  — `objects/` alone is a bag of hash-named blobs, and the way back has to travel with the
  data), object GC with a 24h grace window (safe against a concurrent run without a lock)
  + a process-wide run lock. **Also fixed a pre-existing retention bug**: the min-free loop
  read free space inside a loop that deleted nothing until afterwards, so the reading never
  moved and one pass queued every survivor but one.

- [ ] **#93 — offsite backup destinations (S3 / B2 / R2 / Wasabi).** @devonjones wants
  offsite: a key pair, a bucket, and optionally an API URL so the cheaper S3-compatible
  services work. The storage format and the backend seam it needs shipped with #92 above —
  what remains is the adapter and the multi-destination UI.

  **Don't build full/incremental chains** (the reasoning that shaped #92 and still applies):
  the tape-era model buys restores that need an intact chain, retention that can't drop a
  full until its dependents expire, and a corruption blast radius spanning days.

  Remaining work, in order:

  - **Destinations become a list.** `backup_destination` is a single setting; offsite
    implies plurality (local NAS nightly + S3 weekly, different retention each). This — not
    the storage format — is the real UI change: destination rows with per-row scope,
    schedule, retention. Format stays *derived from the probed destination*, never a
    user-facing mode for the cases where there's no real choice; same instinct as
    `launch.find_app`.
  - **Per-destination scope tier**, because S3 economics demand it: lights are ~99% of the
    bytes, and plenty of users will want offsite to mean journals + `finished/` + `stacks/`
    for a couple of dollars a month with the raws staying on the NAS. Without it the first
    sync runs for a week. Layer it on `scope.is_excluded` (the `Images/*/siril/` rule is the
    shape). One thing to get right: *narrowing* a destination's scope makes the excluded
    objects unreferenced, so the next GC deletes ~400 GB of raws from the offsite store —
    correct, but it must be warned about with an estimate.
  - **`S3Backend`** — boto3 with `endpoint_url`, `object_sizes()` as one paginated LIST (not
    100k HEADs), `delete_objects` in batches for the sweep, `ThreadPoolExecutor` across files
    (throughput here is latency-bound, not bandwidth-bound), `abort_multipart_upload` on
    cancel. Follow the `online`-extra pattern — optional `s3` extra, graceful "not installed"
    error from source (`BackupDepsMissing`, build-aware like
    `catalog._astroquery_missing_message`), bundled in packaged builds. Credentials in
    **keyring**, not `settings.json` (the PyInstaller specs already collect keyring for
    astroquery); the access key id is an identifier, not a secret, so it can stay in settings
    where the UI can show which key is configured.
  - **Provider quirks worth pinning now:** R2 wants `region_name="auto"`; several
    Wasabi/MinIO setups need path-style addressing; and botocore ≥1.36 sends
    `x-amz-checksum-crc32` on every PUT by default, which some S3-compatible providers
    reject — pin `request_checksum_calculation="when_required"` defensively. Since the key
    *is* the sha256, `ChecksumSHA256` on PutObject gets server-side rejection of a corrupted
    upload for free where supported. Document a lifecycle rule to abort incomplete multipart
    uploads (orphaned parts bill silently — the classic S3 backup cost leak), and that egress
    on *restore* is the expensive direction on AWS but cheap or free on B2/R2.
  - `Capabilities.free_bytes is None` on an object store, so `min_free_gb` is meaningless
    there; its analogue is a per-destination `max_store_gb` budget from `state.json`.
    Default a new offsite destination to keep-N only — never surprise-delete an offsite copy.

  **Alternative considered — shell out to `restic`.** Precedent exists (`publish/ghpages.py`
  drives the system git), and restic is already CAS + dedup + prune + S3-with-custom-endpoint.
  Costs: bundling/notarizing a ~25 MB Go binary per platform, a hard external dependency on
  the *data-safety* feature, and an opaque repo the user can't browse without restic. Built
  natively instead — and with #92 landed the remaining delta really is just the adapter.
  Hold restic in reserve if S3 retry/multipart correctness turns ugly.

  Note **#40d** (restore has no store-version gate) is orthogonal and still open either way.

## Security  *(→ [`docs-archive/SECURITY_ASSESSMENT.md`](docs-archive/SECURITY_ASSESSMENT.md))*

Open findings from the 2026-07-30 assessment refresh. Nothing rated above Low; none
is a release blocker for 0.3.0-beta.1 except F8, which is one line.

- [ ] **F8 — `uranometria` is installed from an unpinned git URL.** `.github/workflows/ci.yml:64`
  runs `pip install "uranometria @ git+https://github.com/devonjones/uranometria"`, which
  resolves to whatever is on the default branch at install time — no tag, no SHA, no hash.
  Because it isn't a registry package it is **invisible to Dependabot** and `pip-audit`
  **skips it outright**, so both supply-chain controls have a blind spot exactly here. CI-only
  today (Low); the `pyproject.toml` note says packaged builds will install it the same way,
  and baking an unreviewed upstream state into downloadable artifacts is Medium. **Fix:** pin
  to a commit SHA or tag (`…/uranometria@<sha>`) and treat bumps as reviewed changes; revisit
  when it reaches PyPI and becomes a normal extra. Do this *before* packaging adopts the line.

- [ ] **F9 — `objects.write_journal` trusts a slug validated upstream.** `journal_path` →
  `object_folder_name` falls back to the raw slug and neutralizes only `/`, so `..` survives
  (verified: `Objects/../journal.md`) and on Windows `..\..\x` survives verbatim — `\` is a
  separator there. Not currently reachable: `propose_journal_entry` checks the slug against
  the Library first, and Library slugs derive from folder names already reduced by
  `ingest._safe_segment`. So it's latent — but it's the same shape as the fixed F1 traversal
  (validation upstream, no guard at the writer), and F1's lesson was that the guard belongs at
  the writer. **Fix:** reduce `object_folder_name` via `_safe_segment` and/or assert
  containment under `config.OBJECTS_DIR` in `write_journal`, with a test mirroring
  `test_apply_ops_refuses_writes_outside_the_store`.

- [ ] **F7 — Indirect prompt injection via library content** (accepted design property, track
  don't "fix"). Object names and filenames reaching the assistant originate in FITS `OBJECT`
  headers and on-device filenames — attacker-controlled in a crafted capture file, same source
  as F1. A model can't distinguish those from M110's own prose. Ceiling is **user deception**
  (a plausible proposal the user accepts), not access: `apply.py` is unreachable from the
  server, the outbox is inert and quota'd, and every change is user-accepted against a
  recomputed preview. **Reduce, don't solve:** label/delimit untrusted-derived fields as data
  in tool output; never add an auto-apply mode; teach the skills to treat library text as data.

- [ ] **Verify the repo Settings security toggles are actually on** — Dependabot alerts +
  security updates, CodeQL default setup, secret scanning + push protection. Not visible from
  the working tree, so the assessment can't confirm them. CodeQL would be the standing check
  for F9-shaped bugs. Pairs with adding a **`pip-audit` CI job** (fails on a known-vuln dep at
  PR time; won't cover F8 — pinning is the control there).

## Packaging & release

- [x] **The macOS .app launched as a background app — no menu bar, no Dock icon, absent
  from Force Quit** (done — `fix/macos-background-only`). `BUNDLE` inherits `console`
  from the `COLLECT`, which inherits it from its EXE args **last-one-wins** — and ours is
  the `console=True` MCP server (which must stay console=True: the Windows GUI subsystem
  has no stdio). PyInstaller then stamps `LSBackgroundOnly=True`
  ("console=True implies…", `building/osx.py`), and LaunchServices registers the app as
  `type="BackgroundOnly"`. Fix: set `"LSBackgroundOnly": False` explicitly in the spec's
  `info_plist`, which is merged **over** PyInstaller's defaults. Latent since the MCP
  binary landed (`3e79691`), so it shipped in 0.3.0-beta.1 too — invisible only because
  that build crashed before a window appeared. Verified on a real build: the fresh
  bundle's plist reads `LSBackgroundOnly => false` and the running process registers
  `type="Foreground"` where the installed b2 registers `type="BackgroundOnly"`. Guarded
  by `tests/test_packaging_deps.py::test_macos_bundle_is_not_background_only`.
  ⚠️ Any future spec that adds a console EXE to the same bundle inherits this trap.

- [x] **0.3.0-beta.1 crashed on launch — uranometria's package data wasn't bundled**
  (done — `fix/uranometria-bundle`). The frozen app died with
  `FileNotFoundError: …/Frameworks/uranometria/data/constellations.json` before the window
  appeared: PyInstaller followed `m110.skymap`'s lazy `import uranometria` and froze the
  *modules*, but package **data** is collected for nobody by default — and
  `uranometria.catalog` loads its constellation JSON **at import**. Fatal rather than
  cosmetic because the Library builds its Map view during `CatalogPage.__init__`, so any
  user whose saved `library_view_mode` was `map` (i.e. anyone who'd tried it) hit it at
  launch. ROADMAP item 12 had flagged the `collect_data_files("uranometria")` requirement;
  it never made it into the three specs. Fixed there (data only — `uranometria.annotate`
  imports the excluded matplotlib), plus two follow-ons: `skymap._uranometria` now converts
  **any** import-time failure into `SkymapDepsMissing` (the degrade path every caller
  already handles) so a broken chart library can never again take the app down, and
  `release.yml` installs uranometria for the Linux + Windows jobs — 0.3.0-beta.1 had it in
  the macOS build env only, so those two installers shipped with no Map view at all.
  Verified against a real PyInstaller build, not a source run: data present under
  `Contents/Resources/uranometria/data`, and the rebuilt `.app` launches with
  `library_view_mode = "map"`. Guarded by `tests/test_packaging_deps.py`
  (spec + workflow) and `tests/test_skymap.py` (the degrade path).

- [x] **`hdiutil create` is deprecated (macOS 27)** (done — `fix/packaging-build-warnings`).
  `packaging/macos/make_dmg.sh` built the DMG with `hdiutil create -volname … -srcfolder …`;
  macOS 27 warns *"'hdiutil create -volname -format …' is deprecated. Please use 'diskutil
  image create from/blank --volumeName --format …' instead."* Taken as prescribed here —
  a **capability guard**, not a hard switch: `diskutil image create from --help` decides,
  and anything older falls back to `hdiutil`, so the GitHub macOS runners (which lag OS
  versions, and which `release.yml` documents building on later) can't be broken by this.
  Verified equivalent on the real 0.3.0-beta.4 payload rather than a toy folder: identical
  format (UDZO), partition scheme (GUID), filesystem (APFS), volume name, and contents with
  the `/Applications` symlink intact — and, mounted from the new DMG, the app inside still
  reports `valid on disk` + `satisfies its Designated Requirement`, its **stapled ticket
  validates**, and `spctl` returns `accepted / source=Notarized Developer ID`.
  ⚠️ One real difference: `diskutil` compresses harder — same payload, 110.6 MB vs
  hdiutil's 126.3 MB (the shipped b4 DMG is 125.7 MB, matching hdiutil). Smaller is welcome,
  but it means **a build machine on an older macOS produces a ~12% larger DMG** than a
  current one. Not a correctness problem; worth knowing before comparing artifact sizes
  across machines and concluding something is wrong.
  *(Not verified here: `spctl` on the DMG **itself**, which only passes once the DMG is
  notarized — that happens in `release.py`'s macos phase. The app-inside check above is
  the strongest signal available without submitting a throwaway DMG to Apple.)*

- [x] **The macOS build printed astropy-branded deprecation warnings that weren't astropy's**
  (done — `fix/packaging-build-warnings`). Every build scrolled several
  `WARNING: AstropyDeprecationWarning: …` lines past, which read as "our astropy usage is
  deprecated" and prompted an investigation that found nothing wrong with astropy. They came
  from **astroquery**: the three specs `collect_submodules("astroquery")`, which imports each
  submodule to enumerate it, and `vamdc`, `exoplanet_orbit_database` and `cds` each warn at
  import. Two things made them misleading — astroquery raises them with *astropy's*
  `AstropyDeprecationWarning` class, so astropy's name leads the line; and that class
  subclasses `Warning`, **not** `DeprecationWarning`, so Python's default filters don't
  suppress it the way they suppress ordinary deprecations (which is also why a
  `-W always::DeprecationWarning` test run showed nothing). A fourth,
  `astroquery.dace`, was removed upstream and raises `ImportError`, which PyInstaller
  reported as a failed collection. M110 uses `astroquery.simbad` only, so all four are now
  filtered out of the walk — same move as the `astropy.visualization` filter in
  `pyinstaller-hooks/hook-astropy.py`, and a filtered subtree is never recursed into, hence
  never imported. A rebuild confirms zero `AstropyDeprecationWarning` and no failed
  collection. **Still printed, deliberately:** `PrototypeWarning: pyvo.discover's API is
  still under design` — that's an API-stability notice, not a deprecation, and `pyvo` is a
  live astroquery dependency, so filtering it would be excluding a subtree we might actually
  reach. Lesson for the next one of these: a warning naming a library is not necessarily
  *from* it.

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

- [x] **Closing the Backup dialog mid-probe aborted the process (SIGABRT)**
  *(done — `fix/backup-destination`)*. Reported from a real run: hitting the exit
  button crashed with `Termination Reason: SIGNAL 6, Abort trap`. The stack named it
  exactly — `QThread::~QThread()` → `QObjectPrivate::deleteChildren()` →
  `QWidget::~QWidget()` → `QDialogWrapper::~QDialogWrapper()` — with thread 18
  (`_ProbeWorker`) still live. That is Qt's qFatal *"QThread: Destroyed while thread
  is still running"*, which calls `abort()`; it is **not** a catchable exception.
  **Mechanism:** `_ProbeWorker.probed` is emitted from *inside* `run()`, so the
  GUI-thread slot (`_on_probed`) executes while the worker is still finishing.
  `_finish_probe` dropped the reference there with a bare `deleteLater()` and no
  wait — leaving a **running QThread parented to the dialog with nobody holding it**.
  Closing the dialog then destroyed it mid-run. Worse, it defeated the guard:
  `_stop_probe` checks `is not None`, and the reference had already been cleared, so
  the teardown *looked* protected and did nothing. Reproduced deterministically with
  a slowed probe, then verified fixed.
  **The same bug was in three of four worker dialogs.** `export_dialog` had found and
  fixed it locally — its comment even spells out "fires from run() *as it returns*" —
  and `backup_dialog`, `restore_dialog` and `publish_dialog` all kept the unsafe copy.
  Now one `widgets.drain_worker(worker)` (wait → `deleteLater` → return None) is the
  single way any of them drops a worker, guarded by a test that greps every
  `_finish_*`/`_stop_*` method in all four for it — because the failure aborts the
  interpreter rather than failing an assertion, so the *shape* is what has to be
  asserted. Aggravated by `/Volumes/...` destinations, where the probe is slow enough
  for the race to be routine rather than rare.


- [x] **Controls were too heavy — a density pass measured against native macOS**
  *(done — `fix/ui-density`)*. Reported as "buttons and selectors have unnecessary
  padding… reduce the padding and/or the text size". Measured first, in a real cocoa
  app with the stylesheet toggled on and off (offscreen is Fusion and proves nothing),
  and **two thirds of the report turned out to be mis-aimed** — which is why measuring
  first mattered:
  - **Buttons and combos were already at or below native** — `QPushButton` 30px vs the
    platform's 32, `QComboBox` 30 vs 32, and 4–18px *narrower*. Shrinking them would
    have undershot macOS. **Left alone.**
  - **The body font is exactly the macOS system font** — 13.0pt, byte-identical to
    `QFontDatabase.systemFont(GeneralFont)`. **Not touched.** But the blanket
    `QWidget { font-size: 13px }` *was* overriding the two classes macOS deliberately
    draws smaller (`QToolButton` 10pt→13pt, `QHeaderView` 11pt→13pt) — so the text
    that really was oversized is in table headers and segmented controls, now
    restated at 11px.
  - The bloat was in four places, all now trimmed (styled → native): **text inputs**
    30→26 (21), **nav rail rows** 36→28 (17), **table rows** 27→23 (19), **headers**
    33→29 (21), **segmented buttons** 27→25 (22).

  The input `min-height` was **kept at 20px** and only the padding cut: `min-height`
  sizes the *content* box, so it is the anti-clipping guarantee itself, and trimming
  padding cannot narrow the text band. Both floors are now literals rather than
  `SPACE['xl'] - SPACE['xs']` — that expression let an unrelated spacing tweak move a
  clipping floor silently. `QComboBox` gets its own 24px floor so it stays button-height
  (a pop-up button is not a text field: macOS draws it at 32, not 21).
  Verified: **0 clipped controls** across the main window and all three dialogs.
  ⚠️ **The input change is a no-op under Fusion**, so the "more native" win is macOS-only;
  the table/header/rail changes apply everywhere but are unvalidated on Linux/Windows.

- [x] **Styled spin boxes had no stepper** *(done — same branch)*. Styling a spin box at
  all hands its whole rendering to the stylesheet, so the macOS chevrons degraded into
  two ~2px dots — and adding `::up-button`/`::down-button` rules without
  `::up-arrow`/`::down-arrow` made it *worse*, an empty compartment. Both halves now
  ship together (`theme/icons/chevron-{up,down}.svg`), guarded by a test. The colours are
  why the input rule exists at all (see the QDateEdit note in `qss.py`) — we can't have
  themed colours *and* the native stepper, since setting any property switches the widget
  over. One neutral grey serves both themes: QSS has no `currentColor`.

- [x] **The Backup dialog opened shorter than its own layout minimum** *(done — same
  branch)*. This, not the control padding, is what still looked broken after the
  clipping fix. `self.resize(560, 0)` ran at the *top* of `__init__`, before any widget
  existed, so the zero height clamped to the layout minimum *as it stood at that moment*
  — nothing. Measured: dialog 478px against a `heightForWidth(560)` of 536, leaving the
  group box 58px short and the three spin boxes **physically overlapping by 3px each**
  (6px once the async destination probe wrapped the status line to two lines). Now sized
  at the *end* of `__init__` from `max(sizeHint, heightForWidth)`. Row gaps measured
  −3/−3 → +4/+4.
  Also in that dialog: the three retention rows were independent `QHBoxLayout`s, so the
  fields sat at three different x with three different widths (48px spread) — now one
  `QGridLayout` with a shared label column, measured spread **0px**; and `min_free`'s
  hardcoded `setFixedWidth(90)` was 18px *below* its own sizeHint (it clipped at large
  values), replaced by one width derived from the widest of the three.

- [x] **Spin-box values clipped top-and-bottom in the Backup dialog**
  *(done — `fix/spinbox-text-crop`)*. Reported from the packaged app: the interval,
  keep-newest and min-free fields rendered "11 h" / "all" / "100" with the glyph tops
  and bottoms shaved off. **Root cause is the same asymmetry the buttons already
  fixed:** the QSS styles inputs with `padding: 4px 8px`, which sits *inside* the
  widget — and `QPushButton` and `QCheckBox` each carry an explicit `min-height`
  (the button rule's own comment says why: "a styled QPushButton in a tight layout
  (esp. on macOS) otherwise clips its text top-and-bottom"), while the inputs rule
  declared none. So when a layout squeezed, the inputs were the only thing that
  collapsed. Measured under the real macOS style: `sizeHint` **28**, actual height
  **16**, leaving the inner line edit **6px for a 16px font**.
  The trigger in this dialog is `self.resize(560, 0)` — asking for zero height before
  the layout exists, so Qt clamps against an incomplete minimum. Either fix alone
  resolves it (verified both ways); the **`min-height` on the inputs is the durable
  one**, because it protects every dialog rather than the one that happened to be
  squeezed. `publish_dialog.py` uses the same `resize(w, 0)` idiom and is worth
  keeping in mind. An app-wide sweep of every page + dialog found **3 clipped inputs
  before, 0 after**.

- [x] **"Automation & retention" rendered as "Automation  retention"**
  *(done — same branch)*. Qt reads a single `&` in a `QGroupBox` title as a **mnemonic
  marker**: it's consumed and the next character underlined. A literal ampersand must
  be written `&&`. Guarded by a source scan over `m110/ui/**` for lone ampersands in
  widget labels (`QGroupBox`/`QCheckBox`/`QPushButton`/`QLabel`/`QAction`/`setTitle`/
  `setText`), which also covers `&amp;`-style entities correctly — a widget walk would
  have missed labels behind dialogs a test doesn't construct.

- [ ] **The Backup dialog's retention fields don't line up.** Noticed while fixing the
  clipping above, not part of it. "…at most once every", "Keep newest" and "Keep at
  least" are three independent `QHBoxLayout`s, so their labels have different widths
  and the three input boxes start at three different x positions with three different
  widths. A `QFormLayout`/`QGridLayout` would align them. Cosmetic, uncontroversial,
  but a layout change rather than a fix — left for a deliberate pass.

- [x] **Buttons in table rows were clipped in both directions**
  *(done — `fix/table-row-buttons`)*. Reported against **Saved field guides**, where the
  row read `View | Revea | Delete` with the button tops shaved off, at every window size.
  **Root cause:** the app QSS pads table items (`QTableView::item { padding: 4px 8px }`),
  and Qt lays a cell **widget** out inside that padded rect — but `resizeColumnsToContents`
  measures *items* and skips cell widgets entirely, and the row height is sized for one line
  of text. Measured under the real macOS style: the column was 195px where the buttons
  needed 194 + 17 of inset, and the row 33px where they needed 30 + 9.
  **Fix:** `widgets.fit_cell_widgets(table, *cols)` — a sibling to `fit_table_height` —
  measures the cell widgets themselves and adds the padding, in the *same* `SPACE` tokens
  the stylesheet uses so the two can't drift (a test fails the build if they do). Two
  traps found while fixing it: the grid line eats another pixel, and the row height must be
  a **minimum section size**, because `fit_table_height` calls `resizeRowsToContents`, which
  re-measures from the items and silently undid a per-row height (the first attempt fixed
  the width and left the vertical clipping in place).
  **This was app-wide, not one page.** The Import holding area had hit the same bug
  earlier (#65, *Assign* clipped to *ssig*) and papered over it with hand-tuned widths
  150/130/210 — which fixed that one row, never addressed the row *height*, and was itself
  **3px short** (the cluster needs 213). Both preview tables' remap combos (`ingest_dialog`,
  `import_page`) were vertically clipped too and are now measured. The two holding pickers
  keep an explicit **minimum** width, since the Object combo is editable and wants typing
  room the content can't imply — the intent the old magic numbers carried silently.
  *Open follow-up:* whether a three-button cluster is the right affordance for the guides
  list at all — see the next item.

- [x] **Per-row action buttons → a context menu, for the guides list**
  *(done — same branch)*. The **Saved field guides** row carried `View · Reveal · Delete`
  as three equal buttons. **View duplicated** the row's existing double-click; **Delete was
  styled identically to the benign actions** a few pixels away (there *is* a confirm
  dialog, so the cost was annoyance, not data loss); and it was the odd one out — the
  Library, Processing queue and detail gallery all expose per-row actions through
  `widgets.connect_context_menu`, while the cluster spent ~210px of every row on actions
  that apply to one row at a time (the minimal-chrome rule in [`UI_ROADMAP.md`](UI_ROADMAP.md)).
  Now: double-click opens, right-click gives View / Reveal / Delete… with the destructive
  one behind a separator, and a one-line caption under the table says so — the pane is
  visited rarely enough that relying on right-click-by-convention would have hidden it.
  Split into `_guide_row_at` + an exec-free `_guide_menu` builder, mirroring
  `pages/catalog._object_menu`, because a modal exec can't run headless and PySide6's
  `QMenu.exec` can't be monkeypatched — so the row resolution and the menu contents are
  testable. **Deliberately not applied to the Import holding area:** `Assign` is the
  *primary* action performed on row after row in a triage pass, and burying it in a menu
  would make that flow slower. If anything changes there, `Discard` is the one to demote.

## Open questions

- *(None open.* The royalty-free-images question is **answered** — the decision
  (CDS hips2fits survey cutouts + curated CC-BY heroes; 8-bit sRGB JPEG specs; a
  reference-image tier + attribution) is captured in [`DATA_MODEL.md`](DATA_MODEL.md)
  "Reference images for uncaptured objects" and scheduled as a **UI Phase 2** item in
  [`UI_ROADMAP.md`](UI_ROADMAP.md).)*

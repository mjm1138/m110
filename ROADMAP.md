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
| 10 | **Library backup** — mirrored + pooled snapshots, verify, selective restore, auto-backup, offsite S3 | ✅ shipped, incl. two slots (local + cloud) side by side *(N-destination list → #93)* | [`DONE.md`](DONE.md) |
| 7 | **Processing & curation UX** | 🔶 #17 hinting + curation gallery shipped; #18/#19 open [↓](#7--processing--curation-ux-remainder) | [`DONE.md`](DONE.md), [`BUGS.md`](BUGS.md) |
| 4 | **In-app assistant** (bring-your-own LLM) — MCP server over a read-only tool registry | ✅ M0 shipped *(M1 in-app transport + safe-writes open [↓](#4--in-app-assistant-bring-your-own-llm--m0-shipped))* | [`DONE.md`](DONE.md) |
| 14 | **AstroWizard support** — a second processing workflow: hand a stack off, launch, import the finish back | 🔶 14a + 14b shipped (send-stack, and import the finish back); 14c open [↓](#14--astrowizard-support) | [`DONE.md`](DONE.md), [↓](#14--astrowizard-support) |
| 15 | **Process with me** — guided Siril post-processing: the agent runs every deterministic step in the sandbox, the user does the judgment steps in the GUI | ⬜ open — brief written 2026-10-14; needs the processing-model decision first | [↓](#15--process-with-me-guided-siril-post-processing) |
| 2 | **Plan-file generation** (SSC / NINA device schedules) | ⬜ open | [↓](#2--plan-file-generation-device-schedules) |
| 11 | **Lights Table** (bulk sub inspection/culling) | 🔶 the `rejected/` exclusion tier shipped (#110); the view is open [↓](#11--lights-table) | [↓](#11--lights-table) |
| 12 | **Sky map** (uranometria integration — Library Map view + publish page) | 🔶 12a/12b shipped — Library **Map** view + goal progress; 12c–12e open [↓](#12--sky-map-uranometria-integration) | [`DONE.md`](DONE.md) |
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
- **Processing model:** **prepare-and-guide, not control** — *amended for
  stacking, 2026-08-19.* The app arranges files into Siril's expected layout and
  emits Siril-ready configs + guidance; it does **not** drive Siril/StarNet for
  interactive work (avoids the maintenance tax of wrapping volatile CLIs).
  **The one exception is stacking** (`m110/stacking.py`, the `m110-stack` CLI),
  which runs `siril-cli` itself. The reason the general rule does not cover it:
  a multi-hour unattended batch job is precisely what a human should not have to
  sit through, and the "volatile CLI" cost does not apply — every command emitted
  is stock Siril 1.4, so only the *choice* of settings is ours. The guide posture
  survives where it matters: measuring and proposing is read-only and separate,
  and nothing runs until a human has agreed to the settings. Post-processing
  stays firmly prepare-and-guide (see item 14).
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

- **M0 — tool registry + skills + stdio MCP server. ✅ shipped** (strictly
  read-only).
- **M0.5 — the outbox. ✅ shipped.** Read-only made saving a plan impossible,
  and copy-pasting markdown out of a chat is not a workflow. The invariant was
  relaxed *precisely*: **no tool modifies or deletes anything; a tool may create
  a new file, only in `.m110_internal_data/assistant/outbox/`, under quota.**
  The value was never zero-write — it was "can't damage or silently alter what
  you made", and a new file in a staging folder does neither. Artifacts (field
  guides; **device plan files when item 2 lands**) and proposal envelopes share
  the queue; a banner surfaces it and a modal applies, re-running each
  proposal's preview against the store *as it is now* via `basis.store_state`.
  A preference allows direct saves to `Plans/` once trusted.
- **M1 — in-app HTTP transport over the same registry.** The safe-write
  allowlist arrived early with M0.5 (via the outbox rather than direct writes),
  so what remains is the live transport: an assistant that can see the running
  app's state and drive its UI.
- **M2 — *(optional)* in-app chat**: provider adapters, key handling in the OS
  keychain, cost controls, local models. Only if BYO-client proves insufficient;
  the MCP topology may make it permanently unnecessary.

#### Open

- **M1** — the in-app transport and the safe-write allowlist.
- ✅ **MCP Python SDK v2 migration** *(done 2026-08-16, `feature/mcp-v2`)* — the
  assistant server is off the maintenance-only v1 line; see [`DONE.md`](DONE.md).
- ✅ **Headless stacking + the `siril-stacking` skill** *(done 2026-08-19,
  `feature/siril-stacking`)* — `m110/stacking.py` ported in from the Astronomy
  project, shipped as the `m110-stack` console binary (a third executable from
  the same PyInstaller Analysis, like `m110-mcp`). The assistant gets the pure
  half only: `plan_stack` measures headers and proposes settings, and cannot
  stack. See the amended processing-model decision above, and [`DONE.md`](DONE.md).
- **Processing coach**, deferred: the bundled guidance corpus was withdrawn (see
  [`BUGS.md`](BUGS.md) #45) and replacements need authoring against citable
  sources before the *coaching* leg can ship.
- Cost controls and a model picker belong to whichever client the user brings —
  revisit only if M2 happens.


### 14 — AstroWizard support

Treat **[AstroWizard](https://astrowizard.lukomatico.com/)** as a first-class
processing workflow beside Siril: hand a stack off to it, launch it, and import
the finish back into `finished/` + `stacks/` — the same round-trip
`Images/<target>/siril/` already gets. A second workflow is the point; AstroWizard
is just the one with users asking for it.

**Why it's worth its own slot.** M110's processing story assumes one tool does
everything, because Siril can. AstroWizard splits the job: Siril (or `m110-stack`)
produces the stack, AstroWizard does the whole linear→finished pipeline on top,
orchestrating GraXpert, StarNet2 and RC-Astro through a stepped UI. That is a
*different workflow*, not a different tool for the same job — and it is the shape
every future post-processing integration takes. Getting the second one right is
what makes the third cheap. It also extends the #19 launcher seam
(`processing.WORKFLOWS` + `launch._TOOLS` + `external_app_paths`) into its first
real second consumer, which is the only way that seam gets tested.

#### The handoff is a place, not a filename

AstroWizard's output **cannot be recognised by filename.** Its three exports
(`export_final` / `export_starless` / `export_stars`) go through a native save
dialog, so the user types the name; only `-starless` and `-stars` are hard-coded
fragments. Classification therefore has to be directory-first, which
[`siril._classify`](m110/siril.py) already does (#85, "directory wins").

So the handoff is `Images/<target>/astrowizard/` — a sibling of `siril/`, not a
subdir. These directories name **workflows, not tools**, and they stay separate
because the artifacts have different **lifetimes**: a stack costs hours and is
stable, a finish is cheap and iterated (`--restack` and AstroWizard's "Start over"
both exist because you iterate). One shared directory would archive the expensive
artifact every time a cheap one is redone.

#### What this actually costs us

- **Groundwork: done.** `config.SANDBOX_LINKED_INPUTS` is the single authority every
  sandbox-skipping walk reads — `SANDBOX_DIRNAMES` derives from its keys, and
  `siril._ROOT_SKIP_DIRS`, `ingest._SKIP_DIRS` and `backup.scope.is_excluded` all
  consult it. `config.astrowizard_dir` exists and `m110-stack --handoff` populates
  the sandbox. Lazily created, additive → **no `.store_version` bump**.
  AstroWizard's entry is already there, declaring `frozenset()`: its input is one
  handed-off stack file, not a directory of links, so backup keeps everything in
  `astrowizard/` — the handoff, the exports, and the archived runs alike.
  **Revisit alongside the cleanup finding below:** that reasoning assumed the
  sandbox holds a handoff plus at most three exports. Measured, one finished target
  is ~2.2 GB with **nothing** excluded (`scope.is_excluded` is False for every path
  under `astrowizard/`), and the mirrored format dedups by *path* — so every
  re-finish adds another full copy to every future snapshot. That is precisely the
  failure mode the `siril/lights` exclusion exists to prevent (+139 GB measured on a
  186 GB library). Archiving the step chain on import is what keeps `frozenset()`
  honest; leave the chain in place and `astrowizard/` needs a declared skip instead.
- **Cleanup is the opposite of small — measured, not assumed.** AstroWizard
  autosaves **one file per user action**. A single M27 finish (2026-08-20) left
  **26 files / 2.02 GB** in a 2.2 GB sandbox: `_AW1_init` through `_AW24_rescreen`,
  including three separate `_crop` steps and six separate `_adj_curves` steps, plus
  `.tif` side-outputs.

  **Diagnosed in AstroWizard's own bytecode, and it is a macOS bug, not a design.**
  `generate_save_path` builds the `_AW<n>_` names and **27** step operations call
  `track_temp_file`, so the chain *is* registered; `cleanup_temp_files` deletes
  every tracked file and then clears `history_stack`/`redo_stack` — these are the
  undo history's backing store, and they are meant to be temporary. But its only
  callers are `on_closing`, `load_file` and `start_over`, and `__init__` registers
  **only** `protocol("WM_DELETE_WINDOW", …)`. It is a customtkinter app, and on
  macOS **Cmd+Q / the Apple-menu Quit does not fire `WM_DELETE_WINDOW`** — that
  path is `::tk::mac::Quit`, which appears nowhere in the binary. Quit the normal
  macOS way and the entire chain is orphaned.

  So the earlier claim ("at most three files per run") described the *intent*
  correctly and the *outcome* wrongly, and it was load-bearing for both the backup
  trade-off above and the cost estimate below. **M110 must sweep regardless** — we
  cannot depend on another app's exit path, and a crash or force-quit orphans the
  chain even once that bug is fixed. **The import step
  must archive or discard the chain**, the way `siril.apply_import` archives a run:
  what the user keeps is the finish, not the 24 steps that made it.
- **`hints` needs no change.** `DEFAULT_INTERMEDIATE` already carries `starless`,
  so a `…-starless.png` export classifies as intermediate and correctly stays out
  of `finished/`.
- **The real work is extraction, not new code.** Roughly 200 lines of `siril.py`
  are genuinely tool-agnostic round-trip machinery — `_resolve_import_dest`,
  `_same_bytes`, `_classify`, `_tier_of`, `_finished_outputs`, `scan_finished`,
  `apply_import`, the archive pattern, `FinishedItem`/`ImportPlan`. Lift those
  into a shared module (with `tests/test_siril.py` as the safety net) and
  `astrowizard.py` is thin: no presets, no calibration, no per-filter jobs, no
  `prune_rejected`, and `working_dirs()` is just `[base]`.

#### Gotchas to design around

- **`processing._store_targets` hardcodes `lights/`.** A target holding only
  imported stacks — exactly AstroWizard's case — is invisible to
  `prepare_missing`. Needs a per-workflow target selector (a sixth `Workflow`
  field defaulting to the current behaviour; the dataclass is frozen with
  positional construction, so a defaulted field is source-compatible).
- **`build_derived.ready_for_import` is a single Siril-only boolean.** With two
  workflows the Processing page must say *which* tool has work waiting.
- **`ui/import_dialog.py` is entirely Siril-bound** — module-level `from m110
  import siril`, Siril-worded throughout. It needs a workflow/engine parameter.
  Largest single UI edit in the item.
- **A stale handed-off stack has no signal.** Re-stack in Siril and
  `astrowizard/` silently holds the old copy. `m110-stack --handoff` writes a
  provenance sidecar for this; the UI flow must too — same shape as the
  `hero/<slug>.src` identity sidecar that fixed #17.
- **AstroWizard bundles its own hardened Python** (PyInstaller, `Python.framework`).
  Launch it through `launch._launch_macos` / `_child_env` like Siril, or the
  two-Qt and responsible-process failures apply.
- **StackingWizard still takes no arguments** — re-verified against the 2026.08.27
  and again the 2026.10.05 build; no `argv`, no document types, no URL types, no Apple events. Its folder
  picker seeds `initialdir` from `last_folder` in
  `~/Library/Application Support/StackingWizard/settings.json`, read once in
  `__init__`, which is the only seam for a folder hand-off and is another app's
  private config. Open item + the trade-off in [`BUGS.md`](BUGS.md) → Processing &
  curation UX; developer outreach pending before we reach into it.
  **Feature request to be sent (2026-10-05)** to the developer (Luke, Lukomatico —
  `wizard@lukomatico.com`, the address in the app's own footer): accept a folder as
  the first argument (`StackingWizard <folder>`, or `--folder`), treated as if chosen
  in the picker; optionally a per-run way to supply Workbench settings (JSON/flags)
  without touching the saved defaults. Decision: **no `last_folder` pre-seed** —
  wait for the upstream argument. When it ships, fill `workdir_args` in
  `launch._TOOLS["stackingwizard"]` and drop the reveal-the-folder workaround.
  Also noted in the 2026.10.05 build: Workbench knobs persist under a `workbench`
  key in the same `settings.json` (global, not per folder); the "set aside" folder
  (`SET_ASIDE_DIR`) must be skipped by any M110 walk of a StackingWizard folder.
- **A sandbox that hardlinks a directory of frames must say so in
  `config.SANDBOX_LINKED_INPUTS`.** AstroWizard as scoped links a single file —
  `stacking.apply_handoff` hardlinks the stack into `astrowizard/` root — so its
  entry is `frozenset()`. That does put a second copy of one stack in a mirrored
  snapshot, knowingly: the mapping is directory-based, and the only way to exclude
  the handoff would be to exclude `astrowizard/`, which is where the exports live.
  One file per handed-off target is the right side of that trade. But if the flow
  ever grows to hand over *frames* —
  a directory of subs for a restack, say — that directory's name belongs in the
  mapping. Backup skips exactly the names declared there and keeps everything else,
  and both errors are silent: an undeclared link tree is a second full copy of
  every frame in every mirrored snapshot (measured at +139 GB on a 186 GB library),
  while over-declaring quietly drops authored work from the backup. Same question
  applies to any third workflow.

#### Phasing

- ✅ **14a** *(done 2026-08-20, `feature/astrowizard-launcher`)* — launcher +
  per-tool Preferences rows + **Send stack to AstroWizard** (preview-then-confirm,
  hardlink + sidecar), calling the same `stacking.apply_handoff` the CLI does.
  Two things the build settled: AstroWizard registers **no** document or URL
  types, so nothing can hand it a file — `launch.sets_working_dir` reports that
  and the flow reveals the folder rather than treating it as a fallback; and the
  picker judges *linear vs stretched* from the stack's **HISTORY cards**, because
  `stacks/` accumulates the user's own saved steps and the newest file is very
  often one of them (a file named `_denoise` whose history carries a stretch three
  entries back). See [`DONE.md`](DONE.md).
- **14b** — ✅ **shipped.** `roundtrip.py` holds the tool-agnostic round-trip and
  `siril.py` delegates to it with its API unchanged; `astrowizard.py` is the thin
  second consumer; `Workflow` grew an `importer` field so `build_derived` reports
  `ready_workflows` alongside the boolean; the import dialog takes a workflow.
  Two things only the real round-trip exposed: a loose finished FITS is a *stack*
  for Siril but a *deliverable* for AstroWizard (which is handed a stack and works
  downstream of it), and AstroWizard's per-action autosave chain emits rasters —
  which are deliverables by default with no hint required — so a 41 MB working
  TIFF was offered for import beside the two genuine exports.
- **14c** — the two-stage pipeline model (see
  [`DATA_MODEL.md`](DATA_MODEL.md) → Future directions): "needs stacking" vs
  "needs finishing" as separate states in `build_processing`, so Processing tells
  the user what to do next rather than only what to open.


### 15 — Process with me: guided Siril post-processing

*Brief written 2026-10-14 from the Astronomy session, for the M110 dev session to
pick up. Placed after #14 because it is the next processing workflow; reorder
freely.*

**The idea.** A skill, plus the engine and tools behind it, that runs a Siril
post-processing session *with* the user. The agent does every step that is
deterministic and can run on the command line, inside the object's sandbox.
It hands the user the GUI steps that need aesthetic judgment, one at a time,
with exact instructions. Then it measures the result before moving on. The
target is the complex, multi-input workflows where most of the work lies in
object-specific inputs: combining two filter stacks, choosing a crop, fixing
what a star remover broke. A single-filter "stack → stretch → done" run gets
little from this.

**Provenance: proved by hand on C6 (NGC 6543), 2026-10-13/14.**
- **Data:** LP 725 × 20 s and IRCUT 1360 × 20 s, both 2× drizzle, produced
  with `m110-stack` per filter.
- **Recipe:** LP nebula + IRCUT stars (star replacement). The LP starless
  carries the nebula, the IRCUT star layer supplies broadband-coloured stars,
  and StarComposer recombines them.
- **How it went:** that session was not allowed to write to the M110 store
  (different project). So it tested every command on clone copies, then wrote
  a step-by-step guide, and the user re-typed each command into Siril. The
  agent still did most of the real work: registration, the crop box, SPCC, the
  catalogue diagnosis, the core-repair arithmetic and every verification. The
  user's GUI time went on the steps only a human can judge, plus a lot of
  transcription. This item removes the transcription.

**Why it belongs here rather than in the Astronomy repo:**
- **The sandbox:** the agent's value is writing intermediates in
  `Images/<target>/siril/` and verifying them, and M110 owns that sandbox.
- **The object-specific inputs:** M110 already holds them — coordinates, the
  per-filter split, stack drizzle and dimensions, filter labels (including the
  Caldwell/IRCUT app-default problem).
- **The pattern:** `siril-stacking` already does measure → propose → agree →
  run. This continues it past the stack.
- **The finish:** **Import finished work** closes the loop.

#### The decision it needs: amending "prepare-and-guide"

The foundational processing-model decision allows M110 to *run* Siril for
stacking only, and says post-processing "stays firmly prepare-and-guide". This
item proposes widening that exception to **deterministic post-processing
steps**, on the same reasoning that justified stacking:

- **Stock commands only:** every command is stock Siril 1.4 (`register`,
  `crop`, `platesolve`, `spcc`, `pm`, …) or a script's own documented CLI.
- **Ours is the choice of settings:** only the parameters come from M110,
  measured and shown with reasons before anything runs.
- **Nothing runs unagreed.**
- **Judgment stays human:** stretch, HDR, tone, sharpening, saturation, star
  recombination and the final look are never automated, only guided.

**Decide this with the user before building.** It is a real change to a
guiding principle ("don't wrap volatile external tools"). The RC-Astro and
VeraLux scripts *are* volatile; see trap 8 below. The MCP side can stay
read-only, like `plan_stack`, with a separate runner that writes, like
`m110-stack`.

#### Division of labour, as it fell out on C6

| Agent, headless (`siril-cli` in the sandbox) | User, in the Siril GUI | Agent, measured checks (not eyeballed) |
|---|---|---|
| Register the filter stacks (`convert`, `setref`, single-pass `register -transf=similarity`), with the subject-carrying layer as reference | Stretch: VeraLux HMS, or GHT | Registration: star-pair count, rotation/shift, identical output dimensions |
| A common crop **chosen by measuring** edge noise in every frame | HDR compression (`HDR_multiscale.py`, which has no CLI) | Crop: outer-band noise ÷ centre noise, empty-pixel count |
| `platesolve -force -order=3`, `spcc` with exact sensor/filter names | Tone (Lighthouse, Curves) and Revela | Colour cast before and after SPCC (background ratio per channel) |
| AutoGradientRemoval (CLI mode works under `siril-cli`) | Saturation | Core survival: fraction of nebula flux in the star image vs radius |
| BlurX/StarX/NoiseXTerminator via their `pyscript` CLIs | StarComposer recombination (no undo) | Range guard: `stat` Max before any VeraLux script |
| Core-repair mask + `pm` arithmetic, `stat` guards, file naming | Approving denoise strength visually (the agent proposes and measures) | Repair exactness: restored region vs the pre-removal original |

**Handoff by files on disk** worked and is the recommended first mechanism:
1. The agent writes named intermediates.
2. The user opens one in the GUI, does the judgment step, and saves under an
   agreed name.
3. The agent picks up from that file and verifies it.

A per-session state file in the sandbox (steps done, files, parameters,
measurements) would make the session resumable, and becomes the record
attached to Import finished work. Driving the *running* Siril GUI directly
(a bridge script inside Siril polling for commands) would be smoother. Defer
it until file handoff proves limiting.

#### Architecture sketch (a proposal; the M110 session decides)

- **Engine module** (e.g. `m110/postprocess.py`):
  - *recipes* are ordered steps, each tagged `auto` (emits a Siril script and
    runs it with `siril-cli` in a dedicated workspace) or `human` (emits exact
    instructions plus the expected output filename);
  - *measure* functions use numpy/astropy and are unit-tested on small
    fixtures.
- **Runner CLI** `m110-process <target> <recipe> [--step ID] [--run]`, shaped
  like `m110-stack`: dry-run by default prints the exact commands.
- **Read-only MCP tools:**
  - `plan_process`: inspects the sandbox and proposes a recipe with its
    object-specific parameters (crop box, SPCC filter names, mask centre and
    radii);
  - `check_process`: runs the measured checks on an intermediate.
- **Skill** `process-with-me`: measure → propose → agree → run the auto steps
  → guide the human step → verify → next.
- **First recipes:**
  1. *LP nebula + IRCUT stars* (emission target in both filters; the C6
     acceptance case).
  2. *LP Hα blend onto a broadband galaxy*. `ContinuumSubtraction.py` is
     GUI-only, so either it's a human step or the engine implements the
     `CS = Hα − c·R` fit itself.
  3. The standard single-filter run.
- **Wording to revise:** `siril-stacking` currently says combining filters "is
  not something M110 or this skill does". Revise that wording when this ships.

#### Traps the engine must handle (all hit on C6)

1. **Global compression preference.** Siril's prefs had Rice q64 on, so every
   write became a lossy `.fit.fz`. Start every session with `setcompress 0`.
2. **The Registration tab's two-pass mode chooses its own reference** by image
   quality. On C6 it picked the IRCUT and resampled the LP, which carries the
   subject. Use `setref <seq> 1` then single-pass `register`.
3. **`convert` sequences every image in the CWD.** Use a dedicated workspace
   holding exactly the inputs.
4. **`crop x y w h` counts `y` from the displayed top**, which is the *last*
   FITS row (verified on a copy). Measurements made in FITS array order must be
   converted.
5. **Edge noise band.** Rotated multi-night drizzle stacks have a 200–400 px
   band inside the ragged border with noise up to 2–5× the centre. A crop to
   non-zero pixels is not enough. The accepted C6 box kept only area within 10%
   of centre noise in **both** frames, and the IRCUT's worst edge (380 px)
   decided it.
6. **SPCC names must match the combo strings exactly.**
   - Sensor: `ZWO Seestar S50`.
   - OSC filter for LP data: `ZWO Seestar LP`, Siril's measured duo-band curve
     (~480–505 / ~648–666 nm), better than narrowband mode.
   - OSC filter for IRCUT data: `UV/IR Block`.
   - The existing `plan_stack` warning about the preset labelling LP frames as
     broadband belongs here too.
7. **A local Gaia SPCC catalogue with a missing chunk fails hard,** with no
   online fallback: `Chunk file not found …` / `Catalog error, no stars
   identified!`.
   - *Cause on this machine:* `Siril_Catalog_Installer.py` had skipped the four
     north-polar level-1 chunks (3, 7, 11, 15) on a checksum error at install.
     That broke SPCC for anything near the pole (C6, M81/M82, NGC 7023)
     *intermittently*, depending on the target.
   - *Pre-flight:* compute the HEALPix level-1 chunks a field's SPCC cone
     touches and check they exist.
   - *Repair:* fetch the `.bz2` + `.sha256sum` from Zenodo record 14738271.
   - *Integrity reference:* don't use record 17988559, the uncompressed one
     behind remote access. Its chunk 5 is truncated (28.8 MB against ~111 MB).
8. **RC-Astro script CLIs drift and carry hidden state.**
   - *Labels change with the version:* StarXTerminator's star output is
     "Generate Star Image" / `--stars` in the installed build, while the
     script's fallback schema says rc-astro 2.5 renamed it `--difference`.
     Read the live schema with `rc-astro sxt --json`.
   - *Saved GUI toggles filter CLI flags:* a saved `csep`/`fsep` (NXT) or
     `ansp` (BXT) silently drops flags that don't apply, so pass every toggle
     explicitly.
   - *Defaults are strong:* NXT defaults every strength to 0.90.
   - *Where outputs go:* SXT writes `stars_<loaded basename>` to the Siril WD
     and leaves the starless only in memory.
   - *Linear data:* keep Unscreen off.
9. **Star removers eat compact, bright cores.** At 1.19″/px, StarXTerminator
   and StarNet both took C6's *whole bright nebula* as one bloated star: 100%
   removed within 20 px, ~80% at 45 px, ~50% at 45–70 px.
   - *The repair is exact:* the star image is original − starless, so restore
     with `starless + mask × stars` and blank the same circle in the
     replacement star layer (`stars × (1 − mask)`).
   - *The mask:* PixelMath has no pixel-coordinate variables, so the engine
     must generate a soft disk centred from RA/Dec via the WCS (full weight to
     60 px, cosine to 0 at 85 px on C6). Verified: the restored core matches
     the original to float precision.
   - *Expect it again:* likely on C22, C55 and M57's inner ring.
10. **`pm` sums LIVETIME/STACKCNT across its inputs** unless given `-nosum`.
11. **Script quirks the instructions must override.**
    - VeraLux HMS defaults to the *Rec.709* sensor profile and Target Bg 0.20.
    - StarComposer has no undo, closes itself, and saves
      `VeraLux_StarComposer_result.fit` next to the last-loaded input.
    - AutoGradientRemoval's CLI only runs under `siril-cli`; in the GUI it
      opens its dialog.
12. **VeraLux range guard:** Max above 65535 in display units makes Curves,
    Revela and StarComposer load black. HMS tolerates up to 1.1×.
13. **Pre-SPCC casts are expected** (C6: LP blue, IRCUT red, from how each
    filter passes skyglow). Measure that the background is neutral *after*
    SPCC; don't alarm the user before it.

#### Open questions

- **The processing-model amendment** (above): the user's call.
- **Where the human instructions live:** in chat (the skill), a
  regenerated per-step `next-steps.md` in the sandbox (an existing M110
  pattern), or an in-app pane.
- **Keeping GUI instructions honest** as scripts update. Read labels from the
  installed script source? Pin versions and warn on mismatch?
- **Recipe format:** data (TOML) or code. How far to generalise beyond the
  first two recipes.
- **Relationship to #14 / the #19 launcher seam:** this is a third
  processing workflow beside "process in Siril" and AstroWizard.

#### Phasing

- **P0:** the C6 recipe as engine steps + `m110-process` (dry-run prints
  commands), with measure functions unit-tested on small fixtures.
- **P1:** `plan_process` / `check_process` MCP tools + the `process-with-me`
  skill.
- **P2:** the galaxy Hα-blend recipe to prove the recipe abstraction
  generalises, then the single-filter standard.
- **Later:** a live bridge into the running Siril GUI.

**Acceptance:** C6 end to end from the two per-filter stacks, with the user
touching only the judgment steps. The agent's restored-core file should match
`starless + mask × stars` to float precision, and its crop should measure
within 10% of centre noise at every edge in both frames.

### 2 — Plan-file generation (device schedules)

Emit **machine** plan files from the night plan the sequencer already computes
(`planning.plan_night` / `sequence_plan` — the human-readable half, the field
guide, shipped with Checkpoint B): **SSC schedule JSON** (port the existing
Astronomy generator), **NINA Advanced Sequences** (schema capture pending),
possibly INDI/Ekos. Validate against a real device before shipping.

**2b — Seestar-native plan hand-off** — *shelved (2026-08-25).* The use case:
emit the night plan M110 already computes in a form the stock Seestar app can
import directly, so a user who plans here can shoot it without retyping targets
into the app — and, unlike the printable field guide, carry per-target capture
settings such as exposure and filter through to the device. It is the natural
end of the planning arc, and the only one of the plan-file targets above that
reaches the device's own app rather than a third-party controller.

**There is no open method.** ZWO publishes no plan-file format, no file-based
import route, and no sanctioned interface for third-party tools; the *Seestar
Software License and Service Agreement* permits use of the software and services
through ZWO's own client, and reserves anything else to ZWO's express written
permission.

So this is shelved on **permission, not effort or design** — and deliberately not
pursued further. Revisit only if ZWO publishes an open plan format or a sanctioned
integration path, or grants written permission for one. Until then M110's planning
output stops at the field guide, which is unaffected.

**Permission requested 2026-09-28** — asked ZWO whether a supported plan-import
interface already exists or is planned and, if not, whether they would publish
one or grant written permission on terms they set. **No substantive reply (as of
2026-10-19):** ZWO sent only an automated acknowledgement (ticket 61063) and,
days later, a satisfaction survey — the ticket appears to have been closed
without an answer. That is silence, not a refusal, so 2b stays shelved on the
same terms as above. A possible next step is a neutral question on ZWO's user
forum asking whether a documented plan format is on the Seestar roadmap.

**2c — Dwarf plan hand-off** — *surveyed 2026-09-29; same deferral as the SSC
option above.* The equivalent question for DwarfLab, asked because the answer
frames 2b. The DWARF app has its own scheduling feature, but publishes no plan
import, export, share or backup surface — so there is nothing in their app to
hand a plan to, and no analogue of the route 2b concerned.

The licensing posture is the opposite of ZWO's, though: the DWARFLAB app
agreement restricts reverse-engineering the app itself and building competing
services, but places no restriction on third-party software communicating with
the telescope, and there is no permission gate to clear. The realistic target is
therefore the community tooling rather than the vendor's app:
`astro_dwarf_session`, an actively maintained MIT-licensed **controller** that
pairs with the scope and drives it live over the same protocol the official app
uses — exactly as SSC does for the Seestar. Its plan queue is file-based,
though, so M110's own surface would be writing JSON into a watched directory and
nothing more: the controller does the driving, and M110 stays a planner, per
*Phase ruthlessly; control last* below.

That puts it on the same footing as SSC, because architecturally it is the same
thing: third-party tooling, worth building when there is real user demand rather
than speculatively. The one asymmetry worth recording is that, unlike 2b, it
needs nobody's permission — so if demand does appear, it is the cheaper of the
two to start.


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

- ✅ **Exclusion mechanism shipped** (`feature/rejected-lights`, issue
  [#110](https://github.com/mjm1138/m110/issues/110), asked for by @devonjones —
  explicitly *"not asking for a UI on this yet"*). The **`Images/<target>/rejected/`**
  tier: move a sub there by hand and it leaves the population. Deliberately built as
  a sibling directory rather than a flag file, because every consumer of subs already
  reads `lights/` **and nothing else** — so prep (`siril._lights`), `scan_sessions`
  integration, `build_processing` and the gallery all exclude it for free, with no new
  branch to keep in sync. Two things did need building:
  - **Import treats the two tiers as one population** (`ingest._light_tier_names`), in
    both directions, which is what stops the telescope re-syncing a rejected frame —
    the entire reason to move rather than delete. Plus a `rejected` layout kind, so a
    store-to-store import (a backup, the precursor library) preserves the exclusion
    instead of reading the subs as loose FITS and routing them back into `lights/`.
  - **`siril.prune_rejected`** — `apply_prep` is add-only, so a sub rejected *after*
    prep kept its sandbox hardlink and went on being stacked; without this the feature
    would only ever work on a target that had never been prepped. It unlinks **only**
    when the frame is present in `rejected/` (a sub that merely vanished may be the
    last copy, so it's left alone and counted as an orphan), skips a target with
    un-imported output (`autoprep`'s in-progress guard), and reaches the stale
    `siril/lights/` a multi-filter target leaves behind (BUGS #28). Runs at refresh
    time via `processing.reconcile_rejected`, kept separate from `prepare_missing` so
    that function's "never touches an existing sandbox" invariant stays true.

  Testing note: a telescope is **just a mounted filesystem**, so the device half is
  automated rather than manual-only. `config.VOLUMES_DIR` made the mount probe
  injectable, `tests/_helpers.mount_seestar`/`mount_dwarf` build scratch volumes
  shaped like each device, and the import→reject→re-import round trip runs through
  the *real* probe and scan. `make_test_corpus.py` ships the matching fixtures:
  M101 mid-rejection with a sandbox that pre-dates it (the prune has real work on
  first refresh), M106 the same but with pending output (the skip), and a
  `-device-mount/` sibling still holding the rejected frames.

  **Still open — the view itself:** the autostretched sub browser, in-app flagging
  (which becomes "move to `rejected/`"), per-frame analysis, and delete-with-confirm.
  The `FrameProfile` fingerprint under [#18](BUGS.md) and the per-session capture
  diagnostics (#45) want the same per-sub facts — worth building that layer once.

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
  pip, so the dependency goes into the build venv and PyInstaller freezes it in —
  installed **explicitly** in each build step (see the next bullet: it can't ride
  in the `build` extra), which means every packaged job needs that line or its
  installer silently ships with no Map view. Exact precedent: astroquery, bundled
  for the same reason (issue **#64** — "a frozen app user can't add the extra
  themselves"). uranometria additionally ships package **data** (`data/*.csv`,
  `.json`, `.tsv`, base64 font assets), so the three specs need
  `collect_data_files("uranometria")` — PyInstaller won't pick those up on its own.
  ⚠️ **Both halves shipped wrong in 0.3.0-beta.1** (fixed in `fix/uranometria-bundle`):
  the specs froze the modules without the data, and since `uranometria.catalog` reads
  its constellation JSON *at import*, the app died at launch with a
  `FileNotFoundError`; meanwhile the Linux/Windows jobs never installed it at all.
  Data only, no `collect_submodules` — `uranometria.annotate` imports matplotlib,
  which the specs exclude.
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
  - 🔶 **Engine done** — `m110/skymap.py` (Qt-free): `build_config` turns a slug
    selection into a fully-specified chart config (coords from
    `catalog.load_coords`, so uranometria never does a lookup and the render is
    offline and deterministic), and `render` returns the per-hemisphere charts
    plus each marker's position for hit-testing. Callers pass their own slug
    list, so the Library page's search / catalog filter / captured-only apply to
    the map without this module knowing they exist. Objects with no coordinates
    (`M42_mosaic`, `Unknown`) are skipped and reported, never fatal. Marker color
    reuses `build_derived`'s own `deep_stack`/`initial` verdict so the map, the
    status chips and the prioritizer cannot disagree. Optional import throughout
    (`SkymapDepsMissing`).
  - ✅ **Map view shipped** — a fourth button in the Library's existing
    List·Grid·Feed segment (`ui/sky_map.py`), so it inherits search, the catalog
    filter and captured-only for free and a marker click is just `select_object`
    driving the same `DetailPane`. Painted with `QSvgRenderer` on a plain
    `QWidget` rather than a `QGraphicsView`: the markers are baked into the
    document, so a scene graph bought nothing, and one scale + centre pair maps
    document↔widget coordinates for both painting and hit-testing. Wheel-zoom
    anchors on the cursor, drag pans past a 3 px threshold (so a wobbly click
    still selects), double-click refits. Selection and hover rings are painted
    over the chart rather than baked in, since they change far more often than
    the document. Rendering is deferred while the map is hidden (`_map_dirty`)
    — a render is ~0.1 s, cheap enough to do synchronously but not on every
    keystroke of a search you can't see.
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
- **`DWARF_DARK/` / `CALI_FRAME/` routing** → darks / calibration tiers. The
  device-level library they route into **landed on `main` 2026-10-18**
  (`feature/calibration-library`): `Calibration/<TELESCOP>/{darks,flats,biases}/`,
  header-only matching (`calibration.py`), Siril prep + `m110-stack` use it, and a
  store-shaped `Calibration/` imports as itself. The DwarfLab `CALI_FRAME/`
  recognizer and its header-stamp shim stay on `feature/draco`.
- **Seestar dark library** — slice 1 **shipped 2026-10-18** (`feature/seestar-darks`,
  see [`DONE.md`](DONE.md)): `darklibrary/` imports into `Calibration/<S50_serial>/darks/`,
  the never-re-apply guard (`devices.darks_applied_on_device`), per-session capture
  facts + the inferred on-device dark and its temperature gap (rule v1; `m110-stack
  --max-dark-gap`), and Tools → Devices… (library, captures, sensor health). This is
  also the first per-session device record (`telescop` on every session row) — the
  registry + `Images/<target>/<device>/` level above are still open. Follow-ups:
  - **Confirm the trigger rule on the device** — a controlled two-target plan at
    dusk (≥2.5 °C vs ≈1.5 °C of cooling between targets); rule v1's ≈2 °C threshold
    and "nearest dark, held for the run" are inferred from three nights, not
    documented by ZWO. Revise `calibration.applied_dark` (bump `DARK_RULE`) on any
    surprise.
  - **Cosmetic correction from the hot-pixel map** — feed the warmest master to
    Siril's cosmetic correction to clean residual hot pixels without a second dark
    subtraction.
  - **Re-darking** (research): `sub + D_applied − D_matched` took a real 13.9 °C
    M 72 sub's hot-pixel residue from −142 to −8 ADU. Opt-in, sandbox-only, never
    `lights/`; needs the device's subtraction model confirmed first.
  - **Open questions** (from the 2026-10-18 analysis; none blocks slice 1):
    - *Does the firmware prune old darks?* If it does, M110's copy is the only
      lasting record — the archive then matters more, and the Devices view should
      say which masters are gone from the device.
    - *Does the device re-pick the nearest dark per frame or once per target run?*
      Rule v1 assumes once per run; the data could not tell them apart below ≈12 °C
      (neighbouring darks differ by ≈8 ADU there). A per-frame re-pick would make
      `dark_gap_c` overstate drift on long runs.
    - *S30 / S30 Pro:* `devices.darks_applied_on_device` assumes they dark-subtract
      on-device like the S50 (same ZWO pipeline) — unmeasured. If wrong, those users
      silently lose dark calibration. Verify with one S30 sub + master (the same
      hot-pixel check as the S50).
    - *Which firmware / app version introduced the dark library?* Unknown; record it
      so "subs before the library" can be dated and the S30 question scoped.
    - *A real `m110-stack` run on a Seestar target* (needs Siril) — slice 1's
      proposal was validated header-only (`build_plan`), not end to end.
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
  Planning added post-beta. **Media brought up to parity** (`feature/media-first-class`):
  its own List/Grid views swapped into the Library's view segment, a detail pane,
  device-sidecar video posters, a recursive per-file scan that surfaces stacked
  results, and the aspect-distortion fix behind "the Moon is an oval" (BUGS → UI
  niceties).
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
- **10 — Library backup** — dated snapshots in two formats (mirrored hardlinked
  trees by default; pooled content-addressed storage where the destination can't
  share files — #92), checksum verify, selective restore, retention + object GC,
  opt-in auto-backup, and **offsite destinations on S3-compatible object storage**
  (#93: `S3Backend` with a configurable `endpoint_url` so B2/R2/Wasabi work,
  credentials in the OS keyring, plus an `essentials` scope tier that keeps the
  light frames — ~99% of the bytes — off the meter). *(The destinations **list** —
  NAS nightly + S3 weekly, per-row scope/schedule/retention — remains open; see
  [`BUGS.md`](BUGS.md).)*
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
| Seestar-native plan hand-off | ⏸ **shelved** — no open or sanctioned import method exists, and ZWO's software/services agreement reserves third-party integration to its express written permission. Permission requested 2026-09-28; awaiting reply. See item **2b** |
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

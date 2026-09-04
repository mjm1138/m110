# M110 — Testing Runbook

Two layers: **automated tests** (fast, the first gate — they cover the mechanical
regression: engine logic *and* the UI flows) and a **human pass** for what a
machine can't cheaply judge — look-and-feel, UX, real hardware, and exploratory
bug-finding. Run the automated layer on every change; do a human pass (using
[`tests/MANUAL_TEST_TEMPLATE.md`](tests/MANUAL_TEST_TEMPLATE.md)) before a release
or after touching a feature area.

> **What's automated now (don't re-do these by hand):** the **ingest dialog**
> (grouping, canonicalization, the ⚠ pointing-remap, alias-remember, apply-only-
> checked, cancel safety — `tests/test_ui_ingest.py`); **processing-prep** (sandbox
> hardlinks/preset, autoprep, import+archive, keep-hero re-import, self-heal —
> `tests/test_siril.py` + `tests/test_processing.py`); **Library/detail** (sort,
> status colours, gallery presence — `tests/test_ui_*.py`); and **rendering**
> (thumbnail/hero **golden-image** comparison — `tests/test_render_golden.py`).
> Sections below now covered by automation are marked **⚙**; spot-check them only
> when something looks off.

---

## How to use this runbook

**§2 is organized by feature area, matching the [user guide](docs/README.md).** A
full pass before a release means all of §2; a normal change means **one area**.

Find what you touched, run that section, and glance at the "also worth a look"
column — most regressions here have historically been in a *neighbouring* area
that shared a seam, not the one that was edited.

| If you changed… | Run | Also worth a look |
|---|---|---|
| `ingest.py`, `ui/import_page.py`, `ui/ingest_dialog.py`, `ui/holding_inspect_dialog.py` | **[§2.2 Ingest](#22-ingest--import)** | §2.3 (new objects must appear), §0.3 (corpus fixtures) |
| `catalog.py`, `objects.py`, `ui/pages/catalog.py`, `ui/detail.py`, `ui/media*.py`, `ui/image_*.py` | **[§2.3 Library](#23-library--object-detail)** | §2.1 (theme), §2.7 (what publishes) |
| `siril.py`, `roundtrip.py`, `astrowizard.py`, `stacking.py`, `processing.py`, `launch.py`, `hints.py` | **[§2.4 Processing](#24-processing)** | §2.5 (the sandbox backup rule) |
| `backup/**`, `ui/backup_dialog.py`, `ui/restore_dialog.py` | **[§2.5 Backup](#25-backup--restore)** | §3 (the pooled/format regressions) |
| `planning.py`, `planning_config.py`, `prioritize.py`, `horizon.py`, `glow.py`, `fieldguide.py`, `ui/pages/planning.py` | **[§2.6 Planning](#26-planning)** | §2.3 (pins are shared) |
| `publish/**`, `ui/publish_dialog.py` | **[§2.7 Publishing](#27-publishing)** | §2.3 (curation decides what publishes) |
| `assistant/**` | **[§2.8 Assistant](#28-ai-assistant)** | §2.6 (its planning tools) |
| `config.py`, `migrate.py`, `refresh.py` | **[§2.1 Getting started](#21-getting-started)** + §0.2 migration | **everything** — these are under all of it |
| `ui/theme/**`, `ui/widgets.py`, `ui/main.py` | **[§2.1](#21-getting-started)** (theme, auto-sync) | every area's visuals; §3 (the modal/teardown drill) |
| any `QThread` worker, dialog teardown, or `.exec()` call | **[§3 Regression sweep](#3-regression-sweep-before-a-release)** — the SIGSEGV drill | the area that owns the dialog |
| `pyproject.toml` deps, `packaging/*.spec` | **[§3](#3-regression-sweep-before-a-release)** — the frozen-app items (needs a real build) | §2.1 (launch) |

**Areas with real-hardware or account requirements** — plan for these, they can't
be done ad hoc: §2.2 (a mounted telescope), §2.4 (Siril, AstroWizard), §2.5c (a
cloud provider account), §2.7 (a GitHub repo). §2.5b runs a local S3 server
instead, and needs no account at all.

---

## 0. Safe test environment

**Never run destructive/manual tests against your real data root.** Point M110 at
a throwaway folder:

```bash
export M110_DATA_ROOT=/tmp/m110-test     # disposable; app bootstraps + seeds it
m110                                      # launches against the temp root
# ...test...
rm -rf /tmp/m110-test                     # reset between runs
```

- Ingest from a **Seestar device is copy-only** (the device is never modified), so
  it's safe to ingest into a temp root repeatedly.
- Ingest from **staging *moves*** files — only put throwaway files in a temp
  root's `Inbox/`.
- To test capture status / rendering without a device, copy a few real objects'
  folders into the temp root's `Images/<target>/lights/` and
  `Images/<target>/seestar-stacks/`, then Refresh.

> ⚠ **`M110_DATA_ROOT` is not the whole story.** Settings live at
> **`~/.m110/settings.json`, outside the data root**, and the log lives beside
> them. Anything that opens a dialog reads them, and any save-shaped action writes
> them — a scratch script once overwrote a real backup destination this way. The
> pytest suite seals both (`tests/conftest.py`); a script run by hand does not.
> See the gotcha ("An ad-hoc GUI script must isolate `SETTINGS_FILE`/`APP_CONFIG_DIR`")
> in [`DONE.md` → Engineering reference](DONE.md#engineering-reference--archived-from-claudemd-2026-09-04) before writing one.

### 0.1 Testing from a git worktree

Feature work often happens in a `git worktree` (an isolated checkout of another
branch, e.g. under `.claude/worktrees/<name>/`), and there is one thing to get
right before any result from one means anything.

**Setup: nothing.** No build step — M110 is pure Python — and **no second venv**.
The venv at the main checkout has every dependency and works from any worktree.

**The catch: `pip install -e .` binds to one checkout, and it isn't yours.** The
editable install writes a finder that hardcodes the *main* checkout's package dir:

```
.venv/…/__editable___m110_0_3_0b4_finder.py → /Users/…/Code/m110/m110
```

So whether you exercise your branch or `main` depends entirely on how you launch —
and when it picks the wrong one, **nothing errors**. You get a clean run, a green
suite, a working app, all from code you didn't change. Verified from inside a
worktree by importing a symbol that exists only on the branch:

| how you launch | `sys.path[0]` | code that runs |
|---|---|---|
| `python -m m110.ui.main` (from worktree root) | the cwd | **the worktree** ✅ |
| `pytest -q` (from worktree root) | rootdir | **the worktree** ✅ |
| `m110` (the console script) | `.venv/bin` | **main checkout** ❌ |
| `python tools/<script>.py` | `tools/` | **main checkout** ❌ |

`-m` and `pytest` put the current directory first, which shadows the finder;
a script's directory is first for the other two, which doesn't.

```bash
cd ~/Documents/Code/m110/.claude/worktrees/<name>
source ~/Documents/Code/m110/.venv/bin/activate
export M110_DATA_ROOT=/tmp/m110-test      # §0 still applies — never the real root
python -m m110.ui.main                    # run the app  (NOT `m110`)
pytest -q                                 # run the suite
PYTHONPATH=$PWD python tools/make_test_corpus.py --no-tar   # tools/ needs this
```

**The rule:** `-m` or `pytest` from the worktree root are safe; **everything else
needs `PYTHONPATH=$PWD`.** The `tools/` case is not hypothetical — it surfaced as
`AttributeError: module 'm110.config' has no attribute 'rejected_dir'` while
generating the corpus from a branch that had just added that function.

**Don't `pip install -e .` inside a worktree.** It re-points the shared venv's
finder at *that* worktree, so the main checkout and every other worktree silently
start running the wrong code too. If it happens, re-run it from the main checkout:

```bash
cd ~/Documents/Code/m110 && pip install -e ".[dev]"
```

**Sanity check when a result surprises you** — one line, and it settles the
question before you debug anything else:

```bash
python -c "import m110; print(m110.__file__)"
```

### 0.2 Migration check (#13)

To exercise the in-place migration, **copy** (never move) an old-shaped root — one
with `data/`, `Images/FITS/…`, `site/img/` — to a temp dir, point `M110_DATA_ROOT`
at the copy, and launch. The store should reshape into
`Objects/ Images/ Media/ Inbox/ .m110_internal_data/`; verify
`Objects/<id>/journal.md` populated, renders under `.m110_internal_data/renders/`,
and the old `data/`/`site/`/`Images/FITS` gone. Relaunch → no further change.

### 0.3 Synthetic test corpus (recommended starting point)

Instead of hand-copying folders, generate a ready-made store that exercises the
whole app. The generator is committed; its **output lives outside the repo**.

```bash
python tools/make_test_corpus.py        # → ~/m110-testdata/m110-test-corpus.tar.gz
tar xzf ~/m110-testdata/m110-test-corpus.tar.gz -C ~/Documents
M110_DATA_ROOT=~/Documents/M110-test m110     # then Refresh (Ctrl+R) first
```

What it contains (and what each fixture exercises):

| Fixture | Tests | Area |
|---|---|---|
| `M51` (lights ×2 nights + Seestar stack + real journal notes) | gallery / hero / sessions / journal feed + detail notes | §2.3 |
| `M81` (lights + stack + notes) | captured-with-stack vs captured-lights-only (no gallery) | §2.3 |
| **`M101`** (18 lights, a `siril/` sandbox hardlinking **all 18**, then **2 moved to `rejected/`**) | the **#110 exclusion tier**, shipped mid-rejection: the sandbox pre-dates the rejection, so the first Refresh has real work to do (`processing.reconcile_rejected` prunes exactly those 2 links). Integration/sessions already exclude the pair; the frames are still on disk | §2.4 |
| **`M42`** (**DwarfLab Dwarf 3**: Duo-Band **`.fits`** lights + an in-app `stacked-16_*.fits` stack + `stacked.jpg`) | the **`.fits`** extension end-to-end (sessions + rendering), a **narrowband** filter, a 2nd device in the store; `stacked.jpg` is force-curated **finished** → the detail **Finished / Working** split (#17) | §2.2, §2.3 |
| **`M13`** (globular cluster: lights + Seestar stack) | object-**type** variety (the corpus is otherwise galaxies + nebulae) — the prioritizer type-weights + a non-galaxy hero | §2.6 |
| `M63` (+ `finished/` render + `stacks/` stack, one linear `_og` + one stretched `_processed`) | "up to date" processing status, an imported deliverable in the gallery, and the **AstroWizard picker's** linear-vs-stretched choice | §2.4 |
| `M106` (+ `siril/` sandbox with **unimported** `…_spcc_processed.png/.fit`) | **Import finished work** round-trip (detection fix) | §2.4 |
| `NGC 7000` (captured, **not** in seed catalog) | **auto-cataloging** on Refresh (becomes clickable, gets a journal) | §2.3 |
| `M81 M82` (multi-object folder) | many-to-many target→object rollups | §2.3 |
| `Media/…_photo` stills + **`Lunar_video/`** (an `.mp4` and an `.avi`, each with its device `_thn.jpg` preview frame; a photo's own `_thn.jpg` duplicate; `.avi.idx`/`.avi.txt`; a nested `ASIVideoStack_Output/` holding a `.jpg` + `.fit`) | the Media scope end-to-end: **video posters** (the grid shows the Moon, not a filename), **recursive** discovery of processed output, **kind decided per file** (a `.jpg` in a `_video/` folder is a photo), Open → OS player, and **Tools → Clean up imported sidecars** — which must offer the photo's duplicate and the `.avi` sidecars while **never** offering a video's poster | §2.3 |
| `Inbox/` holding area: `unsorted_dump/` (headerless FITS + a stray render), loose `orphan.fit` + `NGC 281.fit` | **Import → Holding area panel** (6c): per-folder **manual assign** (object + kind → move into the store); `notes.txt`/`*_thn.` alongside are **not** surfaced | §2.2 |
| **`M110-test-import-source/`** (a sibling folder, also unpacked from the tar): Seestar export `M27_sub`/`m13_sub`/`M65_sub`/`M57/`/`Nightscape_photo/` + a `mixed_dump/` + **Dwarf 3 sessions** (`DWARF_RAW_TELE_M 1_…`, a `STARTRAILS_…` folder, a `DWARF_RAW_WIDE_Unknown_…`) | **Import → Browse…**: grouped+selectable preview; **canonicalisation** (`m13`→`M13`); a **mis-pointed** group (`M65`→M66 ⚠ remap, #12); in-app stack + media; the dump's strays **sweep into the holding area** (6c); the **Dwarf** sessions classify `.fits` subs → lights, `stacked-16`→stack tier, startrails → Media, `Unknown` → holding (identify-by-pointing) | §2.2 |
| **`M110-test-device-mount/`** (a sibling folder, also unpacked from the tar): `Seestar S50/MyWorks/M101_sub/` holding **every** M101 frame the device captured — *including the two the store has rejected* — plus 2 genuinely new subs; `DWARF3/Astronomy/DWARF_RAW_TELE_M 42_…` doing the same for M42 | **#110 no-re-sync**: point Import at it and only the **new** subs are offered — a rejected frame is already in the library (in the other tier) and must not come back. A telescope is just a mounted filesystem, so this directory is a faithful stand-in for one | §2.2, §2.4 |

The generator is covered by `tests/test_make_test_corpus.py`, which builds and
self-checks a corpus on every `pytest -q` run (~1s, into a temp dir). Treat a
failure there as a manual-testing outage, not a test nit: it means
`./create_test_harness.sh` will hand the next person a traceback instead of an app.

Regenerate any time (`python tools/make_test_corpus.py`); `--out`/`--tar` relocate
it, `--no-tar` leaves just the directories. The tarball unpacks **three** siblings —
the store `M110-test/`, the external `M110-test-import-source/` you Browse to, and
`M110-test-device-mount/`. The data-root override is the existing `M110_DATA_ROOT`
env var — no special flag.

### 0.4 Simulating a mounted telescope

A device is just a filesystem: USB or SMB, Seestar or Dwarf, it appears as a mount
and the importer walks it like any other directory. So `M110-test-device-mount/`
reproduces the real thing for everything except the Import page's **device
button**, which probes `/Volumes` for a `MyWorks` folder
(`config.find_seestar_myworks`). Two ways to cover that last inch:

- **Browse… to the mount folder** — same recursive scan, same classification, no
  privileges needed. This is enough for every check in §2.2.
- **A real mount**, if you want the device button itself:
  ```bash
  hdiutil create -size 100m -fs APFS -volname "Seestar S50" /tmp/seestar.dmg
  hdiutil attach /tmp/seestar.dmg
  cp -R ~/Documents/M110-test-device-mount/"Seestar S50"/MyWorks "/Volumes/Seestar S50/"
  ```
  M110 then offers **Seestar** as a source exactly as it would for the real scope.
  `hdiutil detach "/Volumes/Seestar S50"` when done.

The probe's own logic (finds a mount, prefers a Seestar/EMMC-named volume over
another disk that happens to hold a `MyWorks`) is covered automatically in
`tests/test_config.py` against a scratch volumes root, and the full
import→reject→re-import round trip for **both** devices in
`tests/test_rejected_lights.py` (`tests/_helpers.mount_seestar` / `mount_dwarf`).

---

## 1. Automated tests (the gate)

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate
pip install -e ".[dev]"   # pytest + pytest-qt (offscreen Qt driving) + boto3
pytest -q                 # all; must be green before a human pass
```

Engine logic is fixture-based and covers: catalog sort, journal read, derived
reader, ingest plan/apply (incl. cancel + Seestar copy), config/bootstrap,
store migration (old → two-axis, idempotent), image rendering (incl. FITS
thumbnail + hero), backup in both formats and against object storage, and the
session-planning math. The **UI is driven offscreen** with **pytest-qt** (`qtbot`)
— pages/dialogs are constructed, interacted with (clicks, checkboxes, dropdowns,
keyboard), and asserted on state + emitted signals. Shared store/builder fixtures
live in `tests/_helpers.py`; the offscreen platform is set in `tests/conftest.py`.
To regenerate the render goldens after an intentional rendering change:

```bash
M110_UPDATE_GOLDENS=1 pytest -q tests/test_render_golden.py   # refresh tests/goldens/
QT_QPA_PLATFORM=offscreen python -m m110.ui.main              # still constructs cleanly
```

Two checks live outside `pytest` because they can't be faked in-process:

```bash
python tools/smoke_mcp.py     # starts the assistant server over real pipes (CI runs this)
```

---

## 2. Human pass — by feature area

The mechanical pass/fail of most of these is now an automated test (see the
**⚙** markers and the note at the top). What a human is uniquely good at — and
should focus on here — is **visual quality** (does the hero/stretch actually look
right), **responsiveness/feel** (flicker, lag), **real hardware** (a mounted
Seestar over SMB/USB, an actual Siril run), **OS integration** (native file
pickers, "Open In…"), and **opportunistic bug-finding**. Use
[`tests/MANUAL_TEST_TEMPLATE.md`](tests/MANUAL_TEST_TEMPLATE.md) to record a pass
(including an exploratory session); file anything you find in `BUGS.md`.

Mark each pass. A **⚙** section is covered by automation — only spot-check it (or
re-run when its area changes and you want eyes on the visuals).

---

### 2.1 Getting started

*User guide: [Getting started / Getting around](docs/README.md)*

#### First launch / data root
- [ ] Fresh `M110_DATA_ROOT` (empty/nonexistent) → launches, creates the folder,
      seeds an **empty** Library (5d) + a `profiles/default.toml`; Library shows
      **0 objects** until you ingest/Add. Top level is
      `Objects/ Images/ Media/ Inbox/ .m110_internal_data/` (internals + README
      hidden inside).
- [ ] **Old-layout root migrates** (see [§0.2](#02-migration-check-13)): a copied
      pre-#13 root reshapes in place on launch; relaunch makes no further change.
- [ ] Preferences (Cmd+,) → change data folder → Save → prompts restart →
      relaunch reads the new folder.
- [ ] `M110_DATA_ROOT` env var overrides the saved preference.

#### Appearance / theme (UI Phase 0)  ⚙ *(tokens/qss/manager/restyle automated — `test_theme_*.py`)*
- [ ] **Preferences → Appearance → Theme**: switch **Light / Dark / Follow system** →
      the whole app (tables, nav rail, menus, dialogs, status chips, muted labels,
      scrollbars) restyles **live** (no restart); status colors + muted text stay legible
      in both.
- [ ] With **Follow system**, flip the OS appearance (macOS System Settings →
      Appearance) → M110 tracks it — immediately on Qt ≥ 6.8, on next window focus on 6.6.
- [ ] The Publish / Import / Ingest dialogs + the fullscreen image viewer inherit the
      theme (global stylesheet).
- [ ] The journal editor (object **Notes → Edit**) uses the bundled **JetBrains Mono**.
- [ ] Chosen theme **persists** across relaunch (`ui_theme` in `~/.m110/settings.json`).

#### Auto-sync (no manual Refresh needed)
- [ ] **On launch** the Library syncs with disk (capture status reflects current
      `Images/`), without pressing anything.
- [ ] **On window focus**: change something on disk (e.g. drop a render into
      `Images/<target>/finished/` or process a stack), switch away and back to
      M110 → the change appears. (Debounced; runs silently.)
- [ ] An auto-refresh that finds **no change** does **not** disturb the view
      (selected object + scroll preserved; no flicker).
- [ ] An auto-refresh that **does** find changes preserves the selected object.
- [ ] UI stays responsive during sync (threaded; "Syncing…" in the status bar).
- [ ] Manual override still works: View menu → Refresh (Ctrl+R).

#### Updates — banner + Preferences  ⚙ *(engine automated — `test_updates.py`; banner/worker — `test_ui_update_notice.py`)*
- [ ] **Help → Check for updates…**: an up-to-date build shows "You're up to date"; a
      newer release shows an **Update available** dialog with **Download** (opens the
      release page).
- [ ] **Launch banner:** when a newer release exists and the throttle allows, a quiet
      dismissible strip appears above the page stack — **Download · Skip this version ·
      ✕**. **Skip** hides it and never shows that version again; **✕** hides it until next
      launch.
- [ ] **Preferences → Updates → "Check for updates on launch"** toggles the launch check;
      the choice persists (`update_check_enabled`).

---

### 2.2 Ingest & import

*User guide: [Ingest & the library layout](docs/ingest.md)*

#### Import — header classification + layout registry  (6b)  ⚙ *(classification/registry automated — `test_ingest.py`)*
- [ ] Point Import at a **copy of `~/Astronomy/Images`** (a throwaway slice — never the
      live dir). The grouped preview sorts `FITS/<obj>/lights` → `Images/<obj>/lights`,
      `…/stacks` → `stacks`, `Finished Images/<obj>` → `finished`, media → `Media/`; the
      Kind cell **tooltip** names the detected layout ("M110 store" / "Seestar" / "Raw
      FITS"). `process/`+`siril/` sandboxes are **not** imported.
- [ ] A **flat pile of loose `.fit`** (mixed `IMAGETYP`) sorts into separate
      **lights / darks / flats / biases** rows by header; a frame with no usable
      `OBJECT`/`IMAGETYP` is left out (no false routing).
- [ ] **Header wins:** a `DARK`-header frame dropped into an `<obj>_sub/` folder routes
      to `Images/<obj>/darks/`, not `lights/`.
- [ ] Pointing column reads **—** for calibration/finished rows (no false ⚠).
- [ ] Pointing Import at the app's **own `Images/` tree** finds **nothing** to import.

#### Import — holding area + manual assign  (6c)  ⚙ *(sweep/assign automated — `test_ingest.py`, `test_ui_ingest.py`)*
- [ ] Import a messy folder containing a **headerless `.fit`** and a **stray `.jpg`**
      (not in a recognized folder): they appear in the preview as **"→ holding area"**
      rows and, after Import, land in the **Holding area panel** (below the preview).
      A `readme.txt` / `.DS_Store` / `*_thn.jpg` is **not** surfaced.
- [ ] In the panel, pick an **Object** (type a new one or choose from the list) + a
      **Kind**, click **Assign** → confirm → files **move** out of `Inbox/` into
      `Images/<obj>/<kind>` (or `Media/`); the panel row disappears; Library refreshes.
- [ ] "Remember alias?" after an assign persists `ingest_aliases.toml`.

#### Import — DwarfLab Dwarf 3  (6b)  ⚙ *(classification automated — `test_ingest_dwarf.py`, `test_dwarf_store.py`)*
- [ ] Browse the corpus import source's **`DWARF_RAW_TELE_M 1_…`** session: the `.fits`
      raw subs group as **lights → `Images/M1/lights/`**; the in-app `stacked-16_*.fits`
      + `stacked.jpg` route to the **stack tier**; the `Thumbnail/` sidecar + aux rasters
      (`stacked_thumbnail`, `img_*`) are **not** surfaced.
- [ ] The **`STARTRAILS_…`** folder imports only its composite `stacked.jpg` +
      `startrails_*.mp4` → **`Media/Startrails_{photo,video}`** (raw subs ignored).
- [ ] The **`DWARF_RAW_WIDE_Unknown_…`** session (OBJECT = the device placeholder
      `Unknown`) sweeps its subs to the **holding area** for identify-by-pointing — no
      literal `Unknown` target is created.
- [ ] After importing the Dwarf object + Refresh: its `.fits` lights produce a **session**
      (Duo-Band filter) and the `stacked-16` stack renders a **hero + gallery thumbnail**.

#### Ingest — Seestar device  (mounted, USB or SMB)
- [ ] Source dropdown offers "Seestar device — <volume>" when mounted.
- [ ] Selecting it shows a **"Scanning…" modal that does NOT freeze**; the dropdown
      stays usable after; Cancel aborts the scan cleanly. *(Scan-freeze regression.)*
- [ ] Preview lists stacks + lights + media as **copies**.
- [ ] Confirm → **"Copying files…" modal with a progress bar** → completes →
      **modal closes** (does not linger). *(Bug #1 regression.)*
- [ ] Device files remain intact (copy, not move).
- [ ] **EPERM regression:** copying from an SMB mount succeeds (no "Operation not
      permitted").

#### Ingest crash/cancel safety  *(Bug #2 regressions — do these deliberately)*
- [ ] **Close the Ingest window while a scan is running** → no crash.
- [ ] **Close the Ingest window right after a copy finishes** → no crash.
- [ ] **Cancel a copy partway** → stops; summary reads "Ingest cancelled — N
      ingested…"; re-running Ingest copies only the remainder (skip-if-present,
      partial-safe).

#### Ingest — staging  (`Inbox/`)  ⚙ *(grouping/canonicalization/pointing automated — `test_ui_ingest.py`)*
> **Legacy / not in the shipping app:** the modal `IngestDialog` these steps drive is
> no longer launched (superseded by the **Import** page in 6a; `Inbox/` is the 6c
> holding area, not a source). Kept for the engine logic it still exercises in tests;
> for the live GUI flow use the sections above with the `M110-test-import-source/`
> folder.
- [ ] With a `<obj>_sub/` of `.fit` files present, the preview shows **one row per
      object** (Object · Kind · Files · Size · → `Images/<obj>/lights/`) — *not*
      one row per frame — with a running total size in the summary. *(#9)*
- [ ] **Checkboxes** default to all-checked; **Select all/none** works; unchecking
      an object updates the summary and **excludes it** from the ingest. *(#10)*
- [ ] Confirm → progress modal ("Moving files…") → completes → **modal closes**.
- [ ] Only the **checked** objects are *moved* (gone from staging); unchecked ones
      stay; Library refreshes to show the imported ones.
- [ ] **Canonicalization (#12a):** a lowercase/variant folder (`m82_sub/`) shows a
      destination of `Images/M82/…` (folded onto the catalog/existing casing).
- [ ] **Pointing (#12b):** an `M81_sub/` whose frames actually point at M82 shows
      a **`⚠ … → M82?`** in the Pointing column with a **remap dropdown**; choosing
      M82 updates the destination, and confirming routes the frames to
      `Images/M82/…`. A correctly-named object shows **✓**; a non-FITS / no-coord
      object shows **—** (unverified, no false alarm).
- [ ] **Alias (#12c):** when prompted after a remap, "remember" writes
      `.m110_internal_data/ingest_aliases.toml`; a later ingest of that source
      folder auto-routes to the remembered object.

---

### 2.3 Library & object detail

*User guide: [The library & object metadata](docs/library.md)*

#### Library  ⚙ *(natural sort, status colours, gallery presence automated — `test_ui_*.py` / `test_catalog.py`)*
- [ ] The Library (5d) is the **captured/annotated collection** — a fresh root
      starts **empty** and grows by ingest / Add-object; the stat row reads
      `N captured / N total`. (Uncaptured catalog members live in **Goals**.)
- [ ] **Object column sorts naturally** (M1, M2, … M10, M100 — *not* lexical),
      and NGC after Messier; click headers to sort each column. *(eyes-on check.)*
- [ ] Status colours: deep-stack green, initial amber, uncaptured muted.

#### Add object / metadata enrichment (5c/5d)
- [ ] **Add object…** (Library menu): type a name/designation (e.g. `NGC 6888`) → an
      editable offline preview resolves instantly; **Look up online** (Simbad) fills gaps
      on a worker thread; confirm → the object joins the Library with a journal stub. A
      duplicate is refused.
- [ ] **Fill in missing metadata** (right-click the corpus `NGC 6992` stub — blank name,
      `unknown` type): fields backfill from the bundled reference + derived season; real
      user values are never overwritten.
- [ ] **Enrich online…** (right-click / Library menu, on a worker): a Simbad tier fills
      gaps the reference lacks (e.g. the off-catalog `IC 1396`); with astroquery/network
      absent it degrades to a clear "not available" dialog (no crash). An object missing
      **only** its filter is **not** offered enrichment (nothing to add — beta.6).
- [ ] **Remove from Library** (right-click → confirm): the row disappears; the on-disk
      captures/journal are **not** deleted (non-destructive).

#### Object detail / gallery
- [ ] Selecting a row shows metadata, capture stats, journal text.
- [ ] **Captured object shows gallery thumbnails + a hero** — including an object
      whose only images are `.fit` Seestar stacks. *(Bug #3 regression.)*
- [ ] Uncaptured object shows "not captured", no broken images.
- [ ] **Hero scales to the pane** and rescales when you resize the window / drag
      the splitter (doesn't overflow on a tall image).
- [ ] **Season column** sorts Jan→Dec by first month, **Year-round last**.
- [ ] **Gallery** shows full thumbnails (not clipped to one strip);
      **double-click** a thumbnail → image viewer opens; **←/→** (and Prev/Next)
      cycle through the gallery; **Esc** closes. Raster renders show full-res; a
      `.fit`-only stack shows its thumbnail. (Re-Refresh once so `full` paths
      populate for data rendered before this change.)
- [ ] Gallery labels + processing rows show the **actual filenames** (no
      standardized "display names").
- [ ] **Journal** renders Markdown with the author's line breaks preserved and no
      stray `<!-- -->` / `-->`; text wraps to the pane width.

#### Inline journal editing (0.1e)
- [ ] Detail pane shows a **Journal** header with an **Edit** button; an object
      with no notes shows "No notes yet — click Edit to start."
- [ ] Edit → raw `journal.md` (frontmatter + Markdown) opens in a monospace
      editor; **the table and Ingest/Refresh lock** while editing.
- [ ] **Save** writes the file and re-renders (body Markdown + frontmatter
      `hero_caption` reflected); the lock releases. Confirm on disk:
      `Objects/<id>/journal.md` changed.
- [ ] **Cancel** discards edits, re-renders the prior content, releases the lock.
- [ ] Editing a frontmatter `hero` / `hero_caption` then Save → after the next
      sync, the gallery hero / caption updates accordingly.

#### Per-image curation — Finished / Working (#17)
- [ ] The detail gallery splits into **Finished** and **Working files** groups. The corpus
      `M42` has its device preview (`stacked.jpg`) force-curated **finished**, so it shows
      in the **Finished** group though it's a device stack.
- [ ] **Right-click a tile → Mark as finished / Mark as working** regroups it in place and
      persists to journal frontmatter (`finished_extra`/`working_extra`).
- [ ] **Right-click → Set as hero** updates the hero — even to an **older** image (the hero
      re-renders, not left stale, #17); **Open in default app** / **Reveal in file
      manager** work (#19).

---

### 2.4 Processing

*User guide: [Processing prep & hardlinks](docs/processing.md)*

#### Processing-prep round-trip (0.1f)  ⚙ *(prep + import round-trip automated — `test_siril.py` / `test_processing.py`)*
**Preference**
- [ ] Preferences (Cmd+,) shows **"Processing workflows you use:"** with **Siril** and
      **AstroWizard** checked (default) and PixInsight / DeepSkyStacker / Astro Pixel
      Processor **disabled ("soon")**. Saving persists the choice (no restart).

**Auto-setup on ingest (no manual action — there is no "Prepare" button)**
- [ ] With Siril enabled, ingesting a new object's lights makes a sandbox at
      `Images/<target>/siril/` automatically: a **literal** `lights/` holding the
      subs as **hardlinks** (`ls -li` → same inode / link count > 1 as
      `../lights/`), plus `presets/naztronomy_smart_scope_presets.json` (valid
      JSON, drizzle matching the frame count) and `next-steps.md`. M110 does
      **not** create a `process/` (Siril makes its own inside the sandbox).
- [ ] A target with **mixed filters** (LP + IRCUT) gets per-filter jobs
      `siril/IRCUT/` and `siril/LP/`, each a self-contained working dir.
- [ ] **Uncheck all workflows** in Preferences → a subsequent ingest creates **no**
      `siril/` sandbox.
- [ ] **Self-heal on refresh:** delete an object's `siril/` folder, then Refresh
      (Ctrl+R) or refocus the window → the sandbox is recreated automatically;
      objects that already have one are untouched (edited presets preserved). The
      **Tools → Prepare working folders** menu action does the same on demand and
      reports how many were created.

**Import finished work**
- [ ] Simulate Siril: drop a `*_processed.png` and a `*_processed.fit` into
      `siril/` (and a `*_og.fit` / `starless_*.fit` — these must be **ignored**).
- [ ] Reopen the object → **"Import finished work…"** appears. Preview lists the
      render (→ `finished/`) and stack (→ `stacks/`) checked, intermediates absent;
      a **hero** picker lists the raster(s); a **cleanup** choice is offered.
- [ ] Import (cleanup = *archive*) → render shows in the gallery, the chosen hero
      becomes the hero; the run's output + intermediates (incl. Siril's `process/`)
      are **moved** into a visible `siril/[<FILTER>/]archive/<timestamp>/`
      (nothing deleted), while `lights/` + `presets/` stay so the sandbox is ready
      for another run. `Images/<target>/lights/` originals are untouched.
- [ ] **Re-import keeps the hero:** process again, import again → the hero picker
      defaults to **"Keep current (…)"**; a second `archive/<timestamp>/` appears
      alongside the first.
- [ ] **Archive retention:** with **Preferences → "Keep the last N processing
      sessions"** set to 2, import a third time → the oldest `archive/<ts>/` is
      gone and the two newest remain. Set it to 0 ("all") → nothing is pruned.

#### Rejecting subs — the `rejected/` tier (#110)  ⚙ *(prune/import/session rules automated — `test_rejected_lights.py`)*
> Driven entirely from a **file manager** for now — there is no UI yet (that's the
> Lights Table). The whole point is that a rejected sub doesn't come back, so the
> device half needs a real telescope.

**The corpus ships mid-rejection**, so most of this is *observe*, not *set up*: `M101`
has 18 subs, a `siril/` sandbox hardlinking **all 18**, and 2 of them already moved to
`rejected/`. Because the sandbox pre-dates the rejection, the first Refresh has real
work to do. Before launching, note the state:

```bash
cd ~/Documents/M110-test/Images/M101
ls rejected/                        # the 2 excluded frames
ls lights/ | wc -l                  # 16
ls siril/lights/ | wc -l            # 18  ← still linking the rejected pair
```

- [ ] Launch against the corpus and **Refresh (Ctrl+R)**. Re-run the commands:
      `siril/lights/` is now **16** and the two rejected names are gone from it,
      while `rejected/` still holds both files, byte-for-byte. `presets/` and
      `next-steps.md` are untouched.
- [ ] M101's **integration time and session frame counts reflect 16, not 18** —
      before *and* after the refresh (moving the files is what excluded them; the
      prune only tidies the working folder).
- [ ] **The frame is not destroyed:** `ls -li rejected/<name>` — still there and
      readable. Move one back into `lights/`, Refresh → it's re-linked into the
      sandbox and counts again.
- [ ] **A sub that merely vanished is left alone:** `rm` a sub from `lights/`
      *without* putting it in `rejected/`, Refresh → its sandbox hardlink is **kept**
      (it may be the last copy). `~/.m110/logs/m110.log` records it as an orphan.
- [ ] **In-progress runs are not disturbed:** `M106` ships in the *same* state — one
      sub rejected, sandbox still linking it — but it also has unimported output, so
      the prune **skips it entirely**. After Refresh, `Images/M106/siril/lights/`
      still has all 13. Import its finished work, Refresh again → *now* the link is
      pruned. (This is the guard that keeps a mid-flight Siril run intact.)

**No re-sync — the part that makes this worth doing.** Use the shipped
`M110-test-device-mount/` (see [§0.4](#04-simulating-a-mounted-telescope) for how it
stands in for a real scope, and for mounting it as an actual volume if you want the
device button):

- [ ] **Import → Browse…** → `M110-test-device-mount/Seestar S50/MyWorks`. The
      preview offers **2 files** — the two new subs. The two rejected names are
      **not listed**, even though the device still holds them. Confirm the import →
      `lights/` goes 16 → 18, `rejected/` is unchanged.
- [ ] Same for the Dwarf: → `M110-test-device-mount/DWARF3/Astronomy`. Only the
      one new `.fits` sub is offered for M42.
- [ ] **Store-to-store keeps the exclusion:** point Import at a *copy* of the store
      (or a restored backup) → files under `Images/<target>/rejected/` are offered as
      **"rejected subs"** routing back to `rejected/`, never into `lights/`.

#### Headless stacking — `m110-stack`  ⚙ *(settings decisions, layout, handoff automated — `test_stacking.py`)*
> Needs **Siril 1.4 installed** and real subs. The synthetic corpus won't stack —
> its frames have no stars — so use a real capture folder, and copy it out of your
> live store first ([§0](#0-safe-test-environment)). What automation *can't* check
> is a real Siril run.

**Proposal (read-only, safe anywhere)** — nothing is written, so this one may point
at the corpus or a real folder:

```bash
m110-stack "M101"                   # by capture-folder name, resolved in the store
m110-stack ~/some/loose/folder      # or any directory of subs
```

- [ ] Reports frames, exposures, filters, coverage depth, and MOSAIC vs single target.
- [ ] Every proposed setting carries a justification; the **three** phase scripts
      (solve · register · stack) print at the end, followed by *"Proposal only —
      nothing written."* Phase 1 must end at `seqplatesolve` and phase 2 must be the
      one carrying `seqapplyreg ... -filter-included`.
- [ ] `ls` the folder before and after: **unchanged**. (This is the same code path the
      assistant's `plan_stack` uses.)
- [ ] With Siril **not** installed (rename `/Applications/Siril.app` briefly), it exits
      with a message naming Preferences → Processing tools, not a traceback.

**Running it** — on a **copy**, and something small (a few dozen subs, not a mosaic):

```bash
m110-stack "<copy>" --run
```

- [ ] A heartbeat line appears at least once a minute naming the current stage, and
      after the first repeat it shows *"(N:NN in this step)"*. **This is the point of
      the whole progress design** — the stack step is silent for long stretches, so
      without the in-step timer there is no way to tell working from wedged.
- [ ] `siril_stack.log` in the working dir fills **as it goes**, not at the end.
- [ ] On success the stack is renamed to the Naztronomy convention and the run reports
      colour vs MONO. **MONO means the debayer/drizzle pairing broke** — worth stopping for.
- [ ] `process/` is removed and the freed GB reported. Re-run with `--keep-process`
      and confirm it survives, then `--restack` reuses it and skips registration.
- [ ] Ctrl-C mid-run leaves no half-written stack.
- [ ] Three Siril runs happen, not two — `siril_stack.log` (solve),
      `siril_stack_register.log`, `siril_stack_stack.log` all appear in the working dir.

**A partial plate solve** — the case that used to lose the whole run. Hard to force
on purpose; if a real set doesn't produce one, the orchestration is covered by
`test_stacking.py` and what's left to check by hand is that a *real* Siril honours
the split.

- [ ] When the log says *"N images successfully platesolved out of M included"* with
      N < M, the run **does not stop**. It prints the solved count, a per-night
      failure table, and — when the failures concentrate on one or two nights — a
      ready-to-paste `--exclude-night`.
- [ ] It then registers and stacks anyway, and the finished stack's frame count
      reflects the solved subset (never the full set).
- [ ] *"Script execution failed"* from phase 1 is **not** echoed at the end next to a
      successful stack.
- [ ] Re-run the same folder with `--min-solved 99`: it stops instead, having
      registered nothing, and tells you how to lower the bar.
- [ ] **Then re-run it with `--exclude-night <that night>`** — the run must report
      *"Cleared N GB of scratch from a previous run"* and the Siril log must show
      `Sequence found: pp_lights_ 1-><reduced count>`, not the original count. Before
      this was fixed, `process/` survived the failure, Siril refused to rebuild an
      existing `.seq` (*"seqfile 'pp_lights_.seq' already exists, not overwriting"*),
      and the exclusion silently applied to nothing while the proposal printed the
      reduced number. The stack came out **wrong and looked right** — the failure
      mode to watch for here.
- [ ] `--restack` must NOT clear it: run it after a successful `--keep-process`
      run and confirm the registered frames are reused, not deleted.

**Handing on to AstroWizard**

```bash
m110-stack "<copy>" --run --handoff
```

- [ ] `Images/<target>/astrowizard/` now holds the stack plus a `.src.json` sidecar
      naming its source, frame count and stacked-at date.
- [ ] It is a **hardlink**, not a copy — the handoff must cost no disk:
      ```bash
      ls -li Images/<target>/siril/*.fit Images/<target>/astrowizard/*.fit
      ```
      the inode numbers (first column) must match.
- [ ] Open that stack in AstroWizard, export a finished image **into that folder**,
      then Refresh M110: Siril's *Import finished work* must **not** offer it. (This is
      the guard in `config.SANDBOX_DIRNAMES` — before it, Siril claimed the file.)
- [ ] Back up the store and confirm the snapshot keeps `astrowizard/`'s authored work
      but **not** its `lights/` link tree (the same rule checked in §2.5a).

#### Send a stack to AstroWizard (14a)  ⚙ *(candidate discovery, linear/stretched, the write automated — `test_stacking.py` / `test_ui_handoff.py`)*
> The corpus ships **M63** with two stacks for exactly this: a linear `_og` and a
> newer stretched `_processed`. What automation can't check is the launch itself.

**The picker**

- [ ] Open M63 → the detail pane shows **Send to AstroWizard…**. An object with no
      stacks at all does *not* show it.
- [ ] The dialog lists both M63 stacks plus the Seestar in-app stack, newest first,
      with frames and integration filled in.
- [ ] The **stretched** one is at the top (it is newest) but the **linear** one is
      what's highlighted. This is the point of the feature — a stretched image is
      the wrong input for AstroWizard, and the newest file usually is one.
- [ ] Click the stretched row: the line under the table warns it has already been
      stretched. Send stays enabled — it's a warning, not a veto.
- [ ] Sort by any column, then select a row: the name in the confirmation matches
      the row you highlighted. (Reading the selection back by position used to send
      a different file.)
- [ ] Hover a truncated name — the tooltip shows it in full.

**The write**

- [ ] Send. `Images/M63/astrowizard/` now holds the stack plus a `.src.json`
      sidecar naming its source, frame count, stacked-at date and whether it was
      stretched.
- [ ] It is a **hardlink**, not a copy:
      ```bash
      ls -li Images/M63/stacks/M63_119x30sec_og.fit Images/M63/astrowizard/*.fit
      ```
      the inode numbers (first column) must match.
- [ ] Send the same stack again: no error, and the dialog now says it is already
      there.

**Launch and Preferences** — needs AstroWizard actually installed.

- [ ] Preferences → Processing tools shows a row for **Siril** and one for
      **AstroWizard**, each with its auto-detected path as placeholder. Setting one
      does not clear the other.
- [ ] After Send, choose **Open AstroWizard**: it launches *and* the folder is
      revealed. It cannot be handed the file — no document types — so opening the
      folder is the point, not a fallback.
- [ ] With AstroWizard *not* installed (rename the .app briefly), Send still works
      and the dialog says where to set its location instead of offering Open.
- [ ] **Stack in StackingWizard…** launches StackingWizard and reveals the
      `astrowizard/` folder — it takes no arguments at all, so revealing the folder
      is the whole of the hand-off.

---

### 2.5 Backup & restore

*User guide: [Backing up your library](docs/backup.md)*

Always against a **temp root** ([§0](#0-safe-test-environment)), never a live
library. The interesting cases are about the *destination*, which unit tests can
only simulate.

Three destination kinds, in increasing cost to set up. **§2.5b needs no account
and is the one to run on every backup change**; §2.5a needs a disk image; §2.5c
needs a provider account and is a per-release check.

#### 2.5a Local destinations

**Setup — a destination with no hardlinks.** FAT32 has none, so a disk image is the
honest test rig (macOS):

```bash
hdiutil create -size 2g -fs "MS-DOS FAT32" -volname M110TEST /tmp/m110test.dmg
hdiutil attach /tmp/m110test.dmg          # mounts at /Volumes/M110TEST
```

(Linux: `mkfs.vfat` a loop file. Windows: format a small VHD as exFAT.)

- [ ] **Capability line, before the first backup.** Tools → Back up…, choose a normal
      folder: "Unchanged files are shared between backups", plus free space. Choose
      `/Volumes/M110TEST`: it says the destination can't share files. Neither needs an
      existing backup to report this.
- [ ] **Typing a path doesn't freeze the window** — including a path that doesn't exist,
      and (if you have one) a disconnected network share.
- [ ] **Format auto-switch.** On `/Volumes/M110TEST` the format shows **Pooled backups**,
      disabled, with the reason. Back up now → the destination has `objects/`,
      `snapshots/`, `INDEX.tsv`, `restore.py`, `README.txt`. Reopen the dialog: the
      choice stuck.
- [ ] **Second backup is cheap.** Back up again with nothing changed → the summary
      reports ~0 new bytes. Repeat on the normal folder in **Mirrored** mode.
- [ ] **`latest/` is browsable and costs nothing.** On the normal folder in pooled mode,
      open `M110-Backups/<store>/latest/` in Finder — real filenames, real folders — and
      confirm the destination's used space didn't roughly double.
- [ ] **A sandbox's work is backed up; its links are not.** In the first snapshot,
      open `Images/M101/siril/`: `archive/20260701-214500/` is there with its four
      intermediates, `presets/` and `next-steps.md` are there — and `lights/` is **not**.
      Then confirm `Images/M101/lights/` *is* there with all 18 subs. This is the whole
      rule (`config.SANDBOX_LINKED_INPUTS`): the frames are backed up once, under the
      path they really live at, while the hand-work beside them is kept. Getting it
      wrong is silent either way — an un-skipped link tree roughly doubles every
      mirrored snapshot, and an over-skipped sandbox loses processing history nobody
      misses until they want it back. Same check on `Images/M106/siril/`.
- [ ] **Restore an OLDER backup**, in each format, to a scratch folder; spot-check that a
      file you changed between backups comes back with its *old* contents.
- [ ] **Verify integrity** passes on a snapshot of each format.
- [ ] **Recovery without M110.** In `M110-Backups/<store>/`, run
      `python3 restore.py latest-manifest.json.gz /tmp/recovered` and confirm the tree
      comes back with real names. This is the drill that matters if the app is ever
      unavailable — do it at least once per release.
- [ ] **Retention across formats.** With both a mirrored and a pooled backup present, set
      keep = 1 → the older one goes, the newest survives, and files shared with it are
      intact. Run it again → it never deletes the last backup.
- [ ] **Mixed destination.** A destination holding both formats lists both in the restore
      picker, labelled, and restores from either.
- [ ] **Scope applies here too**, not just in the cloud: set **Back up: Essentials** on a
      normal folder → the snapshot's file count drops by the light frames, and the
      restore picker labels it "no light frames". *(Regression: mirrored ignored the
      scope setting entirely, silently backing everything up anyway.)*

Then: `hdiutil detach /Volumes/M110TEST && rm /tmp/m110test.dmg`.

#### 2.5b Cloud, locally — MinIO

**Run this one on any backup change.** MinIO is an S3-compatible server you run
yourself, and it exercises the parts of `S3Backend` that a real AWS bucket would
*not*: M110 sends **path-style addressing whenever a custom endpoint is set**, which
is exactly what MinIO-style deployments require and what AWS never sees. It is also
free and repeatable, so the whole backup → verify → restore cycle can be re-run as
often as you like.

**Setting it up.**

*Docker or Podman — identical on macOS, Linux and Windows, and the simplest route:*

```bash
docker run -d --name m110-minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  quay.io/minio/minio server /data --console-address ":9001"
```

*Native, if you'd rather not run a container:*

| | Install | Run |
|---|---|---|
| **macOS** | `curl -O https://dl.min.io/server/minio/release/darwin-arm64/minio && chmod +x minio` (Intel: `darwin-amd64`) | `./minio server ~/minio-data --console-address ":9001"` |
| **Linux** | `curl -O https://dl.min.io/server/minio/release/linux-amd64/minio && chmod +x minio` | `./minio server ~/minio-data --console-address ":9001"` |
| **Windows** (PowerShell) | download `https://dl.min.io/server/minio/release/windows-amd64/minio.exe` | `.\minio.exe server C:\minio-data --console-address ":9001"` |

Native runs use `minioadmin` / `minioadmin` unless you set `MINIO_ROOT_USER` /
`MINIO_ROOT_PASSWORD` first. On Windows, run the server from a terminal you can
leave open, or install it as a service. The direct download is a single static Go
binary and is the reliable route on macOS: `brew install minio/stable/minio` has no
bottle for a pre-release macOS and falls back to a source build, which then demands
a matching Xcode — that is how it failed here on macOS 27.

**Make a bucket.** Open the console at <http://localhost:9001>, sign in with those
credentials, and create a bucket named `m110test`. (Or, with the `mc` client:
`mc alias set local http://localhost:9000 minioadmin minioadmin && mc mb local/m110test`.)

**Point M110 at it** — Tools → Back up:

| Field | Value |
|---|---|
| Destination | `s3://m110test/backups` |
| Endpoint URL | `http://localhost:9000` |
| Region | `us-east-1` |
| Access key ID | `minioadmin` |
| Secret key | `minioadmin` |

Then **Test connection**.

**Or run the whole engine half in one command.** Everything below that isn't about
the dialog itself — probe, both scopes, verify at both depths, whole-tree restore,
retention, the sweep, `restore.py` from a bucket mirror, the credential chain, and
the server-vanishes case — is scripted, the way `tools/smoke_mcp.py` drives the
assistant server. It starts its own MinIO from a binary you point it at, uses a
scratch store and scratch settings, never touches your keyring, and stops the
server when done (~5 s, 57 checks):

```bash
PYTHONPATH=$PWD python tools/drill_backup_s3.py ./minio     # from the repo root — §0.1
```

Run that on any backup change; do the dialog checks below by hand when the UI
changed.

**The checks.**

- [ ] **The cloud fields appear as you type** `s3://…`, and **before any probe**:
      "Backups are stored as" reads **Pooled backups** and is disabled, its note
      doesn't mention file links or a browsable copy, and **Keep at least … GB free**
      is greyed out. (None of that waits for Test connection — it's all knowable from
      the destination string.)
- [ ] **Test connection** → the status line says "Connected".
- [ ] **Wrong credentials fail clearly.** Change one character of the secret → Test
      connection → an actionable message, not a traceback and not a hang. Repeat with
      a **wrong bucket name**, and with the server stopped (`docker stop m110-minio`) —
      each must answer within a few seconds, not after botocore's default ~2 minutes
      of retries.
- [ ] **The secret is not in `settings.json`.**
      `grep -i minioadmin ~/.m110/settings.json` finds the *access key id* but never
      the secret — that lives in the OS keyring. Reopen the dialog: the secret field
      is empty and reads "Saved — leave blank to keep it".
- [ ] **A blank secret keeps the saved one.** Change the interval, Save, reopen, Test
      connection → still connects.
- [ ] **Back up now** on a small store → completes; the summary names an `s3://…`
      snapshot and shows **no "Open folder"** button.
- [ ] **The bucket has the pooled layout and no `latest/`.** In the MinIO console,
      browse `m110test/backups/M110-Backups/<store>/`: `objects/`, `snapshots/`,
      `INDEX.tsv`, `restore.py`, `README.txt` — and **no `latest/`** (it's a hardlink
      tree, which object storage has no concept of).
- [ ] **Second backup uploads ~nothing.** Run it again unchanged → "0 bytes new".
- [ ] **Verify** reports success. It checks presence and size rather than re-reading
      every object — deliberate, since on a real provider that's a full download.
- [ ] **Restore** a few files to a scratch folder; open one and confirm the contents.
- [ ] **Restore the whole tree** and diff it against the store — MinIO is free, so
      this is the place to do the expensive check that §2.5c would bill you for:
      ```bash
      diff -r ~/Documents/M110-test /tmp/restored | grep -v '\.m110_internal_data/derived\|renders\|sessions.jsonl'
      ```
- [ ] **Essentials scope.** Set **Back up: Essentials**, run again → the file count
      drops by the light frames (on the corpus, 251 → 53 — the synthetic frames are
      tiny, so the *byte* saving is nothing like the "few percent" a real library sees;
      it's the file list that matters here). Then restore from the **earlier**
      everything-snapshot and confirm a light frame still comes back — narrowing must
      not have swept it.
- [ ] **The restore picker labels it**: the essentials snapshot reads "no light frames".
- [ ] **Retention.** Take three snapshots, set keep = 1, back up again → the older
      manifests are gone from `snapshots/`. **But the objects are still all there** —
      that is correct, not a bug: the sweep skips anything modified in the last 24h
      (the grace window that makes GC safe against a concurrent run without a lock),
      and everything in a same-day test is younger than that. To watch the sweep
      actually happen, force the clock past the window:
      ```bash
      python -c "import time; from m110 import backup; print(backup.sweep_objects('s3://m110test/backups', now=time.time()+2*86400))"
      ```
      → `objects/` shrinks to only what the surviving snapshot references, and that
      snapshot still verifies. **Keep at least … GB free must have had no effect** —
      there is no volume to measure, and honouring it would prune a cloud history to
      one snapshot per run.
- [ ] **Recovery without M110.** Download the bucket prefix (`mc mirror
      local/m110test/backups /tmp/frombucket`) and run
      `python3 restore.py latest-manifest.json.gz /tmp/recovered` from inside it — the
      same drill as §2.5a, proving the recovery artifacts travel with a cloud backup too.
- [ ] **Server disappears mid-run.** Start a backup of a larger store, `docker stop
      m110-minio` partway → a clear failure **within ~10–15 s** (the connect timeout,
      not botocore's default minutes of retries), the app stays usable, and no
      snapshot manifest is left behind (`snapshots/` unchanged). Restart the server
      and back up again → it resumes, re-uploading only what didn't make it.

**Tear down:** `docker rm -f m110-minio` (or Ctrl-C the server and delete its data
directory). Delete the keyring entry if you like — it's stored under the service
`m110-backup-s3`.

> Other local S3 servers work the same way if you prefer them — LocalStack, Garage,
> SeaweedFS — the only fields that change are the endpoint and credentials.

#### 2.5c Cloud, hosted — B2 or R2

Once §2.5b passes, what's left is what only a **real provider** shows: a service
rejecting a header botocore sends, a bucket subdomain that doesn't resolve, TLS,
and credentials that work in the AWS CLI but not here. Do this **at least once per
release**, against B2 or R2 rather than AWS — they're the point of `endpoint_url`,
they have usable free tiers, and R2 has no egress charge so a full restore drill is
free.

AWS itself is the *least* informative target here: it exercises no custom endpoint,
keeps virtual-host addressing, and never sees the checksum pin. Worth one pass
eventually to confirm the default path; not the one to reach for first.

Use a **throwaway bucket** and a scratch store ([§0](#0-safe-test-environment)).

| Provider | Endpoint URL | Region |
|---|---|---|
| **Backblaze B2** | `https://s3.<region>.backblazeb2.com` | the bucket's region, e.g. `us-west-002` |
| **Cloudflare R2** | `https://<account-id>.r2.cloudflarestorage.com` | `auto` |
| Amazon S3 | *(leave blank)* | e.g. `us-east-1` |

- [ ] **Credentials + Test connection** as in §2.5b, with the provider's endpoint. For
      R2, confirm the **Region** field accepts the literal `auto`.
- [ ] **Back up now** on a small store → completes over TLS against a real host. This
      is the check that a provider isn't rejecting the request botocore builds.
- [ ] **Second backup uploads ~nothing.**
- [ ] **Verify** succeeds, and remains the shallow presence-and-size check.
- [ ] **Restore** a few files and confirm the contents.
- [ ] **Offline behaves.** Turn off the network → Back up now → a clear failure within
      seconds, and the app stays usable.
- [ ] **Automatic backup reaches the bucket.** Tick **Back up automatically**, quit and
      relaunch → the scheduled run uploads to the bucket. *(Regression: the destination
      was wrapped in `Path()` on this path, which collapses `s3://` to `s3:/` and sent
      scheduled backups to a local folder named `s3:` while manual ones worked.)*
- [ ] **Housekeeping.** Delete the test bucket afterwards, and set a lifecycle rule to
      abort incomplete multipart uploads — orphaned parts bill silently.

---

### 2.6 Planning

*User guide: [Session planning](docs/planning.md)*

⚙ *(engine + sequencer + moon model automated — `test_planning_night.py`, `test_prioritize.py`, `test_fieldguide.py`; UI flows in `test_ui_pages.py`)*

- [ ] **Priority targets:** open Planning → the ranked table populates (a background
      recompute runs once/day; **Recompute** forces it). Flip **Strategy**
      (capture-many ↔ go-deep) and nudge a **weight** → the order changes *instantly*
      (no worker spin-up). Right-click **Pin** → floats to #1 with ▲.
- [ ] **Recompute is quick** (`perf/twilight-cache`): with a Messier-sized goal set it
      finishes in **a few seconds**, not ~half a minute. If it crawls, the twilight
      memoization has regressed — check that ranking more targets isn't re-deriving
      each night per target (`planning._twilight_cached.cache_info()` should show far
      more hits than misses, with misses ≈ the number of distinct nights scanned).
- [ ] **Site profiles:** create a profile (coordinates via **Look up location…** if
      online), import a `.hrz`, **Compute light-dome…** → a `<profile>.glow.hrz`
      appears beside the profile. Switching **Location** re-ranks.
- [ ] **Date picker (regression, #43):** open the **Night:** calendar popup — every
      day number and weekday name renders (no "…"), the selected date is a clear
      accent block, and the **Night:** field itself is readable in **dark mode**.
- [ ] **Generate plan:** pick a date + **Targets** count → schedule rows are
      back-to-back (each Start = previous end), starts on 10-minute marks, no
      **Alt** above ~75° (regression, #37), and the **Moon** column shows "—"
      whenever the moon is down at that slot (regression, #36). Changing **Targets**
      re-sequences instantly; changing the date **clears** the plan ("Night
      changed…" — regression for the #36 desync).
- [ ] **Reorder/exclude:** Move up/down re-chains start times from dusk; unchecking
      a row drops it (a substitute may appear).
- [ ] **Timeline:** target curves + dashed moon track (☾) + dotted **ceiling** line +
      colored slot bands along the bottom; repaints on theme change.
- [ ] **Field guide:** Save → appears under Saved field guides + as
      `Plans/<date>_<slug>.md`; the header describes the whole night's moon
      ("… · sets HH:MM"), the footer carries **both** the generation date and the
      plan night; ⚠ appears only on short window-cut descending slots.

---

### 2.7 Publishing

*User guide: [Publishing your collection](docs/publishing.md)*

#### Static-site export (item 8a)  ⚙ *(select/render/exclusion automated — `test_publish_*.py`)*
> Needs the optional extra: `pip install -e ".[publish]"` (jinja2 + markdown).
- [ ] **Library → Publish / share…** opens the dialog: section checkboxes, target
      list (**Static website** + **GitHub Pages** enabled; Netlify shows **"(soon)"**),
      the Repository field under GitHub Pages (enabled only while it's checked),
      site-title field, output-folder chooser.
- [ ] Pick a **throwaway output folder** (NOT inside the data store), click **Publish**
      → modal progress (Cancel works) → "Published N pages" → **Open folder**.
- [ ] Open `index.html`: catalog table, working **filter** box; captured objects link
      to `objects/<slug>.html` (hero, gallery lightbox ←/→/Esc, sessions, notes). Nav
      shows only the **selected** sections.
- [ ] **Per-object exclude:** right-click an object → **Exclude from publishing** →
      re-publish → that object has **no row and no page**; right-click → **Include** →
      reappears.
- [ ] **Journal privacy:** add `private: true` to an object's `journal.md` frontmatter
      (or tick **Exclude all journal notes**) → its notes are absent from the site.
- [ ] **Deps-missing path:** with the `publish` extra uninstalled, Publish shows a
      clear "pip install 'm110[publish]'" message (no crash).

#### GitHub Pages deploy (BUGS #27a)  ⚙ *(git deploy automated against a local bare repo — `test_publish_ghpages.py`)*
> Needs `git` on PATH and a **real GitHub repo you own** with push access via your
> normal auth (SSH key or credential helper). Use a **scratch repo**, not your live
> site's, unless you intend to replace it — the deploy **force-pushes** `gh-pages`.
- [ ] In Publish / share…, check **GitHub Pages**, enter the repo as `owner/repo`
      (or a full git URL) → Publish → progress → success message shows the
      `https://<owner>.github.io/<repo>/` URL + an **Open site** button.
- [ ] In the repo: a `gh-pages` branch with exactly **one commit**
      ("Publish <date> (M110)"), the site files, and `.nojekyll`. Re-publish →
      still one commit (force-replaced, not appended).
- [ ] **Incremental uploads:** set **Uploads → "Upload only what changed"**, publish
      → the deploy is dramatically faster than the replace-mode publish, and the
      branch gains a **second** commit (history kept). Change one image, re-publish
      → only that image uploads (watch the object count in the progress dialog).
      Switch back to **Replace** → the branch collapses to one commit again.
      *(The blob-less tip fetch is only exercisable against a real GitHub remote —
      local bare repos disallow filters by default and take the fallback path.)*
- [ ] First time only: repo **Settings → Pages → deploy from `gh-pages`** — then
      the URL serves the site (allow a minute or two).
- [ ] **Error paths:** unchecked repo field → validation warning; a repo you can't
      push to → "Publish failed" showing git's actual stderr (auth/not-found), no
      crash; app works offline as before when GitHub Pages is unchecked.
- [ ] **Progress + cancel:** during a big deploy the label switches "Rendering
      site…" → "Uploading to GitHub…" with object-count progress; **Cancel**
      mid-upload returns to the dialog within a second or two (no beach ball) and
      `ps | grep "git push"` shows **no leftover push process**; the remote branch
      is unchanged.
- [ ] **Gallery level:** the combo under Image galleries picks finished-only
      (default) / +device stacks / all. Publish at "All", then re-publish at
      "Finished images only" → the output folder **and** the deployed branch
      shrink (stale derivatives + unchecked section pages are swept, not left
      behind).
- [ ] **Save:** change settings → **Save** → dialog closes, nothing publishes;
      reopen → choices kept.

---

### 2.8 AI assistant

*User guide: [Using an AI assistant](docs/assistant.md)*

⚙ *(registry, schemas, serialization, outbox containment and the write-denylist
automated — `tests/test_assistant_*.py`; the server is smoke-tested over real pipes
by `tools/smoke_mcp.py`, which CI runs)*

> **The invariant this section exists to protect:** no assistant tool modifies or
> deletes anything, and a tool may only *create* a file in the outbox, under quota.
> The automated proof is thorough (byte-identical manifest outside the outbox,
> write-syscall interception, a static AST denylist). What a human adds is
> confirming it holds through a **real client**, which the suite never runs.

**The server, without an AI client** — tells "server broken" apart from "client
can't find it", and needs nothing installed:

```bash
python tools/smoke_mcp.py
```

- [ ] Reports the tool count, the skills, and a library summary, ending with
      *"Server is healthy"*. It **discloses** a stale ranking rather than hiding it.
- [ ] With the `assistant` extra uninstalled, the failure names the extra rather than
      raising an ImportError traceback.

**Connecting a real client**

- [ ] **Preferences → AI assistant → Connection details…** offers the same connection
      in three shapes (an `mcpServers` JSON block · command + env · the
      `claude mcp add` line), each with a working **Copy**.
- [ ] **Set up Claude Desktop…** merges M110 into its config *without* disturbing other
      servers already there (check the file before and after). **Disconnect** removes
      only M110's entry.
- [ ] Restart the client → M110's tools are listed, and the skills appear as prompts.
- [ ] Ask it something that reads the library ("what should I shoot tonight?") → it
      answers from the real store.

**The write boundary** — the part worth doing by hand:

- [ ] Take a checksum of the store before a session and after
      (`find ~/Documents/M110-test -type f -not -path '*/.m110_internal_data/derived/*' \
      -not -path '*/renders/*' | sort | xargs shasum | shasum`), with the derived tiers
      excluded. Ask the assistant to do everything it offers — rank, plan, propose pins,
      propose a journal entry, save a field guide. **The checksum must not change**, and
      anything it produced must be sitting in `.m110_internal_data/assistant/`.
- [ ] With **"save plans straight to `Plans/`"** ticked in Preferences, a saved field
      guide lands in `Plans/` instead — the one sanctioned write, and only that one.
- [ ] Ask it to delete or overwrite something explicitly. It must decline and explain,
      not fail with a traceback.
- [ ] Point the client at a **data root that doesn't exist** → a clear
      "store unavailable" message rather than a bare `FileNotFoundError`.

---

### 2.9 Cross-check with the source workflow (optional)

- [ ] Refresh output (sessions/derived) for a shared object matches the reference
      Astronomy `rebuild.sh` (aside from `processing.json`'s `generated_at`).
- [ ] An emitted preset matches the schema/shape of the reference
      `~/Astronomy/Images/FITS/<obj>/presets/naztronomy_smart_scope_presets.json`.

---

## 3. Regression sweep (before a release)

A single pass over the specific bugs we've fixed, so a regression doesn't slip
through the general visual pass. Each item's mechanical half is a named automated
test; these steps confirm the **user-visible** behavior against the corpus (or real
data / a packaged build where noted).

- [ ] **Dwarf `.fits` recognized everywhere** (the `.fit`-only footgun): the corpus `M42`
      (Dwarf `.fits`) shows captured status, a session, a gallery, and a hero — not an
      empty/uncaptured object. *(`test_ingest_dwarf.py`, `test_dwarf_store.py`.)*
- [ ] **Mount mode from the `EQMODE` header** (not the legacy date heuristic): a session's
      **Mount** column matches the frames' `EQMODE` card. *(`test_scan_sessions.py`.)*
- [ ] **Import keep-both on a same-name re-process** (beta.5): re-import a *different* file
      with a name already in `finished/` → it lands as `…-2.<ext>` and the old one is kept;
      a byte-identical file is skipped. *(`test_siril.py`.)*
- [ ] **Set an OLDER image as hero** re-renders the hero (no stale hero — #17).
      *(`test_build_images.py`.)*
- [ ] **Planning date-picker readable** (#43): the **Night:** calendar popup renders every
      day/weekday, the selection is a clear accent block, and the field reads in **dark
      mode**.
- [ ] **Night-plan sanity** (#37/#36): schedule slots are back-to-back on 10-min marks, no
      **Alt** above ~75°, **Moon** reads "—" when the moon is down, and changing the date
      **clears** the stale plan. *(`test_planning_night.py`.)*
- [ ] **Publish — incremental + gallery-level** (#27): "Upload only what changed" sends
      only changed objects; narrowing the gallery level shrinks the output **and** the
      deployed branch. *(`test_publish_ghpages.py`.)*
- [ ] **A sync landing under an open viewer/menu doesn't crash** (the 0.3.0b3 SIGSEGV):
      open an object, switch to another app, come back (this starts a sync),
      **double-click a gallery thumbnail** and leave the viewer up until the status bar
      stops saying "Syncing…" — then close it. The window must survive, and the page
      refreshes on close. Repeat with a **right-click menu** held open across a sync.
      Best on a large store, where the sync is slow enough to overlap.
      *(Policy half: `test_ui_modal_safety.py` — a real nested loop can't be pumped
      offscreen.)*
- [ ] **Backup on a destination that can't share files** (#92) — **real hardware**, see
      [§2.5a](#25a-local-destinations): the format
      switches to **pooled**, the window says why, and a second backup stores ~no new
      bytes. *(`test_backup_pooled.py`.)*
- [ ] **Scheduled backup reaches a cloud destination** (#93): with `s3://…` saved and
      auto-backup on, a *scheduled* run uploads to the bucket — it must not create a local
      folder named `s3:`. *(`test_backup_destination.py`; see
      [§2.5c](#25c-cloud-hosted--b2-or-r2).)*
- [ ] **Essentials scope applies in both formats** (#93): choosing it for a *local*
      folder drops the light frames too, not just for a bucket. *(`test_backup_scope.py`.)*
- [ ] **macOS: Process in Siril launches** (its bundled Python isn't SIGKILLed) — **real
      hardware**; the env-sanitizer half is `test_launch.py`.
- [ ] **Frozen-app astronomy engine** (#75/#74): in a **packaged build**, Planning + the
      priority ranking compute (no "astronomy engine unavailable") and **Enrich online**
      runs. Rebuild required — the PyInstaller-hook tests (`test_packaging_deps.py`) can't
      reproduce the frozen runtime.
- [ ] **Frozen-app cloud backup** (#93): in a **packaged build**, backing up to a bucket
      works — botocore loads its service model from *data files* at client creation, so a
      bundle with the modules but not the data fails only here. Same shape as #75.

---

## 4. Release smoke (2-minute happy path)

1. `pytest -q` green.
2. Launch on a temp root → ingest a couple of objects from the device → Refresh.
3. Confirm those objects show captured status, gallery thumbnails, and a hero.
4. Close the app cleanly (no crash, no orphaned modal).

---

## Known non-issues

- **`processing.json` changes every Refresh** — it stamps a `generated_at`
  timestamp; the rest of `derived/` is deterministic.
- **Changing the data root prompts a restart** — by design (simplest UX);
  Preferences saves + prompts. (Engine modules read paths dynamically now, so the
  restart is no longer a hard requirement.)
- **Qt font warning** ("Populating font family aliases…") on offscreen runs is
  harmless.
- **`m110-backup-s3` entries in your keyring** after cloud-backup testing are
  expected — one per access key id you tried. Delete them by hand if you want a
  clean slate.

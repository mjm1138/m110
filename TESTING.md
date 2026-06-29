# M110 — Testing Runbook

Two layers: **automated tests** (fast, the first gate — they cover the mechanical
regression: engine logic *and* the UI flows) and a **human pass** for what a
machine can't cheaply judge — look-and-feel, UX, real hardware, and exploratory
bug-finding. Run the automated layer on every change; do a human pass (using
[`tests/MANUAL_TEST_TEMPLATE.md`](tests/MANUAL_TEST_TEMPLATE.md)) before a release
or after touching ingest / rendering / data-root code.

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

**Migration check (#13).** To exercise the in-place migration, **copy** (never
move) an old-shaped root — one with `data/`, `Images/FITS/…`, `site/img/` — to a
temp dir, point `M110_DATA_ROOT` at the copy, and launch. The store should
reshape into `Objects/ Images/ Media/ Inbox/ .m110_internal_data/`; verify
`Objects/<id>/journal.md` populated, renders under `.m110_internal_data/renders/`,
and the old `data/`/`site/`/`Images/FITS` gone. Relaunch → no further change.

### Synthetic test corpus (recommended starting point)

Instead of hand-copying folders, generate a ready-made store that exercises the
whole app. The generator is committed; its **output lives outside the repo**.

```bash
python tools/make_test_corpus.py        # → ~/m110-testdata/m110-test-corpus.tar.gz
tar xzf ~/m110-testdata/m110-test-corpus.tar.gz -C ~/Documents
M110_DATA_ROOT=~/Documents/M110-test m110     # then Refresh (Ctrl+R) first
```

What it contains (and what each fixture exercises):

| Fixture | Tests |
|---|---|
| `M51` (lights ×2 nights + Seestar stack + real journal notes) | gallery / hero / sessions / journal feed + detail notes |
| `M81` (lights + stack + notes), `M101` (lights only) | captured-with-stack vs captured-lights-only (no gallery) |
| `M63` (+ `finished/` render + `stacks/` stack) | "up to date" processing status + an imported deliverable in the gallery |
| `M106` (+ `siril/` sandbox with **unimported** `…_spcc_processed.png/.fit`) | **Import finished work** round-trip (detection fix) |
| `NGC 7000` (captured, **not** in seed catalog) | **auto-cataloging** on Refresh (becomes clickable, gets a journal) |
| `M81 M82` (multi-object folder) | many-to-many target→object rollups |
| `Inbox/` holding area: `unsorted_dump/` (headerless FITS + a stray render), loose `orphan.fit` + `NGC 281.fit` | **Import → Holding area panel** (6c): per-folder **manual assign** (object + kind → move into the store); `notes.txt`/`*_thn.` alongside are **not** surfaced |
| **`M110-test-import-source/`** (a sibling folder, also unpacked from the tar): Seestar export `M27_sub`/`m13_sub`/`M65_sub`/`M57/`/`Nightscape_photo/` + a `mixed_dump/` | **Import → Browse…**: grouped+selectable preview; **canonicalisation** (`m13`→`M13`); a **mis-pointed** group (`M65`→M66 ⚠ remap, #12); in-app stack + media; the dump's strays **sweep into the holding area** (6c) |

Regenerate any time (`python tools/make_test_corpus.py`); `--out`/`--tar` relocate
it, `--no-tar` leaves just the directories. The tarball unpacks **two** siblings — the
store `M110-test/` and the external `M110-test-import-source/` you Browse to. The
data-root override is the existing `M110_DATA_ROOT` env var — no special flag. To
exercise the Seestar **copy** path specifically you still need a real mounted device;
the import-source fixture covers the same classification/grouping/pointing logic.

---

## 1. Automated tests (the gate)

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate
pip install -e ".[dev]"   # pulls pytest + pytest-qt (offscreen Qt driving)
pytest -q                 # all (~223); must be green before a human pass
```

Engine logic is fixture-based and covers: catalog sort, journal read, derived
reader, ingest plan/apply (incl. cancel + Seestar copy), config/bootstrap,
store migration (old → two-axis, idempotent), image rendering (incl. FITS
thumbnail + hero), and the session-planning math. The **UI is driven offscreen**
with **pytest-qt** (`qtbot`) — pages/dialogs are constructed, interacted with
(clicks, checkboxes, dropdowns, keyboard), and asserted on state + emitted
signals. Shared store/builder fixtures live in `tests/_helpers.py`; the offscreen
platform is set in `tests/conftest.py`. To regenerate the render goldens after an
intentional rendering change:

```bash
M110_UPDATE_GOLDENS=1 pytest -q tests/test_render_golden.py   # refresh tests/goldens/
QT_QPA_PLATFORM=offscreen python -m m110.ui.main              # still constructs cleanly
```

---

## 2. Human pass (look-and-feel, UX, real hardware, exploration)

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

### A. First launch / data root
- [ ] Fresh `M110_DATA_ROOT` (empty/nonexistent) → launches, creates the folder,
      seeds an **empty** Library (5d) + a `profiles/default.toml`; Library shows
      **0 objects** until you ingest/Add. Top level is
      `Objects/ Images/ Media/ Inbox/ .m110_internal_data/` (internals + README
      hidden inside).
- [ ] **Old-layout root migrates** (see §0 Migration check): a copied pre-#13
      root reshapes in place on launch; relaunch makes no further change.
- [ ] Preferences (Cmd+,) → change data folder → Save → prompts restart →
      relaunch reads the new folder.
- [ ] `M110_DATA_ROOT` env var overrides the saved preference.

### A2. Appearance / theme (UI Phase 0)  ⚙ *(tokens/qss/manager/restyle automated — `test_theme_*.py`)*
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

### B. Library  ⚙ *(natural sort, status colours, gallery presence automated — `test_ui_*.py` / `test_catalog.py`)*
- [ ] The Library (5d) is the **captured/annotated collection** — a fresh root
      starts **empty** and grows by ingest / Add-object; the stat row reads
      `N captured / N total`. (Uncaptured catalog members live in **Goals**.)
- [ ] **Object column sorts naturally** (M1, M2, … M10, M100 — *not* lexical),
      and NGC after Messier; click headers to sort each column. *(eyes-on check.)*
- [ ] Status colours: deep-stack green, initial amber, uncaptured muted.

### C. Object detail / gallery
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

### C2. Inline journal editing (0.1e)
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

### D. Auto-sync (no manual Refresh needed)
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

### E. Ingest — staging  (`Inbox/`)  ⚙ *(grouping/canonicalization/pointing automated — `test_ui_ingest.py`)*
> **Legacy / not in the shipping app:** the modal `IngestDialog` these steps drive is
> no longer launched (superseded by the **Import** page in 6a; `Inbox/` is the 6c
> holding area, not a source). Kept for the engine logic it still exercises in tests;
> for the live GUI flow use **§E2/§E3** with the `M110-test-import-source/` folder.
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

### E2. Import — header classification + layout registry  (6b)  ⚙ *(classification/registry automated — `test_ingest.py`)*
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

### E3. Import — holding area + manual assign  (6c)  ⚙ *(sweep/assign automated — `test_ingest.py`, `test_ui_ingest.py`)*
- [ ] Import a messy folder containing a **headerless `.fit`** and a **stray `.jpg`**
      (not in a recognized folder): they appear in the preview as **"→ holding area"**
      rows and, after Import, land in the **Holding area panel** (below the preview).
      A `readme.txt` / `.DS_Store` / `*_thn.jpg` is **not** surfaced.
- [ ] In the panel, pick an **Object** (type a new one or choose from the list) + a
      **Kind**, click **Assign** → confirm → files **move** out of `Inbox/` into
      `Images/<obj>/<kind>` (or `Media/`); the panel row disappears; Library refreshes.
- [ ] "Remember alias?" after an assign persists `ingest_aliases.toml`.

### F. Ingest — Seestar device  (mounted, USB or SMB)
- [ ] Source dropdown offers "Seestar device — <volume>" when mounted.
- [ ] Selecting it shows a **"Scanning…" modal that does NOT freeze**; the dropdown
      stays usable after; Cancel aborts the scan cleanly. *(Scan-freeze regression.)*
- [ ] Preview lists stacks + lights + media as **copies**.
- [ ] Confirm → **"Copying files…" modal with a progress bar** → completes →
      **modal closes** (does not linger). *(Bug #1 regression.)*
- [ ] Device files remain intact (copy, not move).
- [ ] **EPERM regression:** copying from an SMB mount succeeds (no "Operation not
      permitted").

### G. Ingest crash/cancel safety  *(Bug #2 regressions — do these deliberately)*
- [ ] **Close the Ingest window while a scan is running** → no crash.
- [ ] **Close the Ingest window right after a copy finishes** → no crash.
- [ ] **Cancel a copy partway** → stops; summary reads "Ingest cancelled — N
      ingested…"; re-running Ingest copies only the remainder (skip-if-present,
      partial-safe).

### G2. Processing-prep round-trip (0.1f)  ⚙ *(prep + import round-trip automated — `test_siril.py` / `test_processing.py`)*
**Preference**
- [ ] Preferences (Cmd+,) shows **"Prepare objects for processing in:"** with
      **Siril** checked (default) and PixInsight / DeepSkyStacker / Astro Pixel
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
      **M110 → Prepare working folders** menu action does the same on demand and
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

### G3. Publishing — static-site export (item 8a)  ⚙ *(select/render/exclusion automated — `test_publish_*.py`)*
> Needs the optional extra: `pip install -e ".[publish]"` (jinja2 + markdown).
- [ ] **Library → Publish / share…** opens the dialog: section checkboxes, target
      list (only **Static website** enabled; GitHub Pages/Netlify show **"(soon)"**),
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

### H. Cross-check with the source workflow (optional)
- [ ] Refresh output (sessions/derived) for a shared object matches the reference
      Astronomy `rebuild.sh` (aside from `processing.json`'s `generated_at`).
- [ ] An emitted preset matches the schema/shape of the reference
      `~/Astronomy/Images/FITS/<obj>/presets/naztronomy_smart_scope_presets.json`.

---

## 3. Release smoke (2-minute happy path)

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

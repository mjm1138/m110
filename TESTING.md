# M110 — Testing Runbook

Two layers: **automated tests** (fast, the first gate) and a **manual regression
checklist** for the GUI flows that aren't unit-tested. Run the automated layer on
every change; run the relevant manual sections before a release or after touching
ingest / rendering / data-root code.

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

---

## 1. Automated tests (the gate)

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate
pytest -q                 # all (~85); must be green before manual testing
```

Engine logic is fixture-based and covers: catalog sort, journal read, derived
reader, ingest plan/apply (incl. cancel + Seestar copy), config/bootstrap,
store migration (old → two-axis, idempotent), image rendering (incl. FITS
thumbnail + hero). UI is smoke-tested offscreen:

```bash
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # constructs/imports cleanly
```

---

## 2. Manual regression checklist

Mark each pass. Re-run a section whenever its area changes.

### A. First launch / data root
- [ ] Fresh `M110_DATA_ROOT` (empty/nonexistent) → launches, creates the folder,
      seeds the catalog; Library shows **111 objects, 0 captured**. Top level is
      `Objects/ Images/ Media/ Inbox/ .m110_internal_data/` (seed catalog +
      README inside the hidden internals).
- [ ] **Old-layout root migrates** (see §0 Migration check): a copied pre-#13
      root reshapes in place on launch; relaunch makes no further change.
- [ ] Preferences (Cmd+,) → change data folder → Save → prompts restart →
      relaunch reads the new folder.
- [ ] `M110_DATA_ROOT` env var overrides the saved preference.

### B. Library
- [ ] All catalog objects listed; status bar shows `N/111 captured`.
- [ ] **Object column sorts naturally** (M1, M2, … M10, M100 — *not* lexical),
      and NGC after Messier; click headers to sort each column.
- [ ] Status colours: deep-stack green, initial amber, uncaptured muted.

### C. Object detail / gallery
- [ ] Selecting a row shows metadata, capture stats, journal text.
- [ ] **Captured object shows gallery thumbnails + a hero** — including an object
      whose only images are `.fit` Seestar stacks. *(Bug #3 regression.)*
- [ ] Uncaptured object shows "not captured", no broken images.

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

### E. Ingest — staging  (`Inbox/`)
- [ ] With a `<obj>_sub/` of `.fit` files present, Ingest preview lists them as
      **moves** to `Images/<obj>/lights/`.
- [ ] Confirm → progress modal ("Moving files…") → completes → **modal closes**.
- [ ] Files are *moved* (gone from staging); Library refreshes to show them.

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

### G2. Processing-prep round-trip (0.1f)
**Auto-setup on ingest**
- [ ] After ingesting a new object's lights, a Siril sandbox appears at
      `Images/<target>/siril/` **without any manual action**: a **literal**
      `lights/` (Siril needs that exact name) holding the subs as **hardlinks**
      (`ls -li` → same inode / link count > 1 as `../lights/`), plus
      `presets/naztronomy_smart_scope_presets.json` (valid JSON, drizzle matching
      the frame count) and `next-steps.md`. M110 does **not** create a `process/`
      (Siril makes its own inside the sandbox).
- [ ] A target with **mixed filters** (LP + IRCUT) gets per-filter jobs
      `siril/IRCUT/` and `siril/LP/`, each a self-contained working dir.

**Manual Prepare (secondary)**
- [ ] A captured object's detail pane shows **"Prepare for processing…"**; it
      re-arranges/refreshes the sandbox (idempotent: "0 arranged, N already
      present"). Guidance list opens playbooks (double-click).

**Import finished work**
- [ ] Simulate Siril: drop a `*_processed.png` and a `*_processed.fit` into
      `siril/` (and a `*_og.fit` / `starless_*.fit` — these must be **ignored**).
- [ ] Reopen the object → **"Import finished work…"** appears. Preview lists the
      render (→ `finished/`) and stack (→ `stacks/`) checked, intermediates absent;
      a **hero** picker lists the raster(s); a **cleanup** choice is offered.
- [ ] Import (cleanup = *lights only*) → render shows in the gallery, the chosen
      hero becomes the hero, `siril/**/lights/` is gone but the rest of the
      sandbox stays, and `Images/<target>/lights/` (originals) is **untouched**.
- [ ] Import with cleanup = *whole sandbox* → `siril/` removed; `lights/`,
      `stacks/`, `finished/` all intact. (Blast radius never leaves `siril/`.)

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

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
  root's `Images/From the scope/`.
- To test capture status / rendering without a device, copy a few real objects'
  folders into the temp root's `Images/FITS/<obj>/lights/` and
  `Images/Seestar_stacks/<obj>/`, then Refresh.

---

## 1. Automated tests (the gate)

```bash
cd ~/Documents/Code/m110
source .venv/bin/activate
pytest -q                 # all (~81); must be green before manual testing
```

Engine logic is fixture-based and covers: catalog sort, journal read, derived
reader, ingest plan/apply (incl. cancel + Seestar copy), config/bootstrap,
image rendering (incl. FITS thumbnail + hero). UI is smoke-tested offscreen:

```bash
QT_QPA_PLATFORM=offscreen python -m m110.ui.main   # constructs/imports cleanly
```

---

## 2. Manual regression checklist

Mark each pass. Re-run a section whenever its area changes.

### A. First launch / data root
- [ ] Fresh `M110_DATA_ROOT` (empty/nonexistent) → launches, creates the folder,
      seeds the catalog; Library shows **111 objects, 0 captured**.
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

### D. Refresh (Ctrl+R)
- [ ] After adding light frames to an object, Refresh updates its capture status
      and integration.
- [ ] Refresh generates thumbnails/heroes (gallery populates for new captures).
- [ ] UI stays responsive during Refresh (threaded).

### E. Ingest — staging  (`Images/From the scope/`)
- [ ] With a `<obj>_sub/` of `.fit` files present, Ingest preview lists them as
      **moves** to `FITS/<obj>/lights/`.
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

### H. Cross-check with the source workflow (optional)
- [ ] Refresh output (sessions/derived) for a shared object matches the reference
      Astronomy `rebuild.sh` (aside from `processing.json`'s `generated_at`).

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
- **Changing the data root needs a restart** — by design (some modules bind paths
  at import); Preferences prompts for it.
- **Qt font warning** ("Populating font family aliases…") on offscreen runs is
  harmless.

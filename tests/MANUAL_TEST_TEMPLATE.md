# M110 — Manual Test Pass

> **How to use this template.** Copy this file to a dated working copy (e.g.
> `manual-pass-2026-06-26.md`), fill in the **Result** / **Notes** columns as you
> go, and run the **Exploratory session** at the end. This pass is for what the
> automated suite *can't* judge — **visual quality, feel, real hardware, and
> opportunistic bug-finding**. Everything mechanical is already covered by
> `pytest -q` (see `TESTING.md` §1); don't re-do those by hand.
>
> File any bug you find in **`BUGS.md`** and reference its id in the Notes column.

- **Build / commit under test:** `__________`  (e.g. `git rev-parse --short HEAD`)
- **Date / tester:** `__________`
- **Platform:** `__________`  (macOS / Windows / Linux + version)
- **`pytest -q` green first?**  ☐ yes  (if no, stop and fix — the human pass assumes a green gate)

---

## 0. Setup (safe temp environment — never the live data root)

```bash
# A disposable, pre-populated store that exercises the whole app:
python tools/make_test_corpus.py                       # → ~/m110-testdata/m110-test-corpus.tar.gz
tar xzf ~/m110-testdata/m110-test-corpus.tar.gz -C ~/Documents
M110_DATA_ROOT=~/Documents/M110-test m110              # launch against the temp root
# ...test... then reset between runs:
rm -rf ~/Documents/M110-test
```

- Ingest from a **Seestar device is copy-only** (device never modified) — safe to repeat.
- Ingest from **staging *moves*** files — only put throwaway files in a temp `Inbox/`.
- Corpus contents are listed in `TESTING.md` §0 (fixtures + what each exercises).

---

## 1. Checklist (Result = ✅ pass · ❌ fail · ⏭️ skip · n/a)

Focus on the columns the machine can't: **does it look right, feel right, and
work against real hardware/OS.**

| # | Area | Steps | Expected outcome | Result | Notes / failure mode / bug |
|---|------|-------|------------------|:------:|-----------------------------|
| 1 | First launch | Launch on a fresh empty `M110_DATA_ROOT` | App opens; empty Library (0 objects); `profiles/default.toml` + internals created; no crash, no orphaned modal | | |
| 2 | Data folder | Preferences (Cmd+,) → change folder → Save | Prompts restart; relaunch reads the new folder | | |
| 3 | Hero quality | Open a captured object with a stack | Hero looks correct — **not** blown-out / black / wrongly cropped; FITS stack is sensibly stretched | | |
| 4 | Hero scaling | Resize the window / drag the splitter | Hero rescales smoothly to the pane; no overflow on a tall image; no flicker | | |
| 5 | Gallery viewer | Double-click a thumbnail; use ←/→ and Esc | Full-frame viewer opens; nav cycles; raster shows full-res, `.fit` shows its thumb; Esc closes | | |
| 6 | Journal render | Open an object with real notes | Markdown renders with line breaks; no stray `<!-- -->` / `-->`; wraps to pane width | | |
| 7 | Auto-sync feel | Drop a render into `Images/<t>/finished/`, switch away & back | Change appears within a moment; selection + scroll preserved; "Syncing…" shown; UI stays responsive | | |
| 8 | Ingest — staging visuals | Ingest the corpus `Inbox/` | Grouped preview reads clearly; size total sane; the ⚠ remap is understandable; progress modal closes cleanly | | |
| 9 | Ingest — **real Seestar** (hardware) | Mount the device (USB or SMB), ingest | Source offered; "Scanning…" doesn't freeze; "Copying…" progress bar; modal closes; device files intact; **no EPERM over SMB** | | |
| 10 | Processing — **real Siril run** (hardware) | Process a prepped `siril/` sandbox in Siril, then Import finished work | Deliverable detected; import routes render→`finished/` + stack→`stacks/`; hero set; run archived; `lights/` intact | | |
| 11 | OS integration | (when implemented) "Open In…" / native file picker | Opens the right app / picker on this OS | | |
| 12 | Clean shutdown | Quit the app (incl. Cmd+Q from a viewer) | No crash, no "thread still running" abort, no orphaned modal | | |

*(Add rows for anything new in this build. Delete rows that don't apply.)*

---

## 2. Exploratory session (session-based testing)

Time-boxed, charter-driven poking — this is where most real bugs surface. Run
1–3 short sessions; keep notes as you go.

### Session A
- **Charter (mission):** _e.g. "Stress the ingest remap + alias flow with messy folder names."_
- **Time box:** _e.g. 30 min_
- **Areas covered:** _________________________________________________
- **What I tried / observed:**
  - _________________________________________________________________
  - _________________________________________________________________
- **Failure modes / rough edges:** _(things that worked but felt wrong)_
  - _________________________________________________________________
- **Bugs filed (→ `BUGS.md`):** _e.g. #NN — short description of what you found_
  - _________________________________________________________________

### Session B (optional)
- **Charter:** _____________________________________________________
- **Areas / observations / bugs:** _________________________________

---

## 3. Sign-off

- **Overall:** ☐ ship  ☐ ship with known issues  ☐ blocked
- **Blocking issues:** _____________________________________________
- **New `BUGS.md` entries:** _______________________________________
- **Goldens regenerated?** (only if a rendering change was intentional) ☐ yes — committed `tests/goldens/`

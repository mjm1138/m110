# TESTING.md — what's left before 1.0.0-beta.1

*Updated 2026-11-23 for store v6 and the 1.0.0-beta.1 cut. First written after the 2026-10-27 walk-through.*

**Background.** The 2026-10-27 pass ran against the synthetic corpus, with the app run from source and driven by
background computer use. Background control can't operate modal dialogs, popups or dropdowns. So for most dialog
flows I tested the **engine path by script** (the same calls the dialog makes) and left the **clicking** to you.

**What changed since.** beta.10 was cut on 2026-11-03. Since then `main` has gained:
- the 1.0 redesign (Phases 7 and 8), Night Vision and the Settings window;
- Stackhammer as a second stacking engine;
- N.I.N.A./PINS import;
- Re-match Calibration;
- store **v6** (`seestar-stacks/` → `device-stacks/`);
- the restore version gate (#40d, PR #227).

The freeze starts at 1.0.0-beta.1, so this is the list for that cut. Section numbers (§) refer to
[`TESTING.md`](TESTING.md).

**Carried items.** Anything marked *(carried)* was on the beta.10 list. I have no record of which of those you ran,
so delete any you did.

Priority key:
- **P0**: before cutting 1.0.0-beta.1. Only a person, a real build or real hardware can catch these, and a miss
  ships to users.
- **P1**: before `1.0.0-rc.1`. The engine is covered and only the clicking is missing.
- **P2**: needs accounts or infrastructure.
- **P3**: optional.

---

## Done since the beta.10 cut (2026-11-23, by you in the live library)

- **Store upgrade to v6** on real data, so the separate snapshot-clone upgrade tests are dropped.
- **The 1.0 redesign** in the real Cocoa window.
- **Real Seestar ingest.**
- **N.I.N.A./PINS import.**
- **Stackhammer.**
- **Re-match Calibration.**
- **The Planning changes** (Plan a night first, the telescope label, Start · Duration · End).

---

## P0 — before the 1.0.0-beta.1 cut

1. **Packaged build, §3 and §4.** This is the most likely place for a beta to break. The last frozen build was
   beta.10. Since then the build has gained:
   - modules: `stackhammer`, `capture_profiles`, `backup.storegate`;
   - the redesign's bundled fonts (Newsreader, JetBrains Mono) and Lucide icons;
   - the newly pinned `uranometria`.

   Build the `.app` and launch it on a temp root, then check:
   - **Planning and the ranking run.** Pass: no "astronomy engine unavailable" (#75/#74). *(carried)*
   - **The 1.0 look survives freezing.**
     - Titles are in the serif (Newsreader), and the journal editor is in JetBrains Mono.
     - Every sidebar, header and menu icon draws (no blank squares).
     - The logo is recolored to match the theme.
     - The assets are collected by `collect_data_files("m110")`, but only a real build proves it (the frozen-build
       rule).
   - **Deep Sky › Map draws.** That proves `uranometria` is in the bundle.
   - **Enrich online** runs. *(carried)*
   - **Back up to a bucket** (frozen botocore data files, #93). MinIO is enough. *(carried)*
   - **Process in Siril** launches without the SIGKILL (macOS, real Siril). *(carried)*
   - **Stackhammer from the packaged app.**
     - Settings › Tools finds it.
     - The bundled `m110-stack "<target>" --engine stackhammer` prints a plan.
     - The assistant's `plan_stackhammer` names the bundled helper, not a bare `m110-stack`.
   - **§4 release smoke** on the packaged app: import → Sync → captured status, gallery and hero → clean quit.
     *(carried)*
   - **Linux AppImage and Windows installer.** Do at least a launch-and-Map check on each CI artifact. The full
     real-hardware run is a 1.0 blocker (P1 below), but a beta that won't start on one platform is a P0.

2. **Sync landing under an open viewer/menu, §3 (the 0.3.0b3 SIGSEGV).** *(carried)* This needs a real nested
   event loop, which can't be pumped offscreen.
   - Open the gallery viewer, switch apps and come back so a sync starts, and leave the viewer up through
     "Syncing…".
   - Repeat with a right-click menu held open.
   - A large store makes the overlap likely; your live library will do.

## P1 — before `1.0.0-rc.1`

### New since beta.10 (dialog flows and real-tool runs)

- **Restore gate (#40d), §2.5a "Restore into the store from an older layout".**
  - An older-layout restore lands under `device-stacks/`.
  - A `"store_version": "99"` snapshot is refused for the store but extracts to a folder.
  - The engine and both dialog paths are covered by `tests/test_restore_store_gate.py`.
- **Integration goals by hand (#184), §2.3.** *(carried; it shipped in beta.10 without a human pass)*
  - **Set goal… → change minutes + reason → Save.** The row, the pill and the Library stat row update without a
    Sync.
  - Manage goals: change a list's **Telescope** picker, then check the Overview counts and the board.
  - **Track for another telescope…** creates "<goal> · <telescope>" scoped to that model.
  - Devices → a device with **no preset**: edit Optics → Save. Its goals rescale.
  - Planning: switch the telescope. The ranking re-orders instantly, and the "Of goal" column follows.

### Carried from the 2026-10-27 pass

**Processing (§2.4).** This is still the largest untested block.
- Settings › Processing workflow list, plus "uncheck all → no sandbox on ingest".
- Sandbox inspection:
  - hardlinked `lights/` (`ls -li`), presets and `next-steps.md`;
  - per-filter and per-capture-path job folders;
  - the #174 tier/label values, including Dwarf `Astro`/`Duo-Band`.
- Self-heal on Sync (there is no manual Prepare any more).
- **Update Siril presets?** dialog: Replace selected / Keep existing / no-ask on the second import.
- **Import finished work…**: hero picker, archive cleanup, re-import keeps the hero, archive retention N=2 / 0.
- Rejected tier (§2.4 #110), driven from the file manager:
  - Integration reflects 16, and the vanished sub is left alone.
  - M106 is undisturbed, and store-to-store keeps the exclusion.
- `m110-stack` with real Siril:
  - The plan is read-only.
  - Heartbeat, live log, `-vvv`, rename, `process/` cleanup and Ctrl-C.
  - The three phases, and the run guard against an import or a second run.
  - A partial plate-solve, `--min-solved`, `--exclude-night` and `--restack`.
- **Send to AstroWizard…** (M63): stretched-row warning, hardlink, re-send, Open AstroWizard, the not-installed
  path, and **Stack in StackingWizard…**.

**Backup dialogs (§2.5a, §2.5d).** The engine drill passed in both formats.
- Capability line before the first backup.
- Typing a non-existent path doesn't freeze Settings › Backup.
- **FAT32 format auto-switch** (needs the `M110TEST` disk image).
- `latest/` costs ~nothing on disk.
- §2.5d, both slots:
  - the summary link opens the Cloud segment, and each segment saves only itself;
  - **File › Back Up Now** runs both in sequence, with last-backup times;
  - Restore's **From:** picker.

**Library and object detail (§2.3).**
- **Add object…** (offline preview, Look up online, duplicate refused).
- **Fill in missing metadata** (NGC 6992).
- **Enrich online…** (IC 1396, and the no-network path).
- **Remove from Library** (non-destructive) plus Edit › Undo.
- Gallery viewer: ←/→ and Esc. The hero rescales on resize and splitter moves.
- Inline journal editing: Edit / Save / Cancel, the lock while editing, `hero_caption`.
- Per-image curation:
  - Mark as finished/working;
  - **Set as hero** on an *older* image (§3 #17);
  - Open in default app, and Reveal.
- Auto-sync on window focus: it preserves the selection, with no flicker when nothing changed.

**Planning (§2.6, §3).**
- **Night date-picker popup** (#43): readable, also in Dark and Night Vision.
- Changing the date clears the plan.
- Reorder / exclude re-chains start times.
- **Field guide Save** → listed, with a file in `Plans/`.
- Site profile create + **Look up location…**.

**Import page dialog flows (§2.2).**
- Staging checkboxes / Select all.
- The "Moving files…" modal closes.
- Canonicalization / pointing / retarget / **Remember alias?** prompts.
- Holding **Assign** confirm → files actually move. I confirmed only that nothing moves *without* confirming.
- A flat pile of mixed-`IMAGETYP` `.fit`.
- A headerless `.fit` + stray `.jpg` → holding.
- Importing another library's `Calibration/`.
- A copy of `~/Astronomy/Images` as a real-world source.

**Settings and app chrome (§2.1).**
- Settings › Appearance: Light/Dark/Follow restyle live and persist. Night Vision only by choice.
- Follow-system OS flip. I skipped it to avoid touching your system setting.
- Data-folder change (Settings › General › Change…).
- **Check for Updates…**, the launch banner (Download / Skip / ✕), and the on-launch toggle.

**Publish dialog (§2.7).**
- The static-site render was verified by script, including the blue badge, exclusion and privacy.
- Not yet clicked: the dialog's own flow, Save-without-publishing, and the deps-missing message.

### Platform QE (a 1.0 blocker)

- **Installers on real hardware, all three platforms**, recorded in `TESTING.md`:
  - the notarized macOS `.dmg`;
  - the Linux AppImage on an x86_64 desktop distro (so far only a from-source ARM run on a Pi 5);
  - the Windows installer on a real Windows machine.

## P2 — needs accounts or infrastructure

- **MinIO cloud drill, §2.5b** (local docker):
  - Test connection, a wrong secret, and the secret not stored in `settings.json`;
  - pooled layout with no `latest/`, and a second run of ~0 bytes;
  - restore + full-tree diff, essentials, and retention;
  - recovery without M110, and the server dying mid-run.
- **B2 or R2, §2.5c**: TLS against a real host, an offline failure, a scheduled backup reaching the bucket (§3 #93),
  and housekeeping.
- **GitHub Pages deploy, §2.7**:
  - one commit on `gh-pages`, and an incremental run shipping only what changed;
  - a lower gallery level shrinks the branch;
  - progress + cancel, error paths, and the first-time Pages setting.
- **Real assistant client, §2.8**:
  - Connection details dialog, and the **Set up Claude Desktop…** merge. I skipped it because it edits a real
    client config.
  - The tools and skills listed after a restart: **19 tools, 5 skills** (now including Stackhammer).
  - "What should I shoot tonight?" round-trip.
  - It declines destructive asks.
  - Save-plans-to-`Plans/` preference.
  - `propose_integration_goal` end to end: "set M77's goal to 7 hours" (propose → the app applies → drift check).
  - `plan_stackhammer` → `propose_stackhammer_preset` → the app applies it.

## P3 — optional

- §2.9 cross-check against the `~/Astronomy` source workflow.
- **A v4 → v6 jump in one launch** (a beta.9 user skipping beta.10). Your live library went v4 → v5 → v6 across two
  launches. The single jump runs the same steps in one pass and is covered by tests, so this is a belt-and-braces
  check. To run it, clone `2026-11-01_140625_503201` with `cp -c` and launch on it with `HOME=/tmp/m110-home`, so
  automatic backup doesn't fire.

---

## Open findings to decide (not test steps)

- **`mixed_dump/edit_final.png` creates target `Images/mixed_dump/finished`.** The finished-render rule treats any
  leaf folder as an object; it has behaved this way since 2026-06-30. The corpus comment expects "stray render →
  holding".
  - Decide: should a folder name that isn't a known object go to the holding area?
  - Not in BUGS.md yet.
- **Startrails preview row** shows only `Media/Startrails_video`, though the `.jpg` goes to `_photo`. Display only;
  the import is correct. Not in BUGS.md yet.
- **Corpus gaps that hide code paths from testers:**
  - There are still no `EQMODE=0` frames (the generator writes only `EQMODE=1`), so the Alt-Az path is never
    shown.
  - Re-check after regenerating the corpus: the device-mount and import-source subs carried no `TELESCOP` (they
    landed under model "unknown"), and `Objects/m51` / `Objects/m81` were lowercase. The N.I.N.A. and dark-library
    corpus work since may have fixed both.
  - Whatever is left is a small `make_test_corpus.py` PR.

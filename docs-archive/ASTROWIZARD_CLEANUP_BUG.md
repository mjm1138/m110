# AstroWizard: temp-file cleanup never runs when the app is quit on macOS

**Reported against:** AstroWizard `2026.08.15` (`com.lukomatico.astrowizard`), macOS 27.0 (Apple silicon)
**Severity:** Low risk, high nuisance — no data loss, but unbounded disk growth
**Status:** Diagnosed, one-line fix proposed

---

## Summary

AstroWizard tracks every intermediate it writes and deletes them on exit — that part
works exactly as designed. But the cleanup is wired **only** to Tk's
`WM_DELETE_WINDOW` protocol, and on macOS **Cmd+Q and the Apple-menu → Quit do not
fire `WM_DELETE_WINDOW`**. Those go through `::tk::mac::Quit`, which the app never
registers.

Since Cmd+Q is how most macOS users quit an app, the normal exit path leaves the
entire `_AW<n>_` chain on disk. Closing the window with the red button cleans up
correctly, which is why the behaviour looks inconsistent rather than broken.

## Impact

One real session — a 2117-frame M27 stack taken through the wizard — left **26 files,
2.02 GB**, in the folder the stack was loaded from:

```
M_27_..._og_AW1_init.fits          M_27_..._og_AW16_adj_curves.fits
M_27_..._og_AW2_crop.fits          M_27_..._og_AW17_adj_pop.fits
M_27_..._og_AW3_crop.fits          M_27_..._og_AW18_adj_sat.fits
M_27_..._og_AW4_crop.fits          M_27_..._og_AW19_adj_curves.fits
M_27_..._og_AW5_grax_bg_0.5.fits   M_27_..._og_AW20_adj_curves.fits
M_27_..._og_AW6_colorcal.fits      M_27_..._og_AW21_adj_curves.fits
M_27_..._og_AW7_sharp_Nor.fits     M_27_..._og_AW22_scnr.fits
M_27_..._og_AW8_sharp_Nor.fits     M_27_..._og_AW23_nl_grax_dn_0.3.fits
M_27_..._og_AW9_lin_grax_dn_0.6.fits  M_27_..._og_AW24_rescreen.fits
M_27_..._og_AW10_str_dee.fits      (+ .tif side-outputs)
M_27_..._og_AW11_starless.fits
M_27_..._og_AW12_stars.fits
M_27_..._og_AW13_starsu.fits
M_27_..._og_AW14_adj_nbn_hoo.fits
M_27_..._og_AW15_bg_dark.fits
```

Most are ~83 MB. The count scales with how much the user does — six of those are
separate curve adjustments and three are separate crops — so an iterative session
costs more, and every re-finish of the same target adds another full set. For anyone
whose library is backed up, each orphaned set is also copied into every subsequent
snapshot.

## Steps to reproduce

1. Load a stack and take it through several wizard steps (any that write an
   `_AW<n>_` file — crop, stretch, curves, …).
2. Export the final image.
3. Quit with **Cmd+Q** (or AstroWizard → Quit).
4. Look in the folder the stack was loaded from — the whole `_AW<n>_` chain is
   still there.

**Contrast:** at step 3, close the window with the red traffic-light button
instead. The chain is deleted as intended.

## Diagnosis

From the shipped bytecode (`astro_wizard` module in the app's PyInstaller archive):

| Symbol | Line | Role |
|---|---|---|
| `AstroWizard.generate_save_path` | 1900 | builds the `_AW{edit_counter}_{tag}` names |
| `AstroWizard.track_temp_file` | 1916 | appends the path to `self.temp_files_generated` |
| `AstroWizard.cleanup_temp_files` | 1011 | removes every tracked file, plus `-bxt` / `-nxt` / `-sxt` / `-starless` / `-stars` twins, then clears `history_stack` / `redo_stack` |
| `AstroWizard.on_closing` | 1032 | `cleanup_temp_files()` then `destroy()` |
| `AstroWizard.__init__` | 616 | `self.protocol("WM_DELETE_WINDOW", self.on_closing)` |

The tracking is thorough: **27** distinct operations call `track_temp_file`
(`apply_auto_crop`, `apply_ratio_crop`, `shave_edge`, `flip_rotate`, `apply_binning`,
`run_bxt`, `run_nxt`, `run_sxt`, `run_starnet`, `_run_graxpert_core`,
`apply_permanent_stretch`, `apply_curves_full`, `apply_scnr`, `apply_nbn`,
`adjust_background`, `run_color_calibration`, `run_native_sharpen`,
`rescreen_stars`, `_finish_star_removal`, `_apply_planetary`, …). So the chain is
registered correctly, and `cleanup_temp_files` would delete all of it.

`cleanup_temp_files` has only three callers: `on_closing` (1032), `load_file` (2207)
and `start_over` (5406). That covers "open something else" and "start over", but the
exit path depends entirely on `WM_DELETE_WINDOW`.

**`createcommand` does not appear in `__init__`, and the string `::tk::mac::Quit`
does not appear anywhere in the binary** (checked across all 401 code objects in the
module). Since this is a `customtkinter` / `ctk.CTk` app, standard Tk-on-macOS
semantics apply: the Apple-menu Quit and Cmd+Q are dispatched to `::tk::mac::Quit`,
and when that command is not defined Tk tears the interpreter down without invoking
the window-delete protocol handler.

That the files back the undo stack (`cleanup_temp_files` clears `history_stack` and
`redo_stack` immediately after deleting them) confirms these are intended to be
temporary, not retained work.

## Suggested fix

Register the macOS quit command alongside the existing protocol handler, in
`__init__` near line 616:

```python
self.protocol("WM_DELETE_WINDOW", self.on_closing)

if sys.platform == "darwin":
    # Cmd+Q and Apple menu -> Quit do NOT fire WM_DELETE_WINDOW; Tk dispatches
    # them to ::tk::mac::Quit, and with no such command it exits without ever
    # calling on_closing - so the tracked temp files are never cleaned up.
    self.createcommand("::tk::mac::Quit", self.on_closing)
```

`on_closing` already does the right thing for this path (cleanup, then `destroy()`).

### Worth considering alongside it

A cleanup that only runs at exit is one crash away from leaking regardless of which
exit path is taken. A sweep at **startup** — scan the working folder for
`_AW<n>_`-named files matching the loaded image's stem and offer to remove
orphans from a previous session — would make the guarantee hold even after a
force-quit or a power loss. `generate_save_path` already has the naming convention,
and the `_AW(\d+)_` regex already used in `_refresh_step_page` would identify them.

## Notes

Diagnosed while adding AstroWizard support to [M110](https://m110.space), which hands
a stack to AstroWizard and imports the finish back. Nothing here depends on M110 —
the same behaviour reproduces with a plain folder. Happy to test a build.

No source repository was found for AstroWizard, so this is written as a report
rather than a patch; the fix above is small enough to apply directly.

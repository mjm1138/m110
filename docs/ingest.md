# Ingest & the library layout

← [Back to the guide](README.md)

## Bringing captures in

Open the **Import** page. Pick a source — a mounted Seestar, a DwarfLab Dwarf 3, an
SD card, or any folder of FITS — and M110 scans it (without changing anything) and
shows a **grouped preview**: one row per object, with the kind of file (light subs,
device stack, finished render, media), the file count, size, and where each group
will land. Device layouts are recognized automatically — a Seestar export, a Dwarf 3
`DWARF_RAW_*` / `STARTRAILS_*` session, an M110 store, or a loose pile of FITS.

- Check or uncheck groups; retarget a group to a different object if the name or
  pointing looks off.
- Nothing is written until you click **Import**. From a telescope, M110 **copies**
  (your device is left untouched); from a staging folder it can move.
- Files M110 can't confidently classify go to a **holding area** (the `Inbox/`
  folder) where you assign them by hand — it never silently drops or misfiles a
  frame. The holding panel **suggests** an object and kind from each file's header
  (double-click a row to inspect the header + a thumbnail), and you can **select many
  rows and assign them to one object/kind at once**.

M110 reads the FITS headers to identify each frame (object, date, exposure, filter,
pointing), so it works across devices regardless of their filename conventions.

## Where things land — the library layout

Your data folder is organized around **two views of the same collection**:

```
<data folder>/            (default ~/Documents/M110)
  Objects/<catalog id>/       one folder per catalog object (M101, C20, …)
    journal.md                  your notes for that object
  Images/<target>/            one folder per capture target
    lights/                     raw light subs — the immutable originals
    stacks/                     Siril stacks you've imported back
    seestar-stacks/             the device's own in-app stacks
    finished/                   your finished, hand-processed renders
    working_files/              processing by-products (starless, crop, stretch…)
    previews/                   per-sub JPG previews (only if you opt in)
    siril/                      the processing sandbox (see Processing)
    (darks/ flats/ biases/)     calibration frames, if you have them
  Media/<category>_photo|_video/   lunar / planetary / scenery / startrails
  Plans/                      saved session field guides (see Session planning)
  Inbox/                      holding area for files awaiting manual assignment
  .m110_internal_data/        hidden app state — catalog, sessions, thumbnails
```

**Why two axes?** `Objects/` is the *catalog* view (one entry per sky object).
`Images/` is the *capture* view (one folder per thing you pointed at). They're kept
separate because a single capture can cover several catalog objects — e.g. one
`M81 M82` session feeds both M81 and M82 — so objects and capture targets are a
many-to-many relationship, not a 1:1 mapping.

**The tiers inside `Images/<target>/` matter.** M110 keeps raw subs, stacks, and
finished renders in separate folders on purpose:

- `lights/` holds **only** raw light subs. M110 treats these as immutable — it reads
  them but never writes into this folder. This is what everything else is derived
  from, so keep it clean.
- `stacks/` and `seestar-stacks/` hold integrated stacks (yours from Siril, and the
  device's in-app stacks respectively).
- `finished/` holds your deliverables — the images you've hand-processed and are
  proud of.

You can browse all of this in your file manager, but the easiest way to see it is the
**Library** page and each object's **detail pane**, which groups the gallery into
"Finished" and "Working files."

Next: **[The library & object metadata →](library.md)**

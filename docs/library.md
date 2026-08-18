# The library & object metadata

← [Back to the guide](README.md)

The **Library** is the hub of M110 — your captured and tracked collection. This page
covers the three ways to view it, how to add and describe objects, and how to curate
each object's images.

## Four views of your collection

A segmented control at the top of the Library switches how you see your objects — your
choice is remembered:

- **Grid** (the default home view) — a wall of hero thumbnails, one tile per object,
  each with its designations, status, and integration time. Drag the zoom slider to
  resize the tiles.
- **List** — a sortable table (Object, Name, Type, Season, Mag, Size, Filter, Status,
  Integration, Sessions). Click a header to sort; the Object column sorts *naturally*
  (M1, M2, … M10, M100 — not alphabetically) and by catalog (Messier before NGC).
- **Feed** — a reverse-chronological stream of object cards (hero + notes), a photo-blog
  of your imaging that re-orders as you reprocess.
- **Map** — your collection plotted on a star chart, so you can see where in the sky
  you've been working and what's still empty. See [The sky map](#the-sky-map) below.

The **catalog filter** lists the catalogs you've set as **goals** (turn them on under
Overview → Manage goals); catalogs you aren't working aren't offered.

A separate **Deep sky · Media** toggle switches the whole page between your catalog
objects and your non-catalog **Media** (lunar, planetary, scenery, startrails — photos
and videos). A search box and a **catalog filter** (All / Messier / Caldwell / …) narrow
the deep-sky views, and a stat row shows captured / total counts and integration time.

Media has its own **List** and **Grid** views, in the same place as the deep-sky ones,
plus a category filter, a **Photos · Videos** switch and a search box. Videos show the
preview frame your telescope saved next to the clip, marked with a small ▶; opening one
hands it to your usual video player (M110 doesn't play video itself). Selecting anything
opens a detail panel with a large preview, its capture date, size and dimensions, and
buttons to open it, reveal it in your file manager, or export a shareable copy.

Media is scanned right through, including subfolders — so stacked results you saved
next to a video, or a whole folder of output from a tool like AutoStakkert, show up
as photos rather than staying hidden.

Click any object to open its **detail pane**: the hero, object notes, the gallery, its
capture sessions, and its processing status.

## The sky map

The **Map** view draws a star atlas of your Library: constellation figures, stars, the
coordinate grid, and a marker for every object you're tracking, in its real position.

Markers carry the same colors as the status chips elsewhere in the app — green for a
**deep stack**, amber for an **initial capture**, muted grey for **uncaptured** — so a few
months' work shows up as a bright patch of sky, and the gaps show you what's still to come.
The key lists only the colors actually on the chart, so an unfiltered map of a collection
you've shot every object in doesn't explain a grey you can't see.

- **Click** a marker to open that object, exactly as clicking a row or tile does; **hover**
  one to see its hero image.
- **Filter to a goal** and the rest of that catalog joins the chart in the muted
  not-yet-shot colour, so the map becomes a picture of your progress against the list —
  which is what makes the gaps visible.
- **Scroll** to zoom (the sky under the pointer stays put), **drag** to pan, and
  **double-click** to fit the disc again.
- The **search box** and **catalog filter** narrow the map just as they narrow the list,
  so you can chart one goal list on its own.
- If you've imaged anything far enough south, an **N · S** toggle appears for the second
  disc; with a northern-only collection there's nothing to toggle, so it stays hidden.
- Objects with no known coordinates are named under the chart rather than silently
  dropped — usually combined capture targets (`M42_mosaic`) or something not yet
  identified.
- If nothing matches your filter you still get the sky, with a line saying why it's
  empty — handy when you've just added a goal and haven't shot any of it yet.

The chart is drawn by [uranometria](https://github.com/devonjones/uranometria), an
optional component. If it isn't installed, the Map view says so and tells you what to
install; nothing else in the Library is affected.

## Adding objects

Most objects appear in your Library automatically — when you ingest a capture, M110
promotes that target into the Library and pulls its reference details (type, magnitude,
size, coordinates, season). Known catalog objects fill in fully; off-catalog targets get
a minimal entry you can enrich.

To add one by hand — to plan for something you haven't shot yet, or to fix an
unrecognized target — use **Library → Add object…**:

1. Type a name or designation (e.g. `NGC 6888`, `Bode's Galaxy`, `M13`).
2. M110 resolves it instantly against its bundled reference into an editable preview.
3. **Look up online** queries [Simbad](https://simbad.u-strasbg.fr/) to fill anything the
   reference doesn't have (runs on a background thread).
4. Confirm — the object joins your Library with a journal stub. Duplicates are refused.

## Filling in missing details

Two right-click actions (also on the Library menu) top up an object's metadata. Neither
ever overwrites a value you've set yourself:

- **Fill in missing metadata** — backfills empty fields from M110's **bundled reference**
  plus the derived observing season. Offline and instant. Use it on a stub that predates
  its catalog data (for example an object imported before you activated its catalog).
- **Enrich online…** — adds a **Simbad** lookup for gaps the reference can't cover (common
  for faint, off-catalog targets). It makes a network call, so it's a deliberate action
  rather than part of the automatic refresh. With no network (or without the optional
  online support installed) it shows a clear "not available" message instead of failing.

> An object that's only missing its *filter* isn't offered online enrichment — no catalog
> knows which filter you shot with, so there'd be nothing to add.

## Removing an object

**Right-click → Remove from Library** takes an object out of your collection. This is
**non-destructive**: it removes the Library entry only — your captures, stacks, finished
renders, and journal on disk are left untouched. (Re-ingesting or refreshing will
re-promote a target that still has images.)

## Looking at an object's images

**Double-click any image to open it full-size** in the viewer — a gallery tile, or the
big hero image at the top of the detail pane. Either way you land on that picture and
can page through the object's other images with **Prev/Next** (or ← / →), zoom, toggle
the capture details, and export. Escape closes it.

## Curating an object's images

The detail-pane gallery is split into two groups — **Finished** (your deliverables) and
**Working files** (device stacks, Siril stacks, by-products). M110 sorts each image by
which folder it's in, and you can override any image:

- **Right-click a tile → Mark as finished / Mark as working** moves it between the groups
  (saved per-object, so it sticks).
- **Set as hero** makes that image the object's headline thumbnail — even an *older* image
  than the current hero (the hero re-renders rather than going stale).
- **Open in default app** / **Reveal in file manager** hand the file off to your OS.

What counts as a "finished" render versus an intermediate by-product is decided by
filename keywords you control in **Preferences → Finished-image hints** (defaults:
`processed`, `final`, `finished`, and the intermediates `starless`, `starmask`).

Next: **[Processing prep & hardlinks →](processing.md)**

# M110 — User Guide

**M110 is a photo library for your smart telescope** — a desktop app that turns a
growing pile of Seestar or DwarfLab captures into an organized deep-sky library:
catalog, capture tracking, ingest, Siril processing-prep, and backup. *Lightroom for
smart telescopes.*

This guide covers what you need to use M110 day to day. It's deliberately short;
each page links to the next.

## Contents

1. [Getting started](#getting-started) — install, first launch, your data folder
2. [Getting around](#getting-around) — the navigation rail, page by page
3. **[Ingest & the library layout](ingest.md)** — how captures come in, and where they land on disk
4. **[Processing prep & hardlinks](processing.md)** — the Siril sandbox, and *what hardlinks mean for your files* (important)
5. **[Backing up your library](backup.md)** — snapshots, retention, and how hardlinked backups behave
6. **[On the roadmap](upcoming.md)** — features you'll see referenced in the UI that aren't finished yet (prioritization, session planning)

---

## Getting started

**Install.** Download the build for your platform (macOS · Linux · Windows) and run
it. During the public beta the builds are unsigned, so your OS may warn on first
launch — see the download page for the per-platform "open anyway" step.

**First launch.** M110 asks where to keep your library — its **data folder**. The
default is `~/Documents/M110`. You can accept it or pick another location (for
example an external drive with room for years of subs). M110 creates the folder
structure and a starter catalog there; it never writes anywhere else.

**Your data is yours.** Everything M110 manages lives inside that one folder as plain
files (FITS, JP/PNG/TIFF, Markdown, TOML). There's no database to corrupt and no
lock-in — you can browse it in your file manager any time. Changing the data folder
later (Library → Preferences) takes effect on restart.

> 🔒 **M110 never touches your originals.** Ingest is always *preview-then-confirm*,
> and it **copies** from your telescope rather than moving — your capture files stay
> exactly where they are until you say otherwise.

---

## Getting around

M110 has a **navigation rail** down the left side. The pages:

| Page | What it's for |
|---|---|
| **Summary** | Landing dashboard — goal progress, what's captured, the processing queue, and your priority targets. |
| **Goals** | Choose which catalogs you're working toward (Messier, Caldwell, …) or build a custom goal list. |
| **Library** | Your collection — every object you've shot (and any you're tracking), as a sortable **table** or a **thumbnail grid**. Click an object to open its detail pane: hero image, notes, gallery, sessions, and processing status. |
| **Processing** | The Siril processing-prep queue, grouped by status (needs work / up to date). |
| **Sessions** | A log of every capture session (date, object, frames, exposure, filter, integration). |
| **Journal** | A reverse-chronological feed of your objects, newest activity first — like a photo-blog of your imaging. |
| **Media** | Non-catalog imagery — lunar, planetary, scenery, startrails. |
| **Import** | Bring in new captures from your telescope, a mounted card, or any folder. |

**The object detail pane** (opens when you select an object in the Library) is where
most per-object work happens: read/edit notes, browse the gallery (finished vs.
working files), set a hero image, and see the object's sessions and processing state.

**Slow operations** (refresh, ingest, backup) run in the background with a progress
dialog you can cancel — the window never freezes.

Next: **[Ingest & the library layout →](ingest.md)**

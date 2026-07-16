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
6. **[Session planning](planning.md)** — site profiles, the automatic target ranking, planning a night, and field guides
7. **[Publishing your collection](publishing.md)** — the static-site export and one-click GitHub Pages deploy
8. **[On the roadmap](upcoming.md)** — features you'll see referenced in the UI that aren't finished yet

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

M110 has a **navigation rail** down the left side with five pages. The **Library** is
home — it opens there.

| Page | What it's for |
|---|---|
| **Library** | Your collection — every object you've shot (and any you're tracking). This is the hub. |
| **Overview** | A dashboard of collapsible sections: goal progress, priority targets, integration time & recent sessions, progress by category, and goal setup. |
| **Planning** | What to shoot next, and tonight's plan — site profiles, the automatic target ranking, the night scheduler, and saved field guides. See **[Session planning](planning.md)**. |
| **Import** | Bring in new captures from your telescope, a mounted card, or any folder. |
| **Processing** | The Siril processing-prep queue — what needs a first stack, what's out of date, and what has finished work ready to import. |

### The Library

The Library opens as a **thumbnail grid** (a wall of your objects). A control row at the
top gives you two segmented toggles:

- **Deep sky · Media** — switch the whole page between your catalog objects and your
  non-catalog **Media** (lunar, planetary, scenery, startrails).
- **List · Grid · Feed** — view your deep-sky objects as a sortable **table**, the
  **grid**, or a reverse-chronological **Feed** of object cards (a photo-blog of your
  imaging). Plus a search box and a catalog filter (Messier, Caldwell, …).

Click any object to open its **detail pane** — where most per-object work happens:
hero image, notes, the gallery (split into *Finished* and *Working files*), the
object's capture sessions, and its processing status. Set a hero, mark an image
finished/working, or import finished Siril work from here.

### Overview

Everything that isn't your object collection lives here as **collapsible sections**
(click a heading's triangle to open/close it; your choices are remembered):

- **Goals** — progress toward each catalog you're tracking.
- **Priority targets** — objects you've pinned (right-click → *Pin as priority* in the
  Library). The **Planning** page adds the automatic ranking on top; pins always win.
- **Integration Time and Sessions** — hours per object, your last few sessions, and a
  **View all sessions…** button for the full log.
- **Progress by category** and **Goal checklists** — per-catalog membership with a green
  check for captured / deep-stacked.
- **Manage goals** — pick which catalogs you're working toward, or build a custom list.

**Slow operations** (refresh, ingest, backup) run in the background with a progress
dialog you can cancel — the window never freezes.

Next: **[Ingest & the library layout →](ingest.md)**

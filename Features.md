# M110 — Feature List

A current snapshot of what the M110 app does today, for announcement / marketing use.
(Companion to [`Why M110.md`](Why%20M110.md). Forward-looking items are separated out
at the bottom so this list stays honest about what ships now.)

## Headline features

- **One-click ingest from your Seestar** (or any staging folder) — preview-then-confirm,
  so nothing moves until you say so. Frames are auto-sorted into a clean, per-target
  library, with filename canonicalization and an **RA/Dec pointing sanity-check** that
  catches mis-labeled captures and lets you re-target them before import.
- **Track your progress through a catalog** — pursue the **Messier** catalog, **Caldwell**,
  **RASC Finest**, **Best-of-Sharpless**, **Bennett**, **Lacaille**, or your own **custom
  lists**. Live per-goal progress, a "what's left to capture" checklist, and
  northern- **and** southern-hemisphere collections.
- **The Library, two ways** — a fast, searchable, sortable **table** and a zoomable
  **image grid** of every object, each showing capture status (initial vs. deep stack)
  and total integration time. Filter by catalog, by "captured only," or search.
- **Automatic Siril processing-prep** — on import, each target is arranged into a
  Siril-ready working folder (hardlinked subs, a preset tuned to the frame count, and
  workflow guidance). When you're done, M110 **imports the finished result back** into the
  library and archives the run — all **without ever altering your original frames**.
- **Knows what needs attention** — tracks which targets are deep vs. just started, and
  flags stacks that are **out of date** because you've captured new subs since the last
  stack. A processing queue surfaces what to work on next.
- **Cross-platform, open-source, offline-first** — native-feeling on **macOS, Linux, and
  Windows**; **Apache-2.0**; a self-contained **local data store** you own (no account, no
  cloud, no lock-in).
- **Publish your collection** — export a clean, selective **static website** of your
  objects, galleries, and notes to a local folder to share however you like.

## Other features

- **A full workspace, not a single view** — Summary dashboard, Goals, Library, Processing,
  Sessions, Journal, and Media pages, with a landing dashboard that shows goal progress,
  current integrations, and a processing snapshot.
- **Rich object pages** — theme-aware hero image, a contact-sheet gallery with a
  full-frame **viewer** (zoom, pan, keyboard navigation, metadata overlay), editable
  per-object **notes**, plus per-object capture sessions, processing status, and object
  details (type, magnitude, size, season, RA/Dec).
- **Journal** — a reverse-chronological feed of your captured objects with rendered notes,
  re-ordered as you reprocess.
- **Sessions log** — every capture session (date, frames, exposure, filter, integration,
  mount), sortable and searchable.
- **Media browser** — your non-catalog lunar / planetary / scenery photos and videos, kept
  alongside the deep-sky collection.
- **Add objects by name or designation** with instant **offline** lookup, plus optional
  **online (Simbad)** enrichment for coordinates and metadata; backfill missing metadata
  for objects you already track.
- **Auto-discovery** — shoot something new and it appears in your Library on the next sync,
  pulling full reference metadata for known catalog objects.
- **First-class Seestar stacks & finished renders** — in-app Seestar stacks and your
  hand-finished images sit alongside the raw subs, and any of them can be the object's
  hero.
- **Backup & restore** — fast **hardlinked, dated snapshots** to an external drive
  (near-free incrementals), with integrity verification, selective restore, retention
  policies, and optional auto-backup on launch.
- **Priority targets** view on the dashboard.
- **Light / dark theming** that follows your OS appearance, a tuned design system, and a
  bundled monospace typeface for aligned technical data (RA/Dec, integration, filenames).
- **Astronomer's-notebook branding** — a hand-inked logo and a parchment app icon.
- **Stays out of your way** — auto-syncs on launch, on window focus, and after each
  import; long operations run in the background with progress and a working Cancel.
- **Runs fully offline** — a bundled reference catalog (448 objects) and bundled Siril /
  Seestar workflow playbooks; the internet is only ever optional (online metadata lookups).

## In development (not yet in the app)

*Named here because [`Why M110.md`](Why%20M110.md) describes them — they're the roadmap,
not current features.*

- **Session planning** — pick tonight's targets by your location, horizon, local
  light-pollution domes, and lunar phase; schedule objects at peak visibility; emit a
  field-guide plan. (The positional/observability engine is built; the planning UI is
  next.)
- **Automatic prioritization** — a deterministic, tunable scoring engine that ranks
  targets toward your goals (season urgency, "capture many" vs. "go deep," feasibility),
  replacing today's hand-edited priority list.
- **Optional LLM assistant** — connect Claude (or another LLM) for session-plan help,
  processing/settings advice, and result critique. Core M110 works fully without it.
- **Beyond the Seestar & Siril** — support for other smart telescopes / rigs and additional
  processing workflows over time.

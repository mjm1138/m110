# M110

**Complete the catalog.**

M110 is a cross-platform desktop app (PySide6, over a headless Python engine)
for managing a smart-telescope deep-sky imaging collection: a catalog/library,
capture tracking, ingest from the telescope or staging, and Siril
processing-prep. North star: **"Lightroom for smart telescopes."**

> Named for Messier 110 — the dwarf elliptical in Andromeda that Charles
> Messier observed in 1773 but never added to his catalog; it was retroactively
> designated the 110th and final entry. The whole point of the app is to get
> there. (It's also, fittingly, a row in the app's own catalog.)

## Status

v0.1 ("the Library") feature-complete — catalog/library, capture tracking,
ingest, inline journals, and Siril processing-prep. See [`ROADMAP.md`](ROADMAP.md)
for status and [`CLAUDE.md`](CLAUDE.md) for full developer context.

## Data store

M110 owns its own data folder (catalog, captures, derived rollups, renders),
created and seeded on first launch. Resolution order:

- `M110_DATA_ROOT` env var
- the saved preference (`~/.m110/settings.json`, set via Preferences)
- default: `~/Documents/M110`

It does not require any other project to run.

## Develop / run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
m110                # run the app  (== python -m m110.ui.main)
pytest
```

Requires Python 3.11+.

## Layout

- `m110/` — headless engine (data model, positional/rollup logic, ingest,
  image rendering, processing-prep) + `ui/` (PySide6 front end).
- `tests/` — fixture-based engine tests.

Several engine modules are faithful ports of a mature text-based reference
workflow; see `CLAUDE.md`.

## Name

The app is **M110**. The Python package import id is `m110`. (Deliberately
avoids the ZWO "Seestar" trademark.) For discoverability, lead external copy
with an explicit subtitle, e.g. *"M110 — smart-telescope image management and
deep-sky catalog tracker."*

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

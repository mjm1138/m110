# M110

[![CI](https://github.com/mjm1138/m110/actions/workflows/ci.yml/badge.svg)](https://github.com/mjm1138/m110/actions/workflows/ci.yml)

**Complete the catalog.**

**A photo library for your smart telescope.** M110 is a cross-platform desktop app
that turns a growing pile of Seestar or DwarfLab captures into an organized deep-sky
imaging library — catalog, capture tracking, ingest, and Siril processing-prep — with
a north-star goal to chase.

🌐 **[m110.space](https://m110.space)**  ·  📥 **[Download the beta](https://github.com/mjm1138/m110/releases/latest)** — macOS · Linux · Windows

> Named for **Messier 110** — the dwarf elliptical in Andromeda that Charles Messier
> observed in 1773 but never added to his catalog; it was retroactively designated
> the 110th and final entry. The whole point of the app is to get there. (It's also,
> fittingly, a row in the app's own catalog.)

> ⚠️ **Early beta.** M110 is usable and careful with your data, but expect rough
> edges — [feedback and bug reports](https://github.com/mjm1138/m110/issues) are very
> welcome.

## What it does

- **A real library** — every object you've shot, organized by catalog (Messier,
  Caldwell, and more) with status, integration time, and a per-object journal.
- **One-click ingest** — point it at your Seestar, DwarfLab Dwarf, or a folder; it groups, names, and
  files your subs, stacks, and finished renders. You always preview before anything
  is written.
- **Capture tracking** — sessions, frames, filters, and total integration roll up
  automatically from your FITS headers, so you know what's done and what needs
  another night.
- **Siril processing-prep** — arranges a clean, contained Siril sandbox per target
  (lights linked, a tuned preset ready), then imports your finished work back.
- **A goal to chase** — track progress toward completing a catalog, and see what's
  worth shooting tonight.
- **Safe by design** — local-first, open source, with built-in hardlinked backups.

### It never touches your originals

Ingest is always **preview-then-confirm** and **copies** from your telescope — your
capture files stay exactly where they are. Nothing is moved or modified without your
say-so.

## User guide

New here? The **[user guide](docs/README.md)** covers ingest, the library layout,
processing prep (and what M110's use of **hardlinks** means for your files), backup,
and getting around the app.

## Download

Beta builds are on the **[Releases page](https://github.com/mjm1138/m110/releases/latest)**:

- **macOS** — signed & notarized `.dmg` (opens with no warning).
- **Linux** — `.AppImage` (x86_64; needs `libfuse2`, or run with `--appimage-extract-and-run`).
- **Windows** — installer (unsigned for the beta: on first run, **More info → Run anyway**).

Per-OS notes and screenshots are on **[m110.space](https://m110.space)**.

## Your data

M110 owns a single data folder (catalog, captures, derived rollups, renders),
created and seeded on first launch. It resolves in this order:

1. the `M110_DATA_ROOT` environment variable,
2. your saved preference (set in Preferences), else
3. the default `~/Documents/M110`.

It doesn't require any other app or service to run. The full on-disk layout and file
formats are documented in **[`DATA_MODEL.md`](DATA_MODEL.md)**.

## Contributing & development

M110 is open source under **Apache-2.0** and welcomes contributions. The full setup,
test, and workflow guide is in **[`CONTRIBUTING.md`](CONTRIBUTING.md)**; the short
version (requires Python 3.11+):

```bash
pip install -e ".[dev]"     # engine + PySide6 UI + tests
m110                        # run the app  (== python -m m110.ui.main)
pytest -q                   # run the test suite
```

The app is a **PySide6** front end over a **Qt-free headless Python engine** (so the
engine stays testable and reusable). To get oriented: [`CLAUDE.md`](CLAUDE.md) (module
map + conventions), [`DATA_MODEL.md`](DATA_MODEL.md) (data model), [`ROADMAP.md`](ROADMAP.md)
(what's next), and [`DONE.md`](DONE.md) (how/why each subsystem shipped).

## Name & trademark

The app is **M110** (Python package id `m110`). It's an independent, open-source
project. **"Seestar" is a trademark of ZWO** and **"Dwarf" is a trademark of
DwarfLab** — M110 works *with* your telescope but is not affiliated with or endorsed
by ZWO or DwarfLab.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

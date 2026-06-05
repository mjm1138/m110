# Astronamigo

*(working title)* — a cross-platform desktop app (PySide6) over a headless
Python engine for managing a smart-telescope deep-sky imaging collection:
catalog/library, capture tracking, ingest, and Siril processing-prep.
"Lightroom for smart telescopes."

Standalone sibling to the text-based workflow in `~/Astronomy`. See that
project's `workflow_app_plan.md` for the full plan, scope decisions, and
phasing.

## Status

**v0.1 skeleton (Phase 0 / step 0.1b):** a read-only Library window over the
live data store. Mutating features (Refresh, Ingest, journal editing,
processing-prep) land in later 0.1 steps.

## Parallel-run model

The engine reads the **live** Astronomy data store via a config path, so it
runs alongside the existing `scripts/` + `rebuild.sh` workflow without
disturbing it. Read-only until trusted enough to adopt as "user 0."

- Default data root: `~/Astronomy`
- Override: `export ASTRONAMIGO_DATA_ROOT=/path/to/your/astronomy`

## Develop / run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
astronamigo            # or: python -m astronamigo.ui.main
pytest
```

## Layout

- `astronamigo/` — headless engine (data model, calculations, ingest,
  processing-prep) + `ui/` (PySide6 front end).
- `tests/` — engine tests.

Engine modules are ported incrementally from `~/Astronomy/scripts/` (Phase 0);
`display_names` is the first across.

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for the canonical roadmap, and
[`CLAUDE.md`](CLAUDE.md) for full developer context.

## Name

**"Astronamigo" is a provisional working title** — the final public name is TBD
before release.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

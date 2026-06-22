"""Read the generated derived rollups from the live data store.

These JSONs (totals / priorities / summary / processing) are produced by the
Astronomy `build_derived.py` via `rebuild.sh`. In parallel-run mode M110
*reads* them; recomputing them in-process is a later step (the in-app Refresh
feature). References go through `config.DERIVED_DIR` dynamically so the path is
overridable (and testable).
"""
from __future__ import annotations

import json

from . import config


def _load(name: str):
    p = config.DERIVED_DIR / name
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def derived_available() -> bool:
    return (config.DERIVED_DIR / "totals.json").is_file()


def load_totals() -> dict:
    """{'by_slug': {...}, 'by_folder': {...}}; {} if absent."""
    return _load("totals.json") or {}


def totals_by_slug() -> dict:
    """{slug: {integration_hms, integration_min, frames, session_count, status}}."""
    return load_totals().get("by_slug", {})


def load_priorities() -> list:
    return _load("priorities.json") or []


def load_summary() -> dict:
    return _load("summary.json") or {}


def load_processing() -> dict:
    return _load("processing.json") or {}


def load_images() -> dict:
    """{slug: [ {name, label, viewable, thumb, full, ...} ]}.

    `name` is the actual filename. `thumb` is relative to `config.RENDERS_DIR`;
    `full` (viewable rasters only) is relative to `config.DATA_ROOT`.
    """
    return _load("images.json") or {}


def images_for(slug: str) -> list:
    return load_images().get(slug, [])


def load_sessions() -> list[dict]:
    """Capture sessions from `config.SESSIONS_JSONL` (one JSON object per line).

    Pure reader (mirrors `build_derived.load_sessions` without importing it);
    `[]` if the file is absent. Each row:
    {date, object_dir, slugs, frames, exposure_s, filter, integration_min,
     mount_mode, pre_new_start}.
    """
    p = config.SESSIONS_JSONL
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows

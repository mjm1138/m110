"""Read the generated derived rollups from the live data store.

These JSONs (totals / summary / processing) are produced by the
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
    return json.loads(p.read_text(encoding="utf-8"))


def derived_available() -> bool:
    return (config.DERIVED_DIR / "totals.json").is_file()


def load_totals() -> dict:
    """{'by_slug': {...}, 'by_folder': {...}}; {} if absent."""
    return _load("totals.json") or {}


def totals_by_slug() -> dict:
    """{slug: {integration_hms, integration_min, frames, session_count, status}}."""
    return load_totals().get("by_slug", {})


def load_summary() -> dict:
    return _load("summary.json") or {}


def load_processing() -> dict:
    return _load("processing.json") or {}


def load_goals() -> list:
    """Per active-goal progress [{id,name,total,captured,deep,percent}]; [] if absent."""
    return _load("goals.json") or []


_DEVICE_TOTALS = {"integration_min": 0.0, "sessions": 0, "nights": 0, "objects": 0,
                  "first_capture": None, "last_capture": None}


def normalize_device(d: dict) -> dict | None:
    """One `devices.json` entry with every key its readers use present. The file
    is derived and rewritten on Sync, but an older app version's copy is read at
    launch before that Sync runs (a pre-Devices-page rollup has no ``totals`` /
    ``objects`` / identity keys), so readers never index it raw. None for an entry
    with no device key."""
    if not isinstance(d, dict) or not d.get("device"):
        return None
    d = dict(d)
    totals = d.get("totals") if isinstance(d.get("totals"), dict) else {}
    d["totals"] = {**_DEVICE_TOTALS, **totals}
    for key in ("objects", "masters", "captures"):
        if not isinstance(d.get(key), list):
            d[key] = []
    d["label"] = d.get("label") or d["device"]
    for key in ("nickname", "preset", "model", "serial"):
        d.setdefault(key, None)
    d["retired"] = bool(d.get("retired"))
    d["darks_applied_on_device"] = bool(d.get("darks_applied_on_device"))
    return d


def load_devices() -> list:
    """Per-device identity, totals, objects, calibration library, captures and
    sensor health (`calibration.device_rollup`), each entry `normalize_device`d —
    tolerant of a rollup written by an older version; [] if absent."""
    raw = (_load("devices.json") or {}).get("devices", [])
    if not isinstance(raw, list):
        return []
    return [n for n in (normalize_device(d) for d in raw) if n is not None]


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
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows

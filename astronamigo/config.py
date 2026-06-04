"""Runtime configuration for Astronamigo.

During parallel-run development the app reads the *live* Astronomy data store
through DATA_ROOT (default ~/Astronomy), so it never disturbs the existing
scripts/ + rebuild.sh workflow. Override with the ASTRONAMIGO_DATA_ROOT env var.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT = Path(
    os.environ.get("ASTRONAMIGO_DATA_ROOT", str(Path.home() / "Astronomy"))
).expanduser()

DATA_DIR = DATA_ROOT / "data"
IMAGES_DIR = DATA_ROOT / "Images"
CATALOG_TOML = DATA_DIR / "catalog.toml"
PRIORITIES_TOML = DATA_DIR / "priorities.toml"
SESSIONS_JSONL = DATA_DIR / "sessions.jsonl"
DERIVED_DIR = DATA_DIR / "derived"
OBJECTS_DIR = DATA_DIR / "objects"
SITE_DIR = DATA_ROOT / "site"   # generated site (hero/thumb images live here)


def data_root_ok() -> bool:
    """True if DATA_ROOT looks like a real Astronomy data store."""
    return CATALOG_TOML.is_file()

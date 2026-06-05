"""Runtime configuration for M110.

The app owns its own data store (default ``~/Documents/M110``), resolved
in order from: the ``M110_DATA_ROOT`` env var, the saved preference
(``~/.m110/settings.json``), then the default. Qt-free so the engine
stays headless — the UI Preferences dialog calls ``save_data_root()`` and
prompts a restart.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

APP_CONFIG_DIR = Path.home() / ".m110"
SETTINGS_FILE = APP_CONFIG_DIR / "settings.json"
DEFAULT_DATA_ROOT = Path.home() / "Documents" / "M110"
SEED_DIR = Path(__file__).resolve().parent / "seed"

# Directory skeleton created under a data root.
_SUBDIRS = [
    "data", "data/objects", "data/derived",
    "Images/FITS", "Images/Seestar_stacks", "Images/From the scope",
    "Images/Finished Images",
    "site/img/hero",
]
# Static files seeded from the bundled templates if missing.
_SEED_FILES = ["catalog.toml", "priorities.toml"]


def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def save_data_root(path) -> None:
    """Persist the chosen data root (takes effect on next launch)."""
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    s = _read_settings()
    s["data_root"] = str(Path(path).expanduser())
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


def _resolve_data_root() -> Path:
    env = os.environ.get("M110_DATA_ROOT")
    if env:
        return Path(env).expanduser()
    saved = _read_settings().get("data_root")
    if saved:
        return Path(saved).expanduser()
    return DEFAULT_DATA_ROOT


def _apply(root: Path) -> None:
    global DATA_ROOT, DATA_DIR, IMAGES_DIR, CATALOG_TOML, PRIORITIES_TOML
    global SESSIONS_JSONL, DERIVED_DIR, OBJECTS_DIR, SITE_DIR
    DATA_ROOT = root
    DATA_DIR = root / "data"
    IMAGES_DIR = root / "Images"
    CATALOG_TOML = DATA_DIR / "catalog.toml"
    PRIORITIES_TOML = DATA_DIR / "priorities.toml"
    SESSIONS_JSONL = DATA_DIR / "sessions.jsonl"
    DERIVED_DIR = DATA_DIR / "derived"
    OBJECTS_DIR = DATA_DIR / "objects"
    SITE_DIR = root / "site"


_apply(_resolve_data_root())


def set_data_root(path) -> None:
    """Re-point the in-process data root (tests / runtime best-effort).

    The supported *persistent* change is ``save_data_root()`` + restart, because
    a few ported modules bind their paths at import.
    """
    _apply(Path(path).expanduser())


def data_root_ok() -> bool:
    return CATALOG_TOML.is_file()


def ensure_data_root(root=None) -> Path:
    """Create the directory skeleton and seed catalog/priorities if missing.

    Idempotent — safe to call on every launch.
    """
    r = Path(root).expanduser() if root else DATA_ROOT
    for sub in _SUBDIRS:
        (r / sub).mkdir(parents=True, exist_ok=True)
    for name in _SEED_FILES:
        dst = r / "data" / name
        src = SEED_DIR / name
        if not dst.exists() and src.is_file():
            shutil.copy(src, dst)
    return r


# ── Seestar device detection ────────────────────────────────────────────────

def find_seestar_myworks() -> Path | None:
    """Locate the Seestar's ``MyWorks`` dir across possible mounts.

    Handles USB (``/Volumes/Seestar``) and SMB (``/Volumes/EMMC Images``, etc.)
    by scanning /Volumes for any volume containing a ``MyWorks`` directory,
    preferring obviously-named ones.
    """
    vol = Path("/Volumes")
    if not vol.is_dir():
        return None
    try:
        volumes = list(vol.iterdir())
    except (PermissionError, OSError):
        return None
    volumes.sort(key=lambda p: (0 if ("seestar" in p.name.lower()
                                      or "emmc" in p.name.lower()) else 1, p.name))
    for d in volumes:
        try:
            mw = d / "MyWorks"
            if mw.is_dir():
                return mw
        except (PermissionError, OSError):
            continue
    return None

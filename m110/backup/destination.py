"""Destination-level facts: where a store's backups live, and what the
destination filesystem can do.

Deliberately below the snapshot formats in the dependency order — nothing here
imports a format module, so both can build on it.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .. import config
from .options import BACKUPS_DIRNAME


def store_backup_root(destination: Path, store_name: str | None = None) -> Path:
    """`<destination>/M110-Backups/<store-name>` — snapshots for one store live here."""
    name = store_name or config.DATA_ROOT.name or "M110"
    return Path(destination) / BACKUPS_DIRNAME / name


def supports_hardlinks(dir_path: Path) -> bool:
    """Probe whether `dir_path`'s filesystem supports hardlinks (some SMB/exFAT
    don't). Creates + links + removes two temp files."""
    a = dir_path / ".m110-linkprobe-a"
    b = dir_path / ".m110-linkprobe-b"
    try:
        a.write_text("x", encoding="utf-8")
        try:
            os.link(a, b)
        except (OSError, NotImplementedError, AttributeError):
            return False
        return True
    except OSError:
        return False
    finally:
        for p in (a, b):
            try:
                p.unlink()
            except OSError:
                pass


def free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0

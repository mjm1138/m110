"""Pre-flight inspection of a backup destination."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .destination import store_backup_root, supports_hardlinks
from .options import DestinationInfo
from .retention import list_snapshots


def probe_destination(destination: Path) -> DestinationInfo:
    """Inspect a destination before backing up to it: does it exist, can we write
    to it, does its filesystem support hardlinks (→ shared files between
    snapshots), how much room is left, and what's already there.

    Qt-free and safe to call on a candidate the user hasn't committed to: it
    never creates the `M110-Backups/` tree, and the link probe's two temp files
    are always removed. **Slow on a network share** (it stats the volume and
    reads every existing manifest) — call it from a worker thread, never the GUI
    thread."""
    dest = Path(destination)
    if not str(dest).strip():
        return DestinationInfo(path=dest, exists=False, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0)
    if not dest.is_dir():
        return DestinationInfo(path=dest, exists=False, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0,
                               error="Folder not found")
    if not os.access(dest, os.W_OK):
        return DestinationInfo(path=dest, exists=True, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0,
                               error="Folder is not writable")

    try:
        free: int | None = shutil.disk_usage(dest).free
    except OSError:
        free = None
    # Probe where the snapshots will actually live, but only if it already
    # exists — a probe must not create anything the user hasn't asked for.
    store_root = store_backup_root(dest)
    hardlinks = supports_hardlinks(store_root if store_root.is_dir() else dest)
    snaps = list_snapshots(dest)
    return DestinationInfo(
        path=dest, exists=True, writable=True, hardlinks=hardlinks, free_bytes=free,
        snapshot_count=len(snaps), newest=snaps[0] if snaps else None)

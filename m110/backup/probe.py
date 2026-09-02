"""Pre-flight inspection of a backup destination."""
from __future__ import annotations

import os
import shutil

from .backends import backend_for
from .destination import parse_destination, store_backup_root, supports_hardlinks
from .errors import BackupError
from .formats import FORMAT_POOLED, detect_format, resolve_format
from .options import DestinationInfo
from .retention import list_snapshots


def probe_destination(destination) -> DestinationInfo:
    """Inspect a destination before backing up to it: does it exist, can we write
    to it, does it support hardlinks (→ shared files between snapshots), how much
    room is left, and what's already there.

    Qt-free and safe to call on a candidate the user hasn't committed to: it
    never creates the `M110-Backups/` tree, and the link probe's two temp files
    are always removed. **Slow on a network share or a bucket** (it stats the
    volume or makes a round-trip, and reads existing manifests) — call it from a
    worker thread, never the GUI thread."""
    try:
        dest = parse_destination(destination)
    except BackupError as e:
        return DestinationInfo(path=None, exists=False, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0, error=str(e),
                               destination=str(destination or ""), kind="s3")
    if not dest.raw.strip():
        return DestinationInfo(path=dest.path, exists=False, writable=False,
                               hardlinks=False, free_bytes=None, snapshot_count=0,
                               destination="", kind=dest.kind)
    if not dest.is_local:
        return _probe_cloud(dest)
    return _probe_local(dest)


def _probe_local(dest) -> DestinationInfo:
    path = dest.path
    common = dict(destination=str(dest), kind=dest.kind)
    if not path.is_dir():
        return DestinationInfo(path=path, exists=False, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0,
                               error="Folder not found", **common)
    if not os.access(path, os.W_OK):
        return DestinationInfo(path=path, exists=True, writable=False, hardlinks=False,
                               free_bytes=None, snapshot_count=0,
                               error="Folder is not writable", **common)

    try:
        free: int | None = shutil.disk_usage(path).free
    except OSError:
        free = None
    # Probe where the snapshots will actually live, but only if it already
    # exists — a probe must not create anything the user hasn't asked for.
    store_root = store_backup_root(dest)
    hardlinks = supports_hardlinks(store_root if store_root.is_dir() else path)
    snaps = list_snapshots(dest)
    # Read-only: resolving the format here reports what *would* happen. Persisting
    # a forced switch is the caller's move, so a mere look at a destination never
    # rewrites the user's preference.
    fmt, forced = resolve_format(dest, hardlinks=hardlinks)
    return DestinationInfo(
        path=path, exists=True, writable=True, hardlinks=hardlinks, free_bytes=free,
        snapshot_count=len(snaps), newest=snaps[0] if snaps else None,
        format=fmt, detected_format=detect_format(dest), format_forced=forced, **common)


def _probe_cloud(dest) -> DestinationInfo:
    """Reachability, credentials and contents for a bucket.

    `ensure_root()` creates nothing on object storage — there are no directories
    to make — so it doubles as the "can I reach this, and am I allowed to?" check
    without violating the probe's create-nothing rule. Its failure message is the
    useful one (wrong bucket, bad key, unreachable endpoint), so it is passed
    through rather than replaced.
    """
    common = dict(destination=str(dest), kind=dest.kind, path=None,
                  free_bytes=None, hardlinks=False,
                  format=FORMAT_POOLED, format_forced=True)
    backend = None
    try:
        backend = backend_for(dest)
        backend.ensure_root()
    except BackupError as e:
        return DestinationInfo(exists=False, writable=False, snapshot_count=0,
                               error=str(e), **common)
    except Exception as e:                          # noqa: BLE001 — never crash a probe
        return DestinationInfo(exists=False, writable=False, snapshot_count=0,
                               error=f"Couldn't reach cloud storage: {e}", **common)
    try:
        snaps = list_snapshots(dest)
    except Exception:
        snaps = []
    finally:
        if backend is not None:
            backend.close()
    return DestinationInfo(
        exists=True, writable=True, snapshot_count=len(snaps),
        newest=snaps[0] if snaps else None,
        detected_format=FORMAT_POOLED if snaps else None, **common)

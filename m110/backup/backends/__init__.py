"""Backend registry — the seam a pooled backup writes through.

Registry-shaped from the start (like `publish.PUBLISHERS`) so adding S3 is an
entry plus an adapter, not a change to the format or the callers.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..destination import (KIND_LOCAL, KIND_S3, Destination, backup_root_key,
                           parse_destination, store_backup_root)
from .base import Backend, Capabilities
from .local import LocalBackend
from .memory import MemoryBackend


@dataclass(frozen=True)
class BackendKind:
    id: str
    label: str
    available: bool = True
    reason: str = ""


BACKEND_KINDS: list[BackendKind] = [
    BackendKind(KIND_LOCAL, "Folder, drive or network share"),
    # Offsite object storage (issue #93): same layout, same manifests, same
    # restore path — only put/get/list change.
    BackendKind(KIND_S3, "S3 / S3-compatible cloud"),
]

BACKEND_KINDS_BY_ID = {k.id: k for k in BACKEND_KINDS}


def backend_for(destination, store_name: str | None = None) -> Backend:
    """The backend for a store's backups at `destination`.

    Accepts a `Destination`, a path, or a destination string — the single place
    that decides which adapter a destination resolves to. `S3Backend` is imported
    lazily so that boto3 is only needed by someone who actually uses a bucket.
    """
    dest = parse_destination(destination)
    if dest.kind == KIND_S3:
        from .s3 import S3Backend
        return S3Backend(dest.bucket, backup_root_key(dest, store_name))
    return LocalBackend(store_backup_root(dest, store_name))


__all__ = ["BACKEND_KINDS", "BACKEND_KINDS_BY_ID", "Backend", "BackendKind",
           "Capabilities", "Destination", "LocalBackend", "MemoryBackend",
           "backend_for"]

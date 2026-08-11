"""Backend registry — the seam a pooled backup writes through.

Registry-shaped from the start (like `publish.PUBLISHERS`) so adding S3 is an
entry plus an adapter, not a change to the format or the callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..destination import store_backup_root
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
    BackendKind("local", "Folder, drive or network share"),
    # Offsite object storage (issue #93) plugs in here: same layout, same
    # manifests, same restore path — only put/get/list change.
    BackendKind("s3", "S3 / S3-compatible cloud", available=False,
                reason="Coming soon"),
]

BACKEND_KINDS_BY_ID = {k.id: k for k in BACKEND_KINDS}


def backend_for(destination: Path, store_name: str | None = None) -> Backend:
    """The backend for a store's backups at `destination`."""
    return LocalBackend(store_backup_root(destination, store_name))


__all__ = ["BACKEND_KINDS", "BACKEND_KINDS_BY_ID", "Backend", "BackendKind",
           "Capabilities", "LocalBackend", "MemoryBackend", "backend_for"]

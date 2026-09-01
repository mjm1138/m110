"""Destination-level facts: *where* a store's backups live, and what that
destination can do.

A destination is no longer necessarily a folder. `parse_destination` turns what
the user typed into a `Destination` — a local path, or a bucket + key prefix on
S3-compatible object storage (issue #93). Everything above the storage seam
should hold one of these and ask `backends.backend_for` for a backend, rather
than joining paths itself: after #93 only `LocalBackend` knows what a filesystem
is.

Deliberately below the snapshot formats in the dependency order — nothing here
imports a format module, so both can build on it.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .errors import BackupDestinationError
from .options import BACKUPS_DIRNAME

KIND_LOCAL = "local"
KIND_S3 = "s3"

# Only a known scheme makes a destination remote. Matching `<word>:` generally
# would read a Windows drive letter (`C:\Backups`) as a scheme, which is why
# this is an explicit pattern and not `urlparse().scheme`.
_S3_URI = re.compile(r"^s3://(?P<rest>.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class Destination:
    """Where backups go. One of two shapes, distinguished by `kind`."""

    kind: str
    raw: str                        # exactly what the user typed
    path: Path | None = None        # local only
    bucket: str = ""                # s3 only
    prefix: str = ""                # s3 only; "" means the bucket root

    @property
    def is_local(self) -> bool:
        return self.kind == KIND_LOCAL

    def describe(self) -> str:
        if self.is_local:
            return str(self.path)
        return f"s3://{self.bucket}/{self.prefix}".rstrip("/")

    def __str__(self) -> str:      # what gets persisted / shown
        return self.describe()

    def __fspath__(self) -> str:
        """Lets a local destination still be passed to `Path(...)` / `open(...)`.
        A cloud one raises instead of inventing a path — anything reaching for a
        filesystem here is a call site that hasn't been moved onto the backend
        seam yet, and it should say so loudly rather than build a wrong path."""
        if not self.is_local:
            raise TypeError(
                f"{self.describe()} is not a filesystem path — "
                "use backends.backend_for()")
        return str(self.path)


def parse_destination(value) -> Destination:
    """`Destination` for a user-typed destination (a folder path or `s3://…`).

    Raises `BackupDestinationError` only for a *malformed* S3 URI — an
    unreachable bucket or a missing folder is a probe result, not a parse error.
    """
    if isinstance(value, Destination):
        return value
    raw = str(value or "").strip()
    m = _S3_URI.match(raw)
    if not m:
        return Destination(kind=KIND_LOCAL, raw=raw, path=Path(raw))
    # rstrip only. Stripping the *leading* slash too would turn the malformed
    # `s3:///backups` (empty bucket, typo'd extra slash) into a bucket literally
    # named "backups" — a silent wrong answer where an error is the right one.
    rest = m.group("rest").rstrip("/")
    if not rest:
        raise BackupDestinationError(
            "Cloud destination needs a bucket, e.g. s3://my-bucket/m110")
    bucket, _, prefix = rest.partition("/")
    if not bucket:
        raise BackupDestinationError(
            "Cloud destination needs a bucket, e.g. s3://my-bucket/m110")
    return Destination(kind=KIND_S3, raw=raw, bucket=bucket, prefix=prefix.strip("/"))


def store_name_for(store_name: str | None = None) -> str:
    return store_name or config.DATA_ROOT.name or "M110"


def store_backup_root(destination, store_name: str | None = None) -> Path:
    """`<destination>/M110-Backups/<store-name>` — snapshots for one store live
    here. **Local destinations only**; ask `backend_for` for anything else."""
    dest = parse_destination(destination)
    if not dest.is_local:
        raise BackupDestinationError(
            f"{dest.describe()} has no filesystem path — use backends.backend_for()")
    return dest.path / BACKUPS_DIRNAME / store_name_for(store_name)


def backup_root_key(destination, store_name: str | None = None) -> str:
    """The object-store key prefix a store's backups live under, without a
    trailing slash: `<prefix>/M110-Backups/<store-name>`."""
    dest = parse_destination(destination)
    parts = [p for p in (dest.prefix, BACKUPS_DIRNAME, store_name_for(store_name)) if p]
    return "/".join(parts)


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


def free_bytes(path) -> int:
    """Free space on the destination volume. 0 when unknown — and always 0 for a
    destination with no volume (an object store), where the caller should be
    reading `Capabilities.free_bytes is None` instead."""
    dest = parse_destination(path)
    if not dest.is_local:
        return 0
    try:
        return shutil.disk_usage(dest.path).free
    except OSError:
        return 0

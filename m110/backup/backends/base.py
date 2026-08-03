"""The storage seam a pooled backup writes through.

Mirrors the shape of `publish.PUBLISHERS`: one small interface, several adapters
that write the *same layout*. `LocalBackend` (a folder — direct-attached disk or
a mounted share) is the only one today; an `S3Backend` (boto3 with a configurable
`endpoint_url`, so B2/R2/Wasabi fall out for free) is the reason the seam exists
and slots in beside it (issue #93).

Two design notes that matter more than the method list:

* **`object_sizes()` enumerates the whole object store once per run** rather than
  asking `exists()` per source file. A 100k-file library would otherwise cost
  100k round-trips — minutes of pure latency over SMB, and ~$0.04 of HEAD
  requests per run on S3. One walk (or one paginated LIST) answers it, and the
  sizes it returns for free give the hash-cache a corruption cross-check.
* **Atomicity is the backend's contract, not the caller's.** `put_file` must make
  the object appear complete or not at all, because the whole safety argument of
  the pooled format rests on "a manifest exists ⇒ every object it names exists".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Capabilities:
    """What this destination can do. Detected, never asked — the same instinct as
    `launch.find_app`: the user shouldn't have to know."""
    hardlinks: bool                 # can build the browsable `latest/` tree
    free_bytes: int | None          # None = unknown/meaningless (object stores)
    cheap_list: bool = True         # LIST is free (a folder) vs billed (S3)
    parallel_puts: int = 1          # 1 = serial; >1 = safe pool width


class Backend:
    """Base class + default implementations. Subclasses must provide the
    single-key operations; the plural ones have serviceable defaults."""

    kind = "base"

    # ---- identity ----
    def describe(self) -> str:
        raise NotImplementedError

    def capabilities(self) -> Capabilities:
        raise NotImplementedError

    def ensure_root(self) -> None:
        """Create whatever the destination needs before the first write."""

    # ---- objects ----
    def object_sizes(self) -> dict[str, int]:
        """`{sha256: size}` for every object already stored. One round-trip's
        worth of work, not one per key."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def put_file(self, key: str, src: Path, *, size: int | None = None) -> None:
        raise NotImplementedError

    def put_bytes(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def get_file(self, key: str, dst: Path) -> None:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def list_keys(self, prefix: str) -> Iterator[tuple[str, int, float]]:
        """`(key, size, mtime_epoch)` under `prefix`. mtime backs the GC grace
        window, so it must be the time the object was *stored*."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def delete_many(self, keys: Iterable[str]) -> int:
        removed = 0
        for key in keys:
            self.delete(key)
            removed += 1
        return removed

    # ---- the browsable latest/ tree (link-capable destinations only) ----
    def link(self, key: str, rel: str) -> bool:
        """Place the object at `key` into `latest/<rel>` without copying bytes.
        False when the destination can't (the tree is then simply absent)."""
        return False

    def unlink_rel(self, rel: str) -> None:
        """Remove `latest/<rel>`."""

    def drop_latest(self) -> None:
        """Remove the whole `latest/` tree (used when linking fails part-way)."""

    def close(self) -> None:
        """Release any connection. Safe to call more than once."""

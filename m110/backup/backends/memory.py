"""An in-process backend.

Ships rather than living in the test tree: it is the reference implementation of
the seam (the smallest thing that satisfies the contract) and the fixture the
conformance suite runs `LocalBackend` against. It also stands in for the
"destination that can't hardlink" case without needing an exFAT volume.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Iterator

from .base import Backend, Capabilities

# Monotonic stand-in for storage time — the GC grace window compares against it.
_clock = itertools.count(1_000_000.0, 1.0)


class MemoryBackend(Backend):
    kind = "memory"

    def __init__(self, label: str = "memory", *, hardlinks: bool = False,
                 now=None):
        self._data: dict[str, bytes] = {}
        self._mtime: dict[str, float] = {}
        self._label = label
        self._hardlinks = hardlinks
        self._now = now or (lambda: next(_clock))

    def describe(self) -> str:
        return f"memory:{self._label}"

    def capabilities(self) -> Capabilities:
        return Capabilities(hardlinks=self._hardlinks, free_bytes=None,
                            cheap_list=True, parallel_puts=1)

    def object_sizes(self) -> dict[str, int]:
        return {k.rsplit("/", 1)[-1]: len(v)
                for k, v in self._data.items() if k.startswith("objects/")}

    def exists(self, key: str) -> bool:
        return key in self._data

    def put_file(self, key: str, src: Path, *, size: int | None = None) -> None:
        if key in self._data:
            return
        self.put_bytes(key, Path(src).read_bytes())

    def put_bytes(self, key: str, data: bytes) -> None:
        self._data[key] = bytes(data)
        self._mtime[key] = self._now()

    def get_file(self, key: str, dst: Path) -> None:
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(self._data[key])

    def get_bytes(self, key: str) -> bytes:
        return self._data[key]

    def list_keys(self, prefix: str) -> Iterator[tuple[str, int, float]]:
        for key, blob in sorted(self._data.items()):
            if key.startswith(prefix):
                yield key, len(blob), self._mtime[key]

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._mtime.pop(key, None)

    def set_mtime(self, key: str, when: float) -> None:
        """Test affordance: age an object past the GC grace window."""
        if key in self._mtime:
            self._mtime[key] = when

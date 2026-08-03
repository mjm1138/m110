"""A folder — direct-attached disk, external drive, or a mounted network share."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Iterator

from ..destination import free_bytes, supports_hardlinks
from .base import Backend, Capabilities

OBJECT_MODE = 0o444     # immutable — see the class docstring
BYTES_MODE = 0o644
LATEST_DIRNAME = "latest"


def _chmod_writable(path: Path) -> None:
    """Windows refuses to delete a read-only file; POSIX doesn't care. Cheap
    insurance either way."""
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


class LocalBackend(Backend):
    """Objects are stored read-only (0444) on purpose.

    A `latest/` entry is a *hardlink* to its object — the same inode — so editing
    a file in the browsable tree would silently rewrite the object that every
    snapshot referencing that content shares. Read-only is the guard that makes
    the browsable tree safe to hand to a user.
    """

    kind = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def describe(self) -> str:
        return str(self.root)

    def capabilities(self) -> Capabilities:
        probe_dir = self.root if self.root.is_dir() else self.root.parent
        return Capabilities(
            hardlinks=supports_hardlinks(probe_dir) if probe_dir.is_dir() else False,
            free_bytes=free_bytes(probe_dir) or None,
            cheap_list=True,
            parallel_puts=1,
        )

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- paths ----
    def _path(self, key: str) -> Path:
        return self.root.joinpath(*key.split("/"))

    # ---- objects ----
    def object_sizes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        base = self.root / "objects"
        if not base.is_dir():
            return out
        try:
            for lvl1 in os.scandir(base):
                if not lvl1.is_dir():
                    continue
                for lvl2 in os.scandir(lvl1.path):
                    if not lvl2.is_dir():
                        continue
                    for entry in os.scandir(lvl2.path):
                        if entry.is_file() and not entry.name.endswith(".part"):
                            try:
                                out[entry.name] = entry.stat().st_size
                            except OSError:
                                continue
        except OSError:
            return out
        return out

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def put_file(self, key: str, src: Path, *, size: int | None = None) -> None:
        dst = self._path(key)
        if dst.is_file():
            return                      # content-addressed: already the right bytes
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        # Byte-only copy (no copystat) — same SMB EPERM rule as ingest.
        shutil.copyfile(src, tmp)
        try:
            os.chmod(tmp, OBJECT_MODE)
        except OSError:
            pass
        os.replace(tmp, dst)

    def put_bytes(self, key: str, data: bytes) -> None:
        dst = self._path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, BYTES_MODE)
        except OSError:
            pass
        if dst.exists():
            _chmod_writable(dst)
        os.replace(tmp, dst)

    def get_file(self, key: str, dst: Path) -> None:
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        shutil.copyfile(self._path(key), tmp)
        # Restored files must be editable — objects are 0444, restores are not.
        try:
            os.chmod(tmp, 0o644)
        except OSError:
            pass
        if dst.exists():
            _chmod_writable(dst)
        os.replace(tmp, dst)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def list_keys(self, prefix: str) -> Iterator[tuple[str, int, float]]:
        base = self._path(prefix) if prefix else self.root
        if not base.is_dir():
            return
        for dirpath, _dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, self.root).replace(os.sep, "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            for name in filenames:
                if name.endswith(".part"):
                    continue
                try:
                    st = os.stat(os.path.join(dirpath, name))
                except OSError:
                    continue
                yield (f"{rel_dir}/{name}" if rel_dir else name, st.st_size, st.st_mtime)

    def delete(self, key: str) -> None:
        p = self._path(key)
        _chmod_writable(p)
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def delete_many(self, keys: Iterable[str]) -> int:
        removed = 0
        for key in keys:
            self.delete(key)
            removed += 1
        self._prune_empty_dirs(self.root / "objects")
        return removed

    # ---- latest/ ----
    def _latest_path(self, rel: str) -> Path:
        return self.root.joinpath(LATEST_DIRNAME, *rel.split("/"))

    def link(self, key: str, rel: str) -> bool:
        target = self._latest_path(rel)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                _chmod_writable(target)
                target.unlink()
            os.link(self._path(key), target)
            return True
        except OSError:
            return False

    def unlink_rel(self, rel: str) -> None:
        target = self._latest_path(rel)
        _chmod_writable(target)
        try:
            target.unlink()
        except OSError:
            return
        self._prune_empty_dirs(self.root / LATEST_DIRNAME)

    def drop_latest(self) -> None:
        latest = self.root / LATEST_DIRNAME
        if latest.is_dir():
            for dirpath, _d, filenames in os.walk(latest):
                for name in filenames:
                    _chmod_writable(Path(dirpath) / name)
            shutil.rmtree(latest, ignore_errors=True)

    def _prune_empty_dirs(self, base: Path) -> None:
        if not base.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(base, topdown=False):
            if dirpath == str(base):
                continue
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass

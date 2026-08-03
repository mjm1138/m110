"""**Mirrored snapshots** — dated full trees with hardlink dedup.

    <destination>/M110-Backups/<store-name>/
        2026-07-01_143000/                     one complete, browsable snapshot tree
            Objects/ Images/ Media/ Inbox/ .m110_internal_data/(authored subset)
            .m110-backup-manifest.json         {rel: {size, mtime, sha256}} + metadata
        2026-07-02_090000/ …
        .m110-backup-state.json                index of snapshots for this store

Each snapshot is a *full* tree, but files unchanged since the previous snapshot
(all the immutable raws) are **hardlinked** to it — so incrementals cost only the
changed bytes. Same trick as `rsync --link-dest` and Time Machine.

The property worth protecting: a snapshot needs no software to restore. It is a
folder of your files, in the right places, openable in Finder. That is why this
format stays the default wherever the destination filesystem can link.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .. import config
from .destination import store_backup_root, supports_hardlinks
from .errors import BackupError, BackupDestinationError
from .options import BackupOptions, SnapshotInfo, TIMESTAMP_FMT
from .scope import iter_source_files

MANIFEST_NAME = ".m110-backup-manifest.json"
STATE_NAME = ".m110-backup-state.json"
INCOMPLETE_SUFFIX = ".incomplete"
_MTIME_EPS = 1e-4       # mtime float-compare tolerance (source clock is stable)
_HASH_CHUNK = 1 << 20   # 1 MiB

FORMAT = "mirrored"


# ── hashing / manifest ──────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(snapshot_dir: Path) -> dict | None:
    mf = Path(snapshot_dir) / MANIFEST_NAME
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ── listing ─────────────────────────────────────────────────────────────────

def sweep_incomplete(destination: Path, store_name: str | None = None) -> int:
    """Delete leftover `*.incomplete` snapshot dirs from interrupted runs."""
    root = store_backup_root(destination, store_name)
    removed = 0
    if not root.is_dir():
        return 0
    for d in root.iterdir():
        if d.is_dir() and d.name.endswith(INCOMPLETE_SUFFIX):
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def list_snapshots(destination: Path, store_name: str | None = None) -> list[SnapshotInfo]:
    """Completed mirrored snapshots for this store, newest first. Ignores
    `*.incomplete`.

    Identity comes from the directory *name*: anything that doesn't parse as a
    timestamp isn't a snapshot and is skipped. That is what lets a differently
    named layout share this store root without a flag day."""
    root = store_backup_root(destination, store_name)
    if not root.is_dir():
        return []
    snaps: list[SnapshotInfo] = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.endswith(INCOMPLETE_SUFFIX):
            continue
        if not (d / MANIFEST_NAME).is_file():
            continue
        m = read_manifest(d) or {}
        try:
            created = datetime.strptime(d.name, TIMESTAMP_FMT)
        except ValueError:
            continue
        snaps.append(SnapshotInfo(
            path=d, timestamp=d.name, created=created,
            file_count=int(m.get("file_count", 0)),
            total_bytes=int(m.get("total_bytes", 0)),
            store_version=m.get("store_version"),
            hardlinks=bool(m.get("hardlinks", True)),
            format=FORMAT,
        ))
    snaps.sort(key=lambda s: s.created, reverse=True)
    return snaps


# ── create ──────────────────────────────────────────────────────────────────

def create_snapshot(options: BackupOptions, should_cancel=None, progress=None) -> dict:
    """Write a new snapshot of the current store to the destination. Unchanged
    files hardlink to the previous snapshot; changed/new files are byte-copied.
    Returns a summary dict (or `{"cancelled": True}`)."""
    cancelled = should_cancel or (lambda: False)
    src_root = config.DATA_ROOT
    if not src_root.is_dir():
        raise BackupError(f"Data store not found: {src_root}")
    dest = Path(options.destination)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupDestinationError(f"Can't write to destination: {dest} ({e})")
    if not os.access(dest, os.W_OK):
        raise BackupDestinationError(f"Destination is not writable: {dest}")

    store_root = store_backup_root(dest)
    store_root.mkdir(parents=True, exist_ok=True)
    sweep_incomplete(dest)

    hardlinks = supports_hardlinks(store_root)
    prior = (list_snapshots(dest) or [None])[0]
    prior_manifest = read_manifest(prior.path) if prior else None
    prior_files = (prior_manifest or {}).get("files", {})

    ts = datetime.now().strftime(TIMESTAMP_FMT)
    incomplete = store_root / f"{ts}{INCOMPLETE_SUFFIX}"
    if incomplete.exists():
        shutil.rmtree(incomplete, ignore_errors=True)
    incomplete.mkdir(parents=True)

    rels = iter_source_files(src_root)
    total = len(rels)
    files_meta: dict[str, dict] = {}
    total_bytes = 0
    bytes_new = 0
    linked = 0

    try:
        for i, rel in enumerate(rels, 1):
            if cancelled():
                shutil.rmtree(incomplete, ignore_errors=True)
                return {"cancelled": True}
            src = src_root / rel
            try:
                st = src.stat()
            except OSError:
                continue   # vanished mid-run — skip
            dst = incomplete / rel
            dst.parent.mkdir(parents=True, exist_ok=True)

            prev = prior_files.get(rel)
            reuse = (hardlinks and prior is not None and prev is not None
                     and int(prev.get("size", -1)) == st.st_size
                     and abs(float(prev.get("mtime", -1)) - st.st_mtime) < _MTIME_EPS
                     and prev.get("sha256"))
            if reuse:
                try:
                    os.link(prior.path / rel, dst)
                    sha = prev["sha256"]
                    linked += 1
                except OSError:
                    reuse = False
            if not reuse:
                copy_bytes(src, dst, st)
                sha = _sha256(dst)
                bytes_new += st.st_size

            files_meta[rel] = {"size": st.st_size, "mtime": st.st_mtime, "sha256": sha}
            total_bytes += st.st_size
            if progress:
                progress(i, total)

        manifest = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "timestamp": ts,
            "source_root": str(src_root),
            "store_name": src_root.name,
            "store_version": store_version(src_root),
            "hardlinks": hardlinks,
            "file_count": len(files_meta),
            "total_bytes": total_bytes,
            "bytes_new": bytes_new,
            "linked": linked,
            "files": files_meta,
        }
        (incomplete / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except BaseException:
        shutil.rmtree(incomplete, ignore_errors=True)
        raise

    final = store_root / ts
    os.replace(incomplete, final)
    write_state(store_root, src_root)

    # Imported here rather than at module scope: retention reads every format's
    # snapshot list, so it necessarily sits *above* this module.
    from .retention import apply_retention
    retention = apply_retention(dest, keep=options.retention_keep,
                                min_free_gb=options.min_free_gb)
    return {
        "snapshot": str(final), "timestamp": ts, "file_count": len(files_meta),
        "total_bytes": total_bytes, "bytes_new": bytes_new, "linked": linked,
        "hardlinks": hardlinks, "pruned": retention.get("pruned", 0),
        "format": FORMAT,
    }


def copy_bytes(src: Path, dst: Path, src_stat) -> None:
    """Byte-only copy (no copystat — avoids the SMB EPERM issue, same rule as
    ingest) via a `.part` temp + atomic replace, then restore the source mtime so
    the next incremental recognises the file as unchanged."""
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    try:
        os.utime(dst, ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns))
    except OSError:
        pass


def store_version(src_root: Path) -> str | None:
    try:
        from .. import migrate
        return (src_root / config.INTERNAL_DIRNAME / migrate.VERSION_FILE).read_text(encoding="utf-8").strip()
    except (OSError, ImportError):
        return None


def write_state(store_root: Path, src_root: Path) -> None:
    snaps = [d.name for d in store_root.iterdir()
             if d.is_dir() and not d.name.endswith(INCOMPLETE_SUFFIX)
             and (d / MANIFEST_NAME).is_file()]
    snaps.sort()
    state = {"source_root": str(src_root), "store_name": src_root.name,
             "snapshots": snaps, "updated": datetime.now().isoformat(timespec="seconds")}
    (store_root / STATE_NAME).write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── verify ──────────────────────────────────────────────────────────────────

def verify(snapshot_dir: Path, should_cancel=None, progress=None) -> dict:
    """Recompute every file's sha256 and compare to the manifest — the integrity /
    bit-rot check. Returns {ok, checked, mismatched, missing}."""
    cancelled = should_cancel or (lambda: False)
    manifest = read_manifest(Path(snapshot_dir))
    if manifest is None:
        raise BackupError(f"No manifest in snapshot: {snapshot_dir}")
    files = manifest.get("files", {})
    total = len(files)
    mismatched: list[str] = []
    missing: list[str] = []
    for i, (rel, meta) in enumerate(sorted(files.items()), 1):
        if cancelled():
            return {"cancelled": True}
        p = Path(snapshot_dir) / rel
        if not p.is_file():
            missing.append(rel)
        elif _sha256(p) != meta.get("sha256"):
            mismatched.append(rel)
        if progress:
            progress(i, total)
    return {"ok": not mismatched and not missing, "checked": total,
            "mismatched": mismatched, "missing": missing}


# ── restore ─────────────────────────────────────────────────────────────────

def snapshot_files(snapshot_dir: Path) -> dict[str, dict]:
    """`{rel: {size, mtime, sha256}}` for one snapshot — the public read the UI
    builds its file tree from."""
    return (read_manifest(Path(snapshot_dir)) or {}).get("files", {})


def _expand_relpaths(snapshot_dir: Path, relpaths: list[str]) -> list[str]:
    """Expand any directory selections into their contained files (manifest-backed)."""
    files = snapshot_files(snapshot_dir)
    all_files = list(files.keys())
    out: list[str] = []
    for rel in relpaths:
        rel = rel.rstrip("/")
        if rel in files:
            out.append(rel)
        else:
            prefix = rel + "/"
            out.extend(f for f in all_files if f.startswith(prefix))
    return sorted(set(out))


def preview_restore(snapshot_dir: Path, relpaths: list[str], dest_dir: Path) -> dict:
    """Split the selected files into those that would be newly created vs. those
    that already exist at the target (and would be overwritten)."""
    files = _expand_relpaths(Path(snapshot_dir), relpaths)
    creates, overwrites = [], []
    for rel in files:
        (overwrites if (Path(dest_dir) / rel).exists() else creates).append(rel)
    return {"creates": creates, "overwrites": overwrites, "files": files}


def restore(snapshot_dir: Path, relpaths: list[str], dest_dir: Path, *,
            overwrite: bool = False, should_cancel=None, progress=None) -> dict:
    """Byte-copy selected files out of a snapshot into `dest_dir`, preserving the
    relative tree. Existing files are skipped unless `overwrite=True`. `dest_dir`
    may be a scratch folder (safe default) or `config.DATA_ROOT` (into the store)."""
    cancelled = should_cancel or (lambda: False)
    snapshot_dir = Path(snapshot_dir)
    dest_dir = Path(dest_dir)
    files = _expand_relpaths(snapshot_dir, relpaths)
    total = len(files)
    written, skipped = 0, 0
    for i, rel in enumerate(files, 1):
        if cancelled():
            return {"cancelled": True, "written": written, "skipped": skipped}
        src = snapshot_dir / rel
        dst = dest_dir / rel
        if dst.exists() and not overwrite:
            skipped += 1
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            st = src.stat()
            copy_bytes(src, dst, st)
            written += 1
        if progress:
            progress(i, total)
    return {"written": written, "skipped": skipped, "total": total}


def delete_snapshot(snap: SnapshotInfo) -> None:
    shutil.rmtree(snap.path, ignore_errors=True)

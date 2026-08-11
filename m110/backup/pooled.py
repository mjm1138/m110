"""**Pooled snapshots** — files stored once, addressed by content.

    <destination>/M110-Backups/<store-name>/
        objects/ab/cd/abcdef…        every file, once, named by sha256 of contents
        snapshots/<ts>.json.gz       one self-contained manifest per backup
        latest/                      browsable tree of the newest backup (if links work)
        latest-manifest.json.gz  INDEX.tsv  restore.py  README.txt
        state.json                   a summary cache — nothing depends on it

Why this and not the tape-era full/incremental chain: a chain buys restores that
need every link intact, retention that can't drop a full until its dependents
expire, and a corruption blast radius spanning days. Content addressing gives
incrementals **by construction** with no chain state at all — every snapshot is
independently restorable, retention is "drop a manifest, then sweep objects no
manifest references", and the store is self-validating because an object's name
*is* its checksum.

It also makes dedup the *application's* job (does this hash already exist?)
rather than the *filesystem's* (hardlink to the previous snapshot), which is the
whole point: it works on a share that can't hardlink (issue #92), and on object
storage that has no such concept at all (#93).

**The invariant everything rests on: a manifest exists ⇒ every object it names
exists.** The manifest is written last, after every object is confirmed stored.
A consequence worth knowing: an interrupted first backup **resumes for free** —
the objects it did store are content-addressed, so the next run simply finds them.
"""
from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path

from .. import config
from . import recovery
from .backends import backend_for
from .destination import store_backup_root
from .errors import BackupDestinationError, BackupError
from .hashcache import HashCache, hash_file
from .mirrored import store_version
from .options import BackupOptions, SnapshotInfo, TIMESTAMP_FMT
from .scope import iter_source_files

FORMAT = "pooled"
FORMAT_VERSION = 2
SNAPSHOT_PREFIX = "snapshots/"
SNAPSHOT_SUFFIX = ".json.gz"
OBJECT_PREFIX = "objects/"
STATE_KEY = "state.json"
LATEST_SIDECAR_KEY = "latest/.m110-latest.json"


def object_key(sha: str) -> str:
    """`objects/ab/cd/abcdef…` — two levels of sharding so no directory grows to
    a million entries. Irrelevant to object stores, harmless there."""
    return f"{OBJECT_PREFIX}{sha[:2]}/{sha[2:4]}/{sha}"


def manifest_key(timestamp: str) -> str:
    return f"{SNAPSHOT_PREFIX}{timestamp}{SNAPSHOT_SUFFIX}"


def is_pooled_ref(ref) -> bool:
    """True for a path that names a pooled snapshot manifest."""
    p = Path(ref)
    return p.name.endswith(SNAPSHOT_SUFFIX) and p.parent.name == "snapshots"


def store_root_for_ref(ref) -> Path:
    return Path(ref).parent.parent


# ── listing ─────────────────────────────────────────────────────────────────

def _json_bytes(payload: dict) -> bytes:
    import json as _json
    return _json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")


def _read_state(backend) -> dict:
    try:
        return recovery.read_gzip_json(backend.get_bytes(STATE_KEY))
    except Exception:
        return {}


def read_manifest(ref) -> dict | None:
    """The manifest for one pooled snapshot (accepts its path)."""
    p = Path(ref)
    try:
        return recovery.read_gzip_json(p.read_bytes())
    except Exception:
        return None


def list_snapshots(destination: Path, store_name: str | None = None) -> list[SnapshotInfo]:
    """Pooled snapshots at this destination, newest first.

    Enumerates `snapshots/` and fills the summary fields from `state.json` — a
    *cache*, never the source of truth, so a half-written state file can't make a
    real snapshot invisible. A snapshot the cache doesn't know about costs one
    manifest read."""
    root = store_backup_root(destination, store_name)
    snap_dir = root / "snapshots"
    if not snap_dir.is_dir():
        return []
    backend = backend_for(destination, store_name)
    cached = (_read_state(backend).get("snapshots") or {})
    out: list[SnapshotInfo] = []
    for entry in snap_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(SNAPSHOT_SUFFIX):
            continue
        ts = entry.name[: -len(SNAPSHOT_SUFFIX)]
        try:
            created = datetime.strptime(ts, TIMESTAMP_FMT)
        except ValueError:
            continue
        meta = cached.get(ts)
        if meta is None:
            meta = read_manifest(entry) or {}
        out.append(SnapshotInfo(
            path=entry, timestamp=ts, created=created,
            file_count=int(meta.get("file_count", 0)),
            total_bytes=int(meta.get("total_bytes", 0)),
            store_version=meta.get("store_version"),
            hardlinks=bool(meta.get("hardlinks", False)),
            format=FORMAT,
        ))
    out.sort(key=lambda s: s.created, reverse=True)
    return out


def snapshot_files(ref) -> dict[str, dict]:
    return (read_manifest(ref) or {}).get("files", {})


def delete_snapshot(snap: SnapshotInfo) -> None:
    """Drop the manifest. The objects it referenced are freed by the sweep, which
    is where "does anything else still need this?" is answered."""
    try:
        Path(snap.path).unlink()
    except OSError:
        pass


# ── create ──────────────────────────────────────────────────────────────────

def create_snapshot(options: BackupOptions, should_cancel=None, progress=None) -> dict:
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

    backend = backend_for(dest)
    backend.ensure_root()
    caps = backend.capabilities()
    known = backend.object_sizes()          # one enumeration, not one probe per file

    ts = datetime.now().strftime(TIMESTAMP_FMT)
    rels = iter_source_files(src_root)
    total = len(rels)
    files_meta: dict[str, dict] = {}
    total_bytes = objects_new = bytes_new = 0

    cache = HashCache()
    try:
        for i, rel in enumerate(rels, 1):
            if cancelled():
                # Objects already stored are content-addressed, so the next run
                # finds and reuses them: an interrupted first sync resumes free.
                return {"cancelled": True}
            src = src_root / rel
            try:
                st = src.stat()
            except OSError:
                continue                    # vanished mid-run — skip
            sha = cache.sha256(src, st)
            stored = known.get(sha)
            if stored is not None and stored != st.st_size:
                # An object's size is a function of its bytes, so this can only
                # mean our cached hash is stale (or the stored object is damaged).
                # Rehash from source; a cache that lies must not survive contact.
                cache.forget(src)
                sha = hash_file(src)
                cache.remember(src, st, sha)
                stored = known.get(sha)
            if stored is None:
                backend.put_file(object_key(sha), src, size=st.st_size)
                known[sha] = st.st_size
                objects_new += 1
                bytes_new += st.st_size
            files_meta[rel] = {"size": st.st_size, "mtime": st.st_mtime, "sha256": sha}
            total_bytes += st.st_size
            if progress:
                progress(i, total)
        cache.flush()
        cache.sweep()
    finally:
        cache.close()

    manifest = {
        "format": FORMAT_VERSION,
        "timestamp": ts,
        "created": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(src_root),
        "store_name": src_root.name,
        "store_version": store_version(src_root),
        "app_version": _app_version(),
        "host": platform.node(),
        "scope": "everything",
        "hardlinks": bool(caps.hardlinks),
        "file_count": len(files_meta),
        "total_bytes": total_bytes,
        "bytes_new": bytes_new,
        "objects_new": objects_new,
        "objects_referenced": len({m["sha256"] for m in files_meta.values()}),
        "files": files_meta,
    }
    blob = recovery.gzip_json(manifest)
    # Written LAST, and only once every object above is stored — the invariant
    # that makes retention a refcount instead of a dependency graph.
    backend.put_bytes(manifest_key(ts), blob)

    recovery.write_recovery(backend, manifest, blob)
    linked = _relink_latest(backend, manifest) if caps.hardlinks else 0
    _write_state(backend, manifest, known)

    from .retention import apply_retention
    retention = apply_retention(dest, keep=options.retention_keep,
                                min_free_gb=options.min_free_gb)
    return {
        "snapshot": str(store_backup_root(dest) / manifest_key(ts)),
        "timestamp": ts, "file_count": len(files_meta), "total_bytes": total_bytes,
        "bytes_new": bytes_new, "objects_new": objects_new, "linked": linked,
        "hardlinks": bool(caps.hardlinks), "pruned": retention.get("pruned", 0),
        "swept": retention.get("swept", 0), "format": FORMAT,
    }


def _app_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("m110")
    except Exception:
        return None


def _relink_latest(backend, manifest: dict) -> int:      # noqa: C901
    """Refresh the browsable `latest/` tree **by diff**, not by rebuild.

    A sidecar records which snapshot `latest/` currently mirrors; we compare that
    manifest to the new one and touch only what changed. Rebuilding from scratch
    would mean one link per file per night — the exact per-file round-trip cost
    the pooled format exists to avoid on a network share."""
    import json as _json

    new_files = manifest.get("files", {})
    prior_files: dict[str, dict] = {}
    try:
        sidecar = _json.loads(backend.get_bytes(LATEST_SIDECAR_KEY).decode("utf-8"))
        prior = recovery.read_gzip_json(
            backend.get_bytes(manifest_key(sidecar["timestamp"])))
        prior_files = prior.get("files", {})
    except Exception:
        prior_files = {}        # unknown → rebuild from scratch, still correct

    linked = 0
    for rel in set(prior_files) - set(new_files):
        backend.unlink_rel(rel)
    for rel, meta in new_files.items():
        if prior_files.get(rel, {}).get("sha256") == meta["sha256"]:
            continue
        if not backend.link(object_key(meta["sha256"]), rel):
            # Linking stopped working part-way (a remount, a full disk). A
            # partial tree would be a lie about what the newest backup contains.
            backend.drop_latest()
            return 0
        linked += 1
    backend.put_bytes(LATEST_SIDECAR_KEY,
                      _json.dumps({"timestamp": manifest["timestamp"]},
                                  indent=1).encode("utf-8"))
    return linked


def _write_state(backend, manifest: dict, known: dict[str, int]) -> None:
    state = _read_state(backend)
    snaps = state.get("snapshots") or {}
    snaps[manifest["timestamp"]] = {
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "store_version": manifest.get("store_version"),
        "scope": manifest.get("scope"),
        "hardlinks": manifest.get("hardlinks"),
    }
    state.update({
        "format": FORMAT_VERSION,
        "store_name": manifest.get("store_name"),
        "source_root": manifest.get("source_root"),
        "host": manifest.get("host"),
        "updated": datetime.now().isoformat(timespec="seconds"),
        "hardlinks": manifest.get("hardlinks"),
        "object_count": len(known),
        "object_bytes": sum(known.values()),
        "snapshots": snaps,
    })
    # Plain JSON: it's small, and "a summary you can read" is the point.
    backend.put_bytes(STATE_KEY,
                      _json_bytes(state))


def forget_snapshots(destination: Path, timestamps, store_name: str | None = None) -> None:
    """Drop pruned snapshots from the state cache."""
    backend = backend_for(destination, store_name)
    state = _read_state(backend)
    snaps = state.get("snapshots") or {}
    for ts in timestamps:
        snaps.pop(ts, None)
    if not state:
        return
    state["snapshots"] = snaps
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    # Plain JSON: it's small, and "a summary you can read" is the point.
    backend.put_bytes(STATE_KEY,
                      _json_bytes(state))


# ── verify ──────────────────────────────────────────────────────────────────

def verify(ref, should_cancel=None, progress=None) -> dict:
    """Check that every object this snapshot names is present and still hashes to
    its own name.

    Stronger than the mirrored equivalent by construction: there the manifest's
    sha is inherited across hardlinked generations and only ever re-read here,
    whereas an object's *name* is its checksum, so the store validates itself."""
    cancelled = should_cancel or (lambda: False)
    manifest = read_manifest(ref)
    if manifest is None:
        raise BackupError(f"No manifest at: {ref}")
    root = store_root_for_ref(ref)
    files = manifest.get("files", {})
    total = len(files)
    missing: list[str] = []
    mismatched: list[str] = []
    seen: dict[str, str] = {}       # sha → "ok" | "bad" | "missing"
    for i, (rel, meta) in enumerate(sorted(files.items()), 1):
        if cancelled():
            return {"cancelled": True}
        sha = meta.get("sha256", "")
        status = seen.get(sha)
        if status is None:
            p = root.joinpath(*object_key(sha).split("/"))
            if not p.is_file():
                status = "missing"
            else:
                status = "ok" if hash_file(p) == sha else "bad"
            seen[sha] = status      # dedup: shared content is hashed once
        if status == "missing":
            missing.append(rel)
        elif status == "bad":
            mismatched.append(rel)
        if progress:
            progress(i, total)
    return {"ok": not mismatched and not missing, "checked": total,
            "mismatched": mismatched, "missing": missing}


# ── restore ─────────────────────────────────────────────────────────────────

def _expand_relpaths(ref, relpaths: list[str]) -> list[str]:
    files = snapshot_files(ref)
    out: list[str] = []
    for rel in relpaths:
        rel = rel.rstrip("/")
        if rel in files:
            out.append(rel)
        else:
            prefix = rel + "/"
            out.extend(f for f in files if f.startswith(prefix))
    return sorted(set(out))


def preview_restore(ref, relpaths: list[str], dest_dir: Path) -> dict:
    files = _expand_relpaths(ref, relpaths)
    creates, overwrites = [], []
    for rel in files:
        (overwrites if (Path(dest_dir) / rel).exists() else creates).append(rel)
    return {"creates": creates, "overwrites": overwrites, "files": files}


def restore(ref, relpaths: list[str], dest_dir: Path, *, overwrite: bool = False,
            should_cancel=None, progress=None) -> dict:
    cancelled = should_cancel or (lambda: False)
    manifest = read_manifest(ref) or {}
    meta_by_rel = manifest.get("files", {})
    root = store_root_for_ref(ref)
    backend = _backend_at(root)
    dest_dir = Path(dest_dir)
    files = _expand_relpaths(ref, relpaths)
    total = len(files)
    written = skipped = 0
    for i, rel in enumerate(files, 1):
        if cancelled():
            return {"cancelled": True, "written": written, "skipped": skipped}
        dst = dest_dir / rel
        if dst.exists() and not overwrite:
            skipped += 1
        else:
            meta = meta_by_rel.get(rel, {})
            key = object_key(meta.get("sha256", ""))
            try:
                backend.get_file(key, dst)
            except (OSError, KeyError):
                skipped += 1
                if progress:
                    progress(i, total)
                continue
            # Restore the file's own capture-time mtime: an object's timestamp is
            # when it was stored, which says nothing about the frame.
            mtime = meta.get("mtime")
            if mtime:
                try:
                    os.utime(dst, (mtime, mtime))
                except OSError:
                    pass
            written += 1
        if progress:
            progress(i, total)
    return {"written": written, "skipped": skipped, "total": total}


def _backend_at(store_root: Path):
    from .backends.local import LocalBackend
    return LocalBackend(store_root)

"""Library backup — hardlinked dated snapshots of the data store (ROADMAP item 10).

Qt-free engine (like `ingest`/`siril`/`publish`): pure functions taking optional
`should_cancel`/`progress` callbacks. A backup is an **external output** — it reads
`config.DATA_ROOT` and writes to a user-chosen destination *outside* the store, so
it never changes the on-disk store layout (no `.store_version` impact).

Model — dated snapshots with hardlink dedup (`rsync --link-dest` semantics):

    <destination>/M110-Backups/<store-name>/
        2026-07-01_143000/                     one complete, browsable snapshot tree
            Objects/ Images/ Media/ Inbox/ .m110_internal_data/(authored subset)
            .m110-backup-manifest.json         {rel: {size, mtime, sha256}} + metadata
        2026-07-02_090000/ …
        .m110-backup-state.json                index of snapshots for this store

Each snapshot is a *full* tree, but files unchanged since the previous snapshot
(all the immutable raws) are **hardlinked** to it — so incrementals cost only the
changed bytes. Scope is a **denylist**: back up everything under the store except
known-regenerable/working paths, so new authored data is captured automatically.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config

BACKUPS_DIRNAME = "M110-Backups"
MANIFEST_NAME = ".m110-backup-manifest.json"
STATE_NAME = ".m110-backup-state.json"
INCOMPLETE_SUFFIX = ".incomplete"
TIMESTAMP_FMT = "%Y-%m-%d_%H%M%S_%f"   # microseconds → unique even on rapid runs
_MTIME_EPS = 1e-4       # mtime float-compare tolerance (source clock is stable)
_HASH_CHUNK = 1 << 20   # 1 MiB

# Paths (relative to the store root) that are NOT backed up — all regenerable or
# working-area. Everything else under DATA_ROOT is included (denylist, so future
# authored files are captured without an allowlist to maintain).
_EXCLUDE_INTERNAL = {
    f"{config.INTERNAL_DIRNAME}/derived",
    f"{config.INTERNAL_DIRNAME}/renders",
    f"{config.INTERNAL_DIRNAME}/sessions.jsonl",
}


# Persisted settings (global `~/.m110/settings.json`, via config.get/save_setting).
SETTING_DEST = "backup_destination"
SETTING_AUTO = "backup_auto_on_launch"
SETTING_INTERVAL = "backup_interval_hours"
SETTING_KEEP = "backup_retention_keep"
SETTING_MIN_FREE = "backup_min_free_gb"
DEFAULT_MIN_FREE_GB = 100       # prune oldest snapshots to keep this much free
SETTING_DAILY_HOUR = "backup_daily_hour"
DEFAULT_INTERVAL_HOURS = 12
DEFAULT_DAILY_HOUR = 2          # 02:00 local — the while-running daily backup time


class BackupError(Exception):
    """Base for backup failures."""


class BackupDestinationError(BackupError):
    """The destination is missing, unwritable, or unreachable."""


@dataclass
class BackupOptions:
    destination: Path
    retention_keep: int | None = None       # keep N newest snapshots (None = all)
    min_free_gb: float | None = None         # delete oldest until ≥ this free


@dataclass
class SnapshotInfo:
    path: Path
    timestamp: str
    created: datetime
    file_count: int
    total_bytes: int
    store_version: str | None = None
    hardlinks: bool = True


# ── path scope ──────────────────────────────────────────────────────────────

def _is_excluded(rel: str) -> bool:
    """rel is a POSIX-style path relative to the store root."""
    if rel in _EXCLUDE_INTERNAL:
        return True
    for ex in _EXCLUDE_INTERNAL:
        if rel.startswith(ex + "/"):
            return True
    # Any Siril sandbox: Images/<target>/siril/…  (working area, regenerable).
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "Images" and parts[2] == "siril":
        return True
    return False


def iter_source_files(root: Path) -> list[str]:
    """Relative POSIX paths of every file under `root` that should be backed up
    (denylist applied). Sorted for deterministic ordering."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        # Prune excluded directories in-place so os.walk doesn't descend them.
        kept = []
        for d in dirnames:
            rd = f"{rel_dir}/{d}" if rel_dir else d
            if not _is_excluded(rd):
                kept.append(d)
        dirnames[:] = kept
        for f in filenames:
            rf = f"{rel_dir}/{f}" if rel_dir else f
            if not _is_excluded(rf):
                out.append(rf)
    out.sort()
    return out


# ── hashing / manifest ──────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(snapshot_dir: Path) -> dict | None:
    mf = snapshot_dir / MANIFEST_NAME
    try:
        return json.loads(mf.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# ── destination helpers ─────────────────────────────────────────────────────

def store_backup_root(destination: Path, store_name: str | None = None) -> Path:
    """`<destination>/M110-Backups/<store-name>` — snapshots for one store live here."""
    name = store_name or config.DATA_ROOT.name or "M110"
    return Path(destination) / BACKUPS_DIRNAME / name


def _supports_hardlinks(dir_path: Path) -> bool:
    """Probe whether `dir_path`'s filesystem supports hardlinks (some SMB/exFAT
    don't). Creates + links + removes two temp files."""
    a = dir_path / ".m110-linkprobe-a"
    b = dir_path / ".m110-linkprobe-b"
    try:
        a.write_text("x")
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
    """Completed snapshots for this store, newest first. Ignores `*.incomplete`."""
    root = store_backup_root(destination, store_name)
    if not root.is_dir():
        return []
    snaps: list[SnapshotInfo] = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.endswith(INCOMPLETE_SUFFIX):
            continue
        if not (d / MANIFEST_NAME).is_file():
            continue
        m = _read_manifest(d) or {}
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

    hardlinks = _supports_hardlinks(store_root)
    prior = (list_snapshots(dest) or [None])[0]
    prior_manifest = _read_manifest(prior.path) if prior else None
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
                _copy_bytes(src, dst, st)
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
            "store_version": _store_version(src_root),
            "hardlinks": hardlinks,
            "file_count": len(files_meta),
            "total_bytes": total_bytes,
            "bytes_new": bytes_new,
            "linked": linked,
            "files": files_meta,
        }
        (incomplete / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))
    except BaseException:
        shutil.rmtree(incomplete, ignore_errors=True)
        raise

    final = store_root / ts
    os.replace(incomplete, final)
    _write_state(store_root, src_root)

    retention = apply_retention(dest, keep=options.retention_keep,
                                min_free_gb=options.min_free_gb)
    return {
        "snapshot": str(final), "timestamp": ts, "file_count": len(files_meta),
        "total_bytes": total_bytes, "bytes_new": bytes_new, "linked": linked,
        "hardlinks": hardlinks, "pruned": retention.get("pruned", 0),
    }


def _copy_bytes(src: Path, dst: Path, src_stat) -> None:
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


def _store_version(src_root: Path) -> str | None:
    try:
        from . import migrate
        return (src_root / config.INTERNAL_DIRNAME / migrate.VERSION_FILE).read_text().strip()
    except (OSError, ImportError):
        return None


def _write_state(store_root: Path, src_root: Path) -> None:
    snaps = [d.name for d in store_root.iterdir()
             if d.is_dir() and not d.name.endswith(INCOMPLETE_SUFFIX)
             and (d / MANIFEST_NAME).is_file()]
    snaps.sort()
    state = {"source_root": str(src_root), "store_name": src_root.name,
             "snapshots": snaps, "updated": datetime.now().isoformat(timespec="seconds")}
    (store_root / STATE_NAME).write_text(json.dumps(state, indent=2))


# ── verify ──────────────────────────────────────────────────────────────────

def verify(snapshot_dir: Path, should_cancel=None, progress=None) -> dict:
    """Recompute every file's sha256 and compare to the manifest — the integrity /
    bit-rot check. Returns {ok, checked, mismatched, missing}."""
    cancelled = should_cancel or (lambda: False)
    manifest = _read_manifest(Path(snapshot_dir))
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

def _expand_relpaths(snapshot_dir: Path, relpaths: list[str]) -> list[str]:
    """Expand any directory selections into their contained files (manifest-backed)."""
    manifest = _read_manifest(snapshot_dir) or {}
    all_files = list(manifest.get("files", {}).keys())
    out: list[str] = []
    for rel in relpaths:
        rel = rel.rstrip("/")
        if rel in manifest.get("files", {}):
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
            _copy_bytes(src, dst, st)
            written += 1
        if progress:
            progress(i, total)
    return {"written": written, "skipped": skipped, "total": total}


# ── retention ───────────────────────────────────────────────────────────────

def apply_retention(destination: Path, *, keep: int | None = None,
                    min_free_gb: float | None = None,
                    store_name: str | None = None) -> dict:
    """Delete whole oldest snapshots per policy. No-op unless a policy is set.
    Never deletes the last remaining snapshot. Because unchanged files are
    hardlinked across snapshots, deleting one frees only its unique inodes.

    Policies are count-based (`keep` newest) and space-based (`min_free_gb` free
    on the destination volume) — both prune the *oldest* first. There is
    deliberately no age-based ("older than N days") policy: it would silently wipe
    a whole backup history after a gap in use (e.g. a two-week vacation)."""
    snaps = list_snapshots(destination, store_name)   # newest first
    to_delete: list[SnapshotInfo] = []

    if keep is not None and keep >= 1 and len(snaps) > keep:
        to_delete.extend(snaps[keep:])

    survivors = [s for s in snaps if s not in to_delete]
    if min_free_gb is not None and min_free_gb > 0:
        need = min_free_gb * (1024 ** 3)
        # Delete oldest survivors until free space clears the threshold.
        for s in sorted(survivors, key=lambda s: s.created):
            if _free_bytes(destination) >= need or len(survivors) <= 1:
                break
            to_delete.append(s)
            survivors.remove(s)

    # Never delete every snapshot — keep at least the newest.
    remaining = [s for s in snaps if s not in to_delete]
    if not remaining and snaps:
        newest = max(snaps, key=lambda s: s.created)
        to_delete = [s for s in to_delete if s is not newest]

    pruned = 0
    for s in to_delete:
        shutil.rmtree(s.path, ignore_errors=True)
        pruned += 1
    if pruned:
        root = store_backup_root(destination, store_name)
        _write_state(root, config.DATA_ROOT)
    return {"pruned": pruned, "kept": len(snaps) - pruned}


def _free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


# ── settings helpers (shared by the dialogs + the launch auto-trigger) ───────

def options_from_settings(destination: Path) -> BackupOptions:
    """Build BackupOptions with the saved retention policy for a destination."""
    def _int(key):
        v = config.get_setting(key)
        return int(v) if v not in (None, "", 0) else None

    # Min-free defaults to 100 GB when never configured; an explicit 0 means "off".
    # (Only an absent key gets the default — a stored 0/null is an intentional off.)
    mf = config.get_setting(SETTING_MIN_FREE, DEFAULT_MIN_FREE_GB)
    try:
        min_free = float(mf)
    except (TypeError, ValueError):
        min_free = DEFAULT_MIN_FREE_GB
    return BackupOptions(
        destination=Path(destination),
        retention_keep=_int(SETTING_KEEP),
        min_free_gb=min_free if min_free > 0 else None,
    )


def _auto_enabled_and_reachable(destination: Path) -> Path | None:
    """The destination path iff auto-backup is on and the folder is reachable, else
    None (missing/unreachable → not due, no nag). Shared by both auto triggers."""
    if not config.get_setting(SETTING_AUTO, False):
        return None
    dest = Path(destination)
    return dest if dest.is_dir() else None


def _interval_hours() -> float:
    return float(config.get_setting(SETTING_INTERVAL, DEFAULT_INTERVAL_HOURS) or
                 DEFAULT_INTERVAL_HOURS)


def due_for_auto_backup(destination: Path) -> bool:
    """True iff auto-backup is enabled, the destination is reachable, and it's been
    at least the configured interval since the newest snapshot (drives the
    launch-time trigger). Missing/unreachable destination → not due (no nag)."""
    dest = _auto_enabled_and_reachable(destination)
    if dest is None:
        return False
    snaps = list_snapshots(dest)
    if not snaps:
        return True
    age_hours = (datetime.now() - snaps[0].created).total_seconds() / 3600.0
    return age_hours >= _interval_hours()


def due_for_scheduled_backup(destination: Path, now: datetime | None = None) -> bool:
    """True iff auto-backup is enabled, the destination is reachable, the local clock
    has reached the daily backup hour (default 02:00), we haven't already backed up
    since that hour today, and the newest snapshot is at least `interval` hours old.

    Drives the hourly while-running tick, so a long-lived session (the app left
    running for days) still gets a daily snapshot rather than only backing up at
    launch. The interval acts as a min-age guard here so a fresh launch backup
    doesn't immediately re-fire at 02:00; the once-per-day guard keeps it from
    repeating through the rest of the day."""
    dest = _auto_enabled_and_reachable(destination)
    if dest is None:
        return False
    now = now or datetime.now()
    hour = int(config.get_setting(SETTING_DAILY_HOUR, DEFAULT_DAILY_HOUR) or
               DEFAULT_DAILY_HOUR)
    if now.hour < hour:
        return False                        # before today's scheduled time
    snaps = list_snapshots(dest)
    if not snaps:
        return True
    newest = snaps[0].created
    scheduled_today = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if newest >= scheduled_today:
        return False                        # already backed up since 02:00 today
    age_hours = (now - newest).total_seconds() / 3600.0
    return age_hours >= _interval_hours()

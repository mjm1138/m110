"""What gets backed up.

Scope is a **denylist**: back up everything under the store except known
regenerable/working paths, so new authored data is captured automatically
without an allowlist to maintain.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import config

# Paths (relative to the store root) that are NOT backed up — all regenerable or
# working-area.
_EXCLUDE_INTERNAL = {
    f"{config.INTERNAL_DIRNAME}/derived",
    f"{config.INTERNAL_DIRNAME}/renders",
    f"{config.INTERNAL_DIRNAME}/sessions.jsonl",
    # Assistant staging: regenerable by asking again, and nothing in it is
    # authoritative until the user accepts it into the real store.
    f"{config.INTERNAL_DIRNAME}/assistant",
}


def is_excluded(rel: str) -> bool:
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
            if not is_excluded(rd):
                kept.append(d)
        dirnames[:] = kept
        for f in filenames:
            rf = f"{rel_dir}/{f}" if rel_dir else f
            if not is_excluded(rf):
                out.append(rf)
    out.sort()
    return out

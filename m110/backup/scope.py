"""What gets backed up.

Scope is a **denylist**: back up everything under the store except known
regenerable/working paths, so new authored data is captured automatically
without an allowlist to maintain.

A workflow sandbox (`Images/<target>/siril/`, `astrowizard/`, …) is **not**
excluded wholesale. Only its *linked inputs* are — the hardlink trees declared in
`config.SANDBOX_LINKED_INPUTS` — because those bytes are already in the snapshot
under their real path. What a sandbox otherwise holds is authored work.
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
    return _is_sandbox_linked_input(rel.split("/"))


def _is_sandbox_linked_input(parts: list[str]) -> bool:
    """True for a workflow sandbox's **linked inputs** — the hardlink trees at
    `Images/<target>/<sandbox>/lights/…`, or, for a per-filter Siril job, at
    `Images/<target>/<sandbox>/<FILTER>/lights/…`.

    Only those are skipped, not the whole sandbox. They are hardlinks to frames
    already backed up under `Images/<target>/lights/`, and the mirrored format
    dedups by *relative path*, so leaving them in stores a second full copy of
    every sub. The rest of a sandbox — archived runs, presets, another workflow's
    exports — is hand-work no refresh regenerates, and is backed up.

    Which subdirectories those are is declared per workflow in
    `config.SANDBOX_LINKED_INPUTS`; see the note there before adding a workflow.
    """
    if len(parts) < 4 or parts[0] != "Images":
        return False
    linked = config.SANDBOX_LINKED_INPUTS.get(parts[2])
    if not linked:
        return False
    tail = parts[3:]
    # A job root is the sandbox itself, or one per-filter dir below it. A deeper
    # match is deliberately left in scope: `archive/<ts>/…` is authored output, and
    # a backup denylist should fail toward keeping a file rather than dropping it.
    return tail[0] in linked or (len(tail) > 1 and tail[1] in linked)


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

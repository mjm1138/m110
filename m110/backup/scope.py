"""What gets backed up.

Scope is a **denylist**: back up everything under the store except known
regenerable/working paths, so new authored data is captured automatically
without an allowlist to maintain.

A workflow sandbox (`Images/<target>/siril/`, `astrowizard/`, …) is **not**
excluded wholesale. Only its *linked inputs* are — the hardlink trees declared in
`config.SANDBOX_LINKED_INPUTS` — because those bytes are already in the snapshot
under their real path. What a sandbox otherwise holds is authored work.

**Tiers** (issue #93) sit on top of that denylist, because offsite storage is
metered where a spare drive isn't. Light frames are ~99% of a library's bytes, so
a first sync at full scope is a multi-day, non-trivially-expensive operation that
plenty of people would start and then cancel. `essentials` is the answer: the
irreplaceable and the hand-made go offsite for a couple of dollars a month, and
the raws stay on the drive that can hold them.

**Narrowing a destination's scope deletes nothing immediately.** `sweep_objects`
marks from *every surviving manifest*, so frames dropped from the new scope stay
referenced by the older, wider snapshots until retention prunes those. The
disappearance is real but deferred — which is the window in which to warn.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import config

SCOPE_EVERYTHING = "everything"
SCOPE_ESSENTIALS = "essentials"
DEFAULT_SCOPE = SCOPE_EVERYTHING
SCOPES = (SCOPE_EVERYTHING, SCOPE_ESSENTIALS)

SCOPE_LABELS = {
    SCOPE_EVERYTHING: "Everything",
    SCOPE_ESSENTIALS: "Essentials (no light frames)",
}

SCOPE_BLURBS = {
    SCOPE_EVERYTHING: (
        "Backs up your whole Library, light frames included. The complete "
        "picture, and the right choice for a drive or network share."),
    SCOPE_ESSENTIALS: (
        "Backs up everything except your raw light frames and archived "
        "processing runs — journals, finished images, stacks, plans and settings "
        "all still go. Typically a few percent of the size, which is what makes "
        "cloud storage affordable. Your raws stay wherever they are now."),
}

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

# The per-target tiers `essentials` leaves behind: the frames themselves. Each is
# bulk raw capture the user can keep locally — as opposed to `finished/`,
# `stacks/` and `seestar-stacks/`, which are deliverables, and the
# journals/plans/settings, which are hand-written and irreplaceable.
_BULK_FRAME_TIERS = frozenset({"lights", "rejected", "previews"})

# Archived processing runs are also skipped at `essentials`. They are authored
# output, but they are *bounded and disposable by the app's own policy* —
# `roundtrip.prune_archives` deletes them on a keep-N rule — and one real library
# reached 42 GB across 36 of them, which would swamp the tier's whole purpose.
# The deliverable that mattered was imported to `finished/`, and that is kept.
_ARCHIVE_DIRNAME = "archive"


def is_excluded(rel: str, scope: str = DEFAULT_SCOPE) -> bool:
    """rel is a POSIX-style path relative to the store root."""
    if rel in _EXCLUDE_INTERNAL:
        return True
    for ex in _EXCLUDE_INTERNAL:
        if rel.startswith(ex + "/"):
            return True
    parts = rel.split("/")
    if _is_sandbox_linked_input(parts):
        return True
    return scope == SCOPE_ESSENTIALS and _is_bulk(parts)


def _is_bulk(parts: list[str]) -> bool:
    """True for the raw-frame tiers and archived processing runs — what
    `essentials` leaves at home. See `_BULK_FRAME_TIERS` for the line drawn."""
    if len(parts) < 3 or parts[0] != "Images":
        return False
    if parts[2] in _BULK_FRAME_TIERS:
        return True
    # `Images/<target>/<sandbox>/archive/…`, or one per-filter level deeper.
    if parts[2] in config.SANDBOX_DIRNAMES:
        tail = parts[3:]
        return bool(tail) and (tail[0] == _ARCHIVE_DIRNAME or
                               (len(tail) > 1 and tail[1] == _ARCHIVE_DIRNAME))
    return False


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


def iter_source_files(root: Path, scope: str = DEFAULT_SCOPE) -> list[str]:
    """Relative POSIX paths of every file under `root` that should be backed up
    (denylist + scope tier applied). Sorted for deterministic ordering."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        # Prune excluded directories in-place so os.walk doesn't descend them.
        kept = []
        for d in dirnames:
            rd = f"{rel_dir}/{d}" if rel_dir else d
            if not is_excluded(rd, scope):
                kept.append(d)
        dirnames[:] = kept
        for f in filenames:
            rf = f"{rel_dir}/{f}" if rel_dir else f
            if not is_excluded(rf, scope):
                out.append(rf)
    out.sort()
    return out

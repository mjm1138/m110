"""Workflow round-trip machinery — the half of a processing sandbox that is not
about any particular tool.

Every processing workflow M110 supports has the same shape once the tool itself
is out of the picture:

    hand work in → (you process it in the tool) → import what came back → tidy up

`siril.py` grew all of this first, and roughly two thirds of it never mentioned
Siril: classifying a file as a render or a stack, routing it to `finished/` or
`stacks/`, keeping both copies when a re-processed file collides by name,
detecting whether anything is waiting, and sweeping a finished run into
`archive/<ts>/`. Extracting it is what lets a second workflow — AstroWizard
(ROADMAP 14b) — be thin instead of a second copy of the same 200 lines.

**What stays tool-specific** is expressed by a `Sandbox` descriptor rather than by
forking the code: where the sandbox lives, which of its subdirectories never hold
importable output, whether a stray file in the *object* dir should be claimed,
whether the sandbox splits into per-filter jobs, and what survives the archive
sweep. Everything else here is shared, and a behavioural change lands in both
workflows at once — which is the point, since the two silently disagreeing is the
bug class `config.SANDBOX_LINKED_INPUTS` already exists to prevent.

**Claiming is per-workflow and must stay that way.** `root_outputs` deliberately
skips every registered sandbox (`config.SANDBOX_DIRNAMES`), so one workflow's
importer can never present another's exports as its own finished work. That is not
tidiness: before it existed, Siril's import offered to copy files Siril never made,
and `has_unimported_output` went true off a different tool's output, which made
`autoprep` skip the target.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config, hints, objects

_RASTER_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
_FIT_EXTS = (".fit", ".fits")
# The finished-deliverable / star-layer vocabulary is user-editable and shared —
# see `hints.py` (finished = "processed/final/finished", intermediate =
# "starless/starmask" by default). A finished output looks "final"…
# …and is not a star *layer* (starless/starmask are always intermediates).
# NB: pipeline-step tokens (_og/_crop/_stretch/_spcc/_graxpert) are NOT a veto on
# their own — the Naztronomy/Siril deliverable bakes the steps it went through
# into its name (e.g. "…_spcc_processed.png"). A bare step file is excluded
# anyway because a .fit must carry a finished hint to count as a stack, and those
# rasters are rare; over-vetoing them silently dropped real finished output (#).
# This vocabulary only decides *loose* files — a file sorted into a stacks/ or
# finished/ tier is classified by its directory instead (see `classify`, #85).


class Cancelled(Exception):
    """Raised inside plan/apply when the caller's should_cancel() turns true."""


def link_or_copy(src: str, dst: str) -> None:
    """Hardlink src→dst; byte-copy fallback if linking isn't possible. Idempotent
    and race-safe: if dst already exists (a concurrent or prior prep linked it),
    leave it — never copyfile onto the same inode (which raises SameFileError).

    Shared: both sandboxes that hold frames build their tree this way, and a
    sandbox's linked inputs are exactly what `backup.scope` skips — so the two
    have to agree on what "linked" means."""
    try:
        os.link(src, dst)
    except FileExistsError:
        return                       # already linked (prior/concurrent prep) — fine
    except OSError:
        if not os.path.exists(dst):  # linking unsupported (cross-device, …) → copy
            shutil.copyfile(src, dst)


# ── the per-workflow descriptor ──────────────────────────────────────────────

@dataclass(frozen=True)
class Sandbox:
    """What a workflow has to say about its own sandbox for the shared
    round-trip to drive it.

    `id` is the directory name under `Images/<target>/`, and must be a key of
    `config.SANDBOX_LINKED_INPUTS` — that mapping is the single authority on
    which sandboxes exist, and a name that is not in it is invisible to the
    walks that must skip sandboxes.
    """
    id: str
    skip_dirs: frozenset      # sandbox subdirs that never hold fresh output
    scan_root: bool           # also claim output loose in Images/<target>/?
    split_jobs: bool          # per-filter job subdirs (each with lights/)?
    archive_keep: Callable    # (Path) -> True to survive the archive sweep
    loose_fits_kind: str = "stack"   # what a loose finished .fit/.fits IS here
    #: (Path) -> True for a file that is this workflow's *input*, never its
    #: output. Siril states that structurally — its inputs are the `lights/`
    #: tree, already in `skip_dirs`. AstroWizard's input is a single handed-off
    #: file sitting loose in the sandbox root, so it needs naming at file level
    #: or the importer offers the user their own stack back.
    skip_file: Callable | None = None

    def dir(self, target: str) -> Path:
        return config.target_dir(target) / self.id

    def job_dirs(self, base: Path) -> list[Path]:
        """The dirs to tidy: per-filter subdirs (each has `lights/`) when the
        workflow splits and the sandbox actually is split, else the root."""
        if not self.split_jobs:
            return [base]
        filt = [p for p in base.iterdir() if p.is_dir() and (p / "lights").is_dir()]
        return filt if filt else [base]


# ── classification (shared: directory wins, then the filename vocabulary) ────

# Managed content tiers whose *directory* classifies a file outright — a file the
# user filed under stacks/ is a stack, under finished/ is a deliverable, whatever
# its filename (#85). `seestar-stacks/` is a device tier (in-app stacks ingested
# from the scope), never user processing output, so it is never a source.
_OUTPUT_TIERS = ("stacks", "finished")


def tier_of(dir_parts) -> str | None:
    """The managed output tier (`stacks`/`finished`) among a file's ancestor
    directory names, nearest-to-the-file first, or None if it sits loose."""
    for part in reversed(dir_parts):
        if part in _OUTPUT_TIERS:
            return part
    return None


def classify(path: Path, target: str, tier: str | None = None,
             loose_fits_kind: str = "stack"):
    """(kind, dest) for a candidate file, or None if it's not a finished output.

    **Directory wins (#85).** When `tier` names the managed tier the file sits
    under, that tier classifies it outright — no filename hint required, and the
    star-layer/intermediate veto is *not* applied (the user filed it there on
    purpose; if they disagree they move the file). Only files that sit *loose*
    (no tier dir in their path) fall back to the filename vocabulary: a raster is
    a render; a `.fit` is a stack only if it carries a finished hint, so a bare
    intermediate stays out.

    Tool-agnostic on purpose. AstroWizard's exports cannot be recognised by
    filename at all — they go through a native save dialog, so the user types the
    name — which is exactly why the directory has to be what decides."""
    name = path.name
    if "_thn." in name or name == "lights.fit":
        return None
    ext = path.suffix.lower()

    if tier == "stacks":
        # A stack is a FITS master; a stray raster in stacks/ isn't one (and the
        # gallery already surfaces it), so leave it.
        if ext in _FIT_EXTS:
            return "stack", config.stacks_dir(target) / name
        return None
    if tier == "finished":
        # A deliverable can be a raster or a FITS master — either belongs here.
        if ext in _RASTER_EXTS or ext in _FIT_EXTS:
            return "render", config.finished_dir(target) / name
        return None

    # Loose: classify by the filename vocabulary (hints.py).
    if hints.is_intermediate_name(name):
        return None
    if ext in _RASTER_EXTS:
        return "render", config.finished_dir(target) / name
    if ext in _FIT_EXTS and hints.is_finished_name(name):
        # What a loose finished FITS *is* depends on what the workflow consumes.
        # Siril's sandbox turns frames into a stack, so its finished FITS is a
        # stack master and belongs in `stacks/`. AstroWizard is handed a stack and
        # everything downstream of that is a deliverable, so an exported
        # `…_final.fits` belongs in `finished/` — filing it under `stacks/` would
        # put a stretched, star-reduced image in the tier `build_derived` reads
        # for stack metadata (STACKCNT/LIVETIME/DATE), where it is not a stack and
        # its header no longer describes one.
        if loose_fits_kind == "render":
            return "render", config.finished_dir(target) / name
        return "stack", config.stacks_dir(target) / name
    return None


# ── discovery ────────────────────────────────────────────────────────────────

# Object-root subdirs skipped when scanning Images/<target>/ for output a run left
# there directly (the mis-pointed-working-directory case): raw inputs, the device
# stacks (not user output), per-sub previews, tool scratch, and **every** workflow
# sandbox (`config.SANDBOX_DIRNAMES`) — the owning workflow walks its own sandbox,
# and another workflow's output is not ours to claim. The managed
# `stacks/`/`finished/` tiers are **not** skipped (#85): a file the user sorted into
# one is classified by the tier and, if already exactly in place, dropped by the
# `p == dest` guard in `finished_outputs` so it can't flood the preview.
ROOT_SKIP_DIRS = {
    "lights", "seestar-stacks", "previews",
    "darks", "flats", "biases", "process",
} | set(config.SANDBOX_DIRNAMES)


def sandbox_outputs(target: str, sandbox: Sandbox):
    """Yield (path, kind, dest) for finished outputs inside the workflow's own
    sandbox, skipping the subdirs it declared as never holding fresh output. A
    tier subdir the user saved into classifies its files by that tier (#85)."""
    base = sandbox.dir(target)
    if not base.is_dir():
        return
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        dir_parts = p.relative_to(base).parts[:-1]
        if sandbox.skip_dirs & set(dir_parts):
            continue
        if sandbox.skip_file and sandbox.skip_file(p):
            continue
        c = classify(p, target, tier_of(dir_parts), sandbox.loose_fits_kind)
        if c:
            yield p, c[0], c[1]


def root_outputs(target: str):
    """Yield finished outputs a run left directly in the object dir instead of
    its sandbox — the easy-to-make "I set the working directory to
    Images/<target>/ rather than Images/<target>/siril/" mistake — plus files the
    user sorted straight into `stacks/`/`finished/`."""
    base = config.target_dir(target)
    if not base.is_dir():
        return
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        dir_parts = p.relative_to(base).parts[:-1]
        if ROOT_SKIP_DIRS & set(dir_parts):
            continue
        c = classify(p, target, tier_of(dir_parts))
        if c:
            yield p, c[0], c[1]


def finished_outputs(target: str, sandbox: Sandbox):
    """Every importable finished output for a target under one workflow: its
    sandbox, plus — only if that workflow claims them — any left loose in the
    object dir. A file already sitting *exactly* at its destination (`p == dest`)
    is dropped: it's imported already and the gallery/derived data read it in
    place, so it must not reappear in the import preview (#85)."""
    sources = [lambda t: sandbox_outputs(t, sandbox)]
    if sandbox.scan_root:
        sources.append(root_outputs)
    for source in sources:
        for p, kind, dest in source(target):
            if p == dest:
                continue
            yield p, kind, dest


# ── collision handling ───────────────────────────────────────────────────────

def same_bytes(a: Path, b: Path, chunk: int = 1 << 16) -> bool:
    """True if two files have identical content. Size-checks first (a fast reject),
    then compares chunk-by-chunk with an early exit. Deliberately **not**
    ``filecmp.cmp``, whose stat-signature cache can return a stale verdict when a
    same-size file is rewritten within the mtime resolution. Any OS error → ``False``
    (treat as different)."""
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        with a.open("rb") as fa, b.open("rb") as fb:
            while True:
                ca, cb = fa.read(chunk), fb.read(chunk)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except OSError:
        return False


def resolve_import_dest(dest: Path, src: Path) -> tuple[Path, str]:
    """Where an incoming finished file should land — **keeping both** on a *content*
    collision rather than clobbering or silently skipping. Returns ``(path, disposition)``:

    * ``(dest, "new")``        — nothing at ``dest`` yet; copy there.
    * ``(match, "duplicate")`` — ``src`` is byte-identical to ``dest`` (or an existing
      ``<stem>-N`` sibling); it's already imported → skip (``match`` is the existing copy).
    * ``(free, "renamed")``    — ``dest`` (and any same-named siblings) exist with
      **different** bytes → copy to the first free ``<stem>-N<ext>`` so a re-processed
      render is preserved alongside the old one instead of vanishing into the archive.

    Dedupes against **every** ``<stem>-N`` sibling, so re-running an import doesn't pile
    up ``-2``/``-3`` copies of an already-imported file. Pure read-only (no writes)."""
    if not dest.exists():
        return dest, "new"
    stem, ext = dest.stem, dest.suffix
    cand, n = dest, 1
    while cand.exists():
        if same_bytes(src, cand):
            return cand, "duplicate"
        n += 1
        cand = dest.with_name(f"{stem}-{n}{ext}")
    return cand, "renamed"


# ── plan (read-only) ─────────────────────────────────────────────────────────

@dataclass
class FinishedItem:
    src: str
    name: str
    kind: str            # "render" (→finished/) | "stack" (→stacks/)
    dest: str            # base destination (finished/<name> | stacks/<name>)
    size_bytes: int
    default: bool        # pre-checked in the UI
    already: bool        # a byte-identical copy is already imported → will skip
    note: str = ""       # UI hint, e.g. "kept as M42-2.png" for a re-processed name


@dataclass
class ImportPlan:
    target: str
    items: list                  # list[FinishedItem]
    hero_candidates: list        # render src paths (rasters)
    workflow: str = ""           # which sandbox produced this plan


def has_unimported_output(target: str, sandbox: Sandbox) -> bool:
    """True if there's a finished output not yet imported — including a
    **re-processed file with an existing name but new content** (a plain
    `dest.exists()` check would miss that, the collision footgun)."""
    for p, _kind, dest in finished_outputs(target, sandbox):
        if resolve_import_dest(dest, p)[1] != "duplicate":
            return True
    return False


def scan_finished(target: str, sandbox: Sandbox, should_cancel=None) -> ImportPlan:
    """Read-only: finished outputs for one workflow, classified + routed."""
    items: list[FinishedItem] = []
    heroes: list[str] = []
    for p, kind, dest in sorted(finished_outputs(target, sandbox),
                                key=lambda t: str(t[0])):
        if should_cancel and should_cancel():
            raise Cancelled()
        resolved, disp = resolve_import_dest(dest, p)
        already = disp == "duplicate"          # a byte-identical copy already imported
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        # A re-processed file with an existing name but new content imports under a
        # `<stem>-N` name (both kept) — surface that so it's not a surprise.
        note = f"kept as {resolved.name}" if disp == "renamed" else ""
        items.append(FinishedItem(
            src=str(p), name=p.name, kind=kind, dest=str(dest),
            size_bytes=size, default=not already, already=already, note=note))
        if kind == "render":
            heroes.append(str(p))
    return ImportPlan(target=target, items=items, hero_candidates=heroes,
                      workflow=sandbox.id)


# ── apply (writes finished/ + stacks/, gated cleanup) ────────────────────────

def apply_import(target: str, sandbox: Sandbox, selected_srcs,
                 hero_src: str | None = None, hero_slug: str | None = None,
                 cleanup: str = "archive", progress=None,
                 should_cancel=None) -> dict:
    """Copy the selected finished outputs into the content tiers, optionally set a
    hero, and tidy the sandbox. THE WRITER — callers confirm.

    cleanup: "archive" (default) sweeps each job's intermediates/output/scratch
    into `<job>/archive/<timestamp>/`, keeping whatever the workflow declared so
    the sandbox is ready for another run; "none" leaves it. **Never deletes** and
    never escapes the sandbox. `hero_src=None` keeps the object's current hero."""
    selected = set(selected_srcs)
    plan = scan_finished(target, sandbox)
    chosen = [it for it in plan.items if it.src in selected]
    imported = skipped = 0
    cancelled = False
    hero_name = None
    for i, it in enumerate(chosen, 1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        base_dest = Path(it.dest)
        base_dest.parent.mkdir(parents=True, exist_ok=True)
        # Resolve live (the filesystem may have changed since scan; sequential copies
        # in this loop also update it): identical → skip, different name-collision →
        # land as `<stem>-N` so both are kept.
        final, disp = resolve_import_dest(base_dest, Path(it.src))
        if disp == "duplicate":
            skipped += 1
        else:
            shutil.copyfile(it.src, final)   # bytes only (mirrors ingest)
            imported += 1
        if hero_src and it.src == hero_src:
            hero_name = final.name           # the name it ACTUALLY landed under
        if progress:
            progress(i, len(chosen))

    if cancelled:
        return {"imported": imported, "skipped": skipped,
                "cleaned": "none", "cancelled": True}

    # Hero: the chosen render now lives in finished/ — pin it by the filename it
    # actually landed under (build_images._hero_source matches frontmatter `hero`
    # to the image name; a re-processed render can land as `<stem>-N`, so we can't
    # just use the source name). hero_src=None → leave the current hero.
    if hero_src and hero_slug:
        objects.set_frontmatter_key(
            hero_slug, "hero", hero_name or Path(hero_src).name)

    cleaned = archive_run(target, sandbox) if cleanup == "archive" else "none"
    # Retention runs only where an archive was just written — it is a bound on
    # this sandbox's growth, not a sweep of the library, and "Leave the sandbox
    # as-is" must not delete anything.
    pruned = {"removed": 0, "freed_bytes": 0}
    if cleaned == "archive":
        from . import processing        # local: processing imports us
        pruned = prune_archives(target, sandbox, processing.archive_keep())
    return {"imported": imported, "skipped": skipped, "cleaned": cleaned,
            "pruned": pruned["removed"], "freed_bytes": pruned["freed_bytes"],
            "cancelled": False}


#: The archive dirname `archive_run` writes: `%Y%m%d-%H%M%S`, plus a `-N` suffix
#: when two runs land in the same second.
_ARCHIVE_TS_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")


def prune_archives(target: str, sandbox: Sandbox, keep: int) -> dict:
    """Delete all but the newest `keep` archived runs in each job dir.

    The one place M110 deletes a user's processing history, so it is deliberately
    narrow. Three guards, each earning its place:

    * **`keep <= 0` keeps everything.** Off is the setting's own escape hatch, and
      it must be the safe direction.
    * **Only directories whose *name* parses as our timestamp are candidates.** The
      containment check on a recursive delete — `archive/` is ours, but a user who
      drops a folder of their own in there must not lose it. Same lesson as
      `stacking.clear_scratch`, which only clears a dir holding a real `.seq`.
    * **Ordered by that name, never by mtime.** Ingest and import both copy bytes,
      so mtime is copy time and lies (see the note in `build_processing`); the
      timestamp in the name is what the pipeline actually recorded, and it sorts
      lexically because it is zero-padded and big-endian.

    Returns `{"removed": n, "freed_bytes": n}`. Never escapes the sandbox."""
    if keep <= 0:
        return {"removed": 0, "freed_bytes": 0}
    base = sandbox.dir(target)
    if not base.is_dir():
        return {"removed": 0, "freed_bytes": 0}
    removed = freed = 0
    for jd in sandbox.job_dirs(base):
        arch = jd / "archive"
        if not arch.is_dir():
            continue
        runs = sorted(d for d in arch.iterdir()
                      if d.is_dir() and _ARCHIVE_TS_RE.match(d.name))
        for old in runs[:-keep] if keep < len(runs) else []:
            size = sum(f.stat().st_size for f in old.rglob("*") if f.is_file())
            shutil.rmtree(old)
            removed += 1
            freed += size
    return {"removed": removed, "freed_bytes": freed}


def archive_run(target: str, sandbox: Sandbox) -> str:
    """Move each job's run output/intermediates/scratch into
    `<job>/archive/<timestamp>/`, keeping whatever the workflow's `archive_keep`
    predicate protects. Never deletes; only moves within the sandbox."""
    base = sandbox.dir(target)
    if not base.is_dir():
        return "none"
    job_dirs = sandbox.job_dirs(base)
    ts0 = datetime.now().strftime("%Y%m%d-%H%M%S")
    ts, n = ts0, 2
    while any((jd / "archive" / ts).exists() for jd in job_dirs):
        ts, n = f"{ts0}-{n}", n + 1
    moved = 0
    for jd in job_dirs:
        dest = jd / "archive" / ts
        for child in list(jd.iterdir()):
            if sandbox.archive_keep(child):
                continue
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(dest / child.name))
            moved += 1
    return "archive" if moved else "none"

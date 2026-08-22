"""AstroWizard round-trip: hand a stack over, then import the finish back.

The mirror image of `siril.py`, and deliberately much thinner — everything that
is not specific to this workflow lives in `roundtrip.py`.

**This sandbox is the *finishing* workflow, not one app.** Two tools work in it and
there are two ways a master gets in:

* `stacking.apply_handoff` hardlinks a finished Siril stack into
  `Images/<target>/astrowizard/` with a `.src.json` provenance sidecar; or
* **StackingWizard** stacks in place. It has no CLI at all and finds frames by
  walking the folder it is pointed at, so the frames have to *be* there — hence
  `astrowizard/lights/`, a hardlink tree like Siril's. Pointed at the sandbox it
  writes `<object>_wizardstack.fits` into the root by itself (no dialog), which is
  exactly where AstroWizard then picks it up.

Either way the master is this sandbox's **input**, and `archive_keep` spares it.
That is what lets one directory hold both halves without re-running the argument
that separated `siril/` from `astrowizard/`: the concern there was that a cheap,
iterated finish would archive an expensive, stable stack every time it was redone.
It cannot here, because the stack is never treated as output.

Three things make this sandbox different from Siril's, and they are the entire
contents of the descriptor below:

* **It claims nothing outside itself** (`scan_root=False`). Siril scans the object
  dir too, to recover output from a mis-pointed working directory. AstroWizard
  must not: two workflows both claiming loose files is how one tool's importer
  ends up offering the other's exports, which is the failure `roundtrip`'s
  sandbox-skipping exists to prevent. AstroWizard saves into the folder it was
  pointed at, so there is nothing to recover.
* **No job split** (`split_jobs=False`). Filters are combined *before* a finish,
  not during one, so there is one job and it is the sandbox root.
* **The handoff survives the archive sweep.** It is this workflow's *input* — the
  equivalent of Siril's `lights/` — so archiving it would leave the sandbox unable
  to re-finish without another handoff. It has no fixed name, so it is recognised
  by its provenance sidecar rather than by a filename pattern, which is the same
  reason classification here is directory-first: AstroWizard's exports go through
  a native save dialog and the *user* types the name.

**Why the sweep matters more here than for Siril.** AstroWizard autosaves one file
per user action: a measured M27 finish left 26 files / 2.02 GB of `_AW1_init` …
`_AW24_rescreen` beside the two exports. AstroWizard means to delete them — they
back its undo stack — but only does so from its `WM_DELETE_WINDOW` handler, which
macOS's Cmd+Q never fires, so in practice they are left behind (and a crash would
leave them regardless). Nothing under `astrowizard/` is excluded from backup (`config.SANDBOX_LINKED_INPUTS` gives
it `frozenset()`, correctly — none of it is a hardlink duplicate), and the mirrored
backup format dedups by *path*, so an un-swept chain lands in full in every future
snapshot. Importing the finish is what triggers the sweep, so the round-trip being
closed is also what keeps the sandbox's disk cost honest.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config, roundtrip

#: Sidecar written by `stacking.apply_handoff` beside the handed-off stack.
SRC_SIDECAR_SUFFIX = ".src.json"


def is_handoff(child: Path) -> bool:
    """True for the handed-off stack, or its provenance sidecar.

    Identified by the sidecar, never by the filename: the stack is named by
    whatever produced it and the user may rename it, but `apply_handoff` always
    writes `<filename>.src.json` beside it. That sidecar is also what tells a
    later reader which stack a finish came from, so the two travel together."""
    if child.name.endswith(SRC_SIDECAR_SUFFIX):
        return True
    return child.with_name(child.name + SRC_SIDECAR_SUFFIX).exists()


#: AstroWizard's autosave chain: `<stem>_AW<n>_<step>.<ext>`, one file per user
#: action (`_AW1_init`, `_AW2_crop`, … `_AW24_rescreen`).
_AUTOSAVE_RE = re.compile(r"_AW\d+_")


def is_autosave(child: Path) -> bool:
    """True for a file AstroWizard wrote itself as a per-step snapshot.

    The ROADMAP note that "AstroWizard's output cannot be recognised by filename"
    is about its **exports** — those go through a native save dialog and the user
    types the name, which is why classification is directory-first. Its
    *autosaves* are the opposite: machine-named, and the only reliably matchable
    thing in the sandbox.

    Recognising them is not cosmetic. The step chain is mostly FITS, which the
    filename vocabulary already drops for carrying no finished hint — but it also
    emits rasters (`…_AW10_str_dee_sn_in.tif`), and a loose raster is a
    deliverable by default with no hint required. On a real M27 finish that put a
    41 MB working TIFF in the import preview alongside the two real exports."""
    return bool(_AUTOSAVE_RE.search(child.name))


def _not_output(child: Path) -> bool:
    """Files in the sandbox that are never importable output: the master this
    workflow works *from* (handed off, or stacked here by StackingWizard), and
    AstroWizard's per-step autosaves."""
    return is_handoff(child) or is_master(child) or is_autosave(child)


#: StackingWizard's auto-written stack: `<object>_wizardstack.fits`, or
#: `<object>_combined_wizardstack.fits` when it has combined several nights.
MASTER_TOKEN = "_wizardstack"


def is_master(child: Path) -> bool:
    """True for a stack StackingWizard wrote into this sandbox.

    Recognised by name because there is nothing else to go on — StackingWizard
    writes no sidecar, and unlike `is_handoff` we did not put the file there. The
    name is machine-generated (its stack worker builds it), not user-typed, which
    is what makes matching it honest rather than a guess.

    **An autosave is not a master**, even though it looks like one: AstroWizard
    names each step after the file it opened, so the whole `_AW<n>_` chain carries
    the master's stem. Without this the sweep spared all twelve of them and the
    working area never got tidied."""
    if is_autosave(child):
        return False
    return (MASTER_TOKEN in child.stem.lower()
            and child.suffix.lower() in (".fits", ".fit"))


def _archive_keep(child: Path) -> bool:
    """What survives the sweep: prior archived runs, the linked frames, and
    whichever master this run works from — handed off, or stacked in place.

    Sparing the master is the whole reason two tools can share one directory; see
    the module docstring."""
    return (child.name in ("archive", LIGHTS_DIRNAME)
            or is_handoff(child) or is_master(child))


#: Where StackingWizard finds frames. Literally `lights/`, like Siril's, because
#: the tool walks whatever folder it is given and sorts frames by header.
LIGHTS_DIRNAME = "lights"

SANDBOX = roundtrip.Sandbox(
    id="astrowizard",
    skip_dirs=frozenset({"archive", LIGHTS_DIRNAME}),
    scan_root=False,
    split_jobs=False,
    archive_keep=_archive_keep,
    loose_fits_kind="render",
    skip_file=_not_output,
)


def lights_dir(target: str) -> Path:
    """The sandbox's frame tree — `Images/<target>/astrowizard/lights/`."""
    return config.astrowizard_dir(target) / LIGHTS_DIRNAME


def prepare_lights(target: str, should_cancel=None) -> int:
    """Hardlink the target's raw subs into the sandbox. Returns how many are there.

    Add-only and idempotent, like Siril's prep: new subs join an existing tree and
    nothing is ever removed or rewritten. Hardlinks, so a second frame tree beside
    `siril/lights/` costs directory entries and no image data — and `lights` is
    declared in `config.SANDBOX_LINKED_INPUTS`, so backup skips it rather than
    storing every sub twice."""
    src = config.lights_dir(target)
    if not src.is_dir():
        return 0
    dst = lights_dir(target)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.iterdir()):
        if should_cancel and should_cancel():
            break
        if f.is_file() and config.is_light_frame(f.name):
            roundtrip.link_or_copy(str(f), str(dst / f.name))
            n += 1
    return n


def autoprep(targets, should_cancel=None, only_missing: bool = False) -> dict:
    """Set up finishing sandboxes for the given targets — idempotent, Qt-free.

    Mirrors `siril.autoprep`'s guards for the same reasons: a target with
    un-imported output is left alone (never disturb work in progress), and
    `only_missing=True` skips any target that already has a sandbox, so the
    refresh-time backfill creates only the absent ones.

    Runs only while AstroWizard is ticked in Preferences — `run_autoprep` consults
    `enabled_workflow_ids()` — which is what makes that checkbox mean the same
    thing for both workflows: prepare a working folder for this one."""
    prepared, skipped = [], []
    for target in targets:
        if should_cancel and should_cancel():
            break
        if only_missing and config.astrowizard_dir(target).exists():
            continue
        if has_unimported_output(target):
            skipped.append(target)
            continue
        if prepare_lights(target, should_cancel=should_cancel):
            prepared.append(target)
    return {"prepared": prepared, "skipped": skipped}


def has_unimported_output(target: str) -> bool:
    """True if AstroWizard left a finish that isn't imported yet."""
    return roundtrip.has_unimported_output(target, SANDBOX)


def scan_finished(target: str, should_cancel=None) -> roundtrip.ImportPlan:
    """Read-only: the exports sitting in the AstroWizard sandbox, classified and
    routed. The handed-off stack is not among them — it is an input, and its
    bytes are already in `stacks/` where the handoff hardlinked from."""
    return roundtrip.scan_finished(target, SANDBOX, should_cancel)


def apply_import(target: str, selected_srcs, hero_src: str | None = None,
                 hero_slug: str | None = None, cleanup: str = "archive",
                 progress=None, should_cancel=None) -> dict:
    """Copy the selected exports into the content tiers, optionally set a hero,
    and sweep the run into `astrowizard/archive/<ts>/`. THE WRITER — callers
    confirm."""
    return roundtrip.apply_import(
        target, SANDBOX, selected_srcs, hero_src=hero_src, hero_slug=hero_slug,
        cleanup=cleanup, progress=progress, should_cancel=should_cancel)


def working_dirs(target: str) -> list[Path]:
    """The directory to point AstroWizard at — the sandbox root, or empty when no
    handoff has been made. Unlike Siril there is never more than one: filters are
    combined before a finish, not during it."""
    base = config.astrowizard_dir(target)
    return [base] if base.is_dir() else []

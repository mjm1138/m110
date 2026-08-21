"""AstroWizard round-trip: hand a stack over, then import the finish back.

The mirror image of `siril.py`, and deliberately much thinner — everything that
is not specific to this workflow lives in `roundtrip.py`. There is no prepare
step to speak of: `stacking.apply_handoff` hardlinks a finished stack into
`Images/<target>/astrowizard/` with a `.src.json` provenance sidecar, and that is
the whole of "handing work in". What is left is the return leg.

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
    """Files in the sandbox that are never importable output: the workflow's own
    input, and the tool's per-step autosaves."""
    return is_handoff(child) or is_autosave(child)


def _archive_keep(child: Path) -> bool:
    """What survives the sweep: prior archived runs, and this run's input."""
    return child.name == "archive" or is_handoff(child)


SANDBOX = roundtrip.Sandbox(
    id="astrowizard",
    skip_dirs=frozenset({"archive"}),
    scan_root=False,
    split_jobs=False,
    archive_keep=_archive_keep,
    loose_fits_kind="render",
    skip_file=_not_output,
)


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

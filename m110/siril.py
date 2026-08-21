"""Processing-prep round-trip: prepare a Siril sandbox, then import the result.

**Prepare-and-guide, not control** — M110 never runs Siril. The round-trip:

  prepare → (you process in Siril) → import finished work → clean up

* **Prepare** arranges a *contained* Siril sandbox `Images/<target>/siril/` with a
  literal `lights/` (Siril needs that exact name), the Naztronomy preset in
  `presets/` (auto-loaded), and `next-steps.md`. Lights are placed by **hardlink**
  (no extra disk; reversible). Mixed-filter targets get one job per filter
  (`siril/<FILTER>/`). Set up **automatically on ingest** (`autoprep`).
* Siril runs *inside* the sandbox (it makes its own `process/`, scatters
  intermediates, writes output) — so it never touches the clean content tiers.
* **Import** detects the finished outputs in the sandbox and copies renders →
  `finished/` and the chosen stack → `stacks/`, optionally sets a hero, and
  **cleans up** the sandbox (gated; scoped to `siril/` only).

Mirrors `ingest`'s read-only-plan → gated-apply contract.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config, roundtrip

_log = logging.getLogger("m110")

# Filter token in a Seestar light filename:
#   Light_<object>_<exp>s_<FILTER>_<YYYYMMDD>-<HHMMSS>.fit
_FILTER_RE = re.compile(r"_(LP|IRCUT|UV|DARK)_\d{8}-\d{6}\.fit$", re.IGNORECASE)
OTHER_FILTER = "OTHER"

PRESET_NAME = "naztronomy_smart_scope_presets.json"


# One cancellation type across prep and import: `roundtrip` raises it from the
# shared scan, prep raises it directly, and every existing caller catches
# `siril.PrepCancelled`. Aliasing rather than subclassing keeps those catches
# working against the shared raise — a subclass would not.
PrepCancelled = roundtrip.Cancelled


def filter_of(filename: str) -> str:
    m = _FILTER_RE.search(filename)
    return m.group(1).upper() if m else OTHER_FILTER


# ── Naztronomy preset ────────────────────────────────────────────────────────

def drizzle_for(usable_frames: int) -> tuple[bool, float, float]:
    """(drizzle, amount, pixel_fraction) for a usable frame count.

    Ported from workflows/siril_drizzle_guide.md's decision tree:
      <100 → off; 100–300 → 1.5/1.0; 300–500 → 1.5/0.7; ≥500 → 2.0/0.5.
    """
    if usable_frames < 100:
        return False, 1.0, 1.0
    if usable_frames < 300:
        return True, 1.5, 1.0
    if usable_frames < 500:
        return True, 1.5, 0.7
    return True, 2.0, 0.5


def filter_quality_for(usable_frames: int) -> tuple[bool, float]:
    """(filters_on, quality_pct) for the star-quality reject filters, by frame
    count. More frames ⇒ afford to be pickier (keep a smaller top %); below the
    drizzle floor there aren't enough to filter.
      <100 → off; 100–500 → 98%; 501–1500 → 95%; >1500 → 90%.
    Applied to all four percentile filters (roundness / fwhm / star_count / bg)."""
    if usable_frames < 100:
        return False, 98.0
    if usable_frames <= 500:
        return True, 98.0
    if usable_frames <= 1500:
        return True, 95.0
    return True, 90.0


def default_preset(usable_frames: int,
                   filter_label: str = "No Filter (Broadband)",
                   darks: bool = False, flats: bool = False,
                   biases: bool = False) -> dict:
    """A sensible *starting* Naztronomy Smart Scope preset (refined in the GUI).
    Constant keys are the empirical modal default across the reference presets;
    drizzle (`drizzle_for`) and the star-quality filters (`filter_quality_for`)
    are set by `usable_frames`. The `darks`/`flats`/`biases` toggles are turned on
    when the sandbox has those calibration frames hardlinked in (#57), so the
    script calibrates by default when the frames are present."""
    drizzle, amount, pixel_fraction = drizzle_for(usable_frames)
    filters_on, quality = filter_quality_for(usable_frames)
    return {
        "telescope": "ZWO Seestar S50",
        "filter": filter_label,
        "darks": darks,
        "flats": flats,
        "biases": biases,
        "cleanup": True,
        "batch_size": 25000,
        "bg_extract": True,
        "drizzle": drizzle,
        "drizzle_amount": amount,
        "pixel_fraction": pixel_fraction,
        "filters": filters_on,
        "roundness": quality,
        "fwhm": quality,
        "star_count_filter": quality,
        "bg_filter": quality,
        "feather": False,
        "feather_amount": 20,
        "stack_weighting": True,
        "weighting_method": "Weighted FWHM",
        "spcc": False,
        "compression": False,
    }


# One representative frame count per (drizzle × filter) bucket. Because the
# default preset is a step function of frame count, an *unedited* preset must
# equal the canonical default at one of these — so this set is exactly "every
# preset M110 could have generated" (for a given filter label). Update if the
# `drizzle_for` / `filter_quality_for` breakpoints change.
_DEFAULT_PRESET_REPS = (50, 200, 400, 800, 2000)


def is_default_preset(preset: dict) -> bool:
    """True if `preset` is an untouched M110-generated default (for its own
    filter label and calibration toggles) at *some* frame count — i.e. the user
    hasn't hand-edited it. Lets `apply_prep` re-tune a pristine preset as the
    frame count grows while never clobbering values the user changed. The
    calibration toggles are read back off the preset so a default generated *with*
    calibration (#57) still reads as pristine."""
    label = preset.get("filter", "No Filter (Broadband)")
    darks = bool(preset.get("darks", False))
    flats = bool(preset.get("flats", False))
    biases = bool(preset.get("biases", False))
    return any(preset == default_preset(n, label, darks, flats, biases)
               for n in _DEFAULT_PRESET_REPS)


# ── prepare: plan (read-only) ────────────────────────────────────────────────

@dataclass
class PrepJob:
    filt: str                       # filter token, or "" for the single-filter sandbox root
    job_dir: str                    # working dir Siril opens (has lights/ + presets/)
    preset_path: str
    links: list = field(default_factory=list)  # (src, dst) hardlink ops
    preset: dict = field(default_factory=dict)
    usable_frames: int = 0


@dataclass
class PrepPlan:
    target: str
    siril_dir: str
    jobs: list                      # list[PrepJob]
    star_removal: bool
    total_lights: int = 0
    total_bytes: int = 0
    multi_filter: bool = False
    filters: list = field(default_factory=list)
    # (src, dst) hardlinks for darks/flats/biases → the sandbox root (calibration
    # is shared across filters). Empty when the target has no calibration frames.
    calib_links: list = field(default_factory=list)
    calib_kinds: list = field(default_factory=list)   # ["darks", …] present


def _lights(target: str) -> list[Path]:
    """Raw subs in the target's ``lights/`` — only genuine light frames (the
    shared `config.is_light_frame`). Any stray processing by-product that
    happens to sit in ``lights/`` is ignored, so it can never
    be misread as an extra filter (the phantom ``OTHER`` job) or padded into a
    stack. Defense-in-depth partner to the import guard that keeps such files
    out of ``lights/`` in the first place."""
    d = config.lights_dir(target)
    if not d.is_dir():
        return []
    return sorted(f for f in d.iterdir()
                  if f.is_file() and config.is_light_frame(f.name))


# The calibration tiers, in the order the Naztronomy preset toggles them, and the
# config helper for each source dir.
_CALIB_TIERS = (("darks", config.darks_dir), ("flats", config.flats_dir),
                ("biases", config.biases_dir))


def _calib_frames(target: str) -> dict[str, list[Path]]:
    """Calibration frames (`.fit`/`.fits`) present for `target`, keyed by tier
    (`darks`/`flats`/`biases`); tiers with no frames are omitted."""
    out: dict[str, list[Path]] = {}
    for kind, dir_fn in _CALIB_TIERS:
        d = dir_fn(target)
        if not d.is_dir():
            continue
        frames = sorted(f for f in d.iterdir()
                        if f.is_file() and config.is_fits_file(f.name))
        if frames:
            out[kind] = frames
    return out


def plan_prep(target: str, usable_frames: int | None = None,
              star_removal: bool = False, should_cancel=None) -> PrepPlan:
    """Read-only plan: lay each filter's lights into a literal `lights/` inside a
    contained Siril sandbox, and hardlink any darks/flats/biases beside them so a
    Siril project imported with calibration is reproduced ready to calibrate (#57).
    `usable_frames` (post-rejection, single-filter only) overrides the raw count
    for the drizzle preset. Reads only."""
    lights = _lights(target)
    # Calibration is shared across filters → hardlinked once at the sandbox root
    # (`siril/darks`, `siril/flats`, `siril/biases`). For a single-filter target the
    # sandbox root *is* the job dir, so they sit right beside `lights/`.
    calib = _calib_frames(target)
    calib_kinds = list(calib)
    calib_links = [(str(f), str(config.siril_dir(target) / kind / f.name))
                   for kind, frames in calib.items() for f in frames]
    by_filter: dict[str, list[Path]] = {}
    total_bytes = 0
    for f in lights:
        if should_cancel and should_cancel():
            raise PrepCancelled()
        by_filter.setdefault(filter_of(f.name), []).append(f)
        try:
            total_bytes += f.stat().st_size
        except OSError:
            pass

    filters = sorted(by_filter)
    multi = len(filters) > 1
    jobs: list[PrepJob] = []
    for filt in filters:
        files = by_filter[filt]
        job_dir = config.siril_job_dir(target, filt if multi else None)
        # single-filter target may pass a post-rejection override
        job_usable = (usable_frames if (usable_frames is not None and not multi)
                      else len(files))
        links = [(str(f), str(job_dir / "lights" / f.name)) for f in files]
        jobs.append(PrepJob(
            filt=filt if multi else "",
            job_dir=str(job_dir),
            preset_path=str(job_dir / "presets" / PRESET_NAME),
            links=links,
            preset=default_preset(job_usable,
                                  darks="darks" in calib,
                                  flats="flats" in calib,
                                  biases="biases" in calib),
            usable_frames=job_usable,
        ))

    return PrepPlan(
        target=target,
        siril_dir=str(config.siril_dir(target)),
        jobs=jobs,
        star_removal=star_removal,
        total_lights=len(lights),
        total_bytes=total_bytes,
        multi_filter=multi,
        filters=filters,
        calib_links=calib_links,
        calib_kinds=calib_kinds,
    )


# ── prepare: apply (writes the sandbox) ──────────────────────────────────────

def _link_or_copy(src: str, dst: str) -> None:
    """Hardlink src→dst; byte-copy fallback if linking isn't possible. Idempotent
    and race-safe: if dst already exists (a concurrent or prior prep linked it),
    leave it — never copyfile onto the same inode (which raises SameFileError)."""
    try:
        os.link(src, dst)
    except FileExistsError:
        return                       # already linked (prior/concurrent prep) — fine
    except OSError:
        if not os.path.exists(dst):  # linking unsupported (cross-device, …) → copy
            shutil.copyfile(src, dst)


def _next_steps_md(plan: PrepPlan) -> str:
    lines = [
        f"# Processing {plan.target} — Siril sandbox",
        "",
        "M110 set this up so Siril has a clean, self-contained working folder "
        "(your content tiers stay tidy). M110 does not run Siril for you.",
        "",
        f"> ⚠ **Set Siril's working directory to `{plan.siril_dir}` (or a job "
        "folder below) — not the folder above it.** Output saved above this "
        "folder won't be found when you import. (If you did already, no harm: "
        "M110 also scans the object folder as a fallback.)",
        "",
        "## Jobs",
    ]
    for job in plan.jobs:
        p = job.preset
        drizz = (f"drizzle {p['drizzle_amount']}× / pixel {p['pixel_fraction']}"
                 if p["drizzle"] else "no drizzle (1.0×)")
        where = job.job_dir
        label = job.filt or "all frames"
        lines.append(f"- **{label}** → open Siril in `{where}` "
                     f"({len(job.links)} subs, {drizz})")
    if plan.calib_kinds:
        lines += [
            "",
            f"Calibration frames were hardlinked in ({', '.join(plan.calib_kinds)}/ "
            "at the sandbox root) and the preset's matching toggles are on.",
        ]
    lines += [
        "",
        "## Steps",
        "1. Open **Siril** with a job folder above as the working directory "
        "(it contains a literal `lights/` and a `presets/` the script auto-loads). "
        "Tip: in M110, **Process in Siril** does this for you.",
        "2. Run the **Naztronomy Smart Telescope Processing** script → Load preset.",
        "3. Save your stack and finished render anywhere in this sandbox.",
        "4. Back in M110, reopen this object and click **Import finished work** — "
        "M110 brings your renders into the gallery, the stack into `stacks/`, and "
        "offers to clean the sandbox up.",
        "5. **Quit Siril before processing the next object.** M110 sets the working "
        "directory only when Siril *starts* — if Siril is already open, launching it "
        "for another object won't switch folders, and you'd process in the wrong place.",
        "",
        "_The preset is a starting point — refine it in the script's GUI._",
    ]
    return "\n".join(lines) + "\n"


def _read_preset(path: Path) -> dict:
    """On-disk preset as a dict, or {} if missing/unreadable (→ treated as
    non-default, so `apply_prep` preserves rather than clobbers an odd file)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_prep(plan: PrepPlan, progress=None, should_cancel=None) -> dict:
    """Create the sandbox, hardlink lights per job (+ shared darks/flats/biases at
    the sandbox root), write presets + next-steps. THE WRITER — callers confirm (or
    it runs via `autoprep` after ingest). Idempotent: existing links are skipped."""
    ops = [(src, dst) for job in plan.jobs for (src, dst) in job.links]
    ops += list(plan.calib_links)          # calibration → sandbox root (shared)
    linked = skipped = 0
    cancelled = False
    total = len(ops)
    for i, (src, dst) in enumerate(ops, 1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        dp = Path(dst)
        dp.parent.mkdir(parents=True, exist_ok=True)
        if dp.exists():
            skipped += 1
        else:
            _link_or_copy(src, dst)
            linked += 1
        if progress:
            progress(i, total)

    if not cancelled:
        for job in plan.jobs:
            pp = Path(job.preset_path)
            pp.parent.mkdir(parents=True, exist_ok=True)
            # Re-tune only a pristine (unedited) preset as the frame count grows;
            # never clobber a preset the user has hand-edited. First write always.
            if not pp.exists() or is_default_preset(_read_preset(pp)):
                pp.write_text(json.dumps(job.preset, indent=4) + "\n", encoding="utf-8")
        Path(plan.siril_dir).mkdir(parents=True, exist_ok=True)
        # next-steps.md is app guidance (not user-owned) — always refreshed so the
        # recommended drizzle/filters for the current count stay visible.
        (Path(plan.siril_dir) / "next-steps.md").write_text(_next_steps_md(plan), encoding="utf-8")

    return {"linked": linked, "skipped": skipped, "cancelled": cancelled}


def autoprep(targets, should_cancel=None, only_missing: bool = False) -> dict:
    """Set up sandboxes for the given targets — idempotent, and **skips** any
    target whose sandbox already holds un-imported finished output (never
    disturbs in-progress/finished processing). Qt-free.

    `only_missing=True` additionally skips any target that already has a `siril/`
    sandbox — so a refresh-time backfill creates only the absent ones and never
    rewrites an existing (possibly hand-edited) preset. The default (ingest) path
    re-runs the full prep so new lights get linked and the preset tracks the
    current frame count."""
    prepared, skipped = [], []
    for target in targets:
        if should_cancel and should_cancel():
            break
        if not _lights(target):
            continue
        if only_missing and config.siril_dir(target).exists():
            continue
        if has_unimported_output(target):
            skipped.append(target)
            continue
        plan = plan_prep(target, should_cancel=should_cancel)
        if plan.total_lights:
            apply_prep(plan, should_cancel=should_cancel)
            prepared.append(target)
    return {"prepared": prepared, "skipped": skipped}


def _sandbox_lights_dirs(base: Path) -> list[Path]:
    """Every ``lights/`` inside a sandbox — the root's *and* each per-filter job's.

    Deliberately wider than `_job_dirs`, which returns the per-filter dirs *instead
    of* the root once a target splits. A target that became multi-filter leaves its
    earlier single-filter ``siril/lights/`` behind (BUGS #28), and a stale job dir is
    exactly where a frame the user thinks they excluded would go on being stacked."""
    out = [base / "lights"] if (base / "lights").is_dir() else []
    out += [p / "lights" for p in sorted(base.iterdir())
            if p.is_dir() and (p / "lights").is_dir()]
    return out


def prune_rejected(target: str) -> dict:
    """Drop sandbox hardlinks for subs the user has since moved to ``rejected/`` (#110).

    `apply_prep` is add-only, so a sub rejected *after* prep keeps its hardlink in
    ``siril/[<FILTER>/]lights/`` and Siril goes on stacking it — without this the
    exclusion would only ever work on a target that had never been prepped, i.e. on
    none of the targets a user actually wants it for.

    Narrow on purpose, because the sandbox's posture is **never deletes**:

    * only files directly inside a job's ``lights/`` are considered — never the
      archive, the presets, the calibration links, or anything else the user put there;
    * a file is unlinked **only** when that same name is present in ``rejected/`` —
      the store still holds the frame and we are dropping a redundant link, not data.
      A sub that merely vanished from ``lights/`` is left alone and counted as an
      orphan: it may be the *last* copy (on a filesystem where `_link_or_copy` fell
      back to a byte copy it certainly is);
    * a target holding un-imported finished output is skipped whole — the same guard
      `autoprep` uses, so an in-progress run is never disturbed.
    """
    base = config.siril_dir(target)
    if not base.is_dir():
        return {"pruned": 0, "orphans": 0, "skipped": False}
    if has_unimported_output(target):
        return {"pruned": 0, "orphans": 0, "skipped": True}

    rdir = config.rejected_dir(target)
    rejected = ({f.name for f in rdir.iterdir() if f.is_file()}
                if rdir.is_dir() else set())
    live = {f.name for f in _lights(target)}
    pruned = orphans = 0
    for ldir in _sandbox_lights_dirs(base):
        for f in sorted(ldir.iterdir()):
            if not f.is_file() or not config.is_light_frame(f.name) or f.name in live:
                continue
            if f.name in rejected:
                f.unlink()
                pruned += 1
            else:
                orphans += 1
    if pruned or orphans:
        _log.info("prune_rejected %s: unlinked %d rejected, left %d orphan(s)",
                  target, pruned, orphans)
    return {"pruned": pruned, "orphans": orphans, "skipped": False}

# ── import: the shared round-trip, wearing Siril's sandbox ───────────────────
#
# Detection, classification, collision handling, the import copy and the archive
# sweep all live in `roundtrip.py` — none of that was ever Siril-specific, and a
# second workflow (AstroWizard, ROADMAP 14b) needs exactly the same behaviour.
# What is Siril-specific is the descriptor below, and it is the whole difference:
# a sandbox holding literal `lights/` hardlinks, a Naztronomy preset and Siril's
# own `process/` scratch; per-filter job dirs; and a willingness to claim output
# left loose in the object dir, which is the mis-pointed-working-directory
# recovery (`-d` set to `Images/<target>/` instead of `Images/<target>/siril/`).
#
# The names below are re-exported rather than renamed at the call sites: the UI,
# `build_derived` and the test-suite all reach for `siril.scan_finished` /
# `siril.apply_import` / `siril.has_unimported_output`, and an extraction that is
# behaviour-preserving should not also be an API break.

# Kept in each job dir on cleanup, so the sandbox is ready for another run.
_ARCHIVE_KEEP = {"lights", "darks", "flats", "biases",
                 "presets", "archive", "next-steps.md"}

# Sandbox subdirs that never hold fresh, importable output: the hardlinked
# inputs, Siril's scratch, the preset, and prior archived runs.
_SKIP_DIRS = {"lights", "process", "presets", "archive"}

SANDBOX = roundtrip.Sandbox(
    id="siril",
    skip_dirs=frozenset(_SKIP_DIRS),
    scan_root=True,
    split_jobs=True,
    archive_keep=lambda child: child.name in _ARCHIVE_KEEP,
)

# Re-exports so `siril.X` keeps working for every existing caller and test.
FinishedItem = roundtrip.FinishedItem
ImportPlan = roundtrip.ImportPlan
_ROOT_SKIP_DIRS = roundtrip.ROOT_SKIP_DIRS
_OUTPUT_TIERS = roundtrip._OUTPUT_TIERS
_tier_of = roundtrip.tier_of
_classify = roundtrip.classify
_same_bytes = roundtrip.same_bytes
_resolve_import_dest = roundtrip.resolve_import_dest


def _sandbox_outputs(target: str):
    return roundtrip.sandbox_outputs(target, SANDBOX)


def _root_outputs(target: str):
    return roundtrip.root_outputs(target)


def _finished_outputs(target: str):
    return roundtrip.finished_outputs(target, SANDBOX)


def has_unimported_output(target: str) -> bool:
    """True if Siril left a finished output that isn't imported yet."""
    return roundtrip.has_unimported_output(target, SANDBOX)


def scan_finished(target: str, should_cancel=None) -> roundtrip.ImportPlan:
    """Read-only: finished outputs in the Siril sandbox (and loose in the object
    dir), classified + routed."""
    return roundtrip.scan_finished(target, SANDBOX, should_cancel)


def apply_import(target: str, selected_srcs, hero_src: str | None = None,
                 hero_slug: str | None = None, cleanup: str = "archive",
                 progress=None, should_cancel=None) -> dict:
    """Copy the selected finished outputs into the content tiers, optionally set
    a hero, and tidy the Siril sandbox. THE WRITER — callers confirm."""
    return roundtrip.apply_import(
        target, SANDBOX, selected_srcs, hero_src=hero_src, hero_slug=hero_slug,
        cleanup=cleanup, progress=progress, should_cancel=should_cancel)


def _job_dirs(base: Path) -> list[Path]:
    """The working dirs to tidy: per-filter subdirs (each has lights/) if mixed,
    else the sandbox root."""
    return SANDBOX.job_dirs(base)


def working_dirs(target: str) -> list[Path]:
    """The Siril working directories to offer for a target: the per-filter job
    dirs if the sandbox is split by filter, else the sandbox root. Empty when no
    sandbox exists yet. This is what "Process in Siril" points `-d` at."""
    base = config.siril_dir(target)
    if not base.is_dir():
        return []
    return _job_dirs(base)


def _archive_run(target: str) -> str:
    return roundtrip.archive_run(target, SANDBOX)

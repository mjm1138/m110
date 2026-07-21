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
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, hints, objects

# Filter token in a Seestar light filename:
#   Light_<object>_<exp>s_<FILTER>_<YYYYMMDD>-<HHMMSS>.fit
_FILTER_RE = re.compile(r"_(LP|IRCUT|UV|DARK)_\d{8}-\d{6}\.fit$", re.IGNORECASE)
OTHER_FILTER = "OTHER"

PRESET_NAME = "naztronomy_smart_scope_presets.json"

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


class PrepCancelled(Exception):
    """Raised inside plan/apply when the caller's should_cancel() turns true."""


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


# ── guidance (bundled playbooks) ─────────────────────────────────────────────

_CORE_GUIDANCE = [
    "siril_processing_workflow",
    "siril_drizzle_guide",
    "siril_psf_guide",
    "siril_color_saturation",
    "seestar_s50_imaging_guide",
]


def guidance_ids() -> list[str]:
    if not config.GUIDANCE_DIR.is_dir():
        return []
    return sorted(p.stem for p in config.GUIDANCE_DIR.glob("*.md"))


def guidance_path(doc_id: str) -> Path:
    return config.GUIDANCE_DIR / f"{doc_id}.md"


def guidance_title(doc_id: str) -> str:
    p = guidance_path(doc_id)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                return line.lstrip("# ").strip()
    return doc_id.replace("_", " ").title()


def guidance_for(filters_present: set[str], star_removal: bool) -> list[str]:
    available = set(guidance_ids())
    ids = [d for d in _CORE_GUIDANCE if d in available]
    if "LP" in filters_present and "siril_lp_narrowband_galaxy_blend" in available:
        ids.append("siril_lp_narrowband_galaxy_blend")
    return ids


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
    guidance: list
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
        guidance=guidance_for(set(filters), star_removal),
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


# ── import: detect + plan (read-only) ────────────────────────────────────────

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


def _classify(path: Path, target: str):
    """(kind, dest) for a sandbox file, or None if it's not a finished output."""
    name = path.name
    if "_thn." in name or name == "lights.fit":
        return None
    if hints.is_intermediate_name(name):
        return None
    ext = path.suffix.lower()
    if ext in _RASTER_EXTS:
        return "render", config.finished_dir(target) / name
    if ext in _FIT_EXTS and hints.is_finished_name(name):
        return "stack", config.stacks_dir(target) / name
    return None


# Sandbox subdirs that never hold fresh, importable output: the hardlinked
# inputs, Siril's scratch, the preset, and prior archived runs.
_SKIP_DIRS = {"lights", "process", "presets", "archive"}

# Object-root subdirs skipped when scanning Images/<target>/ for output a run
# left there directly (the mis-pointed-working-directory case, #): the managed
# content tiers (already-imported or raw inputs), and `siril/` — which
# `_sandbox_outputs` already walks — plus Siril's own `process/` scratch.
_ROOT_SKIP_DIRS = {
    "lights", "stacks", "finished", "seestar-stacks", "previews",
    "darks", "flats", "biases", "siril", "process",
}


def _sandbox_outputs(target: str):
    """Yield (path, kind, dest) for finished outputs in the sandbox, skipping
    inputs, Siril scratch, presets, and archived prior runs."""
    base = config.siril_dir(target)
    if not base.is_dir():
        return
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if _SKIP_DIRS & set(p.relative_to(base).parts[:-1]):
            continue
        c = _classify(p, target)
        if c:
            yield p, c[0], c[1]


def _root_outputs(target: str):
    """Yield finished outputs a run left directly in the object dir instead of
    the sandbox — the easy-to-make "I set Siril's working directory to
    Images/<target>/ rather than Images/<target>/siril/" mistake. Skips the
    managed tiers, raw inputs, and the sandbox itself (already walked)."""
    base = config.target_dir(target)
    if not base.is_dir():
        return
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if _ROOT_SKIP_DIRS & set(p.relative_to(base).parts[:-1]):
            continue
        c = _classify(p, target)
        if c:
            yield p, c[0], c[1]


def _finished_outputs(target: str):
    """Every importable finished output for a target: the siril/ sandbox plus
    any a run left loose in the object dir. No src is yielded twice — the root
    walk skips siril/, which the sandbox walk owns."""
    yield from _sandbox_outputs(target)
    yield from _root_outputs(target)


def _same_bytes(a: Path, b: Path, chunk: int = 1 << 16) -> bool:
    """True if two files have identical content. Size-checks first (a fast reject),
    then compares chunk-by-chunk with an early exit. Deliberately **not** ``filecmp.cmp``,
    whose stat-signature cache can return a stale verdict when a same-size file is
    rewritten within the mtime resolution. Any OS error → ``False`` (treat as different)."""
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


def _resolve_import_dest(dest: Path, src: Path) -> tuple[Path, str]:
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
        if _same_bytes(src, cand):
            return cand, "duplicate"
        n += 1
        cand = dest.with_name(f"{stem}-{n}{ext}")
    return cand, "renamed"


def has_unimported_output(target: str) -> bool:
    """True if there's a finished output (in the sandbox or loose in the object dir)
    not yet imported — including a **re-processed file with an existing name but new
    content** (a plain `dest.exists()` check would miss that, the collision footgun)."""
    for p, _kind, dest in _finished_outputs(target):
        if _resolve_import_dest(dest, p)[1] != "duplicate":
            return True
    return False


def scan_finished(target: str, should_cancel=None) -> ImportPlan:
    """Read-only: finished outputs in the sandbox (and loose in the object
    dir), classified + routed."""
    items: list[FinishedItem] = []
    heroes: list[str] = []
    for p, kind, dest in sorted(_finished_outputs(target), key=lambda t: str(t[0])):
        if should_cancel and should_cancel():
            raise PrepCancelled()
        resolved, disp = _resolve_import_dest(dest, p)
        already = disp == "duplicate"          # a byte-identical copy already imported
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        # A re-processed file with an existing name but new content imports under a
        # `<stem>-N` name (both kept) — surface that in the preview so it's not a surprise.
        note = f"kept as {resolved.name}" if disp == "renamed" else ""
        items.append(FinishedItem(
            src=str(p), name=p.name, kind=kind, dest=str(dest),
            size_bytes=size, default=not already, already=already, note=note))
        if kind == "render":
            heroes.append(str(p))
    return ImportPlan(target=target, items=items, hero_candidates=heroes)


# ── import: apply (writes finished/ + stacks/, gated cleanup) ─────────────────

# Kept in each job dir on cleanup, so the sandbox is ready for another run.
_ARCHIVE_KEEP = {"lights", "darks", "flats", "biases",
                 "presets", "archive", "next-steps.md"}


def apply_import(target: str, selected_srcs, hero_src: str | None = None,
                 hero_slug: str | None = None, cleanup: str = "archive",
                 progress=None, should_cancel=None) -> dict:
    """Copy the selected finished outputs into the content tiers, optionally set
    a hero, and tidy the sandbox. THE WRITER — callers confirm.

    cleanup: "archive" (default) sweeps each job's intermediates/output/scratch
    into `siril/[<FILTER>/]archive/<timestamp>/`, keeping `lights/` + `presets/`
    so the sandbox is ready for another run; "none" leaves it. **Never deletes**
    and never escapes `Images/<target>/siril/`. `hero_src=None` keeps the
    object's current hero (the dialog's "keep current" choice)."""
    selected = set(selected_srcs)
    plan = scan_finished(target)
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
        final, disp = _resolve_import_dest(base_dest, Path(it.src))
        if disp == "duplicate":
            skipped += 1
        else:
            shutil.copyfile(it.src, final)   # bytes only (mirrors ingest)
            imported += 1
        if hero_src and it.src == hero_src:
            hero_name = final.name           # the name it ACTUALLY landed under (#)
        if progress:
            progress(i, len(chosen))

    if cancelled:
        return {"imported": imported, "skipped": skipped,
                "cleaned": "none", "cancelled": True}

    # Hero: the chosen render now lives in finished/ — pin it by the filename it
    # actually landed under (build_images._hero_source matches frontmatter `hero` to
    # the image name; a re-processed render can land as `<stem>-N`, so we can't just
    # use the source name). hero_src=None → leave the current hero ("keep current").
    if hero_src and hero_slug:
        objects.set_frontmatter_key(
            hero_slug, "hero", hero_name or Path(hero_src).name)

    cleaned = _archive_run(target) if cleanup == "archive" else "none"
    return {"imported": imported, "skipped": skipped,
            "cleaned": cleaned, "cancelled": False}


def _job_dirs(base: Path) -> list[Path]:
    """The working dirs to tidy: per-filter subdirs (each has lights/) if mixed,
    else the sandbox root."""
    filt = [p for p in base.iterdir() if p.is_dir() and (p / "lights").is_dir()]
    return filt if filt else [base]


def working_dirs(target: str) -> list[Path]:
    """The Siril working directories to offer for a target: the per-filter job
    dirs if the sandbox is split by filter, else the sandbox root. Empty when no
    sandbox exists yet. This is what "Process in Siril" points `-d` at."""
    base = config.siril_dir(target)
    if not base.is_dir():
        return []
    return _job_dirs(base)


def _archive_run(target: str) -> str:
    """Move each job's run output/intermediates/scratch into
    `<job>/archive/<timestamp>/`, keeping lights/ + presets/ for the next run.
    Never deletes; only moves within `Images/<target>/siril/`."""
    base = config.siril_dir(target)
    if not base.is_dir():
        return "none"
    job_dirs = _job_dirs(base)
    ts0 = datetime.now().strftime("%Y%m%d-%H%M%S")
    ts, n = ts0, 2
    while any((jd / "archive" / ts).exists() for jd in job_dirs):
        ts, n = f"{ts0}-{n}", n + 1
    moved = 0
    for jd in job_dirs:
        dest = jd / "archive" / ts
        for child in list(jd.iterdir()):
            if child.name in _ARCHIVE_KEEP:
                continue
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(dest / child.name))
            moved += 1
    return "archive" if moved else "none"

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
from pathlib import Path

from . import config, objects

# Filter token in a Seestar light filename:
#   Light_<object>_<exp>s_<FILTER>_<YYYYMMDD>-<HHMMSS>.fit
_FILTER_RE = re.compile(r"_(LP|IRCUT|UV|DARK)_\d{8}-\d{6}\.fit$", re.IGNORECASE)
OTHER_FILTER = "OTHER"

PRESET_NAME = "naztronomy_smart_scope_presets.json"

_RASTER_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
_FIT_EXTS = (".fit", ".fits")
# A finished output looks "final"…
_FINAL_HINT = re.compile(r"(processed|final|finished)", re.IGNORECASE)
# …and is not one of Siril's many intermediates (starless IS an intermediate).
_INTERMEDIATE = re.compile(
    r"(_og|_crop|_stretch|_spcc|_graxpert|starless|starmask)", re.IGNORECASE)


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


def default_preset(usable_frames: int,
                   filter_label: str = "No Filter (Broadband)") -> dict:
    """A sensible *starting* Naztronomy Smart Scope preset (refined in the GUI).
    Constant keys are the empirical modal default across the reference presets;
    drizzle is set by `usable_frames`."""
    drizzle, amount, pixel_fraction = drizzle_for(usable_frames)
    return {
        "telescope": "ZWO Seestar S50",
        "filter": filter_label,
        "darks": False,
        "flats": False,
        "biases": False,
        "cleanup": True,
        "batch_size": 25000,
        "bg_extract": True,
        "drizzle": drizzle,
        "drizzle_amount": amount,
        "pixel_fraction": pixel_fraction,
        "filters": True,
        "roundness": 95.0,
        "fwhm": 95.0,
        "star_count_filter": 100.0,
        "bg_filter": 95.0,
        "feather": False,
        "feather_amount": 20,
        "stack_weighting": True,
        "weighting_method": "Weighted FWHM",
        "spcc": False,
        "compression": False,
    }


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
        for line in p.read_text().splitlines():
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


def _lights(target: str) -> list[Path]:
    d = config.lights_dir(target)
    if not d.is_dir():
        return []
    return sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() == ".fit")


def plan_prep(target: str, usable_frames: int | None = None,
              star_removal: bool = False, should_cancel=None) -> PrepPlan:
    """Read-only plan: lay each filter's lights into a literal `lights/` inside a
    contained Siril sandbox. `usable_frames` (post-rejection, single-filter only)
    overrides the raw count for the drizzle preset. Reads only."""
    lights = _lights(target)
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
            preset=default_preset(job_usable),
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
    )


# ── prepare: apply (writes the sandbox) ──────────────────────────────────────

def _link_or_copy(src: str, dst: str) -> None:
    """Hardlink src→dst; byte-copy fallback if linking isn't possible."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _next_steps_md(plan: PrepPlan) -> str:
    lines = [
        f"# Processing {plan.target} — Siril sandbox",
        "",
        "M110 set this up so Siril has a clean, self-contained working folder "
        "(your content tiers stay tidy). M110 does not run Siril for you.",
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
    lines += [
        "",
        "## Steps",
        "1. Open **Siril** with a job folder above as the working directory "
        "(it contains a literal `lights/` and a `presets/` the script auto-loads).",
        "2. Run the **Naztronomy Smart Telescope Processing** script → Load preset.",
        "3. Save your stack and finished render anywhere in this sandbox.",
        "4. Back in M110, reopen this object and click **Import finished work** — "
        "M110 brings your renders into the gallery, the stack into `stacks/`, and "
        "offers to clean the sandbox up.",
        "",
        "_The preset is a starting point — refine it in the script's GUI._",
    ]
    return "\n".join(lines) + "\n"


def apply_prep(plan: PrepPlan, progress=None, should_cancel=None) -> dict:
    """Create the sandbox, hardlink lights per job, write presets + next-steps.
    THE WRITER — callers confirm (or it runs via `autoprep` after ingest).
    Idempotent: existing links are skipped."""
    ops = [(job, src, dst) for job in plan.jobs for (src, dst) in job.links]
    linked = skipped = 0
    cancelled = False
    total = len(ops)
    for i, (_job, src, dst) in enumerate(ops, 1):
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
            pp.write_text(json.dumps(job.preset, indent=4) + "\n")
        Path(plan.siril_dir).mkdir(parents=True, exist_ok=True)
        (Path(plan.siril_dir) / "next-steps.md").write_text(_next_steps_md(plan))

    return {"linked": linked, "skipped": skipped, "cancelled": cancelled}


def autoprep(targets, should_cancel=None) -> dict:
    """Set up sandboxes for the given targets after ingest — idempotent, and
    **skips** any target whose sandbox already holds un-imported finished output
    (so it never disturbs in-progress/finished processing). Qt-free."""
    prepared, skipped = [], []
    for target in targets:
        if should_cancel and should_cancel():
            break
        if not _lights(target):
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
    dest: str
    size_bytes: int
    default: bool        # pre-checked in the UI
    already: bool        # already present at dest


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
    if _INTERMEDIATE.search(name):
        return None
    ext = path.suffix.lower()
    if ext in _RASTER_EXTS:
        return "render", config.finished_dir(target) / name
    if ext in _FIT_EXTS and _FINAL_HINT.search(name):
        return "stack", config.stacks_dir(target) / name
    return None


def _sandbox_outputs(target: str):
    """Yield (path, kind, dest) for finished outputs in the sandbox, skipping
    anything under a `lights/` or Siril's own `process/` working dirs."""
    base = config.siril_dir(target)
    if not base.is_dir():
        return
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(base).parts[:-1])
        if "lights" in rel_parts or "process" in rel_parts:
            continue
        c = _classify(p, target)
        if c:
            yield p, c[0], c[1]


def has_unimported_output(target: str) -> bool:
    """True if the sandbox has a finished output not already in finished/stacks."""
    for p, _kind, dest in _sandbox_outputs(target):
        if not dest.exists():
            return True
    return False


def scan_finished(target: str, should_cancel=None) -> ImportPlan:
    """Read-only: finished outputs in the sandbox, classified + routed."""
    items: list[FinishedItem] = []
    heroes: list[str] = []
    for p, kind, dest in sorted(_sandbox_outputs(target), key=lambda t: str(t[0])):
        if should_cancel and should_cancel():
            raise PrepCancelled()
        already = dest.exists()
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        items.append(FinishedItem(
            src=str(p), name=p.name, kind=kind, dest=str(dest),
            size_bytes=size, default=not already, already=already))
        if kind == "render":
            heroes.append(str(p))
    return ImportPlan(target=target, items=items, hero_candidates=heroes)


# ── import: apply (writes finished/ + stacks/, gated cleanup) ─────────────────

def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def apply_import(target: str, selected_srcs, hero_src: str | None = None,
                 hero_slug: str | None = None, cleanup: str = "lights",
                 progress=None, should_cancel=None) -> dict:
    """Copy the selected finished outputs into the content tiers, optionally set
    a hero, and clean up the sandbox. THE WRITER — callers confirm.

    cleanup: "lights" (default; remove only the hardlinked lights/ — safe, the
    originals live in Images/<target>/lights/), "all" (remove the whole sandbox),
    or "none". Destructive removals are **scoped to Images/<target>/siril/**.
    """
    selected = set(selected_srcs)
    plan = scan_finished(target)
    chosen = [it for it in plan.items if it.src in selected]
    imported = skipped = 0
    cancelled = False
    for i, it in enumerate(chosen, 1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        dest = Path(it.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            skipped += 1
        else:
            shutil.copyfile(it.src, dest)   # bytes only (mirrors ingest)
            imported += 1
        if progress:
            progress(i, len(chosen))

    if cancelled:
        return {"imported": imported, "skipped": skipped,
                "cleaned": "none", "cancelled": True}

    # Hero: the chosen render now lives in finished/ — pin it by filename
    # (build_images._hero_source matches frontmatter `hero` to the image name).
    if hero_src and hero_slug:
        objects.set_frontmatter_key(hero_slug, "hero", Path(hero_src).name)

    cleaned = _cleanup_sandbox(target, cleanup)
    return {"imported": imported, "skipped": skipped,
            "cleaned": cleaned, "cancelled": False}


def _cleanup_sandbox(target: str, mode: str) -> str:
    """Remove sandbox files per `mode`, never escaping Images/<target>/siril/."""
    base = config.siril_dir(target)
    if mode == "none" or not base.is_dir():
        return "none"
    if mode == "all":
        if _under(base, config.IMAGES_DIR):
            shutil.rmtree(base)
        return "all"
    if mode == "lights":
        # every literal lights/ under the sandbox (single job or per-filter)
        for d in list(base.rglob("lights")):
            if d.is_dir() and _under(d, base):
                shutil.rmtree(d)
        return "lights"
    return "none"

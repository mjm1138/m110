"""Processing-prep: arrange a Siril working folder for a captured target.

**Prepare-and-guide, not control** — M110 never drives Siril. For a chosen
capture target it:
  (a) arranges the lights into a Siril working dir (`Images/<target>/process/`),
      **split per filter** (`lights_<FILTER>/`) so each stacks correctly;
  (b) emits a **Naztronomy Smart Scope preset** into `process/presets/`
      (the script auto-loads it from there) pre-filled from the target's frame
      count (drizzle decision tree); and
  (c) records `next-steps.md` and points at the relevant workflow guidance.

Mirrors `ingest`'s contract: `plan_prep()` is **read-only** and returns a plan
the UI previews; `apply_prep()` is the **only** writer and runs only after an
explicit confirm. Lights are placed by **hardlink** (no extra disk; reversible —
delete `process/`), with a copy fallback if linking isn't possible.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# Filter token in a Seestar light filename:
#   Light_<object>_<exp>s_<FILTER>_<YYYYMMDD>-<HHMMSS>.fit
_FILTER_RE = re.compile(r"_(LP|IRCUT|UV|DARK)_\d{8}-\d{6}\.fit$", re.IGNORECASE)
OTHER_FILTER = "other"

PRESET_NAME = "naztronomy_smart_scope_presets.json"


class PrepCancelled(Exception):
    """Raised inside plan/apply when the caller's should_cancel() turns true."""


def filter_of(filename: str) -> str:
    """Filter token (upper-case) for a light filename, or OTHER_FILTER."""
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
    """A sensible *starting* Naztronomy Smart Scope preset (the user refines it
    in the script's GUI). Constant keys are the empirical modal default across
    the reference presets; drizzle is set by `usable_frames`."""
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

# Always-relevant core, then conditional add-ons.
_CORE_GUIDANCE = [
    "siril_processing_workflow",
    "siril_drizzle_guide",
    "siril_psf_guide",
    "siril_color_saturation",
    "seestar_s50_imaging_guide",
]


def guidance_ids() -> list[str]:
    """Bundled playbook ids (filenames without .md) that exist on disk."""
    if not config.GUIDANCE_DIR.is_dir():
        return []
    return sorted(p.stem for p in config.GUIDANCE_DIR.glob("*.md"))


def guidance_path(doc_id: str) -> Path:
    return config.GUIDANCE_DIR / f"{doc_id}.md"


def guidance_title(doc_id: str) -> str:
    """First Markdown heading, else a humanized id."""
    p = guidance_path(doc_id)
    if p.is_file():
        for line in p.read_text().splitlines():
            if line.startswith("#"):
                return line.lstrip("# ").strip()
    return doc_id.replace("_", " ").title()


def guidance_for(filters_present: set[str], star_removal: bool) -> list[str]:
    """Relevant playbook ids for a target, in display order (existing ones only)."""
    available = set(guidance_ids())
    ids = [d for d in _CORE_GUIDANCE if d in available]
    if "LP" in filters_present and "siril_lp_narrowband_galaxy_blend" in available:
        ids.append("siril_lp_narrowband_galaxy_blend")
    return ids


# ── plan (read-only) ─────────────────────────────────────────────────────────

@dataclass
class PrepPlan:
    target: str
    process_dir: str                      # abs path to Images/<target>/process
    preset_path: str                      # abs path to process/presets/<PRESET_NAME>
    groups: dict[str, list]               # filter -> [(src_abs, dst_abs)]
    preset: dict
    guidance: list[str]
    usable_frames: int
    frame_basis: str                      # "stack" | "raw"
    star_removal: bool
    total_lights: int = 0
    total_bytes: int = 0
    filters: list[str] = field(default_factory=list)


def _lights(target: str) -> list[Path]:
    d = config.lights_dir(target)
    if not d.is_dir():
        return []
    return sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() == ".fit")


def plan_prep(target: str, usable_frames: int | None = None,
              star_removal: bool = False, should_cancel=None) -> PrepPlan:
    """Read-only plan to arrange `target`'s lights into a Siril working dir.

    `usable_frames` (post-rejection, e.g. from processing `stack_meta`) drives
    the drizzle preset; if None, the raw light count is used. Reads only.
    """
    proc = config.process_dir(target)
    groups: dict[str, list] = {}
    total_bytes = 0
    lights = _lights(target)
    for f in lights:
        if should_cancel and should_cancel():
            raise PrepCancelled()
        filt = filter_of(f.name)
        dst = proc / f"lights_{filt}" / f.name
        groups.setdefault(filt, []).append((str(f), str(dst)))
        try:
            total_bytes += f.stat().st_size
        except OSError:
            pass

    raw = len(lights)
    frame_basis = "raw"
    if usable_frames is None:
        usable_frames = raw
    else:
        frame_basis = "stack"

    filters_present = set(groups.keys())
    preset = default_preset(usable_frames)
    return PrepPlan(
        target=target,
        process_dir=str(proc),
        preset_path=str(proc / "presets" / PRESET_NAME),
        groups=groups,
        preset=preset,
        guidance=guidance_for(filters_present, star_removal),
        usable_frames=usable_frames,
        frame_basis=frame_basis,
        star_removal=star_removal,
        total_lights=raw,
        total_bytes=total_bytes,
        filters=sorted(filters_present),
    )


# ── apply (the only writer) ──────────────────────────────────────────────────

def _link_or_copy(src: str, dst: str) -> None:
    """Hardlink src→dst; fall back to a byte copy if linking isn't possible
    (cross-device, unsupported fs). dst's parent must exist; dst must not."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _next_steps_md(plan: PrepPlan) -> str:
    p = plan.preset
    if p["drizzle"]:
        drizz = (f"drizzle **{p['drizzle_amount']}×** at pixel fraction "
                 f"**{p['pixel_fraction']}**")
    else:
        drizz = "**no drizzle** (stack at 1.0×)"
    star = ("**recommended** for this target (large/extended object)"
            if plan.star_removal else "probably not needed for this target")
    lines = [
        f"# Processing {plan.target} — next steps",
        "",
        "M110 arranged your lights here for Siril (prepare-and-guide; M110 does "
        "not run Siril for you).",
        "",
        "## What's here",
    ]
    for filt in plan.filters:
        lines.append(f"- `lights_{filt}/` — {len(plan.groups[filt])} frames "
                     f"(hardlinked from `../lights/`)")
    lines += [
        f"- `presets/{PRESET_NAME}` — Naztronomy Smart Scope preset "
        "(the script auto-loads it from `presets/`).",
        "",
        "## Steps",
        "1. Open **Siril** with this `process/` folder as the working directory.",
        "2. Run the **Naztronomy Smart Telescope Processing** script and click "
        "**Load preset** — it picks up the JSON in `presets/`.",
        "3. Point it at the `lights_<FILTER>/` set you want to stack (process each "
        "filter separately).",
        f"4. Drizzle is preset to {drizz} for ~{plan.usable_frames} usable frames "
        f"({plan.frame_basis} count) — see `siril_drizzle_guide`.",
        f"5. Star removal: {star} — see the star-removal notes in the guidance.",
        "6. Save the Siril stack to `../stacks/` and your finished render to "
        "`../finished/`.",
        "",
        "_This preset is a starting point — refine it in the script's GUI._",
    ]
    return "\n".join(lines) + "\n"


def apply_prep(plan: PrepPlan, progress=None, should_cancel=None) -> dict:
    """Create the working dir, hardlink lights per filter, and write the preset
    + next-steps. THE ONLY WRITER — callers must confirm. Idempotent: existing
    destinations are skipped, so a re-run just fills what's missing."""
    proc = Path(plan.process_dir)
    ops = [op for g in plan.groups.values() for op in g]
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
        preset_path = Path(plan.preset_path)
        preset_path.parent.mkdir(parents=True, exist_ok=True)
        preset_path.write_text(json.dumps(plan.preset, indent=4) + "\n")
        (proc / "next-steps.md").write_text(_next_steps_md(plan))

    return {"linked": linked, "skipped": skipped, "cancelled": cancelled}

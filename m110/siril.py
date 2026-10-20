"""Processing-prep round-trip: prepare a Siril sandbox, then import the result.

**Prepare-and-guide, not control** — M110 never runs Siril. The round-trip:

  prepare → (you process in Siril) → import finished work → clean up

* **Prepare** arranges a *contained* Siril sandbox `Images/<target>/siril/` with a
  literal `lights/` (Siril needs that exact name), the Naztronomy preset in
  `presets/` (what Naztronomy's *Load Presets* opens), and `next-steps.md`. Lights are placed by **hardlink**
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

from . import calibration, config, devices, roundtrip

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


# A header FILTER value becomes a job folder name (`siril/<FILTER>/`), and headers
# are attacker-controlled like OBJECT — so only a short, plain token is used.
_FILTER_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _+-]{0,31}$")


def frame_filter(path: Path) -> str:
    """The filter a light was shot through: the Seestar filename token as a fast
    path (it mirrors the header), else the header ``FILTER`` card (DwarfLab writes
    ``Astro`` / ``Duo-Band`` / ``VIS``), else `OTHER_FILTER`."""
    tok = filter_of(path.name)
    if tok != OTHER_FILTER:
        return tok
    facts = calibration.frame_facts(path) or {}
    filt = (facts.get("filter") or "").strip()
    return filt if _FILTER_TOKEN_RE.match(filt) else OTHER_FILTER


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


#: The four frame-selection filters, under neutral names. `m110-stack` uses
#: these keys as-is; the Naztronomy preset spells two of them differently
#: (`_PRESET_FILTER_KEYS`).
FILTER_KEYS = ("roundness", "fwhm", "star_count", "bg")
_PRESET_FILTER_KEYS = {"roundness": "roundness", "fwhm": "fwhm",
                       "star_count": "star_count_filter", "bg": "bg_filter"}

# (upper frame bound inclusive, roundness, wFWHM) — first row whose bound holds.
# Each percentage is the share Siril KEEPS, ranked on that one metric over the
# whole set; the four cuts are ANDed, and on real stacks they overlap by only
# 10–45% (#174), so the drops roughly add.
_FILTER_TIERS = ((500, 95.0, 98.0), (1500, 92.0, 95.0), (None, 90.0, 95.0))
_FILTER_FLOOR = 100          # below this there are not enough frames to filter


def is_dual_band(filt: str | None) -> bool:
    """True for a dual-band (Hα + OIII) light-pollution filter: the Seestar's
    ``LP`` and the DwarfLab ``Duo-Band``. Their sky is suppressed and its spread
    small, so a background cut there removes near-arbitrary frames."""
    return re.sub(r"[^a-z]", "", (filt or "").lower()) in {"lp", "duoband", "dualband"}


def filter_quality_for(usable_frames: int, filt: str | None = "") -> tuple[bool, dict]:
    """(filters_on, {roundness, fwhm, star_count, bg}) — the share of frames each
    frame-selection filter keeps, by frame count and filter (#174).

    The four measure different things, so they are tuned apart:

    * **roundness** carries the weight — wind, polar-alignment and tracking
      errors show up as elongation, which rejection cannot catch;
    * **wFWHM** only trims the worst tail, since wFWHM *weighting* already
      down-weights soft frames;
    * **background** is 98%, but off (100) on a dual-band filter (`is_dual_band`);
    * **star count** is off (100): wFWHM already penalises low-star frames, and
      the near-blank ones fail registration anyway.

    Below 100 frames the filters are off; the values are the next tier's."""
    for bound, roundness, fwhm in _FILTER_TIERS:
        if bound is None or usable_frames <= bound:
            break
    return usable_frames >= _FILTER_FLOOR, {
        "roundness": roundness, "fwhm": fwhm, "star_count": 100.0,
        "bg": 100.0 if is_dual_band(filt) else 98.0,
    }


# Naztronomy's `telescope` choice and its two filter labels (broadband, dual-band)
# per `devices.preset_key`. The script sets the telescope first, which refills its
# filter list, then the label — and silently ignores a label that list lacks, so
# the pair must agree. The label drives SPCC (`-oscfilter`, or `-narrowband` with
# Hα/OIII bandwidths for DwarfLab). Unknown devices keep the original S50 default.
_NAZ_SEESTAR = ("No Filter (Broadband)", "LP (Narrowband)")
_NAZ_DWARF = ("Astro filter (UV/IR)", "Dual-Band")
_NAZ_SCOPES = {
    "seestar_s50": ("ZWO Seestar S50", *_NAZ_SEESTAR),
    "seestar_s30": ("ZWO Seestar S30", *_NAZ_SEESTAR),
    "seestar_s30_pro": ("ZWO Seestar S30 Pro", *_NAZ_SEESTAR),
    "dwarf_3": ("Dwarf 3", *_NAZ_DWARF),
    "dwarf_mini": ("Dwarf Mini", *_NAZ_DWARF),
}
_NAZ_DEFAULT = _NAZ_SCOPES["seestar_s50"]
#: Every Naztronomy filter label that means a dual-band filter.
DUAL_BAND_LABELS = frozenset({_NAZ_SEESTAR[1], _NAZ_DWARF[1]})


def naztronomy_scope(telescop: str | None, filt: str | None = "") -> tuple[str, str]:
    """(Naztronomy telescope, filter label) for a ``TELESCOP`` header and a filter
    token."""
    scope, broadband, dual = _NAZ_SCOPES.get(devices.preset_key(telescop) or "",
                                             _NAZ_DEFAULT)
    return scope, dual if is_dual_band(filt) else broadband


def default_preset(usable_frames: int, filt: str | None = "",
                   telescop: str | None = None, darks: bool = False,
                   flats: bool = False, biases: bool = False) -> dict:
    """A sensible *starting* Naztronomy Smart Scope preset (refined in the GUI).
    Constant keys are the empirical modal default across the reference presets;
    drizzle (`drizzle_for`) is set by `usable_frames`, the frame-selection filters
    (`filter_quality_for`) by count and filter, and the telescope and filter label
    by device and filter (`naztronomy_scope`). The `darks`/`flats`/`biases`
    toggles are turned on when the sandbox has those calibration frames
    hardlinked in (#57), so the script calibrates by default when they are present."""
    drizzle, amount, pixel_fraction = drizzle_for(usable_frames)
    filters_on, quality = filter_quality_for(usable_frames, filt)
    telescope, label = naztronomy_scope(telescop, filt)
    return {
        "telescope": telescope,
        "filter": label,
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
        **{_PRESET_FILTER_KEYS[k]: v for k, v in quality.items()},
        "feather": False,
        "feather_amount": 20,
        "stack_weighting": True,
        "weighting_method": "Weighted FWHM",
        "spcc": False,
        "compression": False,
    }


#: Moved to `roundtrip` when a second sandbox started holding frames — both build
#: their link tree the same way, and `backup.scope` skips exactly those trees.
_link_or_copy = roundtrip.link_or_copy


# ── prepare: plan (read-only) ────────────────────────────────────────────────

@dataclass
class PrepJob:
    filt: str                       # filter token, or "" for the single-filter sandbox root
    job_dir: str                    # working dir Siril opens (has lights/ + presets/)
    preset_path: str
    links: list = field(default_factory=list)  # (src, dst) hardlink ops
    preset: dict = field(default_factory=dict)
    usable_frames: int = 0
    # what writing `preset` would do: "new" (no file yet), "same" (already equal),
    # "differs" (a different preset is there — asks before replacing), or
    # "declined" (differs, but the user already kept theirs against this proposal)
    preset_state: str = "new"


@dataclass
class PresetConflict:
    """A job whose preset on disk differs from the one M110 would write. Nothing
    is replaced until the user chooses (`apply_preset_choices`)."""
    target: str
    job: str                        # filter token, or "" for the sandbox root
    preset_path: str
    proposed: dict
    changes: list                   # [(key, on disk, proposed)]; None = absent


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
    # (src, dst) hardlinks for darks/flats/biases → **each job dir** (the
    # Naztronomy script resolves `darks/` against Siril's working directory,
    # which for a mixed-filter target is the per-filter job folder, not the
    # sandbox root). Empty when the target has no calibration frames.
    calib_links: list = field(default_factory=list)
    calib_kinds: list = field(default_factory=list)   # ["darks", …] present
    # "target" (the target's own darks/flats/biases), "library" (one master per
    # tier matched from Calibration/<device>/), or "" (none)
    calib_source: str = ""
    calib_notes: list = field(default_factory=list)   # what the library match said


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
    # Calibration: the target's own darks/flats/biases win (a user's per-project
    # frames); otherwise ONE matched master per tier from the device library
    # (calibration.py — exposure/gain/binning, nearest temperature). Either way
    # the frames are hardlinked into **every job dir** below, because the
    # Naztronomy script looks for `darks/` next to the `lights/` it is run on.
    calib = _calib_frames(target)
    calib_source = "target" if calib else ""
    calib_notes: list[str] = []
    # The telescope picks the preset's Naztronomy telescope + filter label.
    telescop = calibration.device_for_target(target) if lights else None
    if "darks" in calib and devices.darks_applied_on_device(telescop):
        calib_notes.append("this object's darks/ will be applied, but its telescope "
                           "already dark-subtracted the subs — that subtracts twice; "
                           "remove darks/ unless that is intended")
    if not calib and lights:
        match = calibration.match_for_target(target)
        calib_notes = list(match.notes)
        if match:
            calib = {tier: [p] for tier, p in match.as_dict().items()}
            calib_source = "library"
    calib_kinds = list(calib)
    calib_links: list[tuple[str, str]] = []
    by_filter: dict[str, list[Path]] = {}
    total_bytes = 0
    for f in lights:
        if should_cancel and should_cancel():
            raise PrepCancelled()
        by_filter.setdefault(frame_filter(f), []).append(f)
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
        calib_links += [(str(f), str(job_dir / kind / f.name))
                        for kind, frames in calib.items() for f in frames]
        jobs.append(PrepJob(
            filt=filt if multi else "",
            job_dir=str(job_dir),
            preset_path=str(job_dir / "presets" / PRESET_NAME),
            links=links,
            preset=(preset := default_preset(job_usable, filt, telescop,
                                             darks="darks" in calib,
                                             flats="flats" in calib,
                                             biases="biases" in calib)),
            usable_frames=job_usable,
            preset_state=_preset_state(job_dir / "presets" / PRESET_NAME, preset),
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
        calib_source=calib_source,
        calib_notes=calib_notes,
    )


# ── prepare: apply (writes the sandbox) ──────────────────────────────────────

def _filters_md(preset: dict) -> str:
    if not preset.get("filters"):
        return "frame filters off"
    names = (("roundness", "roundness"), ("fwhm", "wFWHM"),
             ("bg_filter", "background"), ("star_count_filter", "star count"))
    on = [f"{label} {preset[k]:g}%" for k, label in names if preset.get(k, 100) < 100]
    return "keep " + " · ".join(on) if on else "frame filters off"


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
                     f"({len(job.links)} subs, {drizz}, {_filters_md(p)}; "
                     f"{p['telescope']} · {p['filter']})")
        if job.preset_state in ("differs", "declined"):
            lines.append("  - the preset in this folder differs from these "
                         "suggestions and was kept as it is")
    if plan.calib_kinds:
        src = ("this object's own frames" if plan.calib_source == "target"
               else "one matching master per tier from the telescope's "
                    "calibration library (`Calibration/<device>/`)")
        lines += [
            "",
            f"Calibration ({', '.join(plan.calib_kinds)}/) was hardlinked into each "
            f"job folder — {src} — and the preset's matching toggles are on. A "
            "folder holding a single file is treated by the script as a master.",
        ]
    if plan.calib_notes:
        lines += [""] + [f"- Calibration note: {n}" for n in plan.calib_notes]
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
    """On-disk preset as a dict, or {} if missing/unreadable (an unreadable file
    differs from any proposal, so it is never replaced without asking)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# Beside the preset: the proposal the user last answered "Keep existing" to, so
# the same question is not asked on every ingest — only once the proposal itself
# changes (a frame-count tier crossed, a new device or filter rule).
_DECLINED_NAME = ".m110_declined_preset.json"
PRESET_ARCHIVE_DIR = "archive"          # presets/archive/<name>.<stamp>.json


def _proposal_hash(preset: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(preset, sort_keys=True).encode()).hexdigest()


def _declined_hash(preset_path: Path) -> str | None:
    try:
        data = json.loads((preset_path.parent / _DECLINED_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("proposal_sha256") if isinstance(data, dict) else None


def _preset_state(preset_path: Path, proposed: dict) -> str:
    if not preset_path.exists():
        return "new"
    if _read_preset(preset_path) == proposed:
        return "same"
    if _declined_hash(preset_path) == _proposal_hash(proposed):
        return "declined"
    return "differs"


def _preset_changes(existing: dict, proposed: dict) -> list:
    keys = list(proposed) + [k for k in existing if k not in proposed]
    return [(k, existing.get(k), proposed.get(k)) for k in keys
            if existing.get(k) != proposed.get(k)]


def _write_preset(path: Path, preset: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preset, indent=4) + "\n", encoding="utf-8")


def archive_preset(preset_path: Path) -> Path | None:
    """Move the preset at `preset_path` into ``presets/archive/``, stamped with
    the time, and return where it went (None if there was nothing there).
    Naztronomy's Load Presets opens only the exact preset name, so an archived
    copy is never picked up by accident."""
    if not preset_path.exists():
        return None
    from datetime import datetime
    adir = preset_path.parent / PRESET_ARCHIVE_DIR
    adir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = adir / f"{preset_path.stem}.{stamp}{preset_path.suffix}"
    n = 1
    while dest.exists():
        n += 1
        dest = adir / f"{preset_path.stem}.{stamp}-{n}{preset_path.suffix}"
    os.replace(preset_path, dest)
    return dest


def apply_preset_choices(conflicts, replace) -> dict:
    """Settle the conflicts `apply_prep` reported. Each one whose `preset_path` is
    in `replace` has its preset archived and the proposal written; every other one
    records that the user kept theirs against this proposal, so it is not asked
    again until the proposal changes. THE WRITER for presets that already exist —
    the caller has shown the user the conflicts and taken their answer."""
    replace = set(replace)
    replaced, kept = [], []
    for c in conflicts:
        pp = Path(c.preset_path)
        side = pp.parent / _DECLINED_NAME
        if c.preset_path in replace:
            archive_preset(pp)
            _write_preset(pp, c.proposed)
            side.unlink(missing_ok=True)
            replaced.append(c.preset_path)
        else:
            pp.parent.mkdir(parents=True, exist_ok=True)
            side.write_text(json.dumps({"proposal_sha256": _proposal_hash(c.proposed)})
                            + "\n", encoding="utf-8")
            kept.append(c.preset_path)
    if replaced or kept:
        _log.info("presets: replaced %d, kept %d", len(replaced), len(kept))
    return {"replaced": replaced, "kept": kept}


def apply_prep(plan: PrepPlan, progress=None, should_cancel=None) -> dict:
    """Create the sandbox, hardlink lights per job (+ shared darks/flats/biases at
    the sandbox root), write presets + next-steps. THE WRITER — callers confirm (or
    it runs via `autoprep` after ingest). Idempotent: existing links are skipped.
    A preset is written only where none exists; one that differs from the
    proposal comes back in ``preset_conflicts`` for `apply_preset_choices`."""
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

    conflicts: list[PresetConflict] = []
    if not cancelled:
        for job in plan.jobs:
            pp = Path(job.preset_path)
            pp.parent.mkdir(parents=True, exist_ok=True)
            # Only a missing preset is written here. One that differs — the user
            # saved their own from Naztronomy, or M110's proposal moved on — is
            # reported, and replaced only when the user says so.
            state = _preset_state(pp, job.preset)
            if state == "new":
                _write_preset(pp, job.preset)
            elif state == "differs":
                conflicts.append(PresetConflict(
                    target=plan.target, job=job.filt, preset_path=str(pp),
                    proposed=job.preset,
                    changes=_preset_changes(_read_preset(pp), job.preset)))
        Path(plan.siril_dir).mkdir(parents=True, exist_ok=True)
        # next-steps.md is app guidance (not user-owned) — always refreshed so the
        # recommended drizzle/filters for the current count stay visible.
        (Path(plan.siril_dir) / "next-steps.md").write_text(_next_steps_md(plan), encoding="utf-8")

    return {"linked": linked, "skipped": skipped, "cancelled": cancelled,
            "preset_conflicts": conflicts}


def autoprep(targets, should_cancel=None, only_missing: bool = False) -> dict:
    """Set up sandboxes for the given targets — idempotent, and **skips** any
    target whose sandbox already holds un-imported finished output (never
    disturbs in-progress/finished processing). Qt-free.

    `only_missing=True` additionally skips any target that already has a `siril/`
    sandbox — so a refresh-time backfill creates only the absent ones and never
    rewrites an existing (possibly hand-edited) preset. The default (ingest) path
    re-runs the full prep so new lights get linked; a preset that no longer
    matches the proposal for the current frame count is returned in
    ``preset_conflicts`` for the caller to put to the user."""
    prepared, skipped, conflicts = [], [], []
    for target in targets:
        if should_cancel and should_cancel():
            break
        # Existence first: it is one stat, and on the refresh-time backfill nearly
        # every target already has its sandbox — listing its lights just to skip
        # it re-walked the whole store on every sync.
        if only_missing and config.siril_dir(target).exists():
            continue
        if not _lights(target):
            continue
        if has_unimported_output(target):
            skipped.append(target)
            continue
        plan = plan_prep(target, should_cancel=should_cancel)
        if plan.total_lights:
            res = apply_prep(plan, should_cancel=should_cancel)
            conflicts += res["preset_conflicts"]
            prepared.append(target)
    return {"prepared": prepared, "skipped": skipped, "preset_conflicts": conflicts}


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

# Kept in each job dir on cleanup, so the sandbox is ready for another run. Siril's
# `process/` scratch stays too: the tools manage it, and an archived copy is
# regenerable bytes multiplied by keep-N (see `config.SANDBOX_SCRATCH`).
_ARCHIVE_KEEP = ({"lights", "darks", "flats", "biases",
                  "presets", "archive", "next-steps.md"}
                 | config.SANDBOX_SCRATCH["siril"])

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

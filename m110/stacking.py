"""Headless Siril stacking, using the Naztronomy method — the ``m110-stack`` CLI.

Reproduces the command sequence of Naztronomy-Smart_Telescope_PP.py through
``siril-cli`` so a stack can be run, scripted and repeated without the GUI, plus
a few settings Naztronomy's GUI does not expose (rejection algorithm chosen by
depth, overlap normalisation for mosaics, noise weighting for mixed exposures,
FITS compression on the intermediates).

Nothing here reimplements an algorithm — every step is a stock Siril 1.4
command. Only the orchestration and the settings *choice* live in Python.

**This is where M110 stopped being purely prepare-and-guide.** Everything else
in the app arranges a sandbox and hands the user to their tool; this module
drives `siril-cli` itself, because a multi-hour stack is exactly the job a human
should not have to sit through. The guide posture survives where it matters:
two-phase by design, so measuring and proposing is read-only and `run_stack` is
reached only after a human has agreed to the settings.

    m110-stack <dir>            # measure + propose (read-only)
    m110-stack <dir> --json     # same, machine-readable
    m110-stack <dir> --run      # execute

<dir> may be an M110 Siril sandbox (containing lights/ and presets/), a folder
containing lights/, or a folder of .fit subs directly.

Qt-free, like every engine module. **astropy is imported lazily** (`_fits()`):
the assistant package reads this module's pure half, and importing astropy at
module scope would break the assistant's no-astropy-at-import budget.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

import numpy as np

from . import config, launch, siril as siril_mod

PRESET_NAME = siril_mod.PRESET_NAME


class StackingError(Exception):
    """Anything that should stop a stack with a message the user can act on.

    The original script `sys.exit()`d at these points. An engine module raises so
    the CLI can turn it into an exit code and the assistant can turn it into a
    tool refusal, rather than killing whichever process imported us.
    """


def _fits():
    """astropy.io.fits, imported on first use — see the module docstring."""
    from astropy.io import fits
    return fits

# Naztronomy's shipped quality-filter defaults.
# Measured on M15: 98% kept 231 frames vs 210 at 95%, with identical FWHM —
# the frames 95% discarded were fine. Matches Naztronomy's M15 preset.
DEFAULT_FILTERS = {"roundness": 98.0, "fwhm": 98.0, "star_count": 98.0, "bg": 98.0}


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def find_siril() -> str | None:
    """Path to a scriptable Siril binary, or None.

    Goes through `launch.find_app("siril")` so the user's Preferences override
    (`external_app_paths`) and the per-platform standard locations are honoured
    once, in one place. That resolver returns the **GUI** binary, so we then
    prefer a `siril-cli` sitting beside it: Siril 1.4 ships both in the same
    directory, and the CLI is the one built for `-s`.
    """
    found = launch.find_app("siril")
    if found:
        cli = Path(found).with_name("siril-cli")
        if os.access(cli, os.X_OK):
            return str(cli)
        return found
    return shutil.which("siril-cli")


def require_siril() -> str:
    """`find_siril` or a `StackingError` naming the fix."""
    found = find_siril()
    if not found:
        raise StackingError(
            "Siril was not found. Install it from https://siril.org, or set its "
            "location in M110 → Preferences → Processing tools."
        )
    return found


def gaia_catalogue(siril: str) -> Path | None:
    """Local Gaia astrometry catalogue, or None. Mosaics do not assemble without it."""
    try:
        out = subprocess.run(
            [siril, "-d", "/tmp", "-s", "-"],
            input="requires 1.2.0\nget core.catalogue_gaia_astro\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=launch._child_env(),
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.splitlines():
        if "catalogue_gaia_astro" in line and "=" in line:
            p = Path(line.split("=", 1)[1].strip())
            return p if p.is_file() else None
    return None


def resolve_layout(root: Path) -> tuple[Path, Path]:
    """(working_dir, lights_dir). Siril's cwd must be the parent of lights/.

    Accepts an M110 sandbox or per-filter job dir (both contain `lights/`), a
    bare `lights/`, or a loose folder of subs — so the CLI works on a directory
    that was never in a store.
    """
    root = root.resolve()
    if (root / "lights").is_dir():
        return root, root / "lights"
    if root.name == "lights":
        return root.parent, root
    if any(p for p in root.iterdir()
           if p.is_file() and config.is_fits_file(p.name)):
        return root.parent, root
    raise StackingError(f"No lights/ folder and no FITS frames under {root}")


def resolve_input(spec) -> Path:
    """A directory, or a capture-folder name in the store.

    Taking a bare name (`m110-stack "NGC 6543"`) is not sugar — it is what lets the
    assistant hand the user a runnable command without putting an absolute path,
    and therefore their home directory, into a model's context.
    """
    p = Path(spec)
    if p.exists():
        return p
    if p.parts and len(p.parts) == 1:
        for candidate in (config.siril_dir(str(spec)), config.target_dir(str(spec))):
            if candidate.is_dir():
                return candidate
    raise StackingError(
        f"{spec!r} is neither a directory nor a capture folder in "
        f"{config.IMAGES_DIR}."
    )


def target_for(working: Path) -> str | None:
    """The capture target a working dir belongs to, or None if it is outside the
    store. `Images/<target>/siril[/<FILTER>]` — walk up to the child of Images/."""
    try:
        rel = working.resolve().relative_to(config.IMAGES_DIR.resolve())
    except (ValueError, OSError):
        return None
    return rel.parts[0] if rel.parts else None


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------


@dataclass
class Survey:
    n_frames: int = 0
    object_name: str = ""
    exposures: dict = field(default_factory=dict)
    filters: dict = field(default_factory=dict)
    nights: dict = field(default_factory=dict)   # date -> {frames, exposures}
    gains: dict = field(default_factory=dict)
    temps: list = field(default_factory=list)
    fov_w: float = 0.0
    fov_h: float = 0.0
    naxis1: int = 0
    naxis2: int = 0
    plate_scale: float = 0.0
    depth_median: int = 0
    depth_min: int = 0
    is_mosaic: bool = False
    span_w: float = 0.0
    span_h: float = 0.0
    integration_min: float = 0.0
    fwhm_by_exposure: dict = field(default_factory=dict)
    _ra: object = None
    _dec: object = None
    _files_by_exp: dict = field(default_factory=dict)

    def public(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if not k.startswith("_")}


@dataclass
class Frame:
    """One light frame's metadata, in the order Siril's `link` will see them."""
    name: str
    exposure: float | None = None
    filter: str = "UNKNOWN"
    gain: int | None = None
    temp: float | None = None
    date: str = ""
    ra: float | None = None
    dec: float | None = None


def read_frames(lights: Path) -> tuple[list[Frame], dict]:
    """Every frame's metadata plus the shared geometry, read once.

    Separate from summarising so a subset can be re-summarised without touching
    the disk again — which is what makes --only-exposure / --exclude-night cheap
    and, more importantly, makes the *proposal* reflect the filtered set rather
    than the folder.
    """
    fits = _fits()
    files = sorted(p for p in lights.iterdir()
                   if p.is_file() and config.is_fits_file(p.name))
    if not files:
        raise StackingError(f"No .fit/.fits frames in {lights}")

    frames: list[Frame] = []
    geom: dict = {}
    for p in files:
        try:
            h = fits.getheader(p)
        except OSError:
            frames.append(Frame(name=p.name))
            continue
        exp = h.get("EXPTIME") or h.get("EXPOSURE")
        frames.append(Frame(
            name=p.name,
            exposure=float(exp) if exp is not None else None,
            filter=(h.get("FILTER") or "").strip() or "UNKNOWN",
            gain=int(h["GAIN"]) if h.get("GAIN") is not None else None,
            temp=float(h["CCD-TEMP"]) if h.get("CCD-TEMP") is not None else None,
            date=str(h.get("DATE-OBS") or "")[:10],
            ra=float(h["RA"]) if h.get("RA") is not None else None,
            dec=float(h["DEC"]) if h.get("DEC") is not None else None,
        ))
        if not geom:
            geom = {"naxis1": h.get("NAXIS1"), "naxis2": h.get("NAXIS2"),
                    "xpixsz": h.get("XPIXSZ"), "focal": h.get("FOCALLEN"),
                    "object": str(h.get("OBJECT", "")).strip()}
    return frames, geom


def summarize(frames: list[Frame], geom: dict) -> Survey:
    s = Survey(n_frames=len(frames))
    exposures: Counter = Counter()
    filters: Counter = Counter()
    gains: Counter = Counter()
    nights: dict = defaultdict(lambda: {"frames": 0, "exposures": Counter()})
    ras, decs = [], []
    total_exp = 0.0
    s.object_name = geom.get("object", "")
    naxis1, naxis2 = geom.get("naxis1"), geom.get("naxis2")
    xpixsz, focal = geom.get("xpixsz"), geom.get("focal")

    for fr in frames:
        if fr.exposure is not None:
            exposures[fr.exposure] += 1
            total_exp += fr.exposure
            s._files_by_exp.setdefault(fr.exposure, []).append(fr.name)
        filters[fr.filter] += 1
        if fr.gain is not None:
            gains[fr.gain] += 1
        if fr.temp is not None:
            s.temps.append(fr.temp)
        if fr.date:
            nights[fr.date]["frames"] += 1
            if fr.exposure is not None:
                nights[fr.date]["exposures"][fr.exposure] += 1
        if fr.ra is not None and fr.dec is not None:
            ras.append(fr.ra)
            decs.append(fr.dec)

    s.exposures = dict(sorted(exposures.items()))
    s.filters = dict(filters)
    s.gains = dict(gains)
    s.integration_min = total_exp / 60.0
    s.nights = {
        d: {"frames": v["frames"], "exposures": dict(sorted(v["exposures"].items()))}
        for d, v in sorted(nights.items())
    }

    if xpixsz and focal:
        s.plate_scale = float(xpixsz) / float(focal) * 206.265
        if naxis1 and naxis2:
            s.naxis1, s.naxis2 = int(naxis1), int(naxis2)
            s.fov_w = naxis1 * s.plate_scale / 3600.0
            s.fov_h = naxis2 * s.plate_scale / 3600.0

    if ras:
        s._ra, s._dec = np.array(ras), np.array(decs)
        cosd = math.cos(math.radians(float(np.mean(s._dec))))
        s.span_w = float(s._ra.max() - s._ra.min()) * cosd + s.fov_w
        s.span_h = float(s._dec.max() - s._dec.min()) + s.fov_h
        s.depth_median, s.depth_min = coverage_depth(s)
        s.is_mosaic = bool(
            s.fov_w and (s.span_w > 1.5 * s.fov_w or s.span_h > 1.5 * s.fov_h)
        )
    else:
        s.depth_median = s.depth_min = s.n_frames
    return s


def select_frames(frames: list[Frame], only_exposure: list[float] | None,
                  exclude_night: list[str] | None,
                  only_night: list[str] | None) -> tuple[list[Frame], list[int]]:
    """(kept frames, 1-based indices to unselect).

    Indices are relative to the FULL sorted file list, because `link` ingests
    every file in lights/ regardless — the selection is applied afterwards with
    `unselect`, and Siril's `calibrate` skips excluded frames by default, so the
    exclusion carries through the rest of the chain.
    """
    kept, dropped = [], []
    for i, fr in enumerate(frames, start=1):
        ok = True
        if only_exposure and (fr.exposure is None or fr.exposure not in only_exposure):
            ok = False
        if only_night and fr.date not in only_night:
            ok = False
        if exclude_night and fr.date in exclude_night:
            ok = False
        (kept if ok else dropped).append(fr if ok else i)
    return kept, dropped


def as_ranges(indices: list[int]) -> list[tuple[int, int]]:
    """Collapse [1,2,3,7,8] to [(1,3),(7,8)] so the script stays readable."""
    out: list[tuple[int, int]] = []
    for i in sorted(indices):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def measure_fwhm_by_exposure(siril: str, lights: Path, s: Survey,
                             n: int = 5) -> dict[float, float]:
    """Median star FWHM per exposure group, from a sample of raw subs.

    Only worth running when exposures are mixed, and then it is decisive: if the
    longer subs are also the softer ones — more tracking error accumulates in a
    longer sub, and a different night may simply have had worse seeing — then
    weighting by noise actively makes the stack worse, because longer subs have
    the better per-frame SNR and so earn *more* weight for being blurrier.
    Measured on M15: 10s subs median FWHM 3.09, 20s subs 4.85.

    One Siril invocation for the whole sample; process startup dominates
    otherwise.
    """
    if len(s._files_by_exp) < 2:
        return {}
    picks, order = [], []
    for exp, files in sorted(s._files_by_exp.items()):
        step = max(1, len(files) // n)
        sel = files[::step][:n]
        picks += sel
        order += [exp] * len(sel)

    script = "requires 1.4.0\n" + "".join(
        f'load "{f}"\nfindstar\n' for f in picks)
    try:
        out = subprocess.run([siril, "-d", str(lights), "-s", "-"], input=script,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=600,
                             env=launch._child_env()).stdout
    except (subprocess.SubprocessError, OSError):
        return {}

    vals = [float(m) for m in re.findall(r"FWHM ([0-9.]+)", out)]
    if len(vals) != len(order):
        return {}
    by: dict[float, list[float]] = {}
    for exp, v in zip(order, vals):
        by.setdefault(exp, []).append(v)
    return {e: float(np.median(v)) for e, v in by.items() if v}


def coverage_depth(s: Survey) -> tuple[int, int]:
    """How many frames actually cover a typical point of sky.

    Counts frames whose centre lies within half the *short* axis of the field,
    so every counted frame provably contains the point (a conservative lower
    bound, since frames offset along the long axis also cover it). For a single
    target this is every frame; for a mosaic it is the depth on one patch of
    sky. This — not len(files) — is what drizzle and rejection resolve against.
    """
    if s._ra is None or not s.fov_h:
        return (s.n_frames, s.n_frames)
    cosd = math.cos(math.radians(float(np.mean(s._dec))))
    x, y = s._ra * cosd, s._dec
    r = min(s.fov_w, s.fov_h) / 2.0
    counts = [
        int(np.count_nonzero((x - x[i]) ** 2 + (y - y[i]) ** 2 < r * r))
        for i in range(len(x))
    ]
    return int(np.median(counts)), int(np.min(counts))


# --------------------------------------------------------------------------
# proposal
# --------------------------------------------------------------------------


@dataclass
class Setting:
    value: object
    why: str


@dataclass
class Proposal:
    settings: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    canvas: tuple = (0, 0)
    disk_gb: float = 0.0
    disk_gb_compressed: float = 0.0
    free_gb: float = 0.0

    def set(self, key, value, why):
        self.settings[key] = Setting(value, why)

    def get(self, key, default=None):
        s = self.settings.get(key)
        return s.value if s else default


def drizzle_for(depth: int) -> tuple[bool, float, float, str]:
    """Drizzle from coverage depth (workflows/siril_drizzle_guide.md)."""
    if depth < 100:
        return (False, 1.0, 1.0,
                f"only {depth} frames cover a typical point — below the ~100 floor "
                "where drizzle has enough sub-pixel views to converge")
    if depth < 300:
        return (True, 1.5, 1.0, f"{depth}-deep at a point: the safe default")
    if depth < 500:
        return (True, 1.5, 0.75,
                f"{depth}-deep: near-matched pixfrac. 1/scale (0.67) is the geometric ideal but too aggressive on a colour sensor, where red and blue have half green's sample density; 0.75 measured better on all three channels")
    return (True, 2.0, 0.5,
            f"{depth}-deep: aggressive matched pair, worth it only if the seeing "
            "on these nights was genuinely good")


def rejection_for(depth: int) -> tuple[str, str, str]:
    """Rejection algorithm by stack depth. Naztronomy hardcodes Winsorized 3 3."""
    if depth < 10:
        return ("p 0.2 0.1", "percentile clipping",
                f"{depth} frames is too few for a sigma estimate to mean anything")
    return ("w 3 3", "Winsorized sigma",
            f"{depth} frames: the general-purpose choice and Naztronomy's default. "
            "Linear-fit clipping was tried on M15 at this depth and measured no "
            "better, so the extra tier is not worth its complexity")


def build_proposal(s: Survey, gaia: Path | None, working: Path,
                   gaia_checked: bool = True) -> Proposal:
    p = Proposal()

    # -- drizzle ---------------------------------------------------------
    driz, scale, pixfrac, why = drizzle_for(s.depth_median)
    p.set("drizzle", driz, why)
    p.set("drizzle_scale", scale, "")
    p.set("pixfrac", pixfrac, "")

    # -- debayer is derived, never a preference --------------------------
    p.set("debayer", not driz,
          "drizzle demosaics as it resamples and needs raw CFA; with drizzle off "
          "nothing else touches the CFA and the stack would come out monochrome")

    # -- rejection -------------------------------------------------------
    rej, rej_name, rej_why = rejection_for(s.depth_median)
    p.set("rejection", rej, f"{rej_name} — {rej_why}")

    # -- weighting -------------------------------------------------------
    if len(s.exposures) > 1:
        f = s.fwhm_by_exposure
        # If the longer subs are also the softer ones, noise weighting rewards
        # them for the wrong reason and drags the stack's resolution down.
        soft = (len(f) > 1
                and max(f, key=lambda e: e) == max(f, key=lambda e: f[e])
                and max(f.values()) > min(f.values()) * 1.15)
        if soft:
            lo, hi = min(f, key=lambda e: f[e]), max(f, key=lambda e: f[e])
            p.set("weight", "wfwhm",
                  f"exposures are mixed AND the longer subs are softer "
                  f"({fmt_exp(hi)} median FWHM {f[hi]:.2f} vs {fmt_exp(lo)} "
                  f"{f[lo]:.2f}). Noise weighting would give those blurrier frames "
                  "more weight for having better per-frame SNR; weight on star "
                  "quality instead")
        else:
            p.set("weight", "noise",
                  "exposures are mixed with comparable sharpness, so weight on the "
                  "real SNR difference between them rather than star quality")
    else:
        p.set("weight", "wfwhm",
              "single exposure, so weight on star quality — Naztronomy's default")

    # -- normalisation ---------------------------------------------------
    # Off by default even on mosaics. In principle it protects large-scale
    # structure (coefficients from shared sky rather than whole-image statistics),
    # but a frame at the mosaic periphery overlaps only one or two neighbours, so
    # its coefficient is the least constrained in the set and the error chains
    # outward. Measured on NGC 7000: 93% of severe seams sat within ~200px of the
    # footprint edge. It is also the prime suspect for a very slow stack step.
    p.set("overlap_norm", False,
          "whole-image normalisation is better constrained. --overlap-norm "
          "computes coefficients on frame overlaps instead, which protects "
          "large-scale structure but is poorly determined for the sparsely "
          "overlapped frames at a mosaic's edge — where it produced visible "
          "seams on NGC 7000")

    p.set("rgb_equal", False,
          "SPCC is the colour-calibration step in your workflow and does this "
          "properly from a star catalogue; -rgb_equal pre-equalises backgrounds "
          "beforehand and only helps if you were going to skip SPCC")

    # -- background extraction -------------------------------------------
    p.set("bg_extract", True,
          "per-frame linear gradient removal before registration")

    # -- quality filters --------------------------------------------------
    p.set("filters", dict(DEFAULT_FILTERS),
          "98% thresholds on roundness, wFWHM, background and star count. 95% was "
          "measurably too tight — it cut 21 of 231 frames on M15 with no FWHM gain")

    # -- compression -------------------------------------------------------
    p.set("compress", True,
          "Rice compression on the intermediate sequences — measured ~3x on this "
          "kind of data, which is the difference between a mosaic fitting on disk "
          "and not, and it cuts the I/O on the registered sequence too")
    p.set("compress_quant", 64,
          "quantisation is noise-scaled and lossy: measured deviation from an "
          "uncompressed stack is ~2% of the image noise sigma at q64, ~3% at q16, "
          "while the compression ratio barely moves (2.8x vs 3.2x). Cheap insurance")

    # Feathering is not optional on a mosaic. Without it each frame's
    # contribution ends abruptly at its border, so at the periphery — where only
    # one or two frames cover — any level offset becomes a hard-edged block.
    if s.is_mosaic:
        p.set("feather", 30,
              "mosaic: ramps each frame's contribution down over 30px at its "
              "borders so coverage changes blend instead of stepping. Leaving it "
              "off is what produced visible tiling at the edges of NGC 7000")
    else:
        p.set("feather", None,
              "single target: every frame covers the same sky, so there are no "
              "coverage boundaries to blend")
    p.set("out", "result", "")

    # -- feasibility -------------------------------------------------------
    if s.plate_scale:
        eff = scale if driz else 1.0
        p.canvas = (int(s.span_w * 3600.0 / s.plate_scale * eff),
                    int(s.span_h * 3600.0 / s.plate_scale * eff))
        # seqapplyreg -framing=max does NOT write canvas-sized frames: each
        # registered frame keeps its own footprint scaled by drizzle, and the
        # canvas is only assembled at stack time. Measured on the NGC 7000
        # mosaic: 16.9 MB/frame compressed at 1.5x, i.e. 27 GB not 162 GB.
        per_frame = (s.naxis1 * eff) * (s.naxis2 * eff) * 3 * 4 if s.naxis1 else 0
        # Plus the intermediates that live alongside it: the linked CFA sequence
        # and one copy per prefix step (pp_, bkg_pp_), all at native scale.
        steps = 2 + (1 if p.get("bg_extract") else 0)
        intermediates = (s.naxis1 * s.naxis2 * 4 * steps) if s.naxis1 else 0
        p.disk_gb = (per_frame + intermediates) * s.n_frames / 1024**3
        # Measured ~3x for Rice q16-q64 on Seestar registered sequences.
        p.disk_gb_compressed = p.disk_gb / 3.0
        p.free_gb = shutil.disk_usage(working).free / 1024**3

    # -- warnings ----------------------------------------------------------
    if len(s.exposures) > 1:
        parts = ", ".join(f"{fmt_exp(e)} x{n}" for e, n in s.exposures.items())
        p.warnings.append(
            f"Mixed exposures ({parts}). -norm=addscale brings them to a common "
            "level, but rejection still clips across two brightness populations. "
            "If the result looks wrong, stack each exposure separately and combine."
        )
    if len(s.gains) > 1:
        p.warnings.append(
            f"Mixed gain ({', '.join(str(g) for g in s.gains)}). That changes the "
            "noise model between frames; normalisation does not fully absorb it."
        )
    if s.temps and (max(s.temps) - min(s.temps)) > 15:
        p.warnings.append(
            f"Sensor temperature spans {min(s.temps):.0f}-{max(s.temps):.0f}C "
            "across the set, so dark current differs between frames."
        )
    # Only when we actually looked: "not checked" is not "not found", and telling
    # a user their catalogue is missing when nothing probed for it is worse than
    # silence — it is the kind of confident wrong answer they would act on.
    if gaia is None and gaia_checked:
        p.warnings.append(
            "Local Gaia astrometry catalogue not found. seqplatesolve will fail "
            "offline and Siril falls back to star registration — a mosaic will "
            "NOT assemble."
        )
    need = p.disk_gb_compressed if p.get("compress") else p.disk_gb
    if need and need > p.free_gb * 0.8:
        p.warnings.append(
            f"-framing=max projects every frame onto the full {p.canvas[0]}x"
            f"{p.canvas[1]} canvas: ~{need:.0f} GB needed against {p.free_gb:.0f} GB "
            "free. Lower the drizzle scale (cost scales with its square) or stack "
            "in parts."
        )
    return p


def reconcile(p: Proposal) -> None:
    """Resolve settings Siril silently drops when combined.

    ``-weight=noise`` is ignored outright when ``-overlap_norm`` is on ("Weighting
    by noise cannot be used with overlap normalization, ignoring weights") — and
    that is exactly the mosaic + mixed-exposure case where noise weighting was
    wanted. Overlap normalisation is the more valuable of the two on a mosaic, so
    keep it and say plainly what was given up. Verified: wfwhm and nbstars do not
    conflict.
    """
    if p.get("overlap_norm") and p.get("weight") == "noise":
        p.set("weight", "wfwhm",
              "noise weighting is incompatible with overlap normalisation and "
              "Siril would silently ignore it; overlap norm matters more on a "
              "mosaic, so weight on star quality instead")
        p.warnings.append(
            "Noise weighting was wanted here (mixed exposures) but cannot be "
            "combined with overlap normalisation, so wFWHM is used instead. The "
            "exposure-to-exposure SNR difference is then handled by -norm=addscale "
            "alone. To weight by noise, pass --no-overlap-norm and accept weaker "
            "protection of large-scale structure across the mosaic."
        )


def fmt_exp(e: float) -> str:
    return f"{int(e) if e == int(e) else e}s"


def naztronomy_name(hdr, drizzle: bool, scale: float, when, suffix: str = "_og") -> str:
    """Naztronomy's output filename, from the stacked image's own header.

    Mirrors save_image() in Naztronomy-Smart_Telescope_PP.py:
        <OBJECT>_<STACKCNT:03d>x<EXPTIME>sec_<DATE-OBS>[_drizzle-N-Nx]_<now>_og

    Note EXPTIME is whatever Siril wrote for the stack — with mixed exposures
    that is the reference frame's, so the name understates the set. Naztronomy's
    own output has the same property; keeping it keeps the names parseable.
    """
    obj = str(hdr.get("OBJECT", "Unknown")).strip().replace(" ", "_")
    exptime = int(hdr.get("EXPTIME", 0) or 0)
    stackcnt = int(hdr.get("STACKCNT", 0) or 0)
    date_obs = str(hdr.get("DATE-OBS", "") or "")
    try:
        from datetime import datetime as _dt
        date_str = _dt.fromisoformat(date_obs).strftime("%Y-%m-%d")
    except ValueError:
        date_str = when.strftime("%Y-%m-%d")

    name = f"{obj}_{stackcnt:03d}x{exptime}sec_{date_str}"
    if drizzle:
        name += "_drizzle-" + str(round(scale, 2)).replace(".", "-") + "x"
    return name + f"_{when.strftime('%Y-%m-%d_%H%M')}{suffix}"


# --------------------------------------------------------------------------
# preset interop
# --------------------------------------------------------------------------


def load_preset(working: Path) -> dict:
    """The Naztronomy preset M110's own prep wrote, or {}. Read through
    `siril._read_preset` so the two agree on what an unreadable file means."""
    return siril_mod._read_preset(working / "presets" / PRESET_NAME)


def check_preset(preset: dict, s: Survey, p: Proposal) -> None:
    if not preset:
        return
    declared = str(preset.get("filter", "")).lower()
    if declared and s.filters:
        actual = max(s.filters, key=s.filters.get)
        if ("no filter" in declared or "broadband" in declared) and actual.upper().startswith("LP"):
            p.warnings.append(
                f"The M110 preset declares filter '{preset['filter']}' but the "
                f"frames are {actual}. That mislabels the data for SPCC."
            )
    if preset.get("drizzle") and p.get("drizzle") is not None:
        pd, pf = preset.get("drizzle_amount"), preset.get("pixel_fraction")
        if (pd, pf) != (p.get("drizzle_scale"), p.get("pixfrac")):
            p.warnings.append(
                f"The M110 preset asks for drizzle {pd}x / {pf}. Coverage depth of "
                f"{s.depth_median} supports "
                f"{p.get('drizzle_scale')}x / {p.get('pixfrac')}. The preset is "
                "keyed on total frame count, which overstates depth on a mosaic."
            )


# --------------------------------------------------------------------------
# script generation
# --------------------------------------------------------------------------


def seq_names(lights_name: str, p: Proposal) -> tuple[str, str]:
    """(pre-registration sequence, registered sequence) for the chosen settings."""
    seq = f"pp_{lights_name}_"
    if p.get("bg_extract"):
        seq = f"bkg_{seq}"
    return seq, f"r_{seq}"


def find_degenerate(process_dir: Path, reg_seq: str) -> list[int]:
    """1-based positions of registered frames that came out effectively empty.

    seqapplyreg can emit a frame with almost no valid pixels — a sub whose plate
    solution placed it off the common canvas. Whole-image normalisation then dies
    on it ("stats failed for N in seq", "Normalization failed. Check image N+1"),
    taking the whole stack with it after all the expensive work is done.
    Compressed file size is a reliable and very cheap proxy: the empty frame in
    the NGC 7000 run was 1.0 MB against a 17.1 MB median.
    """
    files = sorted(process_dir.glob(f"{reg_seq}*.fit*"))
    if len(files) < 3:
        return []
    sizes = [f.stat().st_size for f in files]
    mid = sorted(sizes)[len(sizes) // 2]
    return [i + 1 for i, s in enumerate(sizes) if s < mid * 0.5]


def build_ssf_register(lights_name: str, p: Proposal,
                       unselect: list[int] | None = None) -> str:
    """Phase 1: everything up to and including registration."""
    seq = f"{lights_name}_"
    L = [
        "# Generated by m110-stack — Naztronomy Smart Telescope method.",
        "# Phase 1 of 2: calibrate, background-extract, plate solve, register.",
        "requires 1.4.0",
        "",
        f"cd {lights_name}",
        "# link, not convert: leaves the CFA intact for the drizzle decision below.",
        f"link {lights_name} -out=../process",
        "cd ../process",
        "",
    ]
    if unselect:
        L.append("# Frame selection: calibrate and everything after skip excluded "
                 "frames.")
        L += [f"unselect {seq} {a} {b}" for a, b in as_ranges(unselect)]
        L.append("")

    if p.get("compress"):
        L += [
            "# Compress the intermediates. The registered sequence is by far the",
            "# biggest thing this pipeline writes; Rice quantisation is noise-scaled.",
            f"setcompress 1 -type=rice {p.get('compress_quant')}",
            "",
        ]

    if p.get("debayer"):
        L += ["# -debayer because drizzle is off; without it the stack is monochrome.",
              f"calibrate {seq} -debayer", ""]
    else:
        L += ["# No -debayer: drizzle needs raw CFA and demosaics as it resamples.",
              f"calibrate {seq}", ""]
    seq = f"pp_{seq}"

    if p.get("bg_extract"):
        L += [f"seqsubsky {seq} 1 -samples=10 -tolerance=2.0", ""]
        seq = f"bkg_{seq}"

    L += [
        "# Plate solve with SIP distortion — this is what lets -framing=max",
        "# assemble a mosaic with no panel sorting and no separate stitch.",
        f"seqplatesolve {seq} -nocache -force -disto=ps_distortion -order=4 -radius=25",
        "",
    ]

    reg = [f"seqapplyreg {seq}", "-kernel=square", "-framing=max"]
    if p.get("filters"):
        f = p.get("filters")
        reg += [
            f"-filter-round={f['roundness']}%",
            f"-filter-wfwhm={f['fwhm']}%",
            f"-filter-bkg={f['bg']}%",
            f"-filter-nbstars={f['star_count']}%",
        ]
    if p.get("drizzle"):
        reg += ["-drizzle", f"-scale={p.get('drizzle_scale')}",
                f"-pixfrac={p.get('pixfrac')}"]
    L += [" ".join(reg), "", "close", ""]
    return "\n".join(L)


def build_ssf_stack(lights_name: str, p: Proposal, drop: list[int]) -> str:
    """Phase 2: stack the registered sequence, excluding any empty frames.

    Separate from phase 1 so the degenerate-frame check can run in between, and
    so stack settings can be re-tried without repeating registration — on a large
    mosaic the stack is nearly all of the wall clock, but registration is still
    minutes you should not have to pay twice.
    """
    _, seq = seq_names(lights_name, p)
    L = [
        "# Generated by m110-stack — phase 2 of 2: stack.",
        "requires 1.4.0",
        "",
        "cd process",
        "# Deliverable uncompressed, so downstream tools see a plain FITS.",
        "setcompress 0",
        "",
    ]
    if drop:
        L.append("# Empty registered frames: whole-image normalisation dies on "
                 "these.")
        L += [f"unselect {seq} {i} {i}" for i in drop]
        L.append("")

    stack = [f"stack {seq}", f"rej {p.get('rejection')}", "-norm=addscale",
             "-output_norm", "-maximize", "-filter-included", "-32b"]
    if p.get("overlap_norm"):
        stack.append("-overlap_norm")
    if p.get("rgb_equal"):
        stack.append("-rgb_equal")
    if p.get("weight"):
        stack.append(f"-weight={p.get('weight')}")
    if p.get("feather"):
        stack.append(f"-feather={p.get('feather')}")
    stack.append(f"-out=../{p.get('out')}")
    L += [" ".join(stack), "", "close", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def format_report(s: Survey, p: Proposal, siril: str, working: Path,
                  lights: Path) -> str:
    """The human-readable proposal as text. Returns rather than prints: engine
    modules must not write to stdout (the MCP server speaks JSON-RPC there), so
    the CLI owns the printing."""
    out: list[str] = []
    out.append(f"\nSiril     {siril}")
    out.append(f"Working   {working}")
    out.append(f"Lights    {lights}\n")

    out.append("Dataset")
    if s.object_name:
        out.append(f"  object            {s.object_name}")
    out.append(f"  frames            {s.n_frames}   ({s.integration_min:.0f} min raw integration)")
    out.append(f"  exposures         {', '.join(f'{fmt_exp(e)} x{n}' for e, n in s.exposures.items())}")
    out.append(f"  filters           {', '.join(f'{k} x{v}' for k, v in s.filters.items())}")
    if s.gains:
        out.append(f"  gain              {', '.join(f'{g} x{n}' for g, n in s.gains.items())}")
    if s.temps:
        out.append(f"  sensor temp       {min(s.temps):.0f} to {max(s.temps):.0f} C")
    if len(s.nights) > 1:
        out.append(f"  nights            {len(s.nights)}")
        for d, v in s.nights.items():
            exps = ", ".join(f"{fmt_exp(e)} x{n}" for e, n in v["exposures"].items())
            out.append(f"                      {d}  {v['frames']:4d} frames  {exps}")
    if s.plate_scale:
        out.append(f"  plate scale       {s.plate_scale:.2f} arcsec/px")
        out.append(f"  field of view     {s.fov_w:.2f} x {s.fov_h:.2f} deg")
        out.append(f"  sky coverage      {s.span_w:.2f} x {s.span_h:.2f} deg")
    out.append(f"  layout            {'MOSAIC' if s.is_mosaic else 'single target'}")
    out.append(f"  coverage depth    {s.depth_median} frames at a typical point"
          f"{f' (thinnest {s.depth_min})' if s.depth_min != s.depth_median else ''}")

    out.append("\nProposed settings")
    rows = [
        ("drizzle", f"{p.get('drizzle_scale')}x / pixfrac {p.get('pixfrac')}"
                    if p.get("drizzle") else "off (1.0x)"),
        ("debayer", "yes" if p.get("debayer") else "no (drizzle handles CFA)"),
        ("rejection", f"rej {p.get('rejection')}"),
        ("weighting", p.get("weight") or "off"),
        ("overlap norm", "on" if p.get("overlap_norm") else "off"),
        ("feather", f"{p.get('feather')} px" if p.get("feather") else "off"),
        ("rgb_equal", "on" if p.get("rgb_equal") else "off"),
        ("bg extraction", "on" if p.get("bg_extract") else "off"),
        ("quality filters", "98% round/wfwhm/bkg/stars" if p.get("filters") else "off"),
        ("compression", f"rice q{p.get('compress_quant')}" if p.get("compress") else "off"),
    ]
    for k, v in rows:
        why = p.settings[{"overlap norm": "overlap_norm", "bg extraction": "bg_extract",
                          "quality filters": "filters", "weighting": "weight",
                          "compression": "compress"}.get(k, k)].why
        out.append(f"  {k:17} {v}")
        if why:
            for line in wrap(why, 68):
                out.append(f"  {'':17} {line}")

    if p.canvas[0]:
        out.append(f"\nProjection")
        out.append(f"  canvas            {p.canvas[0]} x {p.canvas[1]} px")
        if p.get("compress"):
            out.append(f"  peak process/     ~{p.disk_gb_compressed:.0f} GB compressed "
                  f"(~{p.disk_gb:.0f} GB uncompressed)")
        else:
            out.append(f"  peak process/     ~{p.disk_gb:.0f} GB")
        out.append(f"  free space        {p.free_gb:.0f} GB")

    if p.warnings:
        out.append("\nWorth knowing")
        for w in p.warnings:
            for i, line in enumerate(wrap(w, 72)):
                out.append(f"  {'!' if i == 0 else ' '} {line}")
    return "\n".join(out)


def run_siril(siril: str, working: Path, ssf: str, log_path: Path,
              heartbeat: int, on_line=None) -> tuple[int, list[str]]:
    """Run the script, streaming progress instead of hoarding it until the end.

    Siril's stdout goes to the log line by line as it arrives, and a heartbeat
    reports the current stage with elapsed time. Long steps — a 900-frame stack
    can run for hours — emit nothing on their own, so without the heartbeat
    there is no way to tell "working hard" from "wedged".

    `on_line(str)` receives each heartbeat line. The CLI passes `print`; leaving
    it None makes this silent, which is what lets a caller with its own progress
    surface (or a test) drive the same code.
    """
    import threading
    import time

    t0 = time.monotonic()
    state = {"stage": "starting", "progress": "", "stage_at": t0, "errors": []}

    # `_child_env` is not optional: a frozen M110 exports QT_PLUGIN_PATH,
    # QML*_IMPORT_PATH and _MEI* into its children, and Siril's own bundled
    # Python then loads our Qt beside its PyQt6 — two Qt sets in one process,
    # SIGABRT. Same sanitizer the "Process in Siril" launcher uses.
    proc = subprocess.Popen(
        [siril, "-d", str(working), "-s", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=launch._child_env(),
        encoding="utf-8", errors="replace",
    )

    def reader():
        with open(log_path, "w", buffering=1, encoding="utf-8",
                  errors="replace") as log:
            for line in proc.stdout:
                log.write(line)
                s = line.rstrip()
                low = s.lower()
                if "running command:" in low:
                    state["stage"] = s.split(":")[-1].strip()
                    state["stage_at"] = time.monotonic()
                    state["progress"] = ""
                elif s.startswith("progress:"):
                    state["progress"] = s[len("progress:"):].strip()
                elif (any(k in low for k in ("error", "failed", "not found"))
                      and "python" not in low):
                    state["errors"].append(s)

    proc.stdin.write(ssf)
    proc.stdin.close()
    threading.Thread(target=reader, daemon=True).start()

    def stamp(t):
        return f"{int(t) // 60:3d}:{int(t) % 60:02d}"

    last_stage, last_beat = None, 0.0
    while proc.poll() is None:
        time.sleep(1)
        now = time.monotonic()
        changed = state["stage"] != last_stage
        if changed or now - last_beat >= heartbeat:
            el = now - t0
            line = f"  [{stamp(el)}] {state['stage']}"
            if not changed:
                line += f"  ({stamp(now - state['stage_at'])} in this step)"
            if state["progress"]:
                line += f"  |  {state['progress'][:60]}"
            if on_line:
                on_line(line)
            last_stage, last_beat = state["stage"], now

    proc.wait()
    if on_line:
        on_line(f"  [{stamp(time.monotonic() - t0)}] done")
    return proc.returncode, state["errors"]


def wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


@dataclass
class Overrides:
    """Every settings override the CLI exposes, as data.

    `build_plan` takes this rather than an argparse namespace so the assistant
    (which has no argparse) reaches exactly the same proposal path the CLI does.
    Field names match the long flags, so `main` fills it reflectively and the two
    cannot drift.
    """
    drizzle: float | None = None
    pixfrac: float | None = None
    no_drizzle: bool = False
    rejection: str | None = None
    weight: str | None = None
    ov: bool | None = None
    rgb_equal: bool = False
    no_bg_extract: bool = False
    no_filters: bool = False
    filter_pct: float | None = None
    feather: int | None = None
    no_compress: bool = False
    compress_quant: int | None = None
    out: str | None = None
    only_exposure: list | None = None
    only_night: list | None = None
    exclude_night: list | None = None


@dataclass
class StackPlan:
    """A measured dataset plus the settings proposed for it, and the exact Siril
    scripts those settings produce. Read-only: building one writes nothing."""
    survey: Survey
    proposal: Proposal
    working: Path
    lights: Path
    siril: str | None
    register_ssf: str
    stack_ssf: str
    frames_total: int
    dropped: list

    def as_json(self) -> dict:
        """The machine-readable proposal — `--json` and the assistant tool both
        return exactly this, so what a model reads is what the CLI printed."""
        p, s = self.proposal, self.survey
        return {
            "survey": s.public(),
            "settings": {k: v.value for k, v in p.settings.items()},
            "justifications": {k: v.why for k, v in p.settings.items() if v.why},
            "warnings": p.warnings,
            "canvas": list(p.canvas),
            "disk_gb": round(p.disk_gb, 1),
            "disk_gb_compressed": round(p.disk_gb_compressed, 1),
            "free_gb": round(p.free_gb, 1),
            "script": self.register_ssf,
        }


def build_plan(directory, ov: Overrides | None = None, *, siril: str | None = None,
               deep_measure: bool = True) -> StackPlan:
    """Measure the data and propose settings. **Writes nothing.**

    `deep_measure=False` skips the two enrichments that shell out to Siril — the
    local-Gaia probe and the per-exposure FWHM measurement — so the whole call is
    pure header reads. That is the mode the assistant uses: it keeps a read-only
    tool genuinely read-only, at the cost of two warnings it cannot raise.
    """
    ov = ov or Overrides()
    working, lights = resolve_layout(resolve_input(directory))

    all_frames, geom = read_frames(lights)
    kept, dropped = select_frames(all_frames, ov.only_exposure, ov.exclude_night,
                                  ov.only_night)
    if not kept:
        raise StackingError("Frame selection excluded everything — nothing to stack.")
    s = summarize(kept, geom)

    gaia = None
    if deep_measure and siril:
        gaia = gaia_catalogue(siril)
        s.fwhm_by_exposure = measure_fwhm_by_exposure(siril, lights, s)
    p = build_proposal(s, gaia, working, gaia_checked=bool(deep_measure and siril))
    if not deep_measure:
        p.warnings.append(
            "Measured from headers only. Two checks that need to run Siril were "
            "skipped: whether the local Gaia catalogue is present (without it a "
            "mosaic will not assemble) and the per-exposure FWHM comparison. Run "
            "`m110-stack <dir>` for those two."
        )
    if dropped:
        p.warnings.append(
            f"Frame selection: stacking {len(kept)} of {len(all_frames)} frames, "
            f"excluding {len(dropped)}. Everything above — depth, drizzle, "
            "weighting, integration — is computed on the selected set."
        )
    check_preset(load_preset(working), s, p)

    # ---- apply overrides -------------------------------------------------
    if ov.drizzle is not None:
        p.set("drizzle", True, "set on the command line")
        p.set("drizzle_scale", ov.drizzle, "")
        p.set("debayer", False, "drizzle is on, so the CFA must stay raw")
    if ov.pixfrac is not None:
        p.set("pixfrac", ov.pixfrac, "")
    if ov.no_drizzle:
        p.set("drizzle", False, "disabled on the command line")
        p.set("drizzle_scale", 1.0, "")
        p.set("debayer", True, "drizzle is off, so the CFA must be debayered here")
    if ov.rejection:
        p.set("rejection", ov.rejection, "set on the command line")
    if ov.weight:
        p.set("weight", None if ov.weight == "none" else ov.weight, "set on the command line")
    if ov.ov is not None:
        p.set("overlap_norm", ov.ov, "set on the command line")
    if ov.rgb_equal:
        p.set("rgb_equal", True, "set on the command line")
    if ov.no_bg_extract:
        p.set("bg_extract", False, "disabled on the command line")
    if ov.no_filters:
        p.set("filters", None, "disabled on the command line")
    elif ov.filter_pct is not None:
        p.set("filters", {k: ov.filter_pct for k in DEFAULT_FILTERS},
              f"all four thresholds set to {ov.filter_pct:g}% on the command line")
    if ov.feather:
        p.set("feather", ov.feather, "set on the command line")
    if ov.no_compress:
        p.set("compress", False, "disabled on the command line")
    if ov.compress_quant is not None:
        p.set("compress_quant", ov.compress_quant, "set on the command line")
    if ov.out:
        p.set("out", ov.out, "")

    # After overrides, so a hand-picked combination is checked too.
    reconcile(p)

    ssf = build_ssf_register(lights.name, p, dropped)
    ssf_stack = build_ssf_stack(lights.name, p,
                                find_degenerate(working / "process",
                                                seq_names(lights.name, p)[1]))

    return StackPlan(
        survey=s, proposal=p, working=working, lights=lights, siril=siril,
        register_ssf=build_ssf_register(lights.name, p, dropped),
        stack_ssf=build_ssf_stack(lights.name, p,
                                  find_degenerate(working / "process",
                                                  seq_names(lights.name, p)[1])),
        frames_total=len(all_frames), dropped=dropped,
    )


# --------------------------------------------------------------------------
# handoff to a post-processing workflow
# --------------------------------------------------------------------------

# Where a finished stack goes when handed on. Keyed by workflow, so a second
# post-processing tool is one entry. `siril` is deliberately absent: it is the
# stacker at the head of the chain, not a destination.
_HANDOFF_DIRS = {"astrowizard": config.astrowizard_dir}

SIDECAR_SUFFIX = ".src.json"


def handoff_targets() -> list[str]:
    return sorted(_HANDOFF_DIRS)


# HISTORY substrings that mean the data is no longer linear. Deliberately only
# *stretches* — background extraction, plate solving, SPCC, deconvolution and
# denoise all leave the data linear, and treating them as disqualifying would rule
# out perfectly good inputs. Matched against Siril's own HISTORY cards and the
# ones third-party tools write through it (VeraLux, Seti Astro).
_STRETCH_MARKERS = (
    "stretch", "histogram transf", "asinh", "midtone", "hyperbolic",
    "curves", "autostretch",
)


def _is_stretched(history: list[str]) -> bool:
    """Whether a stack's recorded HISTORY shows a stretch has been applied.

    Read from the header rather than guessed from the filename, because the
    filename is a convention and this is a fact the pipeline recorded. On a real
    library `stacks/` holds `_og`, `_denoise` and `_finished` side by side, and
    only the header separates them reliably: `_denoise` sounds like a linear step
    and is not, its HISTORY carrying "VeraLux v1.5.2 Stretch" three entries back.
    """
    low = " | ".join(history).lower()
    return any(m in low for m in _STRETCH_MARKERS)


def _provenance(stack: Path) -> dict:
    """What this stack *is*, from facts the pipeline recorded in its header.

    Deliberately not mtime and not a content hash: ingest and import both copy
    bytes, so mtime is copy time and lies; and hashing a multi-GB stack to answer
    "is this still current?" is expensive for no extra certainty. A stack's own
    `DATE`, `STACKCNT` and `LIVETIME` are written by Siril when it made the file,
    so a re-stack changes them and the staleness is visible for free. Same
    identity-not-timestamp reasoning as the `hero/<slug>.src` sidecar (#17).
    """
    info = {"source": stack.name, "size_bytes": stack.stat().st_size}
    try:
        h = _fits().getheader(stack)
    except (OSError, ValueError):
        return info
    steps = [str(x).strip() for x in h.get("HISTORY", [])]
    if steps:
        info["stretched"] = _is_stretched(steps)
    for card, key in (("DATE", "stacked_at"), ("STACKCNT", "frames"),
                      ("LIVETIME", "integration_sec"), ("OBJECT", "object"),
                      ("FILTER", "filter")):
        v = h.get(card)
        if v is not None:
            info[key] = str(v).strip() if isinstance(v, str) else v
    return info


@dataclass
class HandoffCandidate:
    """One stack that could be handed to a post-processing workflow."""
    path: Path
    tier: str                      # "stacks" | "seestar-stacks" | "siril"
    size_bytes: int
    frames: int | None = None
    integration_min: float | None = None
    stacked_at: str | None = None
    filter: str | None = None
    already: bool = False          # a file of this name is already handed over
    stretched: bool | None = None  # None = no HISTORY to judge from

    @property
    def name(self) -> str:
        return self.path.name


def _sandbox_stacks(target: str) -> list[Path]:
    """FITS sitting loose in a Siril job dir — a stack that has been made but not
    yet imported. Only the job roots: `lights/`, `process/`, `presets/` and
    `archive/` are inputs, scratch and history, never a fresh deliverable."""
    from m110 import siril as siril_mod

    out: list[Path] = []
    for job in siril_mod.working_dirs(target):
        out += [q for q in job.iterdir()
                if q.is_file() and config.is_fits_file(q.name)]
    return out


def _candidate_paths(target: str) -> list[tuple[str, Path]]:
    """`(tier, path)` for every stack that could be handed over. Directory reads
    only — no headers — so a caller that just needs "are there any?" does not pay
    for provenance it will throw away. That caller is the object detail pane,
    which asks on every render.

    Intermediates are excluded here, through the shared `hints` vocabulary rather
    than a local rule, so a user's edits to it apply. A `starless_` or `starmask_`
    file carries the same STACKCNT and LIVETIME as the stack it came from, so it
    sorts to the very top on merit and is exactly wrong: those are derived layers,
    not the image. Observed on a real NGC 6543 sandbox, where the two most recent
    files were precisely that pair.
    """
    from m110 import hints

    found: list[tuple[str, Path]] = []
    for tier, d in (("stacks", config.stacks_dir(target)),
                    ("seestar-stacks", config.seestar_stacks_dir(target))):
        if d.is_dir():
            found += [(tier, q) for q in d.iterdir()
                      if q.is_file() and config.is_fits_file(q.name)]
    found += [("siril", q) for q in _sandbox_stacks(target)]
    return [(tier, q) for tier, q in found if not hints.is_intermediate_name(q.name)]


def has_handoff_candidates(target: str) -> bool:
    """Cheap "is there anything to hand over?" — see `_candidate_paths`."""
    return bool(_candidate_paths(target))


def handoff_candidates(target: str,
                       tool: str = "astrowizard") -> list[HandoffCandidate]:
    """Stacks that could be handed to `tool`, best first. **Reads only.**

    Three tiers, because a finished stack legitimately lives in any of them: the
    managed `stacks/` tier, the device's own in-app stacks, and a fresh result
    still sitting in the Siril sandbox before it has been imported. That last is
    the common case right after a run, and omitting it would mean the handoff
    could not be used until the user had done an import they may not want yet.

    Ordered newest-stacked first, since the stack someone wants to finish is
    almost always the one they just made. Anything whose header cannot be read
    still appears — it may be perfectly good, and hiding it would be worse than
    showing it without its facts.
    """
    dest_fn = _HANDOFF_DIRS.get(tool)
    if dest_fn is None:
        raise StackingError(
            f"Unknown handoff target {tool!r}. Known: {', '.join(handoff_targets())}.")
    dest = dest_fn(target)
    existing = {q.name for q in dest.iterdir()} if dest.is_dir() else set()

    out: list[HandoffCandidate] = []
    for tier, path in _candidate_paths(target):
        prov = _provenance(path)
        live = prov.get("integration_sec")
        out.append(HandoffCandidate(
            path=path, tier=tier, size_bytes=prov.get("size_bytes", 0),
            frames=prov.get("frames"),
            integration_min=round(float(live) / 60.0, 1) if live else None,
            stacked_at=prov.get("stacked_at"), filter=prov.get("filter"),
            already=path.name in existing, stretched=prov.get("stretched"),
        ))
    # Newest first; undated stacks sort last rather than being dropped.
    out.sort(key=lambda c: (c.stacked_at or "", c.size_bytes), reverse=True)
    return out


def apply_handoff(stack: Path, tool: str = "astrowizard") -> Path:
    """Hardlink a finished stack into its post-processing sandbox. **Writes.**

    This is the sanctioned writer for the handoff: it runs in the CLI the user
    invoked, never from the assistant, and the app's future "Send stack to…"
    action calls the same code so there is one implementation of the convention.

    The stack is hardlinked, so a handoff costs no disk; and the sandbox is a
    sibling of `siril/` rather than a subdir because the two artifacts have
    different lifetimes — see `config.SANDBOX_DIRNAMES`.
    """
    stack = Path(stack).resolve()
    dir_fn = _HANDOFF_DIRS.get(tool)
    if dir_fn is None:
        raise StackingError(
            f"Unknown handoff target {tool!r}. Known: {', '.join(handoff_targets())}.")
    target = target_for(stack.parent)
    if not target:
        raise StackingError(
            f"{stack.parent} is not inside the M110 store, so there is no capture "
            "target to hand off to. Stack inside Images/<target>/siril/ instead.")

    dest_dir = dir_fn(target)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / stack.name
    siril_mod._link_or_copy(str(stack), str(dest))
    (dest_dir / (stack.name + SIDECAR_SUFFIX)).write_text(
        json.dumps(_provenance(stack), indent=2), encoding="utf-8")
    return dest


def _printer(line: str) -> None:
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Headless Siril stacking, Naztronomy method. "
                    "Measures and proposes by default; --run executes.")
    ap.add_argument("directory", metavar="DIR|TARGET",
                    help="a working directory, or a capture-folder name in the "
                         "M110 store (e.g. \"NGC 6543\")")
    ap.add_argument("--run", action="store_true", help="execute (default: propose only)")
    ap.add_argument("--json", action="store_true", help="machine-readable proposal")
    ap.add_argument("--ssf", type=Path, help="write the generated .ssf here")
    ap.add_argument("--out", help="working name for the stack (default: result)")
    ap.add_argument("--restack", action="store_true",
                    help="reuse the registered sequence already in process/ and "
                         "run only the stack — for retrying stack settings without "
                         "repeating registration. Pair with --keep-process to "
                         "iterate further.")
    ap.add_argument("--keep-process", action="store_true",
                    help="keep the process/ scratch dir; by default it is removed "
                         "after a successful stack (tens of GB on a mosaic)")
    ap.add_argument("--heartbeat", type=int, default=60, metavar="SEC",
                    help="how often to print the current stage while running "
                         "(default 60s; steps can be silent for hours)")
    ap.add_argument("--handoff", metavar="TOOL", nargs="?", const="astrowizard",
                    help="after a successful stack, hardlink it into that "
                         "workflow's sandbox (Images/<target>/<tool>/) with a "
                         "provenance sidecar, ready to open. Default: astrowizard")
    ap.add_argument("--plain-name", action="store_true",
                    help="keep --out as the final name instead of renaming to "
                         "Naztronomy's <OBJECT>_<N>x<exp>sec_<date>_drizzle-..._og")

    g = ap.add_argument_group("overrides")
    g.add_argument("--only-exposure", type=float, action="append", metavar="SEC",
                   help="stack only frames at this exposure (repeatable)")
    g.add_argument("--only-night", action="append", metavar="YYYY-MM-DD",
                   help="stack only frames from this night (repeatable)")
    g.add_argument("--exclude-night", action="append", metavar="YYYY-MM-DD",
                   help="drop a night, e.g. one with poor seeing (repeatable)")
    g.add_argument("--drizzle", type=float, metavar="SCALE")
    g.add_argument("--pixfrac", type=float)
    g.add_argument("--no-drizzle", action="store_true")
    g.add_argument("--rejection", help='e.g. "w 3 3", "l 5 5", "p 0.2 0.1", "none"')
    g.add_argument("--weight", choices=["noise", "wfwhm", "nbstars", "nbstack", "none"])
    # Both default to None so "not passed" is distinguishable from "passed false".
    g.add_argument("--overlap-norm", dest="ov", action="store_true", default=None)
    g.add_argument("--no-overlap-norm", dest="ov", action="store_false", default=None)
    g.add_argument("--rgb-equal", action="store_true")
    g.add_argument("--no-bg-extract", action="store_true")
    g.add_argument("--no-filters", action="store_true")
    g.add_argument("--filter-pct", type=float, metavar="PCT",
                   help="set all four quality-filter thresholds (default 95; "
                        "Naztronomy's M15 preset used 98 — higher keeps more frames)")
    g.add_argument("--feather", type=int, metavar="PX")
    g.add_argument("--no-compress", action="store_true")
    g.add_argument("--compress-quant", type=int, metavar="Q",
                   help="Rice quantisation 0-256 (default 16; higher = less loss)")

    a = ap.parse_args()

    ov = Overrides(**{f.name: getattr(a, f.name) for f in fields(Overrides)})
    try:
        siril = os.environ.get("SIRIL_CLI") or require_siril()
        plan = build_plan(a.directory, ov, siril=siril)
    except StackingError as e:
        print(f"{e}", file=sys.stderr)
        return 2
    s, p = plan.survey, plan.proposal
    working, lights, dropped = plan.working, plan.lights, plan.dropped
    ssf, ssf_stack = plan.register_ssf, plan.stack_ssf

    if a.json:
        print(json.dumps(plan.as_json(), indent=2, default=str))
        return 0

    print(format_report(s, p, siril, working, lights))

    if a.ssf:
        a.ssf.write_text(ssf + "\n" + ssf_stack, encoding="utf-8")
        print(f"\nScript written to {a.ssf}")

    if not a.run:
        print("\n--- phase 1: register " + "-" * 43)
        print(ssf)
        print("--- phase 2: stack " + "-" * 46)
        print(ssf_stack)
        print("-" * 65)
        print("Proposal only — nothing written. Re-run with --run to execute.\n")
        return 0

    # ---- execute ---------------------------------------------------------
    log_path = working / "siril_stack.log"
    print(f"\nRunning Siril in {working}")
    print(f"Live log: {log_path}\n", flush=True)

    reg_seq = seq_names(lights.name, p)[1]
    errors: list[str] = []

    if a.restack:
        n = len(sorted((working / "process").glob(f"{reg_seq}*.fit*")))
        print(f"  --restack: reusing {n} registered frames in process/\n", flush=True)
    else:
        rc, errors = run_siril(siril, working, ssf, log_path, a.heartbeat,
                               on_line=_printer)
        if rc != 0:
            print(f"\nRegistration failed (exit {rc}). Log: {log_path}\n")
            return 1

    # Catch empty registered frames before they kill the stack hours from now.
    drop = find_degenerate(working / "process", reg_seq)
    if drop:
        print(f"  Excluding {len(drop)} empty registered frame(s) at sequence "
              f"position(s) {', '.join(map(str, drop))} — whole-image "
              f"normalisation cannot compute statistics on them.\n", flush=True)
        ssf_stack = build_ssf_stack(lights.name, p, drop)

    rc, errs2 = run_siril(siril, working, ssf_stack, log_path.with_name(
        "siril_stack_stack.log"), a.heartbeat, on_line=_printer)
    errors += errs2

    for e in errors[:10]:
        print(f"  ! {e}", flush=True)

    produced = sorted(working.glob(f"{p.get('out')}.fit*"))
    print(f"\nLog: {log_path}")
    if rc != 0 or not produced:
        print(f"FAILED (exit {rc}). Check the log.\n")
        return 1
    from datetime import datetime
    now = datetime.now()
    fits = _fits()
    stacked: list[Path] = []
    for f in produced:
        h = fits.getheader(f)
        if not a.plain_name:
            new = f.with_name(
                naztronomy_name(h, p.get("drizzle"), p.get("drizzle_scale"), now)
                + f.suffix
            )
            f.rename(new)
            f = new
        stacked.append(f)
        colour = "colour" if h.get("NAXIS3") == 3 else "MONO — check the debayer path"
        print(f"Stacked: {f}")
        print(f"         {f.stat().st_size / 1024**2:.0f} MB, {colour}, "
              f"{h.get('STACKCNT')} frames, {float(h.get('LIVETIME', 0))/60:.0f} min "
              f"integrated")

    if a.handoff:
        for f in stacked:
            try:
                dest = apply_handoff(f, a.handoff)
            except StackingError as e:
                print(f"  ! handoff skipped: {e}")
                break
            print(f"Handed to {a.handoff}: {dest}")

    # Only after a verified stack exists — the scratch is the sole copy of the
    # registered sequence, so never remove it on a failed or partial run.
    scratch = working / "process"
    if scratch.is_dir():
        size_gb = sum(p.stat().st_size for p in scratch.rglob("*") if p.is_file()) / 1024**3
        if a.keep_process:
            print(f"Kept:    {scratch}  ({size_gb:.0f} GB)")
        else:
            shutil.rmtree(scratch)
            print(f"Cleaned: {scratch}  ({size_gb:.0f} GB freed)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

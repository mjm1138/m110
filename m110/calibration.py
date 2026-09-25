"""Pick the calibration master a target needs from the device-level library.

``Calibration/<device>/{darks,flats,biases}/`` (config.calibration_dir) holds
MASTER frames that belong to a telescope, not to a target — the DwarfLab Draco
ships darks across exposure × gain × binning × sensor temperature, flats per
filter, one bias. This module answers "which one for *this* set of lights?"
from **headers only**: the masters' IMAGETYP / EXPTIME / GAIN / XBINNING /
CCD-TEMP / FILTER / NCOMBINE, and the lights' EXPTIME / GAIN / XBINNING /
DET-TEMP (or CCD-TEMP) / FILTER / TELESCOP. It never reads a filename for a
fact — the headerless pre-release masters get theirs stamped at import
(ingest.py's shim), which is what keeps this module permanent.

Rules (`match_masters`):

* **dark** — same exposure, gain and binning; then the nearest sensor
  temperature (ties → the master averaged from more frames). A dark at the wrong
  exposure or gain is worse than none, so those never match.
* **bias** — same binning; the same gain when any candidate has it, else the sole
  candidate with a note (the Draco's flats/bias say ``gain 2`` where its lights
  say 60 — the scale is unverified).
* **flat** — same binning and a filter that resolves to the lights' filter. A
  DwarfLab flat's FILTER is an ``ir_<n>`` index whose mapping to a filter name
  is per device and, for the Draco, **unverified** (`FILTER_INDEX`), so two flats
  that could both apply yield none and a note rather than a guess.

A target whose sampled lights mix exposure/gain/binning is refused with a note:
BUGS.md — "a mixed workspace must match calibration per job or refuse it". The
stacker matches on the frames it actually selected, so ``--only-exposure``
makes such a target stackable with calibration.
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import config, devices
from .ingest import _normalize_imagetyp

TIERS = config.CALIBRATION_TIERS                     # ("darks", "flats", "biases")
_TIER_OF_KIND = {"dark": "darks", "flat": "flats", "bias": "biases"}

# Per-device map of a DwarfLab flat's ``ir_<n>`` FILTER token → the filter name
# the lights carry. UNVERIFIED for the Draco (2026-09 pre-release sample has
# ir_1 and ir_2 and lights shot through 'Duo-Band'; DwarfLab has not said which
# is which). Empty → no ir_ flat can match, and `match_masters` says so.
FILTER_INDEX: dict[str, dict[str, str]] = {
    "draco": {},
    "dwarf_3": {},
}


@dataclass
class MasterInfo:
    path: Path
    tier: str
    exptime: float | None = None
    gain: int | None = None
    binning: int | None = None
    temp_c: float | None = None
    filter: str | None = None
    ncombine: int | None = None


@dataclass
class MatchResult:
    darks: Path | None = None
    flats: Path | None = None
    biases: Path | None = None
    notes: list = field(default_factory=list)
    device: str | None = None

    def as_dict(self) -> dict[str, Path]:
        """{tier: master path} for the tiers that matched."""
        return {t: p for t, p in (("darks", self.darks), ("flats", self.flats),
                                  ("biases", self.biases)) if p is not None}

    def __bool__(self) -> bool:
        return bool(self.as_dict())


def _num(v, cast=float):
    try:
        return cast(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def frame_facts(path) -> dict | None:
    """The header facts calibration matching keys on, or None if unreadable.
    ``temp_c`` is CCD-TEMP, else DET-TEMP (what the Draco writes on a light)."""
    try:
        from astropy.io import fits
        h = fits.getheader(str(path))
    except Exception:
        return None
    filt = h.get("FILTER")
    tel = h.get("TELESCOP")
    temp = h.get("CCD-TEMP")
    if temp is None:
        temp = h.get("DET-TEMP")
    return {
        "imagetyp": _normalize_imagetyp(h.get("IMAGETYP")),
        "exptime": _num(h.get("EXPTIME") if h.get("EXPTIME") is not None
                        else h.get("EXPOSURE")),
        "gain": _num(h.get("GAIN"), int),
        "binning": _num(h.get("XBINNING"), int),
        "temp_c": _num(temp),
        "filter": (str(filt).strip() or None) if filt not in (None, "") else None,
        "ncombine": _num(h.get("NCOMBINE"), int),
        "telescop": (str(tel).strip() or None) if tel not in (None, "") else None,
    }


def library(device: str) -> dict[str, list[MasterInfo]]:
    """Every master in ``Calibration/<device>/<tier>/``, keyed by tier. A file is
    kept for a tier if its IMAGETYP says so or is absent (the folder is trusted);
    one that claims another type is skipped. Tiers with nothing are omitted."""
    out: dict[str, list[MasterInfo]] = {}
    for tier in TIERS:
        d = config.calibration_dir(device, tier)
        if not d.is_dir():
            continue
        masters: list[MasterInfo] = []
        for f in sorted(d.iterdir()):
            if not f.is_file() or not config.is_fits_file(f.name):
                continue
            facts = frame_facts(f)
            if facts is None:
                continue
            kind = facts["imagetyp"]
            if kind is not None and _TIER_OF_KIND.get(kind) != tier:
                continue
            masters.append(MasterInfo(
                path=f, tier=tier, exptime=facts["exptime"], gain=facts["gain"],
                binning=facts["binning"], temp_c=facts["temp_c"],
                filter=facts["filter"], ncombine=facts["ncombine"]))
        if masters:
            out[tier] = masters
    return out


def filter_matches(light_filter: str | None, master_filter: str | None,
                   device: str | None) -> bool:
    """Does a flat shot through `master_filter` serve lights shot through
    `light_filter`? A flat with no FILTER card serves any filter; an ``ir_<n>``
    index resolves through `FILTER_INDEX` for the device (unmapped → no)."""
    if master_filter is None:
        return True
    if light_filter is None:
        return False
    m, l = master_filter.strip().lower(), light_filter.strip().lower()
    if m == l:
        return True
    if m.startswith("ir_"):
        key = devices.preset_key(device) or ""
        mapped = FILTER_INDEX.get(key, {}).get(m)
        return bool(mapped) and mapped.strip().lower() == l
    return False


def _same(a, b, tol=0.0) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def match_masters(facts: dict, device: str) -> MatchResult:
    """The one master per tier for lights with `facts` (``exptime``, ``gain``,
    ``binning``, ``temp_c``, ``filter``) from `device`'s library. Missing tiers
    are None; every non-match and every judgement call lands in ``notes``."""
    res = MatchResult(device=device)
    lib = library(device)
    if not lib:
        res.notes.append(f"no calibration library for {device} "
                         f"(Calibration/{device}/ is empty)")
        return res
    exp, gain, binning = facts.get("exptime"), facts.get("gain"), facts.get("binning")
    temp, filt = facts.get("temp_c"), facts.get("filter")
    what = (f"{exp:g} s" if exp is not None else "? s") + \
           f", gain {gain if gain is not None else '?'}, bin {binning if binning is not None else '?'}"

    # dark: exact exposure/gain/binning, nearest temperature
    darks = [m for m in lib.get("darks", [])
             if _same(m.exptime, exp, 0.01) and m.gain == gain and m.binning == binning]
    if darks:
        def _rank(m: MasterInfo):
            dt = abs(m.temp_c - temp) if (m.temp_c is not None and temp is not None) else 999.0
            return (dt, -(m.ncombine or 0), m.path.name)
        best = min(darks, key=_rank)
        res.darks = best.path
        if best.temp_c is not None and temp is not None:
            dt = best.temp_c - temp
            if abs(dt) > 5:
                res.notes.append(f"nearest master dark is {abs(dt):.0f} °C "
                                 f"{'warmer' if dt > 0 else 'cooler'} than the lights "
                                 f"({best.temp_c:g} vs {temp:g} °C)")
        elif temp is None:
            res.notes.append("lights carry no sensor temperature; the first matching "
                             "dark was taken")
    elif lib.get("darks"):
        res.notes.append(f"no master dark for {what} "
                         f"({len(lib['darks'])} darks in the library, none at those settings)")
    else:
        res.notes.append(f"no master darks in the {device} library")

    # bias: binning, preferring the same gain
    biases = [m for m in lib.get("biases", []) if m.binning == binning]
    if biases:
        same_gain = [m for m in biases if m.gain == gain]
        pool = same_gain or biases
        pool.sort(key=lambda m: m.path.name)
        res.biases = pool[0].path
        if not same_gain:
            res.notes.append(f"no master bias at gain {gain}; using {pool[0].path.name} "
                             f"(gain {pool[0].gain}) — the device's bias/flat gain scale "
                             "is unverified")
        elif len(pool) > 1:
            res.notes.append(f"{len(pool)} master biases match; using {pool[0].path.name}")
    elif lib.get("biases"):
        res.notes.append(f"no master bias at bin {binning}")
    else:
        res.notes.append(f"no master bias in the {device} library")

    # flat: binning + a filter that resolves to the lights' filter, unambiguous
    flats_bin = [m for m in lib.get("flats", []) if m.binning == binning]
    flats = [m for m in flats_bin if filter_matches(filt, m.filter, device)]
    if len(flats) == 1:
        res.flats = flats[0].path
    elif len(flats) > 1:
        names = ", ".join(m.filter or m.path.name for m in flats)
        res.notes.append(f"{len(flats)} master flats could apply ({names}); "
                         "none linked until the choice is unambiguous")
    elif flats_bin:
        tokens = ", ".join(m.filter or "(no FILTER)" for m in flats_bin)
        res.notes.append(f"master flats present ({tokens}) but none is known to match "
                         f"filter {filt or '?'} — the {device} filter-index map is "
                         "unverified, so no flat was linked")
    elif lib.get("flats"):
        res.notes.append(f"no master flat at bin {binning}")
    else:
        res.notes.append(f"no master flats in the {device} library")
    return res


# ── from a set of lights ──────────────────────────────────────────────────────

def facts_from_frames(frames: list[dict]) -> dict:
    """Fold per-frame facts (dicts with exptime/gain/binning/temp_c/filter/
    telescop) into the facts of the **dominant** (exptime, gain, binning) group:
    its median temperature, its most common filter, the first telescope seen.
    ``mixed`` says whether more than one group was present, and ``groups`` how
    many frames each had."""
    groups: Counter = Counter()
    for f in frames:
        groups[(f.get("exptime"), f.get("gain"), f.get("binning"))] += 1
    if not groups:
        return {"exptime": None, "gain": None, "binning": None, "temp_c": None,
                "filter": None, "telescop": None, "mixed": False, "groups": {}}
    (exp, gain, binning), _n = groups.most_common(1)[0]
    members = [f for f in frames
               if (f.get("exptime"), f.get("gain"), f.get("binning")) == (exp, gain, binning)]
    temps = [f["temp_c"] for f in members if f.get("temp_c") is not None]
    filters = Counter(f["filter"] for f in members if f.get("filter"))
    telescop = next((f["telescop"] for f in frames if f.get("telescop")), None)
    return {
        "exptime": exp, "gain": gain, "binning": binning,
        "temp_c": statistics.median(temps) if temps else None,
        "filter": filters.most_common(1)[0][0] if filters else None,
        "telescop": telescop,
        "mixed": len(groups) > 1,
        "groups": {f"{k[0]}s/g{k[1]}/b{k[2]}": n for k, n in groups.items()},
    }


def _sample(paths: list[Path], n: int) -> list[Path]:
    if len(paths) <= n:
        return paths
    step = len(paths) / n
    return [paths[int(i * step)] for i in range(n)]


def target_facts(target: str, sample: int = 24) -> dict:
    """`facts_from_frames` over an evenly spaced sample of the target's raw subs
    (``lights/``, genuine subs only). A sample, because a target can hold
    thousands of frames and one header read per frame is the whole cost."""
    d = config.lights_dir(target)
    if not d.is_dir():
        return facts_from_frames([])
    subs = sorted(f for f in d.iterdir() if f.is_file() and config.is_light_frame(f.name))
    frames = [ff for ff in (frame_facts(p) for p in _sample(subs, sample)) if ff]
    return facts_from_frames(frames)


def device_for_target(target: str) -> str | None:
    """The telescope a target was shot with — its subs' ``TELESCOP``, as the
    library folder name — or None when no sub says."""
    tel = target_facts(target, sample=3).get("telescop")
    return devices.folder_name(tel) if tel else None


def match_for_facts(facts: dict, device: str | None) -> MatchResult:
    """`match_masters` with the two refusals in front: no device, or mixed
    capture settings (which would silently calibrate half the frames wrong)."""
    if not device:
        return MatchResult(notes=["lights carry no TELESCOP header, so no device "
                                  "library can be chosen"])
    if facts.get("mixed"):
        groups = ", ".join(f"{k} ×{n}" for k, n in facts["groups"].items())
        return MatchResult(device=device, notes=[
            f"mixed capture settings ({groups}) — one master cannot calibrate "
            "them all; stack one exposure at a time (m110-stack --only-exposure) "
            "or add per-target darks/flats/biases"])
    return match_masters(facts, device)


def match_for_target(target: str) -> MatchResult:
    """The library masters for a target's lights (prep-time entry point)."""
    facts = target_facts(target)
    tel = facts.get("telescop")
    return match_for_facts(facts, devices.folder_name(tel) if tel else None)

"""Pick the calibration master a target needs from the device-level library.

``Calibration/<device>/{darks,flats,biases}/`` (config.calibration_dir) holds
MASTER frames that belong to a telescope, not to a target — darks across
exposure × gain × binning × sensor temperature, flats per filter, a bias. This
module answers "which one for *this* set of lights?"
from **headers only**: the masters' IMAGETYP / EXPTIME / GAIN / XBINNING /
CCD-TEMP / FILTER / NCOMBINE, and the lights' EXPTIME / GAIN / XBINNING /
DET-TEMP (or CCD-TEMP) / FILTER / TELESCOP. It never reads a filename for a
fact: a master missing a card simply doesn't match on it.

Rules (`match_masters`):

* **dark** — same exposure, gain and binning; then the nearest sensor
  temperature (ties → the master averaged from more frames). A dark at the wrong
  exposure or gain is worse than none, so those never match.
* **bias** — same binning; the same gain when any candidate has it, else the sole
  candidate with a note (some devices record a bias gain on a different scale
  from their lights').
* **flat** — same binning and a filter that resolves to the lights' filter. A
  DwarfLab flat's FILTER is an ``ir_<n>`` index whose mapping to a filter name
  is per device (`FILTER_INDEX`), so two flats that could both apply yield none
  and a note rather than a guess.

A target whose subs carry more than one ``TELESCOP`` is refused too: each
device has its own library.

A target whose sampled lights mix exposure/gain/binning is refused with a note:
BUGS.md — "a mixed workspace must match calibration per job or refuse it". The
stacker matches on the frames it actually selected, so ``--only-exposure``
makes such a target stackable with calibration.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

from . import config, devices
from .ingest import _normalize_imagetyp, _safe_segment

TIERS = config.CALIBRATION_TIERS                     # ("darks", "flats", "biases")
_TIER_OF_KIND = {"dark": "darks", "flat": "flats", "bias": "biases"}

# Per-device map (keyed by `devices.preset_key`) of a DwarfLab flat's ``ir_<n>``
# FILTER token → the filter name the lights carry. No mapping is verified yet, so
# it is empty: no ir_ flat can match, and `match_masters` says so.
FILTER_INDEX: dict[str, dict[str, str]] = {}


DARKS_ON_DEVICE_NOTE = ("subs from this telescope are already dark-subtracted on the "
                        "device; its library darks are kept for reference and are "
                        "never applied again")


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
    ``temp_c`` is CCD-TEMP, else DET-TEMP (what some DwarfLab devices write)."""
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
        # rounded: a float32 card reads 13.8999996185303 for the 13.9 °C it means
        "temp_c": round(t, 2) if (t := _num(temp)) is not None else None,
        "filter": (str(filt).strip() or None) if filt not in (None, "") else None,
        # frames averaged into a master: NCOMBINE, or the Seestar's STACKCNT
        "ncombine": _num(h.get("NCOMBINE") if h.get("NCOMBINE") is not None
                         else h.get("STACKCNT"), int),
        "telescop": (str(tel).strip() or None) if tel not in (None, "") else None,
    }


def library(device: str) -> dict[str, list[MasterInfo]]:
    """Every master in ``Calibration/<device>/<tier>/``, keyed by tier. A file is
    kept for a tier if its IMAGETYP says so or is absent (the folder is trusted);
    one that claims another type is skipped. Tiers with nothing are omitted.
    `device` goes through the same `_safe_segment` ingest writes with, so a
    hostile TELESCOP reads the folder it was imported into, never a path above."""
    out: dict[str, list[MasterInfo]] = {}
    for tier in TIERS:
        d = config.calibration_dir(_safe_segment(device), tier)
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

    # dark: exact exposure/gain/binning, nearest temperature — unless the device
    # already subtracted one before saving the subs (devices.darks_applied_on_device)
    darks = [m for m in lib.get("darks", [])
             if _same(m.exptime, exp, 0.01) and m.gain == gain and m.binning == binning]
    on_device = devices.darks_applied_on_device(device)
    if on_device:
        res.notes.append(DARKS_ON_DEVICE_NOTE)
    elif darks:
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
    elif not on_device:          # a darks-only Seestar library has no bias tier by design
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
    elif not on_device:
        res.notes.append(f"no master flats in the {device} library")
    return res


# ── from a set of lights ──────────────────────────────────────────────────────

def facts_from_frames(frames: list[dict]) -> dict:
    """Fold per-frame facts (dicts with exptime/gain/binning/temp_c/filter/
    telescop) into the facts of the **dominant** (exptime, gain, binning) group:
    its median temperature, its most common filter, the first telescope seen.
    ``mixed`` says whether more than one group was present, and ``groups`` how
    many frames each had; ``telescopes`` lists every distinct TELESCOP (more
    than one is refused by `match_for_facts`)."""
    groups: Counter = Counter()
    for f in frames:
        groups[(f.get("exptime"), f.get("gain"), f.get("binning"))] += 1
    if not groups:
        return {"exptime": None, "gain": None, "binning": None, "temp_c": None,
                "filter": None, "telescop": None, "mixed": False, "groups": {},
                "telescopes": []}
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
        "telescopes": sorted({f["telescop"] for f in frames if f.get("telescop")}),
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
    if len(facts.get("telescopes") or []) > 1:
        return MatchResult(device=device, notes=[
            f"frames from more than one telescope ({', '.join(facts['telescopes'])})"
            " — each has its own calibration library; stack them separately or "
            "add per-target darks/flats/biases"])
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


# ── device-applied darks: which master a capture got, and how far off it was ──
# A Seestar subtracts a dark on the device before it saves a sub
# (devices.darks_applied_on_device), choosing from its own dark library. Nothing
# in a sub's header says which dark, so it is INFERRED (rule v2, measured on an
# S50 2026-10-15…18, DONE.md): at the start of each target run the device uses the
# library dark at the same exposure/gain/binning whose temperature is nearest the
# sensor's, taking a new one first when none is within ~2 °C. During the run the
# choice is *sticky*: it keeps the current dark while the sensor stays within
# `DARK_WINDOW_C` of it, and once it drifts further, switches to the nearest dark
# that IS within the window — or, when none is, keeps the current one (it never
# takes a dark mid-run). Rule v1 assumed no mid-run switch; real C 6 runs showed
# 24.9→23.2 at 22.1 °C and 23.2→13.9 at ≈16.2 °C. The gap between a sub's CCD-TEMP
# and the dark in use is the quality signal: hot pixels come out over- or
# under-subtracted in proportion.
#
# The Seestar's masters carry no DATE-OBS, so *when* a dark existed is read from
# the device's own filename clock — `device_clock`, the ONE filename-time parser
# for this, compared only with the lights' filename clock (same device, both local
# time; no timezone arithmetic) and corroborated by temperature.

DARK_RULE = "v2"
DARK_WINDOW_C = 2.5            # the device's mid-run switching window (rule v2)
DARK_GAP_WARN_C = 3.0          # gap above which the hot-pixel residue is visible
_CONFIRM_WINDOW_S = 10 * 60    # a dark this soon before the run was made for it
_CONFIRM_TEMP_C = 1.0          # …if it matches the run's starting temperature
# Device-clock gap that separates two runs of one target. Generous on purpose: a
# plan's frames of one target are one run (a cloud pause must not look like a new
# target start, which would wrongly re-pick the dark); nights are hours apart.
RUN_BREAK_S = 2 * 60 * 60

_DEVICE_CLOCK_RE = re.compile(r"_(\d{8})-(\d{6})(?:_thn)?\.[A-Za-z]+$")


def device_clock(name: str):
    """The device's local-time stamp at the end of a Seestar filename
    (``…_20261015-215239.fit``) as a naive datetime, or None. Only ever compared
    with another stamp from the same device's clock."""
    m = _DEVICE_CLOCK_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


@dataclass
class AppliedDark:
    master: MasterInfo
    link: str                  # "confirmed" | "inferred"
    rule: str = DARK_RULE

    def gap(self, temp_c: float | None) -> float | None:
        if temp_c is None or self.master.temp_c is None:
            return None
        return abs(temp_c - self.master.temp_c)


def applied_dark(run_start, temp_start: float | None, *, exptime, gain, binning,
                 masters: list[MasterInfo]) -> AppliedDark | None:
    """The library dark the device most likely applied to a run that began at
    device-clock `run_start` with the sensor at `temp_start` — or None when no
    master at these settings existed yet (captures before the library)."""
    if run_start is None:
        return None
    cands = [(made, m) for made, m in _dark_candidates(masters, exptime, gain, binning)
             if made <= run_start]
    if not cands:
        return None
    if temp_start is None:
        made, best = max(cands, key=lambda c: c[0])
    else:
        made, best = min(cands, key=lambda c: (
            abs((c[1].temp_c if c[1].temp_c is not None else 999.0) - temp_start),
            -c[0].timestamp()))
    confirmed = (temp_start is not None and best.temp_c is not None
                 and (run_start - made).total_seconds() <= _CONFIRM_WINDOW_S
                 and abs(best.temp_c - temp_start) <= _CONFIRM_TEMP_C)
    return AppliedDark(best, "confirmed" if confirmed else "inferred")


def _dark_candidates(masters: list[MasterInfo], exptime, gain, binning) -> list:
    """(device-clock made, master) for every master at these settings that says
    when it was made."""
    out = []
    for m in masters:
        made = device_clock(m.path.name)
        if (made is not None and _same(m.exptime, exptime, 0.01)
                and m.gain == gain and m.binning == binning):
            out.append((made, m))
    return out


def applied_darks(frames: list[tuple[str, float | None]], *, exptime, gain, binning,
                  masters: list[MasterInfo]) -> list[AppliedDark | None]:
    """The dark in use for each frame of ONE target run (`frames` = (filename,
    CCD-TEMP) in capture order), by rule v2: the run's starting dark
    (`applied_dark`), then the sticky `DARK_WINDOW_C` switch. A switched-to dark is
    always "inferred". All None when no master existed at the run's start."""
    if not frames:
        return []
    name0, temp0 = frames[0]
    current = applied_dark(device_clock(name0), temp0, exptime=exptime, gain=gain,
                           binning=binning, masters=masters)
    if current is None:
        return [None] * len(frames)
    cands = _dark_candidates(masters, exptime, gain, binning)
    out: list[AppliedDark | None] = []
    for name, temp in frames:
        held = current.master.temp_c
        if temp is not None and held is not None and abs(temp - held) > DARK_WINDOW_C:
            now = device_clock(name)
            near = [m for made, m in cands
                    if (now is None or made <= now) and m.temp_c is not None
                    and abs(temp - m.temp_c) <= DARK_WINDOW_C]
            if near:
                best = min(near, key=lambda m: (abs(temp - m.temp_c), m.path.name))
                if best.path != current.master.path:
                    current = AppliedDark(best, "inferred")
        out.append(current)
    return out


def split_runs(names: list[str]) -> list[list[str]]:
    """Group sub filenames into target runs by device clock (a gap over
    `RUN_BREAK_S` starts a new run). Names without a stamp form their own run."""
    stamped = sorted((c, n) for n in names if (c := device_clock(n)) is not None)
    runs: list[list[str]] = []
    prev = None
    for c, n in stamped:
        if prev is None or (c - prev).total_seconds() > RUN_BREAK_S:
            runs.append([])
        runs[-1].append(n)
        prev = c
    loose = [n for n in names if device_clock(n) is None]
    return runs + ([loose] if loose else [])


# ── sensor health + the per-device rollup (derived/devices.json) ──────────────

_STATS_CACHE_NAME = "master_stats.json"
HOT_SIGMA = 10.0               # a hot pixel: above median + HOT_SIGMA × robust σ


def master_stats(path: Path) -> dict | None:
    """Pixel statistics of one master: median, mean, robust σ (1.4826 × MAD), the
    hot-pixel count (> median + `HOT_SIGMA` σ) and shape. None if unreadable."""
    try:
        from astropy.io import fits
        import numpy as np
        data = fits.getdata(str(path)).astype("float64")
    except Exception:
        return None
    med = float(np.median(data))
    sigma = 1.4826 * float(np.median(np.abs(data - med)))
    hot = int((data > med + HOT_SIGMA * max(sigma, 1.0)).sum())
    return {"median": round(med, 2), "mean": round(float(data.mean()), 2),
            "sigma": round(sigma, 2), "hot_px": hot, "shape": list(data.shape)}


def _content_key(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def device_rollup(sessions: list[dict]) -> dict:
    """``derived/devices.json``: per device (every ``Calibration/<device>/`` and
    every TELESCOP a session names) its library masters with their header facts,
    device-clock time and pixel statistics, how many captures each dark served,
    and the captures themselves with their inferred dark and gap. Pixel stats are
    cached by content hash in ``derived/master_stats.json``, so a refresh only
    reads masters it has never seen. Deterministic (sorted, no timestamps)."""
    import json
    cache_path = config.DERIVED_DIR / _STATS_CACHE_NAME
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    used: dict = {}

    names = set()
    if config.CALIBRATION_DIR.is_dir():
        names |= {d.name for d in config.CALIBRATION_DIR.iterdir()
                  if d.is_dir() and not config.is_hidden_name(d.name)}
    names |= {devices.folder_name(r["telescop"]) for r in sessions if r.get("telescop")}

    out = []
    for dev in sorted(names):
        caps = [r for r in sessions if r.get("telescop")
                and devices.folder_name(r["telescop"]) == dev]
        served: Counter = Counter(ref for r in caps
                                  for ref in (r.get("dark_refs") or
                                              ([r["dark_ref"]] if r.get("dark_ref") else [])))
        masters = []
        for tier, ms in sorted(library(dev).items()):
            for m in ms:
                try:
                    key = _content_key(m.path)
                except OSError:
                    continue
                stats = cache.get(key) or master_stats(m.path)
                if stats is not None:
                    used[key] = stats
                made = device_clock(m.path.name)
                preview = m.path.with_suffix(".jpg")
                masters.append({
                    "tier": tier, "file": m.path.name,
                    "rel": m.path.relative_to(config.DATA_ROOT).as_posix(),
                    "preview": (preview.relative_to(config.DATA_ROOT).as_posix()
                                if preview.is_file() else None),
                    "exptime": m.exptime, "gain": m.gain, "binning": m.binning,
                    "temp_c": m.temp_c, "frames": m.ncombine,
                    "made": made.isoformat() if made else None,
                    "captures": served.get(m.path.name, 0),
                    **(stats or {}),
                })
        masters.sort(key=lambda m: (m["tier"], m["made"] or "", m["file"]))
        out.append({
            "device": dev,
            "label": devices.display_name(dev),
            "darks_applied_on_device": devices.darks_applied_on_device(dev),
            "masters": masters,
            "captures": [{k: r.get(k) for k in (
                "date", "object_dir", "slugs", "frames", "exposure_s", "filter",
                "temp_first", "temp_min", "temp_max", "dark_ref", "dark_temp_c",
                "dark_gap_c", "dark_link", "dark_refs", "dark_rule")} for r in sorted(
                    caps, key=lambda r: (r["date"], r["object_dir"]))],
        })
    out.sort(key=lambda d: (not d["masters"], d["device"]))   # libraries first
    if used != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(used, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
    return {"devices": out}

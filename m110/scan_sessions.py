#!/usr/bin/env python3
"""Scan Images/<target>/lights/ and emit the session index (sessions.jsonl).

Each line is one (date, object, exposure, filter) tuple from the FITS
filenames — the canonical session record. The scan is idempotent: re-running
overwrites sessions.jsonl with the current view of the FITS folder.

The (date, exposure, filter) key for each sub comes from the Seestar/mosaic
filename convention when it matches, else from the FITS header
(`DATE-OBS`/`EXPTIME`/`FILTER`) — so any device's subs (Dwarf 3, …) produce
sessions regardless of filename convention. Seestar filename convention:
  Light_<object>_<exp>s_<filter>_<YYYYMMDD>-<HHMMSS>.fit
  mosaic_<object>_<exp>s_<filter>_<YYYYMMDD>-<HHMMSS>.fit

Object field maps to the FITS folder name (which may differ from the catalog
slug — e.g. "M81 M82" folder covers both M81 and M82 catalog entries).
The folder name is preserved as `object_dir` and we also emit a list of
catalog slugs the session contributes to under `slugs`.

Mount mode is read from the FITS ``EQMODE`` header card — **both** the Seestar
and the DwarfLab Dwarf 3 write it (int ``1`` = Equatorial, ``0`` = Alt-Az), so it's
device-agnostic and per-user-correct. Only when it's absent (pre-``EQMODE`` firmware
or an unknown device) do we fall back to the legacy date heuristic below, which is
specific to *this* store's Seestar switchover and would mislabel anyone else.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# Ported into the M110 engine: paths resolve dynamically from config (so a
# changed data root / test monkeypatch takes effect without re-import).
from . import config  # noqa: E402

SKIP_DIRS = {"M42 copy", "M81 M82 orig", "Template"}
NEW_START = date(2026, 4, 4)
# Mount mode cutover: only the very first session (2026-03-13 M42) was Alt-Az.
# Everything from 2026-03-17 onward was EQ — well before the April 4 new-start.
EQ_FROM = date(2026, 3, 17)

PAT = re.compile(
    r"(?:Light|mosaic)_(.+?)_(\d+(?:\.\d+)?)s_(LP|IRCUT|UV|DARK)_"
    r"(\d{8})-(\d{6})\.fit",
    re.I,
)


def _session_key(path: Path) -> tuple[str, float, str] | None:
    """(iso_date, exposure_s, filter) for one light sub — the fields a session
    row buckets on. Fast path: the Seestar/mosaic filename convention (no header
    read). Fallback: read the FITS header (``DATE-OBS``/``EXPTIME``/``FILTER``) so
    device layouts with other filename conventions (Dwarf 3, …) still produce
    sessions. Returns None if neither yields a usable date+exposure."""
    m = PAT.search(path.name)
    if m:
        d = m.group(4)                          # YYYYMMDD
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return iso, float(m.group(2)), m.group(3).upper()
    try:
        from astropy.io import fits
        hdr = fits.getheader(str(path))
        obs = str(hdr.get("DATE-OBS") or "").strip()
        iso = obs.split("T", 1)[0]              # 'YYYY-MM-DD' from ISO datetime
        exp = float(hdr.get("EXPTIME"))
        if len(iso) != 10 or exp <= 0:
            return None
        filt = str(hdr.get("FILTER") or "").strip().upper()
        return iso, exp, filt
    except Exception:
        return None


def _read_eqmode(path: Path) -> bool | None:
    """Reported mount mode from the FITS ``EQMODE`` card: ``True`` (Equatorial) /
    ``False`` (Alt-Az), or ``None`` when unreadable or absent. **Both** the Seestar
    and the DwarfLab Dwarf 3 write ``EQMODE`` (int ``0``/``1``, comment "Equatorial
    mode"), so this is device-agnostic; ``None`` covers a non-FITS stub or firmware
    predating the card (verified absent on some Dec-2025 Dwarf subs)."""
    try:
        from astropy.io import fits
        val = fits.getheader(str(path)).get("EQMODE")
    except Exception:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("1", "true", "t", "yes"):
            return True
        if s in ("0", "false", "f", "no"):
            return False
    return None


def _mount_mode(rep_path: Path | None, session_date: date) -> str:
    """Mount mode for a session — the reported ``EQMODE`` header card if present
    (authoritative, device-agnostic), else the legacy date heuristic. The date rule
    (:data:`EQ_FROM`) is specific to this store's Seestar switchover: a fine last-resort
    guess for pre-``EQMODE`` data, wrong for anyone else — so header truth always wins."""
    if rep_path is not None:
        eq = _read_eqmode(rep_path)
        if eq is not None:
            return "EQ" if eq else "Alt-Az"
    return "EQ" if session_date >= EQ_FROM else "Alt-Az"


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[/\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


# Words a capture folder adds to an object's name to describe *how* it was shot,
# not *what* was shot. "M42_mosaic" is still M42's frames.
_DECORATIONS = {"mosaic", "panel", "panels", "pane"}


def _undecorated(slug: str) -> str:
    """`slug` with any trailing capture decoration removed ("ngc-7000-mosaic"
    → "ngc-7000"). Returns it unchanged when there is none."""
    parts = slug.split("-")
    while len(parts) > 1 and parts[-1] in _DECORATIONS:
        parts.pop()
    return "-".join(parts)


def folder_to_slugs(folder_name: str, catalog_slugs: set[str]) -> list[str]:
    """Map an FITS folder name to the catalog slugs it contributes to.

    Multi-object frames like "M81 M82" → ["m81", "m82"].
    Suffix forms like "M42_mosaic" → ["m42"].
    NGC3628 → ["ngc-3628"] via space-before-digit fallback.
    """
    # A folder naming 2+ catalog objects is a *combined capture target* and must
    # ALWAYS split into its members — checked before the whole-slug match below,
    # which would otherwise return a combined pseudo-object slug ("m81-m82") the
    # moment one exists in the Library, silently under-counting the pair (#40c).
    # Order matters: this is what makes the fix self-healing rather than dependent
    # on the Library never containing such an entry.
    # Spaced designations are collapsed first ("M 97 M 108" → "M97 M108") so the
    # split works whichever way the designations are typed.
    parts = re.split(r"\s+", re.sub(r"([A-Za-z]+)\s+(\d)", r"\1\2", folder_name))
    out = [ps for ps in (slugify(p) for p in parts) if ps in catalog_slugs]
    if len(out) >= 2:
        return out
    s = slugify(folder_name)
    # A folder named by a *catalog number* ("C 6") names an object the reference
    # keys by its primary designation (ngc-6543), so ask catalog membership.
    from .catalog import designation_index, _normalize_designation
    by_desig = designation_index().get(_normalize_designation(folder_name))
    if by_desig in catalog_slugs:
        return [by_desig]
    # A decorated capture target ("M42_mosaic") is still that object's frames.
    # This runs *before* the whole-folder match on purpose: once a stray
    # "m42-mosaic" entry exists in the Library it would otherwise match itself
    # forever, and the pollution becomes self-sustaining.
    base = _undecorated(s)
    if base != s and base in catalog_slugs:
        return [base]
    if s in catalog_slugs:
        return [s]
    if out:
        return out
    s2 = slugify(re.sub(r"([A-Za-z]+)(\d)", r"\1 \2", folder_name))
    if s2 in catalog_slugs:
        return [s2]
    stem = s.split("-")[0]
    if stem in catalog_slugs:
        return [stem]
    return []


def load_catalog_slugs() -> set[str]:
    """Slugs a capture folder may map to: the user's Library **plus** the bundled
    reference.

    Including the reference is load-bearing for multi-object folders (#40c): a
    combined capture like "M81 M82" must split into `m81` + `m82` — both real
    catalog objects — so the pair's integration credits *both*. Against the Library
    alone, a fresh store maps it to nothing, which is what let it get promoted into
    a synthetic `m81-m82` "object" that then shadowed the split forever.
    """
    slugs: set[str] = set()
    cat_path = config.LIBRARY_TOML
    if cat_path.exists():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        with cat_path.open("rb") as f:
            slugs |= set(tomllib.load(f).get("catalog", {}).keys())
    else:
        print(f"warning: {cat_path} not found; Library slugs skipped",
              file=sys.stderr)
    from .catalog import load_reference        # local: avoids an import cycle
    slugs |= set(load_reference())
    return slugs


def scan() -> list[dict]:
    images = config.IMAGES_DIR
    if not images.is_dir():
        print(f"Images dir not found: {images}", file=sys.stderr)
        sys.exit(1)

    catalog_slugs = load_catalog_slugs()
    rows: list[dict] = []

    for obj_dir in sorted(images.iterdir()):
        if not obj_dir.is_dir() or obj_dir.name in SKIP_DIRS:
            continue
        lights = obj_dir / "lights"
        if not lights.is_dir():
            continue

        # Bucket by (iso-date, exp, filt) to compress to one row per session-segment.
        # Each light's key comes from the filename (Seestar fast path) or its FITS
        # header (device-agnostic fallback — see `_session_key`).
        bucket: dict[tuple[str, float, str], int] = defaultdict(int)
        rep: dict[tuple[str, float, str], Path] = {}   # one sub per bucket → EQMODE read
        for f in lights.iterdir():
            if not f.is_file() or f.suffix.lower() not in config.FIT_EXTS:
                continue
            key = _session_key(f)
            if key is None:
                continue
            bucket[key] += 1
            rep.setdefault(key, f)

        slugs = folder_to_slugs(obj_dir.name, catalog_slugs)
        for (iso, exp, filt), n in sorted(bucket.items()):
            session_date = datetime.strptime(iso, "%Y-%m-%d").date()
            # One header read per session-segment (mount mode is constant within a
            # capture run) — negligible next to the filename fast-path for the subs.
            mount_mode = _mount_mode(rep.get((iso, exp, filt)), session_date)
            row = {
                "date": iso,
                "object_dir": obj_dir.name,
                "slugs": slugs,
                "frames": n,
                "exposure_s": exp if exp != int(exp) else int(exp),
                "filter": filt,
                "integration_min": round(n * exp / 60.0, 2),
                "mount_mode": mount_mode,
                "pre_new_start": session_date < NEW_START,
            }
            rows.append(row)
    rows.sort(key=lambda r: (r["date"], r["object_dir"], r["exposure_s"]))
    return rows


def write_jsonl(rows: list[dict]):
    out = config.SESSIONS_JSONL
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    rows = scan()
    write_jsonl(rows)
    by_dir: dict[str, dict] = {}
    for r in rows:
        d = by_dir.setdefault(r["object_dir"],
                              {"frames": 0, "min": 0.0, "sessions": set()})
        d["frames"] += r["frames"]
        d["min"] += r["integration_min"]
        d["sessions"].add(r["date"])
    print(f"Wrote {len(rows)} session rows to {config.SESSIONS_JSONL}")
    print(f"  {len(by_dir)} object folders, "
          f"{sum(d['frames'] for d in by_dir.values())} total frames")


if __name__ == "__main__":
    main()

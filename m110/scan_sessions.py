#!/usr/bin/env python3
"""Scan Images/<target>/lights/ and emit the session index (sessions.jsonl).

Each line is one (date, object, exposure, filter) tuple from the FITS
filenames — the canonical session record. The scan is idempotent: re-running
overwrites sessions.jsonl with the current view of the FITS folder.

Filename conventions (per CLAUDE.md):
  Light_<object>_<exp>s_<filter>_<YYYYMMDD>-<HHMMSS>.fit
  mosaic_<object>_<exp>s_<filter>_<YYYYMMDD>-<HHMMSS>.fit

Object field maps to the FITS folder name (which may differ from the catalog
slug — e.g. "M81 M82" folder covers both M81 and M82 catalog entries).
The folder name is preserved as `object_dir` and we also emit a list of
catalog slugs the session contributes to under `slugs`.

Mount mode is inferred from date — sessions on or after 2026-04-04 are EQ
unless overridden by data/overrides/sessions.toml (not implemented yet, but
the schema leaves a slot for it).
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


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[/\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def folder_to_slugs(folder_name: str, catalog_slugs: set[str]) -> list[str]:
    """Map an FITS folder name to the catalog slugs it contributes to.

    Multi-object frames like "M81 M82" → ["m81", "m82"].
    Suffix forms like "M42_mosaic" → ["m42"].
    NGC3628 → ["ngc-3628"] via space-before-digit fallback.
    """
    s = slugify(folder_name)
    if s in catalog_slugs:
        return [s]
    parts = re.split(r"\s+", folder_name)
    out = []
    for p in parts:
        ps = slugify(p)
        if ps in catalog_slugs:
            out.append(ps)
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
    cat_path = config.CATALOG_TOML
    if not cat_path.exists():
        print(f"warning: {cat_path} not found; slug mapping skipped",
              file=sys.stderr)
        return set()
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    with cat_path.open("rb") as f:
        data = tomllib.load(f)
    return set(data.get("catalog", {}).keys())


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

        # Bucket by (date, exp, filt) to compress to one row per session-segment
        bucket: dict[tuple[str, float, str], int] = defaultdict(int)
        for f in lights.iterdir():
            if not f.is_file() or f.suffix.lower() != ".fit":
                continue
            m = PAT.search(f.name)
            if not m:
                continue
            exp = float(m.group(2))
            filt = m.group(3).upper()
            d = m.group(4)
            bucket[(d, exp, filt)] += 1

        slugs = folder_to_slugs(obj_dir.name, catalog_slugs)
        for (d, exp, filt), n in sorted(bucket.items()):
            iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            session_date = datetime.strptime(iso, "%Y-%m-%d").date()
            mount_mode = "EQ" if session_date >= EQ_FROM else "Alt-Az"
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
    with out.open("w") as f:
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

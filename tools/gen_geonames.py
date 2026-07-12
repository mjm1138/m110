#!/usr/bin/env python3
"""Generate the bundled populated-places table for the light-dome glow map
(dev/build-time tool — needs network for the one-time download).

Downloads a **GeoNames** ``cities1000`` dump (all populated places with population
≥ 1000, worldwide — both hemispheres), trims it to the four fields the glow engine
needs, and writes a compact gzip TSV:

    m110/seed/geonames/cities1000.tsv.gz     (asciiname \\t lat \\t lon \\t pop \\t cc)

Runtime stays **offline** — only this trimmed, gzipped subset ships and is read by
``m110/glow.py`` (``load_towns``). GeoNames is **CC-BY 4.0**; attribution lives in
``NOTICE`` (keep it there when regenerating).

**Why cities1000 and not cities15000:** skyglow domes are dominated by nearby towns
of a few thousand people, so a 15k-population floor would silently drop the towns
that matter most to rural / dark-site users (and biases against the sparser
southern hemisphere). cities1000 keeps them at a modest bundle size; cities500 is a
drop-in if finer granularity is wanted. VIIRS radiance is the deferred v2 upgrade.

    python tools/gen_geonames.py                # download + trim + write the seed
    python tools/gen_geonames.py path/to/cities1000.zip   # use a local dump instead
"""
from __future__ import annotations

import gzip
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

EXTRACT = "cities1000"
URL = f"https://download.geonames.org/export/dump/{EXTRACT}.zip"
OUT = Path(__file__).resolve().parent.parent / "m110" / "seed" / "geonames" / f"{EXTRACT}.tsv.gz"

# GeoNames dump columns (tab-separated, no header).
C_ASCIINAME, C_LAT, C_LON, C_CC, C_POP = 2, 4, 5, 8, 14
MIN_POP = 1000


def _fetch_zip(src: str | None) -> bytes:
    if src:
        return Path(src).read_bytes()
    print(f"Downloading {URL} …")
    req = urllib.request.Request(URL, headers={"User-Agent": "M110-gen-geonames"})
    with urllib.request.urlopen(req, timeout=60) as r:   # noqa: S310 (fixed host)
        return r.read()


def main(argv: list[str]) -> int:
    raw = _fetch_zip(argv[1] if len(argv) > 1 else None)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(f"{EXTRACT}.txt").decode("utf-8")

    rows, skipped = [], 0
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) <= C_POP:
            continue
        try:
            pop = int(f[C_POP] or 0)
            lat, lon = float(f[C_LAT]), float(f[C_LON])
        except ValueError:
            skipped += 1
            continue
        if pop < MIN_POP:
            continue
        name = f[C_ASCIINAME].replace("\t", " ").strip() or "?"
        rows.append(f"{name}\t{lat:.4f}\t{lon:.4f}\t{pop}\t{f[C_CC]}")

    rows.sort(key=lambda r: -int(r.split("\t")[3]))       # largest first (nicer to scan)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as out:
        out.write("\n".join(rows) + "\n")

    size_mb = OUT.stat().st_size / 1e6
    print(f"Wrote {len(rows):,} towns → {OUT}  ({size_mb:.1f} MB gzipped, "
          f"{skipped} malformed rows skipped)")
    print("Reminder: GeoNames is CC-BY 4.0 — keep the attribution in NOTICE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

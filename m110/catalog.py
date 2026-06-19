"""Read and order the object catalog from the live data store.

Mirrors the shape of Astronomy's `catalog.toml` (a dict keyed by slug; each
value has id/name/type/magnitude/size/season/...).
"""
from __future__ import annotations

import json
import re
import tomllib

from . import config

_M = re.compile(r"^M\s*(\d+)$")
_NGC = re.compile(r"^NGC\s*(\d+)$", re.IGNORECASE)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def load_catalog() -> dict[str, dict]:
    """Return the catalog as {slug: entry}."""
    with open(config.CATALOG_TOML, "rb") as f:
        return tomllib.load(f)["catalog"]


def object_count() -> int:
    return len(load_catalog())


def load_coords() -> dict[str, tuple[float, float]]:
    """Bundled J2000 reference coordinates {slug: (ra_deg, dec_deg)}.

    Shipped with the app (seed/coords.csv) so the ingest pointing check works
    offline and regardless of the store's age. A few asterisms have no single
    coordinate and are simply absent.
    """
    path = config.SEED_DIR / "coords.csv"
    out: dict[str, tuple[float, float]] = {}
    if path.is_file():
        with path.open() as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) != 3 or parts[0] == "slug":
                    continue
                try:
                    out[parts[0]] = (float(parts[1]), float(parts[2]))
                except ValueError:
                    continue
    # Catalog entries may carry their own ra_deg/dec_deg (auto-added captured
    # objects resolved via Simbad) — merge them over the bundled defaults.
    try:
        for slug, e in load_catalog().items():
            if e.get("ra_deg") is not None and e.get("dec_deg") is not None:
                out[slug] = (float(e["ra_deg"]), float(e["dec_deg"]))
    except Exception:
        pass
    return out


def catalog_sort_key(obj_id: str):
    """Natural catalog order: Messier-numeric, then NGC-numeric, then
    alphabetical. Mirrors the site's `_catalog_sort_key` so the GUI Object
    column matches the web view (M1, M2, … M10, not M1, M10, M100).
    Care: "Markarian's Chain" starts with M but isn't a Messier number.
    """
    s = (obj_id or "").strip()
    m = _M.match(s)
    if m:
        return (0, int(m.group(1)), "")
    n = _NGC.match(s)
    if n:
        return (1, int(n.group(1)), "")
    return (2, 0, s.lower())


def season_sort_key(season: str):
    """Sort a season ("Mar–May", "Dec–Feb", "Year-round") by its **first month**,
    January→December; "Year-round", empty, or unparseable sort last.

    Returns (month_index, original) — the string tiebreak keeps it stable.
    """
    s = (season or "").strip()
    # First token before an en-dash / hyphen / space (e.g. "Mar–May" → "Mar").
    first = re.split(r"[–\-\s]+", s, maxsplit=1)[0].lower()[:3]
    return (_MONTHS.get(first, 99), s.lower())


def _simbad_coords(name: str):
    """Best-effort J2000 (ra_deg, dec_deg) via astropy's CDS name resolver, or
    None (offline / unresolved). Short timeout so a refresh never hangs long."""
    try:
        import socket
        socket.setdefaulttimeout(10)
        from astropy.coordinates import SkyCoord
        c = SkyCoord.from_name(name)
        return round(c.ra.deg, 4), round(c.dec.deg, 4)
    except Exception:
        return None


def add_captured_objects(resolve_coords: bool = True) -> list[str]:
    """Promote captured targets that aren't in the catalog into first-class
    catalog objects, so they appear in the Catalog/Summary views, get an object
    page + journal, and are clickable (not just folder-derived rows).

    A capture folder is uncatalogued if `folder_to_slugs` maps it to nothing.
    Adds a minimal entry (id = folder name, type "unknown"), best-effort enriched
    with Simbad coords (→ pointing support). Idempotent + additive: never touches
    an existing entry. Returns the slugs added.
    """
    from . import scan_sessions  # local import: avoids any import cycle
    path = config.CATALOG_TOML
    if not path.is_file() or not config.IMAGES_DIR.is_dir():
        return []
    cat = load_catalog()
    existing = set(cat)

    new: list[tuple[str, dict]] = []
    for d in sorted(p for p in config.IMAGES_DIR.iterdir() if p.is_dir()):
        if not ((d / "lights").is_dir() or (d / "seestar-stacks").is_dir()):
            continue                                  # not a capture target
        folder = d.name
        if scan_sessions.folder_to_slugs(folder, existing):
            continue                                  # already maps to the catalog
        slug = scan_sessions.slugify(folder)
        if not slug or slug in cat or slug in {s for s, _ in new}:
            continue
        entry = {"id": folder, "name": "", "type": "unknown"}
        if resolve_coords:
            rd = _simbad_coords(folder)
            if rd:
                entry["ra_deg"], entry["dec_deg"] = rd
        new.append((slug, entry))

    if new:
        with path.open("a") as f:
            for slug, e in new:
                f.write(f"\n[catalog.{slug}]\n")
                f.write(f"id = {json.dumps(e['id'])}\n")
                f.write(f"name = {json.dumps(e['name'])}\n")
                f.write(f"type = {json.dumps(e['type'])}\n")
                if "ra_deg" in e:
                    f.write(f"ra_deg = {e['ra_deg']}\n")
                    f.write(f"dec_deg = {e['dec_deg']}\n")
    return [s for s, _ in new]

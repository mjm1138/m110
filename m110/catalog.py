"""Read the user's **Library** + the bundled object **reference** / **catalog**
data.

- *Library* (per-store, mutable): `.m110_internal_data/library.toml` — the user's
  corpus of objects (a dict keyed by slug; each value has id/name/type/magnitude/
  size/season/...). This is what the UI tables read.
- *Reference* (app-bundled, immutable): `seed/objects.toml` — intrinsic facts per
  object incl. J2000 `ra_deg/dec_deg`. Seeds the Library + backs coords.
- *Catalogs* (app-bundled): `seed/catalogs/<name>.toml` — named membership lists
  (Messier, …) used by goals (item 5b).
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


def load_library() -> dict[str, dict]:
    """Return the user's Library as {slug: entry} (from `library.toml`)."""
    with open(config.LIBRARY_TOML, "rb") as f:
        return tomllib.load(f)["catalog"]


def object_count() -> int:
    return len(load_library())


def load_reference() -> dict[str, dict]:
    """Bundled object reference dataset {slug: entry} (from `seed/objects.toml`).
    Immutable; ships with the app. `{}` if absent."""
    path = config.SEED_DIR / "objects.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f).get("object", {})


def load_bundled_catalog(name: str) -> dict:
    """A bundled catalog membership list (`seed/catalogs/<name>.toml`):
    `{name, description, members: {slug: designation}}`. `{}` if absent."""
    path = config.SEED_DIR / "catalogs" / f"{name}.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def list_bundled_catalogs() -> list[dict]:
    """All bundled catalogs, by id (filename stem): `[{id, name, description,
    members}]`, sorted by name."""
    d = config.SEED_DIR / "catalogs"
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.toml")):
            data = load_bundled_catalog(p.stem)
            if data:
                out.append({"id": p.stem, "name": data.get("name", p.stem),
                            "description": data.get("description", ""),
                            "members": data.get("members", {})})
    return sorted(out, key=lambda c: c["name"].lower())


def catalogs_for_slug(slug: str) -> list[tuple[str, str]]:
    """Which bundled catalogs an object belongs to → [(catalog name, designation)].
    Empty for a non-catalog Library addition."""
    out = []
    for c in list_bundled_catalogs():
        members = c["members"]
        if slug in members:
            out.append((c["name"], str(members[slug])))
    return out


def add_goal_members_to_library(goal_id: str) -> list[str]:
    """Append a bundled catalog's members to the Library (`library.toml`) that
    aren't already there, pulling intrinsic fields from the reference. Additive +
    idempotent; never overwrites. Returns the slugs added."""
    cat = load_bundled_catalog(goal_id)
    members = cat.get("members", {})
    if not members or not config.LIBRARY_TOML.is_file():
        return []
    have = set(load_library())
    ref = load_reference()
    new = [s for s in members if s not in have and s in ref]
    if new:
        _append_library_entries({s: ref[s] for s in new})
    return new


_LIB_ORDER = ["id", "name", "type", "magnitude", "size", "season", "filter",
              "notes", "ra_deg", "dec_deg"]


def _append_library_entries(entries: dict[str, dict]) -> None:
    """Append `[catalog.<slug>]` blocks to library.toml (the only writer besides
    config seeding + add_captured_objects)."""
    lines = []
    for slug, e in entries.items():
        lines.append(f"\n[catalog.{slug}]")
        for k in _LIB_ORDER:
            v = e.get(k)
            if v is None:
                continue
            lines.append(f"{k} = {v if isinstance(v, (int, float)) else _q(v)}")
    with config.LIBRARY_TOML.open("a") as f:
        f.write("\n".join(lines) + "\n")


def _q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_coords() -> dict[str, tuple[float, float]]:
    """J2000 reference coordinates {slug: (ra_deg, dec_deg)} for the pointing
    check — from the bundled reference (`seed/objects.toml`), with the user's
    Library `ra_deg/dec_deg` (e.g. auto-added captured objects) merged over it.
    Asterisms with no single coordinate are simply absent."""
    out: dict[str, tuple[float, float]] = {}
    for slug, e in load_reference().items():
        if e.get("ra_deg") is not None and e.get("dec_deg") is not None:
            out[slug] = (float(e["ra_deg"]), float(e["dec_deg"]))
    try:
        for slug, e in load_library().items():
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
    """Promote captured targets that aren't in the Library into first-class
    objects, so they appear in the Library/Summary views, get an object page +
    journal, and are clickable (not just folder-derived rows).

    A capture folder is uncatalogued if `folder_to_slugs` maps it to nothing.
    Adds a minimal entry (id = folder name, type "unknown"), best-effort enriched
    with Simbad coords (→ pointing support). Idempotent + additive: never touches
    an existing entry. Returns the slugs added.
    """
    from . import scan_sessions  # local import: avoids any import cycle
    path = config.LIBRARY_TOML
    if not path.is_file() or not config.IMAGES_DIR.is_dir():
        return []
    cat = load_library()
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

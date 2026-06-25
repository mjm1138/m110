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
_C = re.compile(r"^C\s*(\d+)$")
_NGC = re.compile(r"^NGC\s*(\d+)$", re.IGNORECASE)
_IC = re.compile(r"^IC\s*(\d+)$", re.IGNORECASE)

# Display priority when an object carries several catalog designations (general
# Library view). Extend as catalogs are bundled; unknown catalogs fall after these
# (by name), and the intrinsic reference id (NGC/IC/…) sorts last.
_CATALOG_PRIORITY = ["messier", "caldwell"]

_MON_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS = {m.lower(): i for i, m in enumerate(_MON_ABBR, start=1)}

# RA→observing-season calibration. An object's 3-month evening-sky window tracks
# its RA (24h of RA over 12 months); c0 is fit so the derived window reproduces the
# curated Messier seasons in seed/objects.toml (≈98% exact match).
_SEASON_C0 = 10.1


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


def _toml_value(v) -> str:
    """Serialize a Python value as TOML. bool **before** int (bool is an int
    subclass) so a preserved boolean round-trips as lowercase `true`/`false`, not
    Python's `True`/`False` (which is invalid TOML)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return _q(v)


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
    """Natural catalog order: Messier-numeric, then Caldwell, NGC, IC (each
    numeric), then alphabetical. So a Library sorted by the Object column groups
    M1…M110, C1…C109, NGC…, then the rest (M1, M2, … M10, not M1, M10, M100).
    Care: "Markarian's Chain" starts with M but isn't a Messier number.
    """
    s = (obj_id or "").strip()
    for rank, pat in ((0, _M), (1, _C), (2, _NGC), (3, _IC)):
        m = pat.match(s)
        if m:
            return (rank, int(m.group(1)), "")
    return (4, 0, s.lower())


def object_identifiers(slug: str, entry: dict | None = None,
                       primary_catalog: str | None = None) -> list[str]:
    """All of an object's designations, deduped + ordered for display.

    Catalog designations (from membership) come first by `_CATALOG_PRIORITY`
    (then unknown catalogs by name), and the intrinsic reference/Library id last.
    If `primary_catalog` (a catalog id) is given, that catalog's designation is
    forced first — the context for a filtered catalog view.
    e.g. M31 → ["M31"]; NGC 7000 (Caldwell) → ["C20", "NGC 7000"].
    """
    def rank(cid: str) -> int:
        return _CATALOG_PRIORITY.index(cid) if cid in _CATALOG_PRIORITY else 50

    tagged: list[tuple[int, str]] = []
    for c in list_bundled_catalogs():
        desig = c["members"].get(slug)
        if desig is None:
            continue
        r = -1 if c["id"] == primary_catalog else rank(c["id"])
        tagged.append((r, str(desig)))
    tagged.sort(key=lambda t: (t[0],))
    out, seen = [], set()
    for _, d in tagged:
        if d not in seen:
            out.append(d); seen.add(d)
    iid = (entry or {}).get("id")
    if iid and iid not in seen:
        out.append(iid)
    return out or ([iid] if iid else [slug])


def object_label(ids: list[str]) -> str:
    """"PRIMARY (rest, …)" for a display identifier list; "" if empty."""
    if not ids:
        return ""
    return ids[0] + (f" ({', '.join(ids[1:])})" if len(ids) > 1 else "")


def season_sort_key(season: str):
    """Sort a season ("Mar–May", "Dec–Feb", "Year-round") by its **first month**,
    January→December; "Year-round", empty, or unparseable sort last.

    Returns (month_index, original) — the string tiebreak keeps it stable.
    """
    s = (season or "").strip()
    # First token before an en-dash / hyphen / space (e.g. "Mar–May" → "Mar").
    first = re.split(r"[–\-\s]+", s, maxsplit=1)[0].lower()[:3]
    return (_MONTHS.get(first, 99), s.lower())


def season_from_ra(ra_deg) -> str:
    """Derive an object's observing-season window ("Mon–Mon") from its J2000 RA.

    The 3-month evening window an object is best placed advances ~1 month per 2h of
    RA (24h ↔ 12 months); `_SEASON_C0` is calibrated against the curated Messier
    seasons. Offline + deterministic; shared with the bundled-data generator
    (`tools/gen_caldwell.py`). Returns "" for an invalid RA."""
    try:
        ra = float(ra_deg)
    except (TypeError, ValueError):
        return ""
    center = ((ra / 30.0) + _SEASON_C0 - 1) % 12 + 1     # center month, 1..12 float
    cm = ((round(center) - 1) % 12) + 1
    lo = ((cm - 2) % 12) + 1                              # month before the center
    hi = (cm % 12) + 1                                   # month after the center
    return f"{_MON_ABBR[lo - 1]}–{_MON_ABBR[hi - 1]}"


# Structured fields a Library entry can carry, in canonical write order (notes is
# user content — never auto-filled).
_FILLABLE = ["name", "type", "magnitude", "size", "season", "filter",
             "ra_deg", "dec_deg"]


def _is_missing(field: str, value) -> bool:
    """A Library field counts as missing (eligible for fill) if it's absent, blank,
    a placeholder "unknown" type, or a null magnitude — never a real user value."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if field == "type" and str(value).strip().lower() == "unknown":
        return True
    return False


def fill_missing_metadata(slug: str) -> dict:
    """Backfill an existing Library entry's **missing** structured fields from the
    bundled reference (and derive `season` from coords if still missing). Never
    overwrites a present, real value — preserves user edits. Returns the
    `{field: value}` actually filled (empty if nothing to do or slug unknown).

    Reference-only/offline: covers catalog objects whose Library row predates the
    reference data (e.g. captured-but-uncatalogued stubs). Online enrichment for
    fields the reference itself lacks is a later step (ROADMAP 5c)."""
    lib = load_library()
    entry = lib.get(slug)
    if entry is None:
        return {}
    ref = load_reference().get(slug, {})
    filled = _compute_fill(entry, ref)
    if filled:
        entry.update(filled)
        _write_library(lib)
    return filled


def fill_all_missing_metadata() -> dict[str, dict]:
    """Backfill every Library entry in a single rewrite. Returns
    `{slug: {field: value}}` for entries that gained fields."""
    lib = load_library()
    ref = load_reference()
    out: dict[str, dict] = {}
    for slug, entry in lib.items():
        filled = _compute_fill(entry, ref.get(slug, {}))
        if filled:
            entry.update(filled)
            out[slug] = filled
    if out:
        _write_library(lib)
    return out


def _compute_fill(entry: dict, ref: dict) -> dict:
    """Fields to add to `entry` from `ref` (+ derived season). Pure; no I/O."""
    filled: dict = {}
    for f in _FILLABLE:
        if not _is_missing(f, entry.get(f)):
            continue
        rv = ref.get(f)
        if rv is not None and not (isinstance(rv, str) and not rv.strip()):
            filled[f] = rv
    if _is_missing("season", filled.get("season", entry.get("season"))):
        ra = filled.get("ra_deg", entry.get("ra_deg"))
        if ra is not None:
            s = season_from_ra(ra)
            if s:
                filled["season"] = s
    return filled


def _write_library(entries: dict[str, dict]) -> None:
    """Rewrite library.toml from `entries`, preserving **every** key per entry
    (canonical order first, then any extras) so nothing is lost. The targeted writer
    for in-place updates (the add paths stay append-only)."""
    lines = ["# M110 Library — your object corpus (catalog members + additions).",
             "# M110 reads/writes this file.\n"]
    for slug, e in entries.items():
        lines.append(f"[catalog.{slug}]")
        extra = [k for k in e if k not in _LIB_ORDER]
        for k in _LIB_ORDER + extra:
            if k not in e:
                continue
            v = e[k]
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    config.LIBRARY_TOML.write_text("\n".join(lines))


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

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
_CATALOG_PRIORITY = ["messier", "caldwell", "rasc-finest", "herschel400",
                     "sharpless-best", "bennett", "lacaille"]

_MON_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS = {m.lower(): i for i, m in enumerate(_MON_ABBR, start=1)}

# RA→observing-season calibration. An object's 3-month evening-sky window tracks
# its RA (24h of RA over 12 months); c0 is fit so the derived window reproduces the
# curated Messier seasons in seed/objects.toml (≈98% exact match).
_SEASON_C0 = 10.1


class LibraryParseError(Exception):
    """`library.toml` is present but not valid TOML. Carries the file path so the
    user can find + fix their hand-edit (we never auto-rewrite a corrupt file —
    that would risk losing their corpus)."""


def load_library() -> dict[str, dict]:
    """Return the user's Library as {slug: entry} (from `library.toml`).

    **Self-heals duplicate object blocks** (e.g. from an interrupted/concurrent
    append) by keeping the first block per slug and rewriting the file — so a
    duplicate can never brick the app. Other malformed TOML raises
    `LibraryParseError` (with the file + line), since `library.toml` is
    user-editable and the most common mistake is a `True` instead of `true`."""
    try:
        with open(config.LIBRARY_TOML, "rb") as f:
            return tomllib.load(f).get("catalog", {})   # {} for an empty Library
    except UnicodeDecodeError as e:
        bad = e.object[e.start] if e.start < len(e.object) else 0
        raise LibraryParseError(
            f"{config.LIBRARY_TOML} is not valid UTF-8 (byte 0x{bad:02x} at position "
            f"{e.start}). This usually means it was written by an older M110 build on "
            "Windows (which used the cp1252 locale encoding). Delete the data folder "
            "(or just that file) to let M110 recreate it as UTF-8, or re-save it as "
            "UTF-8.") from e
    except tomllib.TOMLDecodeError as e:
        healed = _dedupe_catalog_text(config.LIBRARY_TOML.read_text(encoding="utf-8"))
        if healed is not None:
            try:
                data = tomllib.loads(healed).get("catalog", {})
            except tomllib.TOMLDecodeError:
                data = None
            if data is not None:
                config.LIBRARY_TOML.write_text(healed, encoding="utf-8")   # persist the repair
                print("  library.toml: removed duplicate object blocks (self-healed)")
                return data
        raise LibraryParseError(
            f"{config.LIBRARY_TOML} is not valid TOML: {e}\n"
            "Fix the hand-edit in that file (note: TOML booleans are lowercase "
            "`true`/`false`, not `True`/`False`) and try again.") from e


def _dedupe_catalog_text(text: str) -> str | None:
    """Drop duplicate `[catalog.<slug>]` blocks (keep the first of each). Returns
    the repaired text, or None if there were no duplicates to remove."""
    header = re.compile(r"^\[catalog\.([^\]]+)\]\s*$")
    out, seen, skip, changed = [], set(), False, False
    for ln in text.splitlines(keepends=True):
        m = header.match(ln)
        if m:
            if m.group(1) in seen:
                skip, changed = True, True
                continue
            seen.add(m.group(1))
            skip = False
        if not skip:
            out.append(ln)
    return "".join(out) if changed else None


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
    hemisphere, source_url, members}]`, sorted by name."""
    d = config.SEED_DIR / "catalogs"
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.toml")):
            data = load_bundled_catalog(p.stem)
            if data:
                out.append({"id": p.stem, "name": data.get("name", p.stem),
                            "description": data.get("description", ""),
                            "hemisphere": data.get("hemisphere", ""),
                            "source_url": data.get("source_url", ""),
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


def remove_library_entry(slug: str) -> bool:
    """Remove a single object from the Library (`library.toml`). Non-destructive:
    leaves `Objects/<id>/` (the journal) intact. Returns True if it was present.
    Backs the Library "Remove from Library" action."""
    lib = load_library()
    if slug not in lib:
        return False
    del lib[slug]
    _write_library(lib)
    return True


def remove_goal_members_from_library(goal_id: str, *, members=None) -> list[str]:
    """Prune a (de-activated) goal's members from the Library — but only those
    that are **uncaptured AND un-noted AND not in another active goal**. Captured
    or annotated objects always stay (the user has engaged with them). Returns the
    slugs removed. `members` may be passed in (e.g. for an already-deleted custom
    goal whose definition is gone)."""
    from . import goals as goals_mod, objects, derived
    if members is None:
        members = goals_mod.goal_members(goal_id)
    if not members:
        return []
    lib = load_library()
    captured = set(derived.load_totals().get("by_slug", {}))
    # Slugs still claimed by another *active* goal must be kept.
    other_active: set[str] = set()
    for gid in goals_mod.active_goal_ids():
        if gid == goal_id:
            continue
        other_active.update(goals_mod.goal_members(gid))
    removed = []
    for slug in members:
        if slug not in lib:
            continue
        if slug in captured or slug in other_active or objects.has_notes(slug):
            continue
        del lib[slug]
        removed.append(slug)
    if removed:
        _write_library(lib)
    return removed


_LIB_ORDER = ["id", "name", "type", "magnitude", "size", "season", "filter",
              "notes", "ra_deg", "dec_deg", "publish"]


def set_publish_flag(slug: str, publish: bool) -> bool:
    """Set an object's publish opt-out in `library.toml`. Default-publish: a True
    flag is stored as *absence* of the key (keeps the file clean), excluding sets
    `publish = false`. Returns True if the entry existed. Backs the Library
    "Exclude from publishing" / "Include in publishing" action."""
    lib = load_library()
    if slug not in lib:
        return False
    if publish:
        lib[slug].pop("publish", None)
    else:
        lib[slug]["publish"] = False
    _write_library(lib)
    return True


def _append_library_entries(entries: dict[str, dict]) -> None:
    """Append `[catalog.<slug>]` blocks to library.toml (the only writer besides
    config seeding + add_captured_objects). **Never writes a slug that's already in
    the file** — a duplicate block is invalid TOML, so this guard (re-read just
    before append, tolerant regex so it works even on an already-dup'd file) is the
    last line of defense against bricking the store."""
    existing: set[str] = set()
    if config.LIBRARY_TOML.is_file():
        existing = set(re.findall(r"^\[catalog\.([^\]]+)\]",
                                  config.LIBRARY_TOML.read_text(encoding="utf-8"), re.M))
    lines = []
    for slug, e in entries.items():
        if slug in existing:
            continue                       # already present → skip (no duplicate)
        existing.add(slug)
        lines.append(f"\n[catalog.{slug}]")
        for k in _LIB_ORDER:
            v = e.get(k)
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
    if lines:
        with config.LIBRARY_TOML.open("a", encoding="utf-8") as f:
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
# Fields that a catalog/online lookup can actually backfill. `filter` is deliberately
# NOT here: it's a per-capture setting (which filter you shot with), so no reference
# catalog or Simbad ever provides it — counting it as a gap made objects offer "Enrich
# online" and then find nothing (the NGC 6960 case). It's still a real Library field
# (see `_LIB_ORDER`), just not one enrichment can fill.
_FILLABLE = ["name", "type", "magnitude", "size", "season", "ra_deg", "dec_deg"]


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


def _has_gaps(entry: dict) -> bool:
    """True if any fillable field is still missing (worth an online lookup)."""
    return any(_is_missing(f, entry.get(f)) for f in _FILLABLE)


def fill_missing_metadata(slug: str, *, online: bool = False) -> dict:
    """Backfill an existing Library entry's **missing** structured fields from the
    bundled reference (and derive `season` from coords if still missing). Never
    overwrites a present, real value — preserves user edits. Returns the
    `{field: value}` actually filled (empty if nothing to do or slug unknown).

    Reference-only by default (offline) — covers catalog objects whose Library row
    predates the reference data (e.g. captured-but-uncatalogued stubs). With
    `online=True`, any gaps the reference can't fill are looked up on Simbad (the
    Veil's mag/size, etc.); raises `OnlineLookupError` if astroquery/network is
    unavailable (the caller surfaces a message)."""
    lib = load_library()
    entry = lib.get(slug)
    if entry is None:
        return {}
    filled = _compute_fill(entry, load_reference().get(slug, {}))
    if online:
        merged = {**entry, **filled}
        if _has_gaps(merged):
            data = resolve_object_online([merged.get("id") or slug]).get(
                merged.get("id") or slug, {})
            filled.update(_compute_fill(merged, data))
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


def enrich_online(slugs=None) -> dict[str, dict]:
    """Online (Simbad) enrichment for existing Library entries with gaps the bundled
    reference + derived season can't fill. One batched lookup; single rewrite. Never
    overwrites real user values. `slugs=None` → every entry with remaining gaps.
    Returns `{slug: {field: value}}`; raises `OnlineLookupError` if astroquery/network
    is unavailable."""
    lib = load_library()
    ref = load_reference()
    targets = list(lib) if slugs is None else [s for s in slugs if s in lib]
    # Apply the (free, offline) reference pass first, then see who still has gaps.
    base = {s: {**lib[s], **_compute_fill(lib[s], ref.get(s, {}))} for s in targets}
    gapped = {s: e for s, e in base.items() if _has_gaps(e)}
    if not gapped:
        # still persist any reference-only fills we computed above
        return fill_all_missing_metadata()
    names = {s: (e.get("id") or s) for s, e in gapped.items()}
    data = resolve_object_online(list(names.values()))
    out: dict[str, dict] = {}
    for slug, entry in lib.items():
        filled = _compute_fill(entry, ref.get(slug, {}))
        if slug in names:
            merged = {**entry, **filled}
            filled.update(_compute_fill(merged, data.get(names[slug], {})))
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
    config.LIBRARY_TOML.write_text("\n".join(lines), encoding="utf-8")


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


# ── online (Simbad) enrichment — optional `online` extra, explicit-use only ──────

class OnlineLookupError(Exception):
    """Online lookup couldn't run — astroquery isn't installed (the `online` extra)
    or the network/Simbad is unavailable. Distinct from a clean no-match (→ no
    entry in the result dict). The UI turns this into a friendly message."""


def _astroquery_missing_message() -> str:
    """The message for "astroquery can't be imported", tailored to how M110 is run.
    A **frozen** app has no pip, so telling the user to `pip install` is impossible —
    and packaged builds are *meant* to bundle astroquery (issue #64), so its absence
    there is a build defect worth reporting. From **source**, the extra is the fix."""
    import sys
    if getattr(sys, "frozen", False):
        return ("Online lookup isn't available in this build. It should be included — "
                "please report it via Help → Report a problem.")
    return ("Online lookup needs the optional 'online' extra "
            "(pip install 'm110[online]').")


# Simbad object-type code → our vocabulary (mirrors gen_caldwell._our_type, which
# maps Wikipedia prose; this maps Simbad's otype short codes — incl. AGN/Seyfert/
# QSO galaxy subtypes and the various nebula codes).
_SIMBAD_TYPE = {
    # galaxies (incl. AGN / Seyfert / QSO / interacting / cluster-member subtypes)
    "g": "galaxy", "gig": "galaxy", "gip": "galaxy", "gic": "galaxy",
    "bic": "galaxy", "ig": "galaxy", "pag": "galaxy", "grg": "galaxy",
    "clg": "galaxy", "sbg": "galaxy", "bcg": "galaxy", "h2g": "galaxy",
    "emg": "galaxy", "lsb": "galaxy", "rg": "galaxy", "agn": "galaxy",
    "syg": "galaxy", "sy": "galaxy", "sy1": "galaxy", "sy2": "galaxy",
    "lin": "galaxy", "qso": "galaxy", "bla": "galaxy", "bll": "galaxy",
    "gin": "galaxy", "gam": "galaxy",
    "glc": "globular", "gl?": "globular",
    "opc": "open_cluster", "cl*": "open_cluster", "as*": "open_cluster",
    "cl?": "open_cluster", "op?": "open_cluster",
    "pn": "planetary", "pn?": "planetary",
    "snr": "emission_snr", "sr?": "emission_snr", "sn?": "emission_snr",
    "dne": "dark_nebula", "gly": "dark_nebula",
    "hii": "emission", "emn": "emission", "rne": "emission", "neb": "emission",
    "gne": "emission", "cld": "emission", "ism": "emission", "mol": "emission",
    "hh": "emission",
}


def _simbad_type(otype) -> str:
    """Map a Simbad otype code to our type vocabulary; 'unknown' if unrecognized."""
    return _SIMBAD_TYPE.get(str(otype or "").strip().lower(), "unknown")


def _simbad_row_to_entry(row) -> dict:
    """Extract `{type, magnitude, size, ra_deg, dec_deg}` from a Simbad result row
    (shared by runtime enrichment + the bundled-data tool). Missing fields omitted."""
    out: dict = {}
    try:
        if row["ra"] is not None and not getattr(row["ra"], "mask", False):
            out["ra_deg"] = round(float(row["ra"]), 5)
            out["dec_deg"] = round(float(row["dec"]), 5)
    except Exception:
        pass
    try:
        maj = float(row["galdim_majaxis"]); minr = float(row["galdim_minaxis"])
        if maj == maj:                                   # not NaN
            out["size"] = f"{maj:.0f}'×{minr:.0f}'" if minr == minr else f"{maj:.0f}'"
    except Exception:
        pass
    try:
        v = float(row["V"])
        if v == v:
            out["magnitude"] = round(v, 1)
    except Exception:
        pass
    for col in ("otype", "otype_txt", "main_type"):
        try:
            t = _simbad_type(row[col])
            if t != "unknown":
                out["type"] = t
                break
        except Exception:
            continue
    return out


def resolve_object_online(names) -> dict[str, dict]:
    """Simbad lookup (one query per name) → `{queried-name: entry}` (entries hold any
    of type/magnitude/size/ra_deg/dec_deg that resolved). Names that don't resolve are
    simply absent. Raises `OnlineLookupError` if astroquery is missing or every query
    fails (offline). Network only runs when a caller explicitly invokes this."""
    names = [n for n in names if n]
    if not names:
        return {}
    try:
        import socket
        socket.setdefaulttimeout(15)
        from astroquery.simbad import Simbad
    except Exception as e:                                # astroquery absent OR failing to import
        # Log the real error with its traceback. astroquery can import cleanly from
        # source yet FAIL in a packaged build (e.g. #74: KeyError('astropy') because
        # astroquery's minversion() needed astropy's dist-info, which wasn't bundled).
        # The user only sees the generic "not available" message, so without this the
        # actual cause is invisible — surface it to the log / crash report.
        import logging
        logging.getLogger("m110").warning(
            "online lookup: astroquery.simbad could not be imported (%s: %s)",
            type(e).__name__, e, exc_info=True)
        raise OnlineLookupError(_astroquery_missing_message()) from e
    try:
        sim = Simbad()
        sim.add_votable_fields("V", "dim", "otype")
    except Exception as e:                                # bad astroquery setup
        raise OnlineLookupError(f"Simbad lookup failed: {e}") from e
    # Query one name at a time with query_object (singular), NOT the batch
    # query_objects: the batch path injects Simbad's int64 `object_number_id` (oid)
    # column, and astropy's VOTable parser overflows converting it on **Windows**, where
    # a C `long` is 32-bit — "OverflowError: Python int too large to convert to C long
    # (… col 'object_number_id')". query_object returns no int64 columns, so it's
    # cross-platform safe. We key by the *input* name (the singular query resolves the
    # name itself and needs no echo column). Per-name is fine: single lookups are the
    # common case, and bulk enrich is a backgrounded, cancellable action.
    out: dict[str, dict] = {}
    first_error: Exception | None = None
    for name in names:
        try:
            res = sim.query_object(name)
        except Exception as e:                            # network / Simbad hiccup
            if first_error is None:
                first_error = e
            continue
        if res is None or len(res) == 0:                  # unresolved name → skip quietly
            continue
        entry = _simbad_row_to_entry(res[0])
        if entry:
            out[name] = entry
    # Nothing resolved AND a query errored → Simbad/network is down; surface it. All-empty
    # with no error just means none of the names matched — return {} quietly (not an error).
    if not out and first_error is not None:
        raise OnlineLookupError(f"Simbad lookup failed: {first_error}") from first_error
    return out


def _designation_index() -> dict[str, str]:
    """`{slugified-designation: reference-slug}` across bundled catalogs, so a typed
    designation like 'C20' resolves to its reference slug (ngc-7000)."""
    from . import scan_sessions
    idx: dict[str, str] = {}
    for cat in list_bundled_catalogs():
        for slug, desig in cat.get("members", {}).items():
            idx[scan_sessions.slugify(str(desig))] = slug
    return idx


def resolve_new_object(identifier: str, *, online: bool = False) -> dict:
    """Resolve a typed name/designation into a candidate Library entry (no disk
    write) for the Add-object flow. Cascade: bundled reference (by slug or catalog
    designation) → online Simbad (when `online`) → coords-only fallback; `season` is
    always derived from resolved coords; `type` defaults 'unknown'.

    Returns `{"slug","entry","source"}` where `source` maps each filled field to
    'reference' / 'online' / 'derived' for the preview. Raises `OnlineLookupError`
    only if `online` and the lookup can't run."""
    from . import scan_sessions
    ident = (identifier or "").strip()
    norm = scan_sessions.slugify(ident)
    ref = load_reference()
    slug = norm if norm in ref else _designation_index().get(norm, norm)

    entry: dict = {"id": ident}
    source: dict = {}
    refent = ref.get(slug)
    if refent:
        for f in ["id", "name", *_FILLABLE]:
            v = refent.get(f)
            if v is not None and not (isinstance(v, str) and not v.strip()):
                entry[f] = v
                source[f] = "reference"
    if online and _has_gaps(entry):
        data = resolve_object_online([ident]).get(ident, {})
        for f, v in _compute_fill(entry, data).items():
            entry[f] = v
            source.setdefault(f, "online")
    # season is always derivable from coords if still missing
    if _is_missing("season", entry.get("season")) and entry.get("ra_deg") is not None:
        s = season_from_ra(entry["ra_deg"])
        if s:
            entry["season"] = s
            source.setdefault("season", "derived")
    entry.setdefault("type", "unknown")
    return {"slug": slug, "entry": entry, "source": source}


def add_library_entry(slug: str, entry: dict) -> None:
    """Commit a new object to the Library: append `[catalog.<slug>]` and create its
    journal stub. Refuses to overwrite an existing slug (`ValueError`)."""
    from . import scan_sessions
    slug = scan_sessions.slugify(slug)
    if not slug:
        raise ValueError("empty slug")
    if slug in load_library():
        raise ValueError(f"{slug} is already in the Library")
    clean = {k: v for k, v in entry.items()
             if v is not None and not (isinstance(v, str) and not v.strip())}
    clean.setdefault("id", slug)
    clean.setdefault("type", "unknown")
    _append_library_entries({slug: clean})
    config._ensure_object_stubs(config.DATA_ROOT, config.INTERNAL_DIR)


def add_captured_objects(resolve_coords: bool = True) -> list[str]:
    """Promote captured targets that aren't in the Library into first-class
    objects, so they appear in the Library/Summary views, get an object page +
    journal, and are clickable (not just folder-derived rows).

    A capture folder maps to the **catalog objects it contains** (`folder_to_slugs`
    against the Library + bundled reference): "M81" → m81, and a *combined* "M81 M82"
    → m81 + m82. Each mapped member missing from the Library is added from the
    reference — so a combined capture promotes **both** objects (#40c). Only a folder
    that maps to *no* catalog object (a genuinely off-catalog target) becomes an
    object in its own right: a minimal entry (id = folder name, type "unknown"),
    best-effort enriched with Simbad coords (→ pointing support).

    A capture **target** is never itself promoted into the object axis — that's the
    Images/ axis, and doing so created a synthetic `m81-m82` pseudo-object that then
    shadowed the folder→slug split (the M81/M82 under-count). Idempotent + additive:
    never touches an existing entry. Returns the slugs added.
    """
    from . import scan_sessions  # local import: avoids any import cycle
    path = config.LIBRARY_TOML
    if not path.is_file() or not config.IMAGES_DIR.is_dir():
        return []
    cat = load_library()
    ref = load_reference()
    known = set(cat) | set(ref)      # the object universe a folder may resolve into

    new: dict[str, dict] = {}
    for d in sorted(p for p in config.IMAGES_DIR.iterdir() if p.is_dir()):
        if not ((d / "lights").is_dir() or (d / "seestar-stacks").is_dir()):
            continue                                  # not a capture target
        folder = d.name
        members = scan_sessions.folder_to_slugs(folder, known)
        if members:
            # Known catalog object(s) — ensure each is in the Library, with its
            # full reference metadata. A combined folder promotes every member.
            for m in members:
                if m in cat or m in new or m not in ref:
                    continue
                entry = dict(ref[m])
                entry.setdefault("id", m.upper())
                new[m] = entry
            continue
        # Off-catalog target: no catalog object to credit, so the target doubles
        # as its own object.
        slug = scan_sessions.slugify(folder)
        if not slug or slug in cat or slug in new:
            continue
        entry = {"id": folder, "name": "", "type": "unknown"}
        if resolve_coords:
            rd = _simbad_coords(folder)
            if rd:
                entry["ra_deg"], entry["dec_deg"] = rd
        new[slug] = entry

    if new:
        _append_library_entries(new)
    return list(new)

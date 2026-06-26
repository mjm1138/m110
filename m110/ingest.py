"""Ingest new captures from the 'Inbox' staging area into the collection.

Faithful port of `scan_staging.py`'s classification, but returns a structured
**plan** (list of IngestOp) the GUI previews *before* any move. The actual move
(`apply_ops`) is the only thing that writes into the content tree, and the UI
gates it behind an explicit confirmation — honouring the hard rule "never modify
the content tree without explicit confirmation."

Staging layout recognised:
  <object>_sub/      raw Light_*.fit    → Images/<object>/lights/
  <object>/          in-app stacks      → Images/<object>/seestar-stacks/
  <Category>_photo|_video/  media       → Media/<Category>_photo|_video/
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import catalog, config

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore

POINTING_TOL_DEG = 0.15   # frame-vs-catalog separation that flags a name mismatch


class IngestCancelled(Exception):
    """Raised inside a scan when the caller's should_cancel() turns true."""


def _staging() -> Path:
    return config.STAGING_DIR


@dataclass
class IngestOp:
    src: str         # absolute source file
    dest: str        # absolute destination file
    kind: str        # 'light' | 'stack' | 'media'
    group: str       # source directory name
    dest_rel: str    # destination relative to the data root (for display)
    new_object: bool = False  # a new capture-target dir will be created
    action: str = "move"      # 'move' (staging) | 'copy' (device)
    size_bytes: int = 0       # source file size (stat'd on the scan worker)


@dataclass
class IngestGroup:
    """One source folder's worth of ops, aggregated for a per-object preview."""
    group: str               # source directory name (the selectable unit)
    object: str              # friendly object/category label
    kind: str                # 'light' | 'stack' | 'media'
    frames: int              # number of new files
    size_bytes: int          # total size of the new files
    dest_dir: str            # destination dir, relative to the data root
    new_object: bool
    action: str
    ops: list                # the underlying IngestOps
    pointing: str | None = None    # warning text if the frame's RA/DEC ≠ the name
    suggested: str | None = None   # slug of a better-matching catalog object


# ── classification helpers (ported verbatim) ───────────────────────────────────

def is_media_dir(name: str) -> bool:
    return name.endswith("_photo") or name.endswith("_video")


def fits_object_name(scope_name: str) -> str:
    """Seestar 'M 13' → FITS 'M13'; multi-object names left as-is."""
    return re.sub(r"^M (\d+)$", r"M\1", scope_name)


def is_stacked_fit(filename: str) -> bool:
    return (filename.startswith("Stacked_")
            or filename.startswith("DSO_Stacked_")
            or filename.startswith("Video_Stacked_"))


def _fit_files(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() == ".fit")


def _all_files(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and not f.name.startswith("."))


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# ── name canonicalization + alias table (#12a, #12c) ──────────────────────────

def _alias_path() -> Path:
    return config.INTERNAL_DIR / "ingest_aliases.toml"


def load_aliases() -> dict[str, str]:
    """Per-store known-quirk remaps {source name: canonical target}."""
    p = _alias_path()
    if not p.is_file():
        return {}
    try:
        with p.open("rb") as f:
            return dict(tomllib.load(f).get("alias", {}))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def add_alias(src: str, dst: str) -> None:
    """Remember a remap so future ingests of `src` route to `dst`. Only writer."""
    aliases = load_aliases()
    aliases[src] = dst
    p = _alias_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[alias]"]
    for k, v in sorted(aliases.items()):
        lines.append(f"{json.dumps(k)} = {json.dumps(v)}")   # TOML strings ≈ JSON
    p.write_text("\n".join(lines) + "\n")


def canonical_target(name: str) -> str:
    """Resolve a device folder name to a canonical destination object: alias →
    existing Images/<dir> casing → catalog id casing → normalized name. Folds
    case variants (`m82`→`M82`) and known quirks onto one folder."""
    aliases = load_aliases()
    low = name.lower()
    for k, v in aliases.items():
        if k.lower() == low:
            return v

    norm = fits_object_name(name)
    nlow = norm.lower()

    images = config.IMAGES_DIR
    if images.is_dir():
        for d in images.iterdir():
            if d.is_dir() and d.name.lower() == nlow:
                return d.name              # reuse the existing folder's casing

    try:
        cat = catalog.load_library()
    except Exception:
        cat = {}
    # The user's Library first, then the bundled reference (so a brand-new catalog
    # object — not yet in the Library — still folds onto its canonical id casing).
    for source in (cat, catalog.load_reference()):
        for slug, e in source.items():
            if (e.get("id") or "").lower() == nlow or slug.lower() == nlow:
                return e.get("id") or norm
    return norm


# ── pointing verification (#12b) ──────────────────────────────────────────────

def _parse_sexagesimal(ra: str, dec: str):
    def _val(s):
        parts = [float(x) for x in str(s).replace(":", " ").split()]
        v = parts[0] + (parts[1] / 60 if len(parts) > 1 else 0) + \
            (parts[2] / 3600 if len(parts) > 2 else 0)
        return v, parts[0]
    try:
        ra_h, _ = _val(ra)
        dec_v, dec_first = _val(dec)
        sign = -1 if str(dec).strip().startswith("-") else 1
        return ra_h * 15.0, sign * abs(dec_v)
    except (ValueError, IndexError):
        return None


def frame_radec(path: str):
    """(ra_deg, dec_deg) from a frame header, or None. Seestar uses RA/DEC in
    degrees; falls back to sexagesimal OBJCTRA/OBJCTDEC."""
    try:
        from astropy.io import fits
    except ImportError:
        return None
    try:
        with fits.open(path) as h:
            hdr = h[0].header
            if hdr.get("RA") is not None and hdr.get("DEC") is not None:
                return float(hdr["RA"]), float(hdr["DEC"])
            ra, dec = hdr.get("OBJCTRA"), hdr.get("OBJCTDEC")
            if ra and dec:
                return _parse_sexagesimal(ra, dec)
    except Exception:
        return None
    return None


def _separation_deg(ra1, dec1, ra2, dec2) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = (math.sin((d2 - d1) / 2) ** 2
         + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2)
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def _slug_for_object(obj: str, cat: dict) -> str | None:
    # Library first, then the bundled reference (catalog objects not yet captured).
    for source in (cat, catalog.load_reference()):
        for slug, e in source.items():
            if (e.get("id") or "") == obj:
                return slug
        if obj in source:
            return obj
    return None


def _nearest(coords: dict, ra: float, dec: float):
    best, best_sep = None, 999.0
    for slug, (cra, cdec) in coords.items():
        s = _separation_deg(ra, dec, cra, cdec)
        if s < best_sep:
            best, best_sep = slug, s
    return best, best_sep


def annotate_pointing(groups: list[IngestGroup], should_cancel=None) -> list[IngestGroup]:
    """Flag groups whose sample frame points >0.15° from the named object, and
    suggest the nearest catalog object. Reads ONE frame per group (worker I/O).
    Degrades to no-op where coords/frames are unavailable."""
    coords = catalog.load_coords()
    if not coords:
        return groups
    try:
        cat = catalog.load_library()
    except Exception:
        cat = {}
    for g in groups:
        if should_cancel and should_cancel():
            break
        if g.kind == "media" or not g.ops:
            continue
        radec = frame_radec(g.ops[0].src)
        if radec is None:
            continue
        slug = _slug_for_object(g.object, cat)
        proposed = coords.get(slug) if slug else None
        if proposed is None:
            continue                          # unknown object → unverified
        sep = _separation_deg(radec[0], radec[1], proposed[0], proposed[1])
        if sep <= POINTING_TOL_DEG:
            continue                          # pointing matches the name ✓
        near, near_sep = _nearest(coords, *radec)
        if near and near != slug and near_sep <= POINTING_TOL_DEG:
            near_id = (cat.get(near, {}).get("id")
                       or catalog.load_reference().get(near, {}).get("id") or near)
            g.pointing = f"⚠ {sep:.2f}° off — looks like {near_id}"
            g.suggested = near
        else:
            g.pointing = f"⚠ points {sep:.2f}° from {g.object}"
    return groups


def retarget(group: IngestGroup, new_object: str) -> IngestGroup:
    """Rebuild a group's ops to land under a different destination object (used by
    the remap dropdown). Only light/stack groups are retargetable."""
    root = config.DATA_ROOT
    dst_dir = (config.lights_dir(new_object) if group.kind == "light"
               else config.seestar_stacks_dir(new_object))
    new_flag = not config.target_dir(new_object).is_dir()
    new_ops = []
    for op in group.ops:
        dest = dst_dir / Path(op.src).name
        new_ops.append(replace(op, dest=str(dest),
                               dest_rel=str(dest.relative_to(root)),
                               new_object=new_flag))
    return replace(group, object=new_object, dest_dir=str(dst_dir.relative_to(root)),
                   new_object=new_flag, ops=new_ops, pointing=None, suggested=None)


# ── planning ────────────────────────────────────────────────────────────────

def staging_available() -> bool:
    return _staging().is_dir()


def seestar_available() -> bool:
    return config.find_seestar_myworks() is not None


def _scan_base(base, action: str, should_cancel=None) -> list[IngestOp]:
    """Classify a base dir laid out like the Seestar staging/MyWorks structure
    and return the operations to bring NEW files into the collection. Reads only.
    `action` is 'move' (staging) or 'copy' (device — leaves originals in place).
    `should_cancel` is an optional callable checked at directory boundaries;
    if it returns true, IngestCancelled is raised (for a responsive Cancel)."""
    if base is None or not base.is_dir():
        return []

    def _ck():
        if should_cancel and should_cancel():
            raise IngestCancelled()

    entries = sorted(e.name for e in base.iterdir()
                     if e.is_dir() and not e.name.startswith("."))
    sub_dirs = [e for e in entries if e.endswith("_sub")]
    media_dirs = [e for e in entries if is_media_dir(e)]
    stack_dirs = [e for e in entries if not e.endswith("_sub") and not is_media_dir(e)]

    root = config.DATA_ROOT
    ops: list[IngestOp] = []

    for sub in sub_dirs:
        _ck()
        obj = canonical_target(sub[:-4])  # strip "_sub"; fold case/aliases
        src_dir = base / sub
        dst_dir = config.lights_dir(obj)
        existing = set(_fit_files(dst_dir))
        new_object = not config.target_dir(obj).is_dir()
        for f in _fit_files(src_dir):
            if f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "light", sub,
                                str(dest.relative_to(root)), new_object, action,
                                _size(src_dir / f)))

    for sd in stack_dirs:
        _ck()
        obj = canonical_target(sd)
        src_dir = base / sd
        dst_dir = config.seestar_stacks_dir(obj)
        existing = set(_fit_files(dst_dir))
        for f in _fit_files(src_dir):
            if not is_stacked_fit(f) or f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "stack", sd,
                                str(dest.relative_to(root)), False, action,
                                _size(src_dir / f)))
        # Also pull the device's preview renders (.jpg/.png) into the same stack
        # folder so the gallery has ready-made images; skip the Seestar's
        # *_thn.* sidecar thumbnails.
        existing_all = set(_all_files(dst_dir))
        for f in _all_files(src_dir):
            if "_thn." in f or f in existing_all:
                continue
            if f.rsplit(".", 1)[-1].lower() in ("jpg", "jpeg", "png"):
                dest = dst_dir / f
                ops.append(IngestOp(str(src_dir / f), str(dest), "stack", sd,
                                    str(dest.relative_to(root)), False, action,
                                    _size(src_dir / f)))

    for md in media_dirs:
        _ck()
        src_dir = base / md
        dst_dir = config.MEDIA_DIR / md
        existing = set(_all_files(dst_dir))
        for f in _all_files(src_dir):
            if f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "media", md,
                                str(dest.relative_to(root)), False, action,
                                _size(src_dir / f)))
    return ops


def _object_label(group: str, kind: str) -> str:
    """Friendly object/category name for a source folder. Folds onto the canonical
    destination target (case/alias), so the preview label matches where the files
    actually land (e.g. `m13_sub` → "M13", not "m13")."""
    if kind == "media":
        return group
    base = group[:-4] if group.endswith("_sub") else group   # strip "_sub"
    return canonical_target(base)


def group_ops(ops: list[IngestOp]) -> list[IngestGroup]:
    """Aggregate a flat op list into one IngestGroup per source folder — the unit
    the preview shows and the user selects. Order: objects A→Z, media last."""
    by_group: dict[str, list[IngestOp]] = {}
    for op in ops:
        by_group.setdefault(op.group, []).append(op)

    groups: list[IngestGroup] = []
    for name, gops in by_group.items():
        kind = gops[0].kind
        # destination dir = parent of the first op's destination
        dest_dir = str(Path(gops[0].dest_rel).parent)
        groups.append(IngestGroup(
            group=name,
            object=_object_label(name, kind),
            kind=kind,
            frames=len(gops),
            size_bytes=sum(o.size_bytes for o in gops),
            dest_dir=dest_dir,
            new_object=any(o.new_object for o in gops),
            action=gops[0].action,
            ops=gops,
        ))
    # media rows after catalog objects, then by object name
    groups.sort(key=lambda g: (g.kind == "media", g.object.lower()))
    return groups


def scan_staging_plan(should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for the Inbox staging area (moves). Reads only."""
    return _scan_base(_staging(), "move", should_cancel)


def scan_seestar_plan(should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for a mounted Seestar's MyWorks (copies — leaves the device
    untouched). Empty if no Seestar is mounted. Reads only."""
    return _scan_base(config.find_seestar_myworks(), "copy", should_cancel)


def apply_ops(ops: list[IngestOp], progress=None, should_cancel=None) -> dict:
    """Perform the moves/copies. THIS WRITES INTO Images/ — callers must confirm.

    Creates destination dirs, skips files that already exist at the destination.
    `progress(i, total)` is called after each op. `should_cancel()` is checked
    before each op; cancelling stops cleanly (files already done stay done — safe,
    since a re-scan simply lists whatever's still missing).
    """
    moved = skipped = 0
    total = len(ops)
    cancelled = False
    for i, op in enumerate(ops, 1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        os.makedirs(os.path.dirname(op.dest), exist_ok=True)
        if os.path.exists(op.dest):
            skipped += 1
        else:
            if op.action == "copy":
                # Bytes only (no copystat): copying from an SMB-mounted Seestar,
                # copying the source's flags/xattrs onto the destination raises
                # EPERM on macOS. Write to a temp then atomically rename so an
                # interrupted copy never leaves a partial file that a re-scan
                # would treat as "already present".
                tmp = op.dest + ".part"
                try:
                    shutil.copyfile(op.src, tmp)
                    os.replace(tmp, op.dest)
                except BaseException:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                    raise
            else:
                shutil.move(op.src, op.dest)
            moved += 1
        if progress:
            progress(i, total)
    return {"moved": moved, "skipped": skipped, "cancelled": cancelled}

"""Ingest new captures from the 'From the scope' staging area into the collection.

Faithful port of `scan_staging.py`'s classification + path conventions, but
returns a structured **plan** (list of IngestOp) the GUI previews *before* any
move. The actual move (`apply_ops`) is the only thing that writes into Images/,
and the UI gates it behind an explicit confirmation — honouring the hard rule
"never modify Images/ without explicit confirmation."

Staging layout recognised:
  <object>_sub/      raw Light_*.fit    → Images/FITS/<object>/lights/
  <object>/          in-app stacks      → Images/Seestar_stacks/<object>/
  <Category>_photo|_video/  media       → Images/<Category>_photo|_video/
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import config


class IngestCancelled(Exception):
    """Raised inside a scan when the caller's should_cancel() turns true."""


def _staging() -> Path:
    return config.IMAGES_DIR / "From the scope"


@dataclass
class IngestOp:
    src: str         # absolute source file
    dest: str        # absolute destination file
    kind: str        # 'light' | 'stack' | 'media'
    group: str       # source directory name
    dest_rel: str    # destination relative to Images/ (for display)
    new_object: bool = False  # FITS object dir will be created
    action: str = "move"      # 'move' (staging) | 'copy' (device)


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

    imgs = config.IMAGES_DIR
    fits_base = imgs / "FITS"
    stacks_base = imgs / "Seestar_stacks"
    ops: list[IngestOp] = []

    for sub in sub_dirs:
        _ck()
        obj = fits_object_name(sub[:-4])  # strip "_sub"
        src_dir = base / sub
        dst_dir = fits_base / obj / "lights"
        existing = set(_fit_files(dst_dir))
        new_object = not (fits_base / obj).is_dir()
        for f in _fit_files(src_dir):
            if f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "light", sub,
                                str(dest.relative_to(imgs)), new_object, action))

    for sd in stack_dirs:
        _ck()
        obj = fits_object_name(sd)
        src_dir = base / sd
        dst_dir = stacks_base / obj
        existing = set(_fit_files(dst_dir))
        for f in _fit_files(src_dir):
            if not is_stacked_fit(f) or f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "stack", sd,
                                str(dest.relative_to(imgs)), False, action))
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
                                    str(dest.relative_to(imgs)), False, action))

    for md in media_dirs:
        _ck()
        src_dir = base / md
        dst_dir = imgs / md
        existing = set(_all_files(dst_dir))
        for f in _all_files(src_dir):
            if f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "media", md,
                                str(dest.relative_to(imgs)), False, action))
    return ops


def scan_staging_plan(should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for the 'From the scope' staging area (moves). Reads only."""
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

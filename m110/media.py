"""Read non-catalog media from the data store's `Media/` axis.

Ingest drops lunar/planetary/scenery captures into
`Media/<Category>_photo|_video/`; this is the read side (Qt-free, like
`derived.load_sessions`) that the UI's Media page renders. No derived JSON — the
folder is scanned directly on demand.

Two things this module is deliberate about:

* **The walk is recursive and the kind is per file, not per folder.** The old
  scanner read one level and only accepted the extension matching the folder's
  `_photo`/`_video` suffix, which silently hid real work: the
  `Video_Stacked_*.jpg`/`.fit` results that land at the top of a `_video/` folder,
  and whole subfolders of processed output (`ASIVideoStack_Output/`). Same lesson
  `ingest.scan_directory_plan` already learned — a shallow scan misses nested
  subtrees and gives no sign that it did.
* **`_thn.` sidecars are never listed, but a video's sidecar is load-bearing.**
  The Seestar writes `<stem>_thn.jpg` beside every capture. Beside a *photo* it is
  a redundant low-res duplicate (listing it showed every photo twice); beside a
  *video* it is the only poster frame we have, so it is retained on disk and
  resolved through `poster_for`. `cleanup_candidates` honours that distinction.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config

# Photo extensions the UI can show. `.fit`/`.fits` are included because real
# stacked lunar/planetary results are saved as FITS beside the video they came
# from; they render through `build_images` rather than directly (see poster_for).
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".fit", ".fits")
_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")

# Photo extensions Qt can show *faithfully* on its own. TIFF is deliberately NOT
# here even though Qt decodes it: astro TIFFs are 32-bit float or uint16 with the
# signal packed into a narrow range, and Qt maps that linearly — a faint stack
# comes out at max luminance 14/255, i.e. black. `build_images._open_image`
# percentile-stretches it (same file: 255). Anything not listed gets a render.
_QT_READABLE = (".jpg", ".jpeg", ".png")

SIDECAR_MARKER = "_thn."

# Device sidecars that carry no content and that nothing in the app reads. The
# Seestar writes these next to a `-RAW.avi`; they were imported by accident (the
# media ingest branch used to copy every file) and are pure noise in the store.
_JUNK_SUFFIXES = (".avi.idx", ".avi.txt")

# Seestar/Dwarf capture filenames lead with the capture timestamp, e.g.
# `2026-05-31-002114-Lunar.jpg`. Used for **display ordering only** — never
# arithmetic. (Header truth > file metadata > filenames; a filename is the weakest
# signal and is trusted here only because nothing depends on it being right.)
_STAMP_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})")


@dataclass(frozen=True)
class MediaItem:
    """One media file on the `Media/` axis.

    `category` is the folder prefix (`Lunar_photo` → "Lunar"); `kind` is decided
    by the file's own extension, so a `.jpg` sitting in a `_video/` folder is a
    photo. `subfolder` is the store-relative path below the category dir ("" at
    the top level), which is how processed-output subtrees stay attributable.
    `captured` is the filename timestamp when present, else the file mtime.
    """
    name: str
    path: Path
    category: str
    kind: str            # 'photo' | 'video'
    size_bytes: int
    mtime: float
    captured: float
    subfolder: str = ""

    @property
    def key(self) -> str:
        """Stable identity for the UI (tile keys, selection restore)."""
        return str(self.path)


def is_sidecar(name: str) -> bool:
    """A device thumbnail sidecar (`<stem>_thn.jpg`).

    The one definition — `ingest` and the cleanup action both defer to it, so the
    rule can't drift the way it did when the media ingest branch quietly skipped
    the filter every other path applied.
    """
    return SIDECAR_MARKER in name


def is_junk(name: str) -> bool:
    """A device sidecar carrying no content (`.avi.idx` / `.avi.txt`)."""
    low = name.lower()
    return any(low.endswith(s) for s in _JUNK_SUFFIXES)


def kind_for(name: str) -> str | None:
    """'photo' | 'video' from the file's own extension, or None if not media."""
    ext = Path(name).suffix.lower()
    if ext in _PHOTO_EXTS:
        return "photo"
    if ext in _VIDEO_EXTS:
        return "video"
    return None


def _category_of(folder: str) -> str | None:
    """`Lunar_photo` → "Lunar". None when the folder isn't a media category."""
    if folder.endswith("_photo") or folder.endswith("_video"):
        return folder.rsplit("_", 1)[0]
    return None


def _captured_from_name(name: str, fallback: float) -> float:
    m = _STAMP_RE.match(name)
    if not m:
        return fallback
    try:
        return datetime(*(int(g) for g in m.groups())).timestamp()
    except ValueError:
        return fallback


def list_media() -> list[MediaItem]:
    """Every media file under `Media/`, flat and newest-first.

    Recursive: processed output nested under a category folder is real work and
    belongs in the library. Sidecars, junk and non-media files are excluded.
    Returns `[]` when `Media/` is absent.
    """
    root = config.MEDIA_DIR
    if not root.is_dir():
        return []
    out: list[MediaItem] = []
    for cat_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        category = _category_of(cat_dir.name)
        if category is None:
            continue
        for dirpath, dirnames, filenames in os.walk(cat_dir):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            here = Path(dirpath)
            rel = here.relative_to(cat_dir)
            subfolder = "" if rel == Path(".") else str(rel)
            for fname in sorted(filenames):
                if fname.startswith(".") or is_sidecar(fname) or is_junk(fname):
                    continue
                kind = kind_for(fname)
                if kind is None:
                    continue
                f = here / fname
                try:
                    st = f.stat()
                except OSError:
                    continue
                out.append(MediaItem(
                    name=fname, path=f, category=category, kind=kind,
                    size_bytes=st.st_size, mtime=st.st_mtime,
                    captured=_captured_from_name(fname, st.st_mtime),
                    subfolder=subfolder))
    out.sort(key=lambda i: (-i.captured, i.category.lower(), i.name.lower()))
    return out


def categories() -> list[str]:
    """Category names present in the store, A→Z (for the UI filter)."""
    return sorted({i.category for i in list_media()})


def sidecar_for(path: Path) -> Path | None:
    """The `<stem>_thn.jpg` sitting beside `path`, if it exists."""
    cand = path.with_name(f"{path.stem}{SIDECAR_MARKER}jpg")
    return cand if cand.is_file() else None


def needs_render(item: MediaItem) -> bool:
    """True when this item's still has to be generated rather than read directly."""
    return (item.kind == "photo"
            and item.path.suffix.lower() not in _QT_READABLE)


def _render_path(item: MediaItem) -> Path:
    """Where this item's generated poster lives (content-hashed, may not exist)."""
    from . import build_images
    return config.MEDIA_RENDERS_DIR / f"{build_images.img_hash(item.path)}.jpg"


def poster_for(item: MediaItem, *, render: bool = True) -> Path | None:
    """A displayable still for `item`, or None to fall back to a placeholder.

    Ordered tiers, so a richer source can be added ahead of the fallback without
    reshaping callers:

    1. **video** → the device's sibling `<stem>_thn.jpg` poster frame. Every
       Seestar capture ships one, which is why video thumbnails cost no new
       dependency. *(A decoded frame-grab tier would slot in right here for
       devices that write no sidecar.)*
    2. **photo** Qt shows faithfully (JPEG/PNG) → the file itself.
    3. **photo** it doesn't (FITS, astro TIFF) → a cached render via
       `build_images.make_thumb`, generic over any source and destination.

    `render=False` makes tier 3 **non-blocking**: an already-cached render is
    returned, otherwise None. Generating one costs ~0.1 s, so a view that builds
    every visible tile up front must not do it inline — that scales straight into
    a multi-second freeze on a store full of stacked results. Callers pass
    `render=False` for bulk population and let a worker fill them in
    (`render_posters`); a single-image consumer like the detail pane can render.
    """
    if item.kind == "video":
        return sidecar_for(item.path)
    if not needs_render(item):
        return item.path
    try:
        cached = _render_path(item)
    except OSError:                     # the source vanished under us
        return None
    if cached.exists():
        return cached
    if not render:
        return None
    from . import build_images
    config.MEDIA_RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    return build_images.make_thumb(item.path, config.MEDIA_RENDERS_DIR)


def pending_posters(items) -> list[MediaItem]:
    """Items whose poster still has to be generated (cheap: a stat each)."""
    return [i for i in items
            if needs_render(i) and poster_for(i, render=False) is None]


def render_posters(items, progress=None, should_cancel=None) -> int:
    """Generate the missing posters for `items`. Returns how many were made.

    Qt-free and interruptible so the UI can run it on a worker.
    """
    made = 0
    todo = pending_posters(items)
    for n, item in enumerate(todo, 1):
        if should_cancel is not None and should_cancel():
            break
        if poster_for(item, render=True) is not None:
            made += 1
        if progress is not None:
            progress(n, len(todo))
    return made


def cleanup_candidates() -> list[Path]:
    """Imported files under `Media/` that carry no content and nothing reads.

    Namely the redundant `<stem>_thn.jpg` beside a **photo**, and `.avi.idx` /
    `.avi.txt` device sidecars. A sidecar serving as a **video poster** is never
    returned — it is the only still that video has (see `poster_for`). An
    *orphaned* sidecar (its source file is gone) is returned, since it can no
    longer be a poster for anything.
    """
    root = config.MEDIA_DIR
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        here = Path(dirpath)
        names = set(filenames)
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            if is_junk(fname):
                out.append(here / fname)
                continue
            if not is_sidecar(fname):
                continue
            stem = fname.split(SIDECAR_MARKER)[0]
            # Which source does this sidecar belong to? If it's a video, the
            # sidecar is the poster and must survive.
            source_kinds = {kind_for(n) for n in names
                            if n != fname and Path(n).stem == stem}
            if "video" in source_kinds:
                continue
            out.append(here / fname)
    return out


def discard(paths) -> dict:
    """Permanently delete the given files from `Media/`.

    **Destructive — callers MUST confirm.** Two guards, both deliberate: a path
    that escapes `config.MEDIA_DIR` is skipped (the containment rule
    `ingest.discard_holding` already follows), and a path that is not currently a
    `cleanup_candidates()` entry is skipped too. The second guard is what keeps a
    stale selection from deleting content: the candidate set is recomputed here,
    so a file that became a video poster between preview and confirm survives.

    Returns ``{"deleted": n, "bytes": n, "skipped": n}``.
    """
    base = config.MEDIA_DIR.resolve()
    allowed = {p.resolve() for p in cleanup_candidates()}
    deleted = freed = skipped = 0
    for raw in paths:
        p = Path(raw)
        try:
            rp = p.resolve()
        except OSError:
            skipped += 1
            continue
        if base not in rp.parents or rp not in allowed:
            skipped += 1
            continue
        try:
            size = rp.stat().st_size
            rp.unlink()
        except OSError:
            skipped += 1
            continue
        deleted += 1
        freed += size
    return {"deleted": deleted, "bytes": freed, "skipped": skipped}

"""Read non-catalog media from the data store's `Media/` axis.

Ingest drops lunar/planetary/scenery captures into
`Media/<Category>_photo|_video/`; this is the read side (Qt-free, like
`derived.load_sessions`) that the UI's Media page renders. No derived JSON — the
folder is scanned directly on demand.
"""
from __future__ import annotations

from . import config

_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")


def _kind_for(folder: str) -> str | None:
    if folder.endswith("_photo"):
        return "photo"
    if folder.endswith("_video"):
        return "video"
    return None


def scan() -> list[dict]:
    """Enumerate `Media/` → one entry per `<Category>_photo|_video/` folder:

    `{category, kind, dir, items: [{name, path, size_bytes, mtime}]}`,
    sorted by category A→Z then photos before videos. `[]` if `Media/` is
    absent/empty. Only files whose extension matches the folder kind are listed.
    """
    root = config.MEDIA_DIR
    if not root.is_dir():
        return []
    exts = {"photo": _PHOTO_EXTS, "video": _VIDEO_EXTS}
    out: list[dict] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        kind = _kind_for(d.name)
        if kind is None:
            continue
        items = []
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in exts[kind]:
                st = f.stat()
                items.append({"name": f.name, "path": f,
                              "size_bytes": st.st_size, "mtime": st.st_mtime})
        if not items:
            continue
        category = d.name.rsplit("_", 1)[0]
        out.append({"category": category, "kind": kind, "dir": d, "items": items})
    out.sort(key=lambda c: (c["category"].lower(), c["kind"] != "photo"))
    return out

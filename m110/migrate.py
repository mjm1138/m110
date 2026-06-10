"""In-place migration of a data store to the current (two-axis) layout.

The store originally mixed machine state and content across `data/`, `Images/`
(with jargon subfolders `FITS` / `Seestar_stacks` / `Finished Images` /
`From the scope`), and `site/`. The current layout (store version 2) is:

    Objects/<catalog id>/journal.md          (catalog-object axis)
    Images/<target>/{lights,stacks,seestar-stacks,finished}/
    Media/<Category>_photo|_video/
    Inbox/                                   (ingest staging)
    .m110_internal_data/{catalog,priorities,sessions,...}  + derived/ + renders/

`migrate_store()` is **idempotent** and **version-stamped**: it runs only when an
old-layout marker is present and the store hasn't reached version 2, moves data
with same-filesystem renames (cheap), and a re-run resumes a partial move rather
than duplicating or destroying anything. It is Qt-free and only ever exercised on
temp/throwaway roots in tests — never pointed at a live root in validation.
"""
from __future__ import annotations

import shutil
from pathlib import Path

STORE_VERSION = 2
INTERNAL_DIRNAME = ".m110_internal_data"
VERSION_FILE = ".store_version"

_STACK_EXTS = (".fit", ".fits", ".tif", ".tiff")


def _read_version(root: Path) -> int:
    f = root / INTERNAL_DIRNAME / VERSION_FILE
    try:
        return int(f.read_text().strip())
    except (OSError, ValueError):
        return 0


def _has_old_layout(root: Path) -> bool:
    return ((root / "data" / "catalog.toml").is_file()
            or (root / "Images" / "FITS").is_dir()
            or (root / "site").is_dir())


def _relocate(src: Path, dst: Path) -> None:
    """Move `src` to `dst`, merging into an existing `dst` (resume-safe).

    - Missing `src`: no-op.
    - `dst` absent: plain move (same-fs rename).
    - Both dirs: recurse per child, then drop the emptied `src`.
    - `dst` already a file: keep it (already migrated), leave `src` be.
    """
    if not src.exists():
        return
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return
    if src.is_dir() and dst.is_dir():
        for child in list(src.iterdir()):
            _relocate(child, dst / child.name)
        try:
            src.rmdir()
        except OSError:
            pass


def _rmdir_if_empty(d: Path) -> None:
    try:
        d.rmdir()
    except OSError:
        pass


# OS-generated junk that shouldn't keep a legacy container "alive" after its
# real contents have been migrated out.
_JUNK_FILES = {".DS_Store", ".localized", "Thumbs.db"}


def _drop_legacy(d: Path) -> None:
    """Remove a legacy directory tree if it holds nothing but OS junk files.

    Recurses depth-first; a directory is removed only once it contains solely
    junk files (which are deleted) — never a dir with real content left in it.
    """
    if not d.is_dir():
        return
    for child in list(d.iterdir()):
        if child.is_dir():
            _drop_legacy(child)
    remaining = list(d.iterdir())
    if remaining and all(c.is_file() and c.name in _JUNK_FILES for c in remaining):
        for c in remaining:
            try:
                c.unlink()
            except OSError:
                pass
    _rmdir_if_empty(d)


def _load_slug_to_id(catalog_toml: Path) -> dict[str, str]:
    """Map catalog slug → display id (e.g. 'm101' → 'M101') for journal folders."""
    if not catalog_toml.is_file():
        return {}
    try:
        import tomllib
    except ImportError:  # pragma: no cover - py<3.11 fallback
        import tomli as tomllib  # type: ignore
    try:
        with catalog_toml.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    return {slug: (entry.get("id") or slug)
            for slug, entry in data.get("catalog", {}).items()}


def _safe_id(obj_id: str) -> str:
    return obj_id.replace("/", "-").strip()


def _is_media_name(name: str) -> bool:
    return name.endswith("_photo") or name.endswith("_video")


def migrate_store(root) -> bool:
    """Bring an older store at `root` up to the current layout.

    Returns True if a migration was performed, False if nothing was needed.
    """
    root = Path(root).expanduser()
    if _read_version(root) >= STORE_VERSION:
        return False
    if not _has_old_layout(root):
        return False

    internal = root / INTERNAL_DIRNAME
    internal.mkdir(parents=True, exist_ok=True)

    data = root / "data"
    images = root / "Images"
    site = root / "site"

    # Capture the slug→id map before catalog.toml moves.
    slug_to_id = _load_slug_to_id(data / "catalog.toml")
    if not slug_to_id:
        slug_to_id = _load_slug_to_id(internal / "catalog.toml")

    # 1. Machine state: data/*.toml, sessions.jsonl, derived/ → internal/
    for name in ("catalog.toml", "priorities.toml", "sessions.jsonl",
                 "processing_overrides.toml"):
        _relocate(data / name, internal / name)
    _relocate(data / "derived", internal / "derived")

    # 2. Generated renders: site/img/ → internal/renders/ (carries hero/)
    _relocate(site / "img", internal / "renders")

    # 3. Journals: data/objects/<slug>.md → Objects/<id>/journal.md
    objects_old = data / "objects"
    if objects_old.is_dir():
        for md in sorted(objects_old.glob("*.md")):
            slug = md.stem
            obj_id = _safe_id(slug_to_id.get(slug, slug))
            _relocate(md, root / "Objects" / obj_id / "journal.md")
        _rmdir_if_empty(objects_old)

    # 4. Capture content. Images/FITS/<t> collapses up to Images/<t>, with
    #    root-level stack files folded into stacks/.
    fits = images / "FITS"
    if fits.is_dir():
        for t_dir in sorted(p for p in fits.iterdir() if p.is_dir()):
            dest = images / t_dir.name
            _relocate(t_dir / "lights", dest / "lights")
            _relocate(t_dir / "stacks", dest / "stacks")
            for f in list(t_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in _STACK_EXTS:
                    _relocate(f, dest / "stacks" / f.name)
            # Preserve any remaining subdirs (darks/flats/biases/process/…) and
            # stray files at the target root.
            for f in list(t_dir.iterdir()):
                _relocate(f, dest / f.name)
            _drop_legacy(t_dir)
        _drop_legacy(fits)

    # 5. Seestar in-app stacks → Images/<t>/seestar-stacks/
    seestar = images / "Seestar_stacks"
    if seestar.is_dir():
        for t_dir in sorted(p for p in seestar.iterdir() if p.is_dir()):
            _relocate(t_dir, images / t_dir.name / "seestar-stacks")
        _drop_legacy(seestar)

    # 6. Hand-finished renders → Images/<t>/finished/
    finished = images / "Finished Images"
    if finished.is_dir():
        for t_dir in sorted(p for p in finished.iterdir() if p.is_dir()):
            _relocate(t_dir, images / t_dir.name / "finished")
        _drop_legacy(finished)

    # 7. Non-catalog media → Media/<Category>_photo|_video/
    if images.is_dir():
        for md in sorted(p for p in images.iterdir()
                         if p.is_dir() and _is_media_name(p.name)):
            _relocate(md, root / "Media" / md.name)

    # 8. Ingest staging → Inbox/
    _relocate(images / "From the scope", root / "Inbox")

    # 9. Drop legacy containers (also clears OS-junk-only leftovers like .DS_Store
    #    that would otherwise keep an emptied dir alive).
    _drop_legacy(data)
    _drop_legacy(site)
    _drop_legacy(images / "From the scope")

    (internal / VERSION_FILE).write_text(str(STORE_VERSION))
    return True

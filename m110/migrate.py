"""In-place migration of a data store to the current (two-axis) layout.

The store originally mixed machine state and content across `data/`, `Images/`
(with jargon subfolders `FITS` / `Seestar_stacks` / `Finished Images` /
`From the scope`), and `site/`. The current layout (store version 6) is:

    Objects/<catalog id>/journal.md          (catalog-object axis)
    Images/<target>/{lights,stacks,device-stacks,finished}/
    Media/<Category>_photo|_video/
    Inbox/                                   (ingest staging)
    .m110_internal_data/{library,priorities,sessions,...}  + derived/ + renders/

`migrate_store()` is **idempotent** and **version-stamped**: it runs whenever the
store hasn't reached the current version — an old-layout marker triggers the v0→v2
two-axis reshape, and later version bumps run regardless (v2→v3 renames the
per-store `catalog.toml` → `library.toml`; v3→v4 purges capture targets that were
wrongly promoted into the object axis — see `_prune_combined_target_objects`;
v4→v5 marks the retired `priorities.toml` as no longer read —
`_mark_priorities_retired`; v5→v6 renames each target's `seestar-stacks/` tier to
the vendor-neutral `device-stacks/` — `_rename_device_stacks`).
Moves use same-filesystem renames
(cheap); a re-run resumes a partial move rather than duplicating or destroying
anything. Qt-free, and only ever exercised on temp/throwaway roots in tests —
never pointed at a live root in validation.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

STORE_VERSION = 6
INTERNAL_DIRNAME = ".m110_internal_data"
VERSION_FILE = ".store_version"

_STACK_EXTS = (".fit", ".fits", ".tif", ".tiff")


def _read_version(root: Path) -> int:
    f = root / INTERNAL_DIRNAME / VERSION_FILE
    try:
        return int(f.read_text(encoding="utf-8").strip())
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
    if remaining and all(c.is_file() and (c.name in _JUNK_FILES or c.name.startswith("._"))
                         for c in remaining):
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
    changed = False
    if _has_old_layout(root):
        _reshape_v0_to_v2(root)
        changed = True
    # v2 → v3: the per-store object set is the user's Library, not a "catalog".
    internal = root / INTERNAL_DIRNAME
    cat, lib = internal / "catalog.toml", internal / "library.toml"
    if cat.is_file() and not lib.is_file():
        cat.rename(lib)
        changed = True
    # v3 → v4: purge capture targets that were wrongly promoted into the object axis.
    if _prune_combined_target_objects(root):
        changed = True
    # v4 → v5: say so in priorities.toml, which nothing has read since the prioritizer.
    if _mark_priorities_retired(root):
        changed = True
    # v5 → v6: the device-stack tier holds Dwarf/Draco stacks too — not "seestar".
    if _rename_device_stacks(root):
        changed = True
    if internal.is_dir():
        (internal / VERSION_FILE).write_text(str(STORE_VERSION), encoding="utf-8")
    return changed


# v6: the per-target device-stack tier (mirrors `config.DEVICE_STACKS_DIRNAME` /
# `LEGACY_DEVICE_STACKS_DIRNAME`; duplicated because config imports this module).
DEVICE_STACKS = "device-stacks"
LEGACY_DEVICE_STACKS = "seestar-stacks"


def _merge_keep_both(src: Path, dst: Path) -> None:
    """Move every file under `src` into `dst`, **never overwriting**: a name free in
    `dst` is a plain rename; a name taken by different bytes lands beside it as
    `<stem>-N<ext>` (the import keep-both rule, `roundtrip.resolve_import_dest`); a
    byte-identical copy is already there, so it is left where it is and logged —
    nothing is deleted. Emptied directories are removed; non-empty ones never."""
    from .roundtrip import resolve_import_dest   # local: config imports migrate
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if child.is_dir():
            if target.exists() and not target.is_dir():
                log.warning("store v6: kept %s (a file of that name is in %s)", child, dst)
                continue
            _merge_keep_both(child, target)
            continue
        if not target.exists():
            shutil.move(str(child), str(target))
            continue
        if target.is_dir():
            log.warning("store v6: kept %s (a folder of that name is in %s)", child, dst)
            continue
        free, disposition = resolve_import_dest(target, child)
        if disposition == "duplicate":
            log.warning("store v6: left %s in place — an identical copy is already %s",
                        child, free)
            continue
        shutil.move(str(child), str(free))
        log.warning("store v6: %s collided with a different file; kept both as %s",
                    child, free.name)
    _rmdir_if_empty(src)


def _rename_device_stacks(root: Path) -> bool:
    """v5 → v6: `Images/<t>/seestar-stacks/` → `Images/<t>/device-stacks/`.

    The tier holds every telescope's own in-app stacks (Seestar, Dwarf 3, Draco),
    so the vendor name was wrong. Same-filesystem renames, so it is cheap; if both
    folders exist (an older build wrote the old one after an upgrade) the contents
    merge with keep-both collisions (`_merge_keep_both`) and the old folder is
    removed only once it holds nothing but OS junk. Hero `.src` sidecars that
    recorded a source under the old name are repointed, so the hero is not
    re-rendered for a rename. Idempotent: a second run finds nothing to do."""
    images = root / "Images"
    if not images.is_dir():
        return False
    changed = False
    for t_dir in sorted(p for p in images.iterdir() if p.is_dir()):
        old = t_dir / LEGACY_DEVICE_STACKS
        if not old.is_dir():
            continue
        _merge_keep_both(old, t_dir / DEVICE_STACKS)
        _drop_legacy(old)
        if old.exists():
            log.warning("store v6: %s still holds files (see above); left in place", old)
        changed = True
    hero = root / INTERNAL_DIRNAME / "renders" / "hero"
    if hero.is_dir():
        for sc in hero.glob("*.src"):
            try:
                lines = sc.read_text(encoding="utf-8").split("\n")
            except (OSError, UnicodeDecodeError):
                continue
            sep = "\\" if "\\" in lines[0] else "/"     # str(relative_to) on Windows
            parts = lines[0].split(sep)
            if len(parts) >= 4 and parts[0] == "Images" and parts[2] == LEGACY_DEVICE_STACKS:
                parts[2] = DEVICE_STACKS
                lines[0] = sep.join(parts)
                sc.write_text("\n".join(lines), encoding="utf-8")
                changed = True
    return changed


PRIORITIES_RETIRED_HEADER = (
    "# M110 no longer reads this file (retired in 0.3; nothing parses it any more).\n"
    "# Priorities are ranked automatically on the Planning page; pin or deprioritize\n"
    "# objects there or in the Library, and set an object's integration goal in its\n"
    "# detail pane. Kept only so nothing you wrote here is lost — safe to delete.\n\n"
)


def _mark_priorities_retired(root: Path) -> bool:
    """v4 → v5: prepend a "no longer read" header to a hand-edited `priorities.toml`.

    The curated priority list was replaced by the prioritizer long ago, but every
    store was still seeded with it — so editing it silently did nothing. Prepends
    only (the user's text is kept verbatim), and only once."""
    path = root / INTERNAL_DIRNAME / "priorities.toml"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if text.startswith(PRIORITIES_RETIRED_HEADER.splitlines()[0]):
        return False
    path.write_text(PRIORITIES_RETIRED_HEADER + text, encoding="utf-8")
    return True


def _prune_combined_target_objects(root: Path) -> bool:
    """v3 → v4: drop synthetic "combined capture target" objects from the Library.

    A multi-object capture folder ("M81 M82") was wrongly promoted into the
    catalog-object axis as a pseudo-object (slug `m81-m82`, type "unknown"), which
    then shadowed the folder→slug split so the pair's integration never credited
    M81/M82 (#40c). Capture targets belong to the Images/ axis only. Non-destructive:
    the `Objects/<id>/` journal folder is left alone. Returns True if any were removed.
    """
    lib_path = root / INTERNAL_DIRNAME / "library.toml"
    if not lib_path.is_file():
        return False
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    try:
        with lib_path.open("rb") as f:
            cat = tomllib.load(f).get("catalog", {})
    except Exception:
        return False
    if not cat:
        return False
    from .catalog import load_reference          # local: config imports migrate
    from .scan_sessions import folder_to_slugs
    ref = set(load_reference())
    if not ref:
        return False
    doomed = []
    for slug, e in cat.items():
        if slug in ref:
            continue                              # a real catalog object
        if (e.get("type") or "unknown") != "unknown":
            continue                              # user gave it a real type — keep
        # Its id is a folder name; if that folder names 2+ catalog objects it's a
        # combined capture target, not an object.
        if len(folder_to_slugs(str(e.get("id") or slug), ref)) >= 2:
            doomed.append(slug)
    if not doomed:
        return False
    _remove_library_blocks(lib_path, doomed)
    return True


def _remove_library_blocks(path: Path, slugs) -> None:
    """Strip whole `[catalog.<slug>]` blocks from library.toml, leaving the rest of
    the file (comments, ordering, formatting) verbatim."""
    targets = {f"[catalog.{s}]" for s in slugs}
    out, skipping = [], False
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            skipping = st in targets
        if not skipping:
            out.append(line)
    path.write_text("".join(out), encoding="utf-8")


def _reshape_v0_to_v2(root: Path) -> None:
    """The original old-layout reshape (data/ + Images/FITS/ + site/ → two-axis)."""
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

    # 5. Seestar in-app stacks → Images/<t>/device-stacks/
    seestar = images / "Seestar_stacks"
    if seestar.is_dir():
        for t_dir in sorted(p for p in seestar.iterdir() if p.is_dir()):
            _relocate(t_dir, images / t_dir.name / DEVICE_STACKS)
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

"""Per-object journal + image lookups for the detail view.

Reads the per-object Markdown journal (`Objects/<catalog id>/journal.md`) and
resolves the generated hero image. Config paths are referenced dynamically (via
the `config` module) so they're overridable and testable.
"""
from __future__ import annotations

from pathlib import Path

from . import catalog, config


def object_folder_name(slug: str) -> str:
    """Human-friendly folder name for a catalog slug — the catalog `id`
    (e.g. 'm101' → 'M101'), falling back to the slug if unknown."""
    try:
        obj_id = catalog.load_catalog().get(slug, {}).get("id") or slug
    except Exception:
        obj_id = slug
    return obj_id.replace("/", "-").strip()


def journal_path(slug: str) -> Path:
    return config.OBJECTS_DIR / object_folder_name(slug) / "journal.md"


def read_journal(slug: str) -> tuple[dict, str]:
    """Return (frontmatter, body_markdown).

    Frontmatter is parsed loosely (simple `key: value`, quotes stripped) — enough
    for display fields like `hero_caption`. Missing file → ({}, "").
    """
    p = journal_path(slug)
    if not p.is_file():
        return {}, ""
    text = p.read_text()
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2].lstrip("\n")
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm, body


def hero_path(slug: str) -> Path | None:
    """Path to the generated hero JPG, or None if it doesn't exist."""
    p = config.HERO_DIR / f"{slug}.jpg"
    return p if p.is_file() else None

"""Per-object journal + image lookups for the detail view.

Reads the per-object Markdown journal (`data/objects/<slug>.md`) and resolves
the generated hero image. Config paths are referenced dynamically (via the
`config` module) so they're overridable and testable.
"""
from __future__ import annotations

from pathlib import Path

from . import config


def journal_path(slug: str) -> Path:
    return config.OBJECTS_DIR / f"{slug}.md"


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
    p = config.SITE_DIR / "img" / "hero" / f"{slug}.jpg"
    return p if p.is_file() else None

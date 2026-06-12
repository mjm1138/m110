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


def read_journal_text(slug: str) -> str:
    """Raw `journal.md` text for editing (frontmatter + body), or "" if absent."""
    p = journal_path(slug)
    return p.read_text() if p.is_file() else ""


def write_journal(slug: str, text: str) -> Path:
    """Write the raw `journal.md` for an object, creating its folder if needed.

    The only writer of a journal file. Returns the path written.
    """
    p = journal_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


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


def set_frontmatter_key(slug: str, key: str, value: str) -> Path:
    """Upsert a single `key: "value"` into the journal's YAML-ish frontmatter,
    preserving the other frontmatter lines and the Markdown body. Creates the
    journal (with a frontmatter block) if it doesn't exist yet."""
    import re as _re
    text = read_journal_text(slug)
    new_line = f'{key}: "{value}"'

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_lines = parts[1].strip("\n").splitlines()
            body = parts[2].lstrip("\n")
        else:
            fm_lines, body = [], text
    else:
        fm_lines, body = [], text

    out, found = [], False
    for line in fm_lines:
        if _re.match(rf"\s*{_re.escape(key)}\s*:", line):
            out.append(new_line)
            found = True
        else:
            out.append(line)
    if not found:
        out.append(new_line)

    new_text = "---\n" + "\n".join(out) + "\n---\n\n" + body
    return write_journal(slug, new_text)


def hero_path(slug: str) -> Path | None:
    """Path to the generated hero JPG, or None if it doesn't exist."""
    p = config.HERO_DIR / f"{slug}.jpg"
    return p if p.is_file() else None

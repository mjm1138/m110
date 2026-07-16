"""Per-object journal + image lookups for the detail view.

Reads the per-object Markdown journal (`Objects/<catalog id>/journal.md`) and
resolves the generated hero image. Config paths are referenced dynamically (via
the `config` module) so they're overridable and testable.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import catalog, config

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ORDERED_RE = re.compile(r"\d+\.\s")


def _is_block_start(line: str) -> bool:
    s = line.lstrip()
    return (s.startswith(("#", ">", "-", "*", "+", "|", "```"))
            or bool(_ORDERED_RE.match(s)))


def journal_to_markdown(body: str) -> str:
    """Prepare a journal body for display: drop editor-only HTML comments and
    preserve the author's single line breaks (Markdown otherwise folds them into
    spaces), without disturbing paragraphs, lists, headings, or fenced code."""
    body = _HTML_COMMENT_RE.sub("", body)
    lines = body.split("\n")
    out: list[str] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if (not in_fence and line.strip() and nxt.strip()
                and not _is_block_start(line) and not _is_block_start(nxt)
                and not line.endswith("  ")):
            out.append(line + "  ")        # Markdown hard break
        else:
            out.append(line)
    return "\n".join(out).strip("\n")


def object_folder_name(slug: str) -> str:
    """Human-friendly folder name for a catalog slug — the catalog `id`
    (e.g. 'm101' → 'M101'), falling back to the slug if unknown."""
    try:
        obj_id = catalog.load_library().get(slug, {}).get("id") or slug
    except Exception:
        obj_id = slug
    return obj_id.replace("/", "-").strip()


def journal_path(slug: str) -> Path:
    return config.OBJECTS_DIR / object_folder_name(slug) / "journal.md"


def read_journal_text(slug: str) -> str:
    """Raw `journal.md` text for editing (frontmatter + body), or "" if absent."""
    p = journal_path(slug)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def write_journal(slug: str, text: str) -> Path:
    """Write the raw `journal.md` for an object, creating its folder if needed.

    The only writer of a journal file. Returns the path written.
    """
    p = journal_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def has_notes(slug: str) -> bool:
    """True if the user has actually written notes for this object — i.e. the
    journal body has real prose beyond the generated stub (the `# id — name`
    heading + the boilerplate HTML comment). Used to decide whether a goal
    deactivation may prune an object from the Library (annotated objects stay)."""
    import re as _re
    _, body = read_journal(slug)
    if not body.strip():
        return False
    body = _re.sub(r"<!--.*?-->", "", body, flags=_re.DOTALL)   # drop comments
    body = _re.sub(r"^\s*#.*$", "", body, flags=_re.MULTILINE)   # drop headings
    return bool(body.strip())


def read_journal(slug: str) -> tuple[dict, str]:
    """Return (frontmatter, body_markdown).

    Frontmatter is parsed loosely (simple `key: value`, quotes stripped) — enough
    for display fields like `hero_caption`. Missing file → ({}, "").
    """
    p = journal_path(slug)
    if not p.is_file():
        return {}, ""
    text = p.read_text(encoding="utf-8")
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


def _upsert_frontmatter(slug: str, key: str, new_line: str | None) -> Path:
    """Upsert (or, when `new_line` is None, delete) a single frontmatter line by
    key, preserving the other lines + the Markdown body. Creates the journal (with
    a frontmatter block) if absent."""
    import re as _re
    text = read_journal_text(slug)

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
            found = True
            if new_line is not None:
                out.append(new_line)          # else: drop it (delete)
        else:
            out.append(line)
    if not found and new_line is not None:
        out.append(new_line)

    new_text = "---\n" + "\n".join(out) + "\n---\n\n" + body
    return write_journal(slug, new_text)


def set_frontmatter_key(slug: str, key: str, value: str) -> Path:
    """Upsert a single `key: "value"` into the journal's YAML-ish frontmatter,
    preserving the other frontmatter lines and the Markdown body. Creates the
    journal (with a frontmatter block) if it doesn't exist yet."""
    return _upsert_frontmatter(slug, key, f'{key}: "{value}"')


def get_frontmatter_list(slug: str, key: str) -> list[str]:
    """A list-valued frontmatter key (stored as a JSON array), or [] if absent /
    unparseable. Pairs with :func:`set_frontmatter_list`."""
    import json
    fm, _ = read_journal(slug)
    raw = fm.get(key)
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [str(v) for v in val] if isinstance(val, list) else []


def set_frontmatter_list(slug: str, key: str, values: list[str]) -> Path:
    """Upsert a list-valued frontmatter key as a JSON array; an empty list deletes
    the key (keeps the frontmatter tidy)."""
    import json
    if values:
        return _upsert_frontmatter(slug, key, f"{key}: {json.dumps(list(values))}")
    return _upsert_frontmatter(slug, key, None)


# ── per-image curation overrides (#17): finished / working, on top of the tier ──
_CURATION_KEYS = {"finished": "finished_extra", "working": "working_extra"}


def get_curation(slug: str) -> dict[str, str]:
    """`{filename: "finished"|"working"}` per-image overrides for this object."""
    out: dict[str, str] = {}
    for state, key in _CURATION_KEYS.items():
        for name in get_frontmatter_list(slug, key):
            out[name] = state
    return out


def image_state(name: str, label: str, curation: dict[str, str]) -> str:
    """"finished" | "working" for a gallery image — the curation override wins
    over the tier default (finished/ folder = finished, stacks etc. = working).
    The single rule shared by the detail-pane gallery groups and the publish
    finished-only filter."""
    if name in curation:
        return curation[name]
    return "finished" if label == "Finished render" else "working"


def set_curation(slug: str, name: str, state: str | None) -> Path | None:
    """Force `name` to "finished" or "working" (or None to clear the override).
    A name is only ever in one list. Returns the written path, or None if nothing
    changed."""
    if state is not None and state not in _CURATION_KEYS:
        return None
    changed = None
    for st, key in _CURATION_KEYS.items():
        cur = get_frontmatter_list(slug, key)
        want = [n for n in cur if n != name]
        if st == state:
            want.append(name)
        if want != cur:
            changed = set_frontmatter_list(slug, key, want)
    return changed


def hero_path(slug: str) -> Path | None:
    """Path to the generated hero JPG, or None if it doesn't exist."""
    p = config.HERO_DIR / f"{slug}.jpg"
    return p if p.is_file() else None

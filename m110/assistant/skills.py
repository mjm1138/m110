"""Skills — the procedures that turn twelve tools into three useful behaviours.

One source of truth, three serving surfaces, one loader, so they cannot drift:

  * **MCP prompts** — the good ergonomics. In a client that surfaces prompts,
    the user picks "Plan a night" instead of typing a paragraph.
  * **MCP resources** at ``m110-skill://<id>`` — for clients that browse
    resources rather than prompts.
  * **the `get_skill` tool** — and this one is *not* optional. Plenty of clients
    don't surface prompts at all, subagents can't invoke them, and a model
    mid-task that realises it needs the critique procedure has to be able to
    *pull* it. It is also how a non-Claude client gets skills at all.

Files live at ``skills/<id>/SKILL.md`` — deliberately the Claude Skill on-disk
layout, so the directory can be symlinked into ``~/.claude/skills/`` unchanged.

Frontmatter is parsed loosely, matching `objects.read_journal`: flat
``key: value`` lines only, no YAML dependency. Prompt arguments are a
comma-separated ``arguments:`` line rather than a nested list, which keeps the
file both trivially parseable and a legitimate Claude Skill (which only requires
``name`` and ``description``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
URI_SCHEME = "m110-skill"


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    body: str
    arguments: tuple[str, ...] = ()

    @property
    def uri(self) -> str:
        return f"{URI_SCHEME}://{self.id}"

    def render(self, values: dict | None = None) -> str:
        """Body with ``{{arg}}`` placeholders substituted; unfilled ones removed
        so a half-supplied prompt never ships literal braces to the model."""
        out = self.body
        for arg in self.arguments:
            supplied = (values or {}).get(arg)
            out = out.replace("{{" + arg + "}}",
                              str(supplied) if supplied else f"(not specified — ask, "
                                                             f"or use the default {arg})")
        return out


def _parse(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm, parts[2].lstrip("\n")


def _load(path: Path) -> Skill | None:
    try:
        fm, body = _parse(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    sid = path.parent.name
    args = tuple(a.strip() for a in fm.get("arguments", "").split(",") if a.strip())
    return Skill(id=sid, name=fm.get("name", sid.replace("-", " ").title()),
                 description=fm.get("description", ""), body=body, arguments=args)


def all_skills() -> list[Skill]:
    if not SKILLS_DIR.is_dir():
        return []
    found = [_load(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))]
    return [s for s in found if s is not None]


def get(skill_id: str) -> Skill | None:
    return next((s for s in all_skills() if s.id == skill_id), None)


def id_from_uri(uri: str) -> str | None:
    m = re.fullmatch(rf"{URI_SCHEME}://([\w-]+)", str(uri))
    return m.group(1) if m else None

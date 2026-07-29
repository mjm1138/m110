"""Saved field guides. List + read folded into one tool with an optional name —
two near-identical tools would burn schema budget for nothing.
"""
from __future__ import annotations

from pathlib import Path

from m110 import config, fieldguide
from m110.assistant.registry import ToolError, register
from m110.assistant.store import require_store


@register(
    name="saved_plans",
    title="Saved field guides",
    description=(
        "The user's saved observing plans from M110's Plans/ folder. Omit `name` to "
        "list them (newest first); pass one to read its markdown. Instant. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string",
                     "description": ("Filename of a guide to read, e.g. "
                                     "'2026-07-13_summer-galaxies.md'. Omit to list.")},
        },
    },
    cost="instant",
    engine=("m110.fieldguide.list_guides", "m110.fieldguide.read"),
)
def saved_plans(name: str | None = None) -> dict:
    require_store()
    guides = fieldguide.list_guides()

    if name is None:
        return {"count": len(guides),
                "guides": [{k: g[k] for k in ("name", "date", "title")} for g in guides]}

    match = next((g for g in guides if g["name"] == name), None)
    if match is None:
        raise ToolError(
            f"No saved plan named {name!r}. Available: "
            f"{', '.join(g['name'] for g in guides) or '(none)'}"
        )

    # list_guides paths come from PLANS_DIR, but re-anchor before reading so a
    # crafted name can never walk outside it.
    path = Path(match["path"]).resolve()
    plans_dir = Path(config.PLANS_DIR).resolve()
    if plans_dir not in path.parents:
        raise ToolError(f"{name!r} is not inside the Plans folder.")

    return {"name": match["name"], "date": match["date"], "title": match["title"],
            "markdown": fieldguide.read(path)}

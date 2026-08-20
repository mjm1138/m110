"""`get_skill` — the agent-agnostic way to reach a procedure.

MCP prompts are nicer ergonomics where a client surfaces them, but plenty don't,
subagents can't invoke them, and a model that realises mid-task it needs the
critique procedure has to be able to pull it. This tool is also the only route
for a non-Claude client.
"""
from __future__ import annotations

from m110.assistant import skills as skills_mod
from m110.assistant.registry import ToolError, register


@register(
    name="get_skill",
    title="Get skill",
    description=(
        "Fetch one of M110's procedures for working with this library — how to plan a "
        "night, how to stack a target with Siril, how to critique an image, and how to "
        "talk about the numbers without inventing any. Omit `id` to list them; the "
        "listing is generated from what is installed, so it is the authority on which "
        "procedures exist. Read the relevant one before a planning, stacking or "
        "critique task rather than improvising. Instant. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string",
                   "description": ("Skill id, e.g. 'plan-a-night'. Omit to list "
                                   "the available skills with descriptions.")},
        },
    },
    cost="instant",
    engine=("m110.assistant.skills.all_skills", "m110.assistant.skills.get"),
)
def get_skill(id: str | None = None) -> dict:
    available = skills_mod.all_skills()

    if id is None:
        return {"count": len(available),
                "skills": [{"id": s.id, "name": s.name, "description": s.description,
                            "arguments": list(s.arguments)} for s in available]}

    skill = skills_mod.get(id)
    if skill is None:
        raise ToolError(
            f"No skill {id!r}. Available: {', '.join(s.id for s in available) or '(none)'}"
        )
    return {"id": skill.id, "name": skill.name, "description": skill.description,
            "arguments": list(skill.arguments), "instructions": skill.body}

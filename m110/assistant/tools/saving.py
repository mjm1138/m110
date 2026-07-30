"""Tier-1 artifacts — the assistant hands you a new file.

These create, never modify. A field guide the assistant drafts is additive,
regenerable and non-authoritative, so there is no drift problem: a new file
cannot conflict with a store that changed underneath it. That asymmetry is why
artifacts go straight to the outbox while mutations still need a proposal
envelope with a fingerprint.

By default the file is staged for review. With `assistant_direct_save` on, a
field guide skips staging and lands in `Plans/` where the app already lists it.
"""
from __future__ import annotations

from datetime import date, datetime

from m110 import config, fieldguide
from m110.assistant import outbox
from m110.assistant.registry import ToolError, register
from m110.assistant.store import require_store

SETTING_DIRECT_SAVE = "assistant_direct_save"


def direct_save_enabled() -> bool:
    return bool(config.get_setting(SETTING_DIRECT_SAVE, False))


def _parse_day(text: str | None) -> date:
    if not text:
        return date.today()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"date must be YYYY-MM-DD, got {text!r}") from None


@register(
    name="save_field_guide",
    title="Save a field guide",
    description=(
        "Save an observing plan as a field guide the user keeps. Pass the markdown "
        "from plan_night's field_guide_markdown, or your own write-up for a trip. "
        "By default this is STAGED for the user to accept in M110 (they'll see a "
        "prompt); if they've enabled direct saving it goes straight to their Plans "
        "folder. Either way it only ever creates a new file — it cannot overwrite or "
        "change anything. Instant."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "markdown"],
        "properties": {
            "title": {"type": "string",
                      "description": "Short title, e.g. 'Summer galaxies from the cabin'."},
            "markdown": {"type": "string",
                         "description": ("The guide body in markdown — normally "
                                         "plan_night's field_guide_markdown verbatim.")},
            "date": {"type": "string",
                     "description": ("The night the plan is FOR (YYYY-MM-DD), not "
                                     "today's date. Defaults to today.")},
        },
    },
    cost="instant",
    engine=("m110.fieldguide.save", "m110.assistant.outbox.write"),
)
def save_field_guide(title: str, markdown: str, date: str | None = None) -> dict:
    require_store()
    if not markdown.strip():
        raise ToolError("markdown must not be empty.")
    day = _parse_day(date)

    if direct_save_enabled():
        path = fieldguide.save(day, title, markdown)
        return {
            "saved": True,
            "staged": False,
            "name": path.name,
            "location": "Plans",
            "message": (f"Saved to the user's Plans folder as {path.name}. It's "
                        "listed under Saved field guides on the Planning page."),
        }

    stem = f"{day.isoformat()}_{outbox.safe_name(title, default='plan')}"
    path = outbox.write(f"{stem}.md", markdown, kind="artifact")
    return {
        "saved": False,
        "staged": True,
        "name": path.name,
        "location": "assistant outbox",
        "message": (f"Staged as {path.name}. M110 will show the user a prompt to "
                    "accept it into their Plans folder — tell them to look for the "
                    "assistant banner in the app. Nothing was changed in their "
                    "library."),
        "outbox": outbox.usage(),
    }


@register(
    name="list_pending",
    title="List pending items",
    description=(
        "What you've handed the user that they haven't accepted yet — staged plans "
        "and proposed changes. Useful before offering to save something again, and "
        "to remind them there's something waiting. Instant. Read-only."
    ),
    params={"type": "object", "additionalProperties": False, "properties": {}},
    cost="instant",
    engine=("m110.assistant.outbox.items",),
)
def list_pending() -> dict:
    require_store()
    rows = [{"name": i.name, "kind": i.kind, "title": i.title,
             "action": i.action or None, "target": i.target or None,
             "created": i.created}
            for i in outbox.items()]
    return {
        "count": len(rows),
        "items": rows,
        "usage": outbox.usage(),
        "note": ("These are waiting for the user to accept or discard in M110. "
                 "You cannot apply them yourself." if rows else
                 "Nothing pending."),
    }

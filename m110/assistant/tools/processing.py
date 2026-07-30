"""Processing-queue state — what's stacked, what's stale, what's ready to import."""
from __future__ import annotations

from m110 import derived
from m110.assistant.registry import ToolError, register
from m110.assistant.store import require_store


@register(
    name="get_processing_state",
    title="Processing state",
    description=(
        "Siril processing state per capture folder: integration, frame counts, the "
        "latest stack, how many frames arrived since it was made, and whether finished "
        "output is waiting to be imported. Omit `target` for the whole queue. Instant; "
        "cached data only. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target": {"type": "string",
                       "description": ("Capture-folder name, e.g. 'M51' or 'M81 M82'. "
                                       "Omit for every folder. Note this is the capture "
                                       "target (a folder), not an object slug — one "
                                       "folder can feed several objects.")},
            "status": {"type": "string",
                       "enum": ["not_processed", "out_of_date", "up_to_date"],
                       "description": "Only folders in this state."},
        },
    },
    cost="instant",
    engine=("m110.derived.load_processing",),
)
def get_processing_state(target: str | None = None, status: str | None = None) -> dict:
    require_store()
    if not derived.derived_available():
        return {"derived_available": False,
                "note": "No derived data yet — the user needs to Refresh in M110."}

    data = derived.load_processing()
    folders = data.get("folders", {})

    if target:
        match = folders.get(target) or next(
            (v for k, v in folders.items() if k.lower() == target.lower()), None)
        if match is None:
            raise ToolError(
                f"No capture folder {target!r}. Known folders: "
                f"{', '.join(sorted(folders)) or '(none)'}"
            )
        return {"folder": match}

    rows = list(folders.values())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {
        "counts": data.get("counts", {}),
        "ready_for_import": [r["folder"] for r in folders.values()
                             if r.get("ready_for_import")],
        "folders": rows,
    }

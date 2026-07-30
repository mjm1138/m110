"""Library query tools."""
from __future__ import annotations

from m110 import catalog, derived
from m110.assistant.registry import register
from m110.assistant.store import require_store


@register(
    name="list_objects",
    title="List objects",
    description=(
        "Search and filter the user's library. Returns matching objects with their "
        "designations, type, season, and captured integration time. Instant; reads "
        "cached data only. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string",
                      "description": "Case-insensitive substring match on designation or name."},
            "captured_only": {"type": "boolean",
                              "description": "Only objects with captured integration time."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100,
                      "description": "Maximum rows to return (default 25)."},
        },
    },
    cost="instant",
    engine=("m110.catalog.load_library", "m110.catalog.object_identifiers",
            "m110.derived.totals_by_slug"),
)
def list_objects(query: str | None = None, captured_only: bool = False,
                 limit: int = 25) -> dict:
    require_store()
    library = catalog.load_library()
    totals = derived.totals_by_slug() if derived.derived_available() else {}

    rows = []
    for slug, entry in library.items():
        ids = catalog.object_identifiers(slug, entry)
        name = entry.get("name", "")
        if query:
            hay = " ".join([*ids, name, slug]).lower()
            if query.lower() not in hay:
                continue
        total = totals.get(slug) or {}
        integration = total.get("integration_min", 0) or 0
        if captured_only and not integration:
            continue
        rows.append({
            "slug": slug,
            "identifiers": ids,
            "name": name,
            "type": entry.get("type"),
            "season": entry.get("season"),
            "integration_min": integration,
            "sessions": total.get("sessions", 0),
        })

    rows.sort(key=lambda r: (-r["integration_min"], r["slug"]))
    return {"total_matched": len(rows), "returned": min(len(rows), limit),
            "objects": rows[:limit]}

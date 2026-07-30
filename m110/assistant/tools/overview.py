"""Orientation tool — the first call in almost every conversation.

Collapses ~8 engine reads into one round trip. Every extra round trip is a
chance for the model to stop early and guess.
"""
from __future__ import annotations

from m110 import catalog, derived, goals, prioritize
from m110.assistant.registry import register
from m110.assistant.store import require_store


@register(
    name="get_store_overview",
    title="Store overview",
    description=(
        "Orientation for this M110 library: object counts, capture totals, active "
        "goals, current prioritizer tuning, and whether the cached ranking is stale. "
        "Call this first. Instant; reads cached data only. Read-only."
    ),
    params={"type": "object", "additionalProperties": False, "properties": {}},
    cost="instant",
    engine=("m110.derived.load_summary", "m110.catalog.object_count",
            "m110.goals.active_goal_ids", "m110.prioritize.load_strategy",
            "m110.prioritize.is_stale"),
)
def get_store_overview() -> dict:
    require_store()
    if not derived.derived_available():
        return {
            "derived_available": False,
            "note": ("No derived data yet — the library has not been refreshed. "
                     "Capture counts and rankings are unavailable until the user "
                     "runs Refresh in M110."),
            "object_count": catalog.object_count(),
        }

    summary = derived.load_summary()
    active = goals.active_goal_ids()
    return {
        "derived_available": True,
        "object_count": catalog.object_count(),
        "summary": summary,
        "active_goals": [{"id": gid, "name": goals.goal_name(gid)} for gid in active],
        "tuning": {"strategy": prioritize.load_strategy()},
        "ranking": {
            "context_stale": prioritize.is_stale(),
            "note": ("Ranking contexts are stale; season and tonight factors may be "
                     "out of date. Disclose this when citing ranks."
                     if prioritize.is_stale() else None),
        },
    }

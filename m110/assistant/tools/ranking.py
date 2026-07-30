"""The prioritizer ranking — the engine's answer to "what should I shoot?".

Reads the **cached** observability contexts and re-ranks them with the pure
scorer. It must never call `prioritize.build_contexts`, which runs an astropy
observability pass over every goal member plus everything captured — minutes,
not seconds. Conveniently it also can't: rebuilding means `write_contexts`, and
this layer does not write.
"""
from __future__ import annotations

from m110 import pins, prioritize
from m110.assistant.registry import register
from m110.assistant.store import require_store


@register(
    name="rank_targets",
    title="Rank targets",
    description=(
        "The prioritizer's ranked target list, with the per-factor breakdown behind "
        "each score (goal, urgency, completion, tonight, type weight, feasibility). "
        "Uses the CACHED observability contexts and the pure scorer — instant, and it "
        "never recomputes astronomy. If the cache is stale the ranking is still "
        "returned, flagged with context_stale; disclose that when citing ranks. "
        "Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "strategy": {
                "type": "string", "enum": ["capture", "deep"],
                "description": ("Override the saved strategy: 'capture' favours breadth "
                                "(many targets started), 'deep' favours finishing "
                                "targets already begun."),
            },
            "visible_tonight_only": {
                "type": "boolean",
                "description": ("Drop targets known to be out of season. Targets whose "
                                "observability is unknown are kept, not hidden."),
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100,
                      "description": "Maximum rows to return (default 20)."},
        },
    },
    cost="instant",
    engine=("m110.prioritize.load_contexts", "m110.prioritize.rank",
            "m110.prioritize.filter_visible_tonight", "m110.prioritize.load_weights",
            "m110.prioritize.load_strategy", "m110.prioritize.is_stale",
            "m110.pins.load"),
)
def rank_targets(strategy: str | None = None, visible_tonight_only: bool = False,
                 limit: int = 20) -> dict:
    require_store()
    contexts = prioritize.load_contexts()
    strategy = strategy or prioritize.load_strategy()
    weights = prioritize.load_weights()
    stale = prioritize.is_stale()

    if not contexts:
        return {
            "rows": [], "total_ranked": 0,
            "context_stale": stale,
            "note": ("No cached ranking contexts. The user needs to open M110's "
                     "Planning page and Recompute — this server is read-only and "
                     "cannot build them (the astropy pass takes minutes)."),
        }

    rows = prioritize.rank(contexts, weights, strategy, pins.load())
    total = len(rows)
    if visible_tonight_only:
        rows = prioritize.filter_visible_tonight(rows)

    return {
        "rows": rows[:limit],
        "total_ranked": total,
        "returned": min(len(rows), limit),
        "strategy": strategy,
        "weights": weights,
        "context_stale": stale,
        "note": ("Ranking contexts were not computed today; the season and tonight "
                 "factors may be out of date. Say so when citing ranks, and suggest "
                 "Recompute on M110's Planning page." if stale else None),
        # The one scoring rule a reader reliably gets wrong.
        "scoring_note": ("urgency is multiplied by the completion factor, so a target "
                         "that is already deep scores zero urgency no matter how soon "
                         "its season closes."),
    }

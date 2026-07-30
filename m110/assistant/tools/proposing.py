"""Proposal tools — suggest a change, with the engine's own before/after.

Three separate tools rather than one `propose(kind, payload)`. A discriminated
union with three mutually exclusive payload shapes is exactly what models get
wrong, and the failure is silent: a well-formed envelope carrying the wrong
fields. Three narrow schemas make the mistake unrepresentable.

None of these change anything. Each returns an envelope whose `preview` was
computed by the pure scorer, and stages it in the assistant outbox so the app
can offer to apply it — the envelope still carries the manual steps, so a full
outbox degrades to copy-paste rather than to nothing.
"""
from __future__ import annotations

from m110 import objects as journals, pins, prioritize
from m110.assistant import proposals
from m110.assistant.registry import ToolError, register
from m110.assistant.store import require_store

_FACTORS = ("goal", "urgency", "completion", "tonight")


def _ranked(weights, strategy, pin_state=None):
    contexts = prioritize.load_contexts()
    if not contexts:
        raise ToolError(
            "No cached ranking contexts, so no before/after can be computed. The user "
            "needs to Recompute on M110's Planning page first — a proposal without the "
            "engine's own preview would be guesswork."
        )
    return prioritize.rank(contexts, weights, strategy,
                           pin_state if pin_state is not None else pins.load())


@register(
    name="propose_weights",
    title="Propose tuning change",
    description=(
        "Propose a change to the prioritizer's strategy, factor weights, or per-type "
        "multipliers, and return the engine-computed before/after ranking it would "
        "produce. Does NOT apply anything — the user makes the change in M110. Use this "
        "instead of suggesting the user hand-pick targets. Instant. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["rationale"],
        "properties": {
            "rationale": {"type": "string",
                          "description": "Why this helps, in the user's terms."},
            "strategy": {"type": "string", "enum": ["capture", "deep"],
                         "description": "Proposed strategy. Omit to keep the current one."},
            "factors": {
                "type": "object", "additionalProperties": False,
                "description": "Proposed factor weights; omit any to keep it unchanged.",
                "properties": {
                    "goal": {"type": "number", "minimum": 0, "maximum": 5,
                             "description": "Weight on active-goal membership."},
                    "urgency": {"type": "number", "minimum": 0, "maximum": 5,
                                "description": "Weight on a closing seasonal window."},
                    "completion": {"type": "number", "minimum": 0, "maximum": 5,
                                   "description": "Weight on how far along a target is."},
                    "tonight": {"type": "number", "minimum": 0, "maximum": 5,
                                "description": "Weight on tonight's altitude and clear hours."},
                },
            },
            "type_groups": {
                "type": "object", "additionalProperties": False,
                "description": "Proposed per-type multipliers; omit any to keep it.",
                "properties": {
                    "galaxy": {"type": "number", "minimum": 0, "maximum": 5,
                               "description": "Multiplier for galaxies."},
                    "globular": {"type": "number", "minimum": 0, "maximum": 5,
                                 "description": "Multiplier for globular clusters."},
                    "open_cluster": {"type": "number", "minimum": 0, "maximum": 5,
                                     "description": "Multiplier for open clusters."},
                    "nebula": {"type": "number", "minimum": 0, "maximum": 5,
                               "description": "Multiplier for nebulae."},
                },
            },
        },
    },
    cost="instant",
    engine=("m110.prioritize.load_contexts", "m110.prioritize.rank",
            "m110.prioritize.load_weights", "m110.prioritize.load_strategy",
            "m110.prioritize.type_weights_from_groups",
            "m110.prioritize.groups_from_type_weights"),
)
def propose_weights(rationale: str, strategy: str | None = None,
                    factors: dict | None = None,
                    type_groups: dict | None = None) -> dict:
    require_store()
    if not (strategy or factors or type_groups):
        raise ToolError("Propose at least one of: strategy, factors, type_groups.")

    current = prioritize.load_weights()
    current_strategy = prioritize.load_strategy()
    new_strategy = strategy or current_strategy

    current_groups = prioritize.groups_from_type_weights(current.type_weights)
    merged_groups = {**current_groups, **(type_groups or {})}
    proposed = prioritize.Weights(
        **{f: (factors or {}).get(f, getattr(current, f)) for f in _FACTORS},
        type_weights=prioritize.type_weights_from_groups(merged_groups),
    )

    before = _ranked(current, current_strategy)
    after = _ranked(proposed, new_strategy)
    preview = proposals.rank_delta(before, after)

    changes = []
    if strategy and strategy != current_strategy:
        changes.append(f"Strategy: **{current_strategy} → {strategy}**")
    for f in _FACTORS:
        old, new = getattr(current, f), getattr(proposed, f)
        if old != new:
            changes.append(f"{f.title()}: **{old} → {new}**")
    for g, new in (type_groups or {}).items():
        old = current_groups.get(g, 1.0)
        if old != new:
            changes.append(f"Object types → {g}: **{old} → {new}**")

    summary = (
        "**Proposed tuning change — not applied.**\n\n"
        + "\n".join(f"- {c}" for c in changes)
        + "\n\nTo apply: M110 → **Planning** → *Tuning weights*, set the values above.\n\n"
        + ("The ranking would not change." if preview["unchanged"] else
           "Resulting top of the ranking:\n\n" + proposals.markdown_table(preview["after"]))
    )

    return proposals.emit(
        action="set_weights",
        title="Adjust prioritizer tuning",
        rationale=rationale,
        payload={"strategy": new_strategy, "weights": proposals.as_dict(proposed)},
        preview=preview,
        summary=summary,
        tools=("rank_targets",),
        functions=("m110.prioritize.rank", "m110.prioritize.score_target"),
    )


@register(
    name="propose_pins",
    title="Propose pin changes",
    description=(
        "Propose pinning targets to the top of the priority list, deprioritizing them "
        "out of it, or clearing existing overrides — with the engine-computed ranking "
        "that would result. Does NOT apply anything. Instant. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["rationale"],
        "properties": {
            "rationale": {"type": "string", "description": "Why, in the user's terms."},
            "pin": {"type": "array", "items": {"type": "string"},
                    "description": "Slugs to pin to the top."},
            "deprioritize": {"type": "array", "items": {"type": "string"},
                             "description": "Slugs to hide from the priority list."},
            "clear": {"type": "array", "items": {"type": "string"},
                      "description": "Slugs whose existing pin/deprioritize to remove."},
        },
    },
    cost="instant",
    engine=("m110.prioritize.load_contexts", "m110.prioritize.rank", "m110.pins.load"),
)
def propose_pins(rationale: str, pin: list | None = None,
                 deprioritize: list | None = None, clear: list | None = None) -> dict:
    require_store()
    pin = [s.strip().lower() for s in (pin or [])]
    deprioritize = [s.strip().lower() for s in (deprioritize or [])]
    clear = [s.strip().lower() for s in (clear or [])]
    if not (pin or deprioritize or clear):
        raise ToolError("Propose at least one of: pin, deprioritize, clear.")

    both = set(pin) & set(deprioritize)
    if both:
        raise ToolError(f"Cannot both pin and deprioritize: {', '.join(sorted(both))}")

    current = pins.load()
    proposed = {**current}
    for slug in clear:
        proposed.pop(slug, None)
    for slug in pin:
        proposed[slug] = pins.PIN
    for slug in deprioritize:
        proposed[slug] = pins.DEPRIORITIZE

    weights, strategy = prioritize.load_weights(), prioritize.load_strategy()
    preview = proposals.rank_delta(_ranked(weights, strategy, current),
                                   _ranked(weights, strategy, proposed))

    lines = []
    if pin:
        lines.append(f"Pin: **{', '.join(pin)}** (right-click → Pin as priority)")
    if deprioritize:
        lines.append(f"Deprioritize: **{', '.join(deprioritize)}** (right-click → Deprioritize)")
    if clear:
        lines.append(f"Clear override: **{', '.join(clear)}**")

    summary = (
        "**Proposed priority overrides — not applied.**\n\n"
        + "\n".join(f"- {ln}" for ln in lines)
        + "\n\nTo apply: right-click the object in M110's **Library** or **Planning** list."
        + ("" if preview["unchanged"] else
           "\n\nResulting top of the ranking:\n\n" + proposals.markdown_table(preview["after"])))

    return proposals.emit(
        action="set_pins",
        title="Adjust priority pins",
        rationale=rationale,
        payload={"pin": pin, "deprioritize": deprioritize, "clear": clear},
        preview=preview,
        summary=summary,
        tools=("rank_targets",),
        functions=("m110.prioritize.rank",),
    )


@register(
    name="propose_journal_entry",
    title="Propose journal entry",
    description=(
        "Propose text to add to an object's journal — an image critique, a session "
        "note, a processing decision. Does NOT write: it returns the markdown for the "
        "user to paste into M110's Object Notes. Instant. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["slug", "markdown", "rationale"],
        "properties": {
            "slug": {"type": "string", "description": "Object slug, e.g. 'm51'."},
            "markdown": {"type": "string",
                         "description": ("The entry body in markdown. Include a dated "
                                         "heading, and for a critique the grounding "
                                         "block naming which file was examined.")},
            "rationale": {"type": "string", "description": "Why this is worth recording."},
            "section": {"type": "string",
                        "description": "Optional heading to file it under."},
        },
    },
    cost="instant",
    engine=("m110.objects.read_journal", "m110.objects.read_journal_text",
            "m110.objects.has_notes"),
)
def propose_journal_entry(slug: str, markdown: str, rationale: str,
                          section: str | None = None) -> dict:
    require_store()
    from m110 import catalog

    slug = slug.strip().lower()
    if slug not in catalog.load_library():
        raise ToolError(f"No object {slug!r} in this library. Use list_objects to search.")
    if not markdown.strip():
        raise ToolError("markdown must not be empty.")

    body = f"## {section}\n\n{markdown.strip()}\n" if section else markdown.strip() + "\n"
    summary = (
        f"**Proposed journal entry for {slug} — not written.**\n\n"
        "To add it: open the object in M110, click **Edit** under Object Notes, and "
        "paste the text below.\n\n---\n\n" + body
    )

    return proposals.emit(
        action="append_journal",
        title=f"Add a journal entry for {slug}",
        rationale=rationale,
        payload={"slug": slug, "markdown": body, "section": section, "mode": "append"},
        target={"slug": slug},
        summary=summary,
        # The apply path must not clobber edits made after this was drafted.
        journal_slug=slug,
        tools=("get_object", "get_image"),
        functions=("m110.objects.read_journal",),
    )

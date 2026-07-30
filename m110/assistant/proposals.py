"""The proposal envelope — how the assistant suggests a change it may not make.

v1 is read-only: a proposal is returned as tool *output* and nothing is staged
to disk. The envelope is nevertheless designed as the seam a later phase grows
an apply path onto, because retrofitting provenance into a format already in use
is a migration, and designing it in now costs one dict.

Two fields carry the weight:

`preview` is computed by running the **pure** scorer twice — current weights vs
proposed — so a before/after ranking cannot be fabricated. It is the difference
between "the model says this will help" and "the engine computed this".

`basis.store_state` fingerprints the data the proposal was reasoned over. By the
time an apply path exists this sequence *will* happen: the user gets a proposal,
goes and shoots for four hours, imports, refreshes, then clicks Apply. The apply
path compares the fingerprint and either re-previews or refuses.

`apply.safe_write` is the growth seam named in the plan. Only the five
allowlisted actions carry True; anything else can never be dispatched even if
the envelope is otherwise well formed.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

SCHEMA = "m110.proposal/v1"

# Actions a future phase may apply behind a confirmation. Anything not listed
# here is proposal-only, permanently.
SAFE_WRITE_ACTIONS = {
    "set_weights": "prioritize.save_weights",
    "set_strategy": "prioritize.save_strategy",
    "set_pins": "pins.set_state",
    "append_journal": "objects.write_journal",
    "save_field_guide": "fieldguide.save",
}


def store_fingerprint(*, journal_slug: str | None = None) -> dict:
    """What the proposal was reasoned over, so a later apply can detect drift."""
    from m110 import config, objects, prioritize

    generated = None
    path = config.DERIVED_DIR / "prioritized.json"
    if path.is_file():
        try:
            generated = json.loads(path.read_text(encoding="utf-8")).get("generated")
        except (OSError, ValueError):
            generated = None

    totals = config.DERIVED_DIR / "totals.json"
    state = {
        "contexts_generated": generated,
        # Date granularity isn't enough: `generated` is today's date, so a
        # same-day Recompute — the ordinary case — would look identical. The
        # file's mtime is what actually detects it.
        "contexts_mtime": (datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                           if path.is_file() else None),
        "contexts_stale": prioritize.is_stale(),
        "totals_mtime": (datetime.fromtimestamp(totals.stat().st_mtime).isoformat()
                         if totals.is_file() else None),
        "journal_sha256": None,
    }
    if journal_slug:
        try:
            text = objects.read_journal_text(journal_slug)
        except OSError:
            text = ""
        state["journal_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return state


def build(*, action: str, title: str, rationale: str, payload: dict,
          summary: str, preview: dict | None = None, target: dict | None = None,
          tools: tuple[str, ...] = (), functions: tuple[str, ...] = (),
          reversible: bool = True, journal_slug: str | None = None) -> dict:
    """Assemble an envelope. Does not write anything, by design."""
    return {
        "schema": SCHEMA,
        "id": str(uuid.uuid4()),
        "created": datetime.now().astimezone().isoformat(),
        "action": action,
        "title": title,
        "rationale": rationale,
        "target": target,
        "payload": payload,
        "preview": preview or {},
        "basis": {
            "tools": list(tools),
            "functions": list(functions),
            "store_state": store_fingerprint(journal_slug=journal_slug),
        },
        "reversible": reversible,
        "apply": {
            "handler": SAFE_WRITE_ACTIONS.get(action),
            "requires_confirmation": True,
            "safe_write": action in SAFE_WRITE_ACTIONS,
        },
        # v1 applies nothing. The user acts in the app, so every proposal must
        # carry the literal steps — a proposal they can't act on is noise.
        "summary": summary,
        "how_to_apply": (
            "M110's assistant server is read-only, so this has NOT been applied. "
            "Show the user the summary above and let them make the change in the app."
        ),
    }


def emit(**kwargs) -> dict:
    """Build a proposal AND stage it for the app to offer.

    Every proposal tool returns through here, so a tool added later is queued by
    construction rather than by remembering. Staging is best-effort: if the
    outbox is full the proposal is still returned — its `summary` carries the
    manual steps, so the user is never left with nothing to act on.
    """
    from m110.assistant import outbox

    envelope = build(**kwargs)
    try:
        path = outbox.write_proposal(envelope)
        envelope["staged_as"] = path.name
        envelope["how_to_apply"] = (
            "This has NOT been applied. It is waiting in M110 — the app will show "
            "the user a prompt to review and apply it. The summary below is also "
            "there, so they can apply it by hand instead if they prefer."
        )
    except outbox.OutboxError as exc:
        envelope["staged_as"] = None
        envelope["how_to_apply"] = (
            f"This has NOT been applied, and could not be queued in M110 ({exc}). "
            "Show the user the summary below so they can apply it by hand."
        )
    return envelope


def rank_delta(before: list[dict], after: list[dict], *, limit: int = 10) -> dict:
    """Before/after ranking plus the rows that actually moved."""
    def rows(rs):
        return [{"rank": r["rank"], "slug": r["slug"], "score": r["score"]}
                for r in rs[:limit]]

    pos_before = {r["slug"]: r["rank"] for r in before}
    pos_after = {r["slug"]: r["rank"] for r in after}
    moved = [
        {"slug": slug, "from": pos_before[slug], "to": pos_after[slug],
         "change": pos_before[slug] - pos_after[slug]}
        for slug in pos_after
        if slug in pos_before and pos_before[slug] != pos_after[slug]
    ]
    # Order by how close to the top the move happened, not by its magnitude: a
    # target going 176 -> 80 is a bigger number but pure noise, while 4 -> 1 is
    # the thing the user will actually notice.
    moved.sort(key=lambda m: (min(m["from"], m["to"]), -abs(m["change"])))
    return {"before": rows(before), "after": rows(after),
            "moved": moved[:limit],
            "total_moved": len(moved),
            "unchanged": not moved}


def markdown_table(rows: list[dict]) -> str:
    lines = ["| Rank | Object | Score |", "|---:|---|---:|"]
    lines += [f"| {r['rank']} | {r['slug']} | {r['score']} |" for r in rows]
    return "\n".join(lines)


def as_dict(value: Any) -> dict:
    """dataclass-or-dict → dict (Weights arrives as either)."""
    import dataclasses
    return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else dict(value)

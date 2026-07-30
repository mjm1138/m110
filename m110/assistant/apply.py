"""Accepting what the assistant handed over. **App-side only.**

This is the one module in the assistant package that calls engine writers, and
it is deliberately *not reachable from any tool* — nothing under `tools/`, nor
`registry`, nor `mcp_server`, imports it. `test_assistant_registry` asserts that
separation, so the read-only proof stays airtight: the server can queue things,
and only the user, in the app, can turn a queued thing into a change.

Two kinds of item:

* **Artifacts** move into place. A field guide becomes a real file in `Plans/`.
* **Proposals** are applied — but only after re-running their `preview` against
  the store *as it is now*. The envelope's `basis.store_state` is what makes
  that possible: a proposal drafted before a four-hour session and a refresh is
  reasoning about a library that no longer exists, and applying it blind would
  be exactly the silent-damage failure the whole design exists to prevent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from m110 import config, fieldguide, objects as journals, pins, prioritize
from m110.assistant import outbox, proposals


class ApplyError(Exception):
    """The item could not be applied. The message is user-facing."""


@dataclass(frozen=True)
class DriftReport:
    """How far the store has moved since a proposal was drafted."""
    drifted: bool
    reasons: tuple[str, ...] = ()

    def describe(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "no changes since drafted"


def _load(name: str) -> dict:
    try:
        envelope = json.loads(outbox.read(name))
    except (OSError, ValueError) as exc:
        raise ApplyError(f"Couldn't read {name}: {exc}") from exc
    if not str(envelope.get("schema", "")).startswith("m110.proposal/"):
        raise ApplyError(f"{name} is not a proposal.")
    return envelope


def check_drift(envelope: dict) -> DriftReport:
    """Compare the store now against the fingerprint taken when this was drafted."""
    was = (envelope.get("basis") or {}).get("store_state") or {}
    now = proposals.store_fingerprint(
        journal_slug=(envelope.get("target") or {}).get("slug"))

    reasons = []
    if (was.get("contexts_generated") != now.get("contexts_generated")
            or was.get("contexts_mtime") != now.get("contexts_mtime")):
        reasons.append("the priority ranking has been recomputed")
    if was.get("totals_mtime") != now.get("totals_mtime"):
        reasons.append("your capture data has changed (a refresh or new imports)")
    if was.get("journal_sha256") and was["journal_sha256"] != now.get("journal_sha256"):
        reasons.append("this object's notes were edited")
    return DriftReport(drifted=bool(reasons), reasons=tuple(reasons))


def repreview(envelope: dict) -> dict:
    """Re-run the proposal's before/after against the CURRENT store.

    The stored `preview` describes a store that may be gone. This recomputes it
    with the same pure scorer, so what the user is shown is what will happen.
    """
    action = envelope.get("action")
    payload = envelope.get("payload") or {}
    contexts = prioritize.load_contexts()
    if not contexts:
        return {}

    strategy = prioritize.load_strategy()
    weights = prioritize.load_weights()
    before = prioritize.rank(contexts, weights, strategy, pins.load())

    if action == "set_weights":
        w = payload.get("weights") or {}
        proposed = prioritize.Weights(
            **{k: v for k, v in w.items() if k != "type_weights"},
            type_weights=w.get("type_weights") or {})
        after = prioritize.rank(contexts, proposed,
                                payload.get("strategy") or strategy, pins.load())
    elif action == "set_pins":
        state = dict(pins.load())
        for slug in payload.get("clear") or []:
            state.pop(slug, None)
        for slug in payload.get("pin") or []:
            state[slug] = pins.PIN
        for slug in payload.get("deprioritize") or []:
            state[slug] = pins.DEPRIORITIZE
        after = prioritize.rank(contexts, weights, strategy, state)
    else:
        return {}
    return proposals.rank_delta(before, after)


# ── artifacts ────────────────────────────────────────────────────────────────

def accept_artifact(name: str, *, title: str | None = None) -> Path:
    """Move a staged artifact into the real store. Markdown → `Plans/`."""
    item = next((i for i in outbox.items() if i.name == name), None)
    if item is None:
        raise ApplyError(f"{name} is no longer in the outbox.")
    if item.kind != "artifact":
        raise ApplyError(f"{name} is a proposal — apply it instead.")
    if item.path.suffix.lower() != ".md":
        raise ApplyError(f"M110 doesn't know where to file {item.path.suffix} yet.")

    text = outbox.read(name)
    # The staged name is `<YYYY-MM-DD>_<slug>.md`; recover the night it plans for
    # so the guide lands under the right date rather than today's.
    stem = Path(name).stem
    day, sep, rest = stem.partition("_")
    try:
        plan_day = date.fromisoformat(day)
    except ValueError:
        plan_day, rest = date.today(), stem
    # Prefer the name the user actually asked for — it's carried in the staged
    # filename — over the document's H1, which for a generated guide is just
    # "Observing plan — <date>" and makes for a redundant filename.
    path = fieldguide.save(plan_day, title or rest or item.title, text)
    outbox.discard(name)
    return path


# ── proposals ────────────────────────────────────────────────────────────────

def _apply_set_weights(payload: dict) -> str:
    w = payload.get("weights") or {}
    weights = prioritize.Weights(
        **{k: v for k, v in w.items() if k != "type_weights"},
        type_weights=w.get("type_weights") or {})
    prioritize.save_weights(weights)
    if payload.get("strategy"):
        prioritize.save_strategy(payload["strategy"])
    return "Tuning updated."


def _apply_set_pins(payload: dict) -> str:
    changed = 0
    for slug in payload.get("clear") or []:
        pins.set_state(slug, None)
        changed += 1
    for slug in payload.get("pin") or []:
        pins.set_state(slug, pins.PIN)
        changed += 1
    for slug in payload.get("deprioritize") or []:
        pins.set_state(slug, pins.DEPRIORITIZE)
        changed += 1
    return f"{changed} priority override(s) updated."


def _apply_append_journal(payload: dict) -> str:
    slug = payload.get("slug")
    if not slug:
        raise ApplyError("The proposal names no object.")
    existing = journals.read_journal_text(slug)
    body = (payload.get("markdown") or "").rstrip() + "\n"
    sep = "" if existing.endswith("\n\n") or not existing else "\n"
    journals.write_journal(slug, f"{existing}{sep}\n{body}")
    return f"Added to {slug}'s notes."


_HANDLERS = {
    "set_weights": _apply_set_weights,
    "set_pins": _apply_set_pins,
    "append_journal": _apply_append_journal,
}


def apply_proposal(name: str, *, force: bool = False) -> str:
    """Apply a staged proposal. Refuses on drift unless `force`."""
    envelope = _load(name)
    action = envelope.get("action")

    if not (envelope.get("apply") or {}).get("safe_write"):
        raise ApplyError(f"'{action}' is not on the list of changes M110 will apply.")
    handler = _HANDLERS.get(action)
    if handler is None:
        raise ApplyError(f"M110 doesn't know how to apply '{action}' yet.")

    drift = check_drift(envelope)
    if drift.drifted and not force:
        raise ApplyError(
            "Your library has changed since this was suggested — "
            f"{drift.describe()}. Review the updated preview before applying.")

    result = handler(envelope.get("payload") or {})
    outbox.discard(name)
    return result


def discard(name: str) -> bool:
    return outbox.discard(name)

"""Manual Pin / Deprioritize priority overrides (ROADMAP item 1 · BUGS #3).

The self-contained "manual overrides" slice of the auto-prioritizer, shipped
ahead of the scoring engine so the **Priority Targets** view has a reason to
exist for a fresh user (who has no hand-edited `priorities.toml`). The user marks
Library objects **Pin** (surface as a priority) or **Deprioritize** (suppress
from priority suggestions); the state is a **stable per-store prefs file** that
survives derived-data regeneration — it is *not* computed.

Stored in `.m110_internal_data/pins.toml` as a single `[pins]` table mapping a
Library slug to ``"pin"`` or ``"deprioritize"``. Qt-free; additive and lazily
created (absence = no overrides); never destructive. When the scorer lands, the
computed rank composes with these overrides (pins float up, deprioritized drop
out). Today's manual slice is simpler: pin = always shown, deprioritize = hidden.
"""
from __future__ import annotations

import tomllib

from . import config

PIN = "pin"
DEPRIORITIZE = "deprioritize"
_VALID = (PIN, DEPRIORITIZE)
# Read-compat for the pre-rename value (was "mute"); mapped forward on load.
_LEGACY = {"mute": DEPRIORITIZE}


def load() -> dict[str, str]:
    """The `{slug: "pin"|"deprioritize"}` map for the current store, tolerant of
    absence / a malformed file (→ empty). Legacy ``"mute"`` values are mapped
    forward; unknown state values are dropped."""
    path = config.PINS_TOML
    if path.is_file():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        pins = data.get("pins", {})
        if isinstance(pins, dict):
            out = {}
            for k, v in pins.items():
                v = _LEGACY.get(v, v)
                if v in _VALID:
                    out[str(k)] = v
            return out
    return {}


def get_state(slug: str) -> str | None:
    """``"pin"``, ``"deprioritize"``, or ``None`` (normal) for `slug`."""
    return load().get(slug)


def set_state(slug: str, state: str | None) -> None:
    """Set `slug`'s override. ``None`` (or an unrecognized value) clears it.
    Idempotent; rewrites the whole file preserving the other entries."""
    pins = load()
    if state in _VALID:
        pins[slug] = state
    else:
        pins.pop(slug, None)
    _write(pins)


def pinned_slugs() -> set[str]:
    return {s for s, v in load().items() if v == PIN}


def deprioritized_slugs() -> set[str]:
    return {s for s, v in load().items() if v == DEPRIORITIZE}


def _quote(s: str) -> str:
    """A TOML basic-string key (slugs can carry apostrophes / spaces)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write(pins: dict[str, str]) -> None:
    lines = ['# Manual Pin / Deprioritize priority overrides (#3). '
             'slug = "pin" | "deprioritize".',
             "# Stable user prefs — survives derived-data regeneration.", "", "[pins]"]
    for slug in sorted(pins):
        if pins[slug] in _VALID:
            lines.append(f"{_quote(slug)} = {_quote(pins[slug])}")
    config.PINS_TOML.parent.mkdir(parents=True, exist_ok=True)
    config.PINS_TOML.write_text("\n".join(lines) + "\n", encoding="utf-8")

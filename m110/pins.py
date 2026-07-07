"""Manual Pin / Mute priority overrides (ROADMAP item 1 · BUGS #3).

The self-contained "manual overrides" slice of the auto-prioritizer, shipped
ahead of the scoring engine so the **Priority Targets** view has a reason to
exist for a fresh user (who has no hand-edited `priorities.toml`). The user marks
Library objects **Pin** (surface as a priority) or **Mute** (suppress from
priority suggestions); the state is a **stable per-store prefs file** that
survives derived-data regeneration — it is *not* computed.

Stored in `.m110_internal_data/pins.toml` as a single `[pins]` table mapping a
Library slug to ``"pin"`` or ``"mute"``. Qt-free; additive and lazily created
(absence = no overrides); never destructive. When the scorer lands, the computed
rank composes with these overrides (pins float up, mutes drop out).
"""
from __future__ import annotations

import tomllib

from . import config

PIN = "pin"
MUTE = "mute"
_VALID = (PIN, MUTE)


def load() -> dict[str, str]:
    """The `{slug: "pin"|"mute"}` map for the current store, tolerant of absence /
    a malformed file (→ empty). Unknown state values are dropped."""
    path = config.PINS_TOML
    if path.is_file():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        pins = data.get("pins", {})
        if isinstance(pins, dict):
            return {str(k): v for k, v in pins.items() if v in _VALID}
    return {}


def get_state(slug: str) -> str | None:
    """``"pin"``, ``"mute"``, or ``None`` (normal) for `slug`."""
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


def muted_slugs() -> set[str]:
    return {s for s, v in load().items() if v == MUTE}


def _quote(s: str) -> str:
    """A TOML basic-string key (slugs can carry apostrophes / spaces)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write(pins: dict[str, str]) -> None:
    lines = ["# Manual Pin / Mute priority overrides (#3). slug = \"pin\" | \"mute\".",
             "# Stable user prefs — survives derived-data regeneration.", "", "[pins]"]
    for slug in sorted(pins):
        if pins[slug] in _VALID:
            lines.append(f"{_quote(slug)} = {_quote(pins[slug])}")
    config.PINS_TOML.parent.mkdir(parents=True, exist_ok=True)
    config.PINS_TOML.write_text("\n".join(lines) + "\n")

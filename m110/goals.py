"""Goals — the bundled catalogs the user is actively pursuing.

A goal is a bundled catalog id (e.g. "messier", "caldwell") flagged active in the
**per-store** `.m110_internal_data/goals.toml` (`active = [...]`). Per-store (not a
global setting) so each data store tracks its own goals and a fresh store starts at
the default (Messier). Per-goal progress is computed in `build_derived.build_goals`.
Activating a goal **populates the Library** with its members (additive). Qt-free.
"""
from __future__ import annotations

import tomllib

from . import config, catalog

DEFAULT = ["messier"]


def active_goal_ids() -> list[str]:
    """Active goal ids for the current store (default ["messier"] if unset)."""
    path = config.GOALS_TOML
    if path.is_file():
        try:
            val = tomllib.load(open(path, "rb")).get("active")
            if isinstance(val, list) and val:
                return [str(x) for x in val]
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return list(DEFAULT)


def set_active_goals(ids) -> list[str]:
    """Persist the active-goal selection (per-store) and add any of those goals'
    members not yet in the Library (additive; de-activating never removes — that
    lands with the Goals-view reframe). Returns the slugs added to the Library."""
    ids = [str(i) for i in ids] or list(DEFAULT)
    _write_active(ids)
    added: list[str] = []
    for gid in ids:
        added += catalog.add_goal_members_to_library(gid)
    return added


def ensure_library_has_active_goals() -> list[str]:
    """Reconcile: add any active-goal members missing from the Library. Keeps the
    Library in sync with the per-store goals on launch (idempotent)."""
    added: list[str] = []
    for gid in active_goal_ids():
        added += catalog.add_goal_members_to_library(gid)
    return added


def _write_active(ids: list[str]) -> None:
    config.GOALS_TOML.parent.mkdir(parents=True, exist_ok=True)
    body = "active = [" + ", ".join('"' + i.replace('"', '\\"') + '"' for i in ids) + "]\n"
    config.GOALS_TOML.write_text("# Active goals (catalogs being tracked) for this store.\n" + body)

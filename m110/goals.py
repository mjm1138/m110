"""Goals — the bundled catalogs the user is actively pursuing.

A goal is just a bundled catalog id (e.g. "messier", "caldwell") flagged active in
the user's settings. Per-goal progress is computed in `build_derived.build_goals`.
Activating a goal **populates the Library** with its members (additive). Qt-free.
"""
from __future__ import annotations

from . import config, catalog

SETTING_KEY = "active_goals"
DEFAULT = ["messier"]


def active_goal_ids() -> list[str]:
    val = config.get_setting(SETTING_KEY, None)
    return [str(x) for x in val] if isinstance(val, list) and val else list(DEFAULT)


def set_active_goals(ids) -> list[str]:
    """Persist the active-goal selection and add any of those goals' members that
    aren't yet in the Library (additive; deactivating never removes objects).
    Returns the slugs added to the Library."""
    ids = [str(i) for i in ids] or list(DEFAULT)
    config.save_setting(SETTING_KEY, ids)
    added: list[str] = []
    for gid in ids:
        added += catalog.add_goal_members_to_library(gid)
    return added

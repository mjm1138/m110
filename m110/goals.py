"""Goals — the catalogs / object lists the user is actively pursuing.

A goal is either a **bundled catalog** id (e.g. "messier", "caldwell") or a
**custom** user-defined list. Both are tracked in the **per-store**
`.m110_internal_data/goals.toml`:

    active = ["messier", "my-veil-project"]

    [[custom]]
    id = "my-veil-project"
    name = "Veil Project"
    members = ["C33", "C34", "NGC6960"]

Per-store (not a global setting) so each data store tracks its own goals and a
fresh store starts at the default (Messier). Per-goal progress is computed in
`build_derived.build_goals`.

As of Phase 5d the Library is the **captured/annotated collection** — activating
a goal no longer bulk-seeds its members into the Library; uncaptured members live
in the Goals view as a checklist. Deactivating a goal prunes its uncaptured,
un-noted, not-in-another-active-goal members from the Library. Qt-free.
"""
from __future__ import annotations

import re
import tomllib

from . import config, catalog

DEFAULT = ["messier"]


# ── reads ────────────────────────────────────────────────────────────────────

def _load() -> dict:
    """Parsed goals.toml (`{active: [...], custom: [...]}`), tolerant of absence
    / malformed files."""
    path = config.GOALS_TOML
    if path.is_file():
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return {}


def active_goal_ids() -> list[str]:
    """Active goal ids for the current store (default ["messier"] if unset)."""
    val = _load().get("active")
    if isinstance(val, list) and val:
        return [str(x) for x in val]
    return list(DEFAULT)


def custom_goals() -> list[dict]:
    """User-defined goals: `[{id, name, members: {slug: designation}}]`. Members
    are normalised to a {slug: designation} dict (stored as a slug list)."""
    out = []
    for c in _load().get("custom", []) or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        members = c.get("members", []) or []
        out.append({
            "id": str(c["id"]),
            "name": str(c.get("name", c["id"])),
            "members": {str(s): str(s) for s in members},
        })
    return out


def _custom_by_id(gid: str) -> dict | None:
    for c in custom_goals():
        if c["id"] == gid:
            return c
    return None


def goal_members(gid: str) -> dict:
    """Unified member lookup → {slug: designation}. Bundled catalog or custom
    list; `{}` for an unknown id."""
    custom = _custom_by_id(gid)
    if custom is not None:
        return custom["members"]
    return catalog.load_bundled_catalog(gid).get("members", {})


def goal_name(gid: str) -> str:
    """Display name for a goal id (bundled or custom); falls back to the id."""
    custom = _custom_by_id(gid)
    if custom is not None:
        return custom["name"]
    return catalog.load_bundled_catalog(gid).get("name", gid)


def list_goals() -> list[dict]:
    """Every selectable goal — bundled catalogs + custom lists — as
    `[{id, name, kind, active, total}]`, sorted bundled-first then by name."""
    active = set(active_goal_ids())
    out = []
    for c in catalog.list_bundled_catalogs():
        out.append({"id": c["id"], "name": c["name"], "kind": "bundled",
                    "active": c["id"] in active, "total": len(c["members"])})
    for c in custom_goals():
        out.append({"id": c["id"], "name": c["name"], "kind": "custom",
                    "active": c["id"] in active, "total": len(c["members"])})
    out.sort(key=lambda g: (g["kind"] != "bundled", g["name"].lower()))
    return out


# ── writes ─────────────────────────────────────────────────────────────────--

def set_active_goals(ids) -> dict:
    """Persist the active-goal selection (per-store). No longer seeds the Library;
    deactivating a goal prunes its uncaptured/un-noted/not-in-another-goal members
    (`catalog.remove_goal_members_from_library`). Returns
    {"removed": [slugs]} for any pruned by a deactivation."""
    ids = [str(i) for i in ids] or list(DEFAULT)
    was_active = set(active_goal_ids())
    _write(ids, custom_goals())
    removed: list[str] = []
    for gid in was_active - set(ids):
        removed += catalog.remove_goal_members_from_library(gid)
    return {"removed": removed}


def create_custom_goal(name: str, members, *, activate: bool = True) -> str:
    """Create a custom goal from an arbitrary slug list; returns its id. Auto-slugs
    the name to an id (uniquified against existing goals)."""
    name = (name or "").strip() or "Custom goal"
    gid = _unique_id(_slugify(name))
    existing = custom_goals()
    existing.append({"id": gid, "name": name,
                     "members": {str(s): str(s) for s in members}})
    active = active_goal_ids()
    if activate and gid not in active:
        active = active + [gid]
    _write(active, existing)
    return gid


def edit_custom_goal(gid: str, *, name: str | None = None, members=None) -> None:
    """Update a custom goal's name and/or member list. No-op for an unknown id."""
    existing = custom_goals()
    for c in existing:
        if c["id"] == gid:
            if name is not None:
                c["name"] = name.strip() or c["name"]
            if members is not None:
                c["members"] = {str(s): str(s) for s in members}
            break
    else:
        return
    _write(active_goal_ids(), existing)


def delete_custom_goal(gid: str) -> dict:
    """Delete a custom goal (and deactivate it, pruning the Library like a
    deactivation). Returns {"removed": [slugs]}."""
    was_active = gid in active_goal_ids()
    members_snapshot = goal_members(gid)
    remaining = [c for c in custom_goals() if c["id"] != gid]
    active = [g for g in active_goal_ids() if g != gid]
    _write(active, remaining)
    removed: list[str] = []
    if was_active and members_snapshot:
        removed = catalog.remove_goal_members_from_library(gid, members=members_snapshot)
    return {"removed": removed}


def _write(active: list[str], custom: list[dict]) -> None:
    """Rewrite goals.toml preserving both the active set and the custom goals."""
    config.GOALS_TOML.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Active goals (catalogs / lists being tracked) for this store.",
             "active = [" + ", ".join(_q(i) for i in active) + "]\n"]
    for c in custom:
        lines.append("[[custom]]")
        lines.append("id = " + _q(c["id"]))
        lines.append("name = " + _q(c["name"]))
        mem = ", ".join(_q(s) for s in c["members"])
        lines.append("members = [" + mem + "]\n")
    config.GOALS_TOML.write_text("\n".join(lines))


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "goal"


def _unique_id(base: str) -> str:
    taken = {g["id"] for g in list_goals()}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"

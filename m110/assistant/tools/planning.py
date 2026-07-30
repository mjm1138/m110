"""The two tools that actually compute astronomy.

`m110.planning` and `m110.fieldguide` are safe to import here: both keep astropy
behind function-level imports, so module import stays cheap and the MCP handshake
budget is unaffected. What is *not* cheap is calling them — hence the cost labels
and the caps below.

`plan_night` deliberately absorbs rank -> plan -> sequence -> render as ONE
pipeline, mirroring `ui/pages/planning.py::_on_generate`. Split into four tools,
a model could feed a hand-picked target list straight into `sequence_plan` and
produce a schedule the engine would never have produced — a plausible-looking
night that the app itself disagrees with.
"""
from __future__ import annotations

import time
from datetime import date, datetime

from m110 import fieldguide, pins, planning as planning_engine, planning_config, prioritize
from m110.assistant.registry import ToolError, register
from m110.assistant.serialize import ToolResult
from m110.assistant.store import require_store

# Chart-shaped arrays: ~40 (time, alt, clear) tuples per target, plus the moon
# track. They drive the timeline widget and are pure bloat to a reader.
_CHART_KEYS = frozenset({"samples", "track"})

MAX_CANDIDATES = 30      # matches the UI's cap on the astropy work
MAX_SLUGS = 5


def _parse_day(text: str | None) -> date:
    if not text:
        return date.today()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"date must be YYYY-MM-DD, got {text!r}") from None


def _site(profile: str | None):
    if not profile:
        return planning_config.load_active_site()
    available = planning_config.list_profiles()
    if profile not in available:
        raise ToolError(
            f"No site profile {profile!r}. Available: {', '.join(available) or '(none)'}"
        )
    return planning_config.load_site(profile)


def _window(plan: dict) -> dict:
    """`plan_night` returns `window` as a bare (dusk, dawn) tuple — name the ends
    rather than emitting a two-element array nothing identifies."""
    dusk, dawn = plan.get("window", (None, None))
    return {"dusk": dusk, "dawn": dawn}


@register(
    name="object_observability",
    title="Object observability",
    description=(
        "Whether specific objects are up on a given night from the user's site, when "
        "each transits, how long it stays above the altitude and light-dome floor, and "
        "its separation from the moon. Set include_season_scan to also compute how many "
        "nights remain before each target's season closes (much slower). Runs real "
        "astronomy — takes a few seconds. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["slugs"],
        "properties": {
            "slugs": {
                "type": "array", "items": {"type": "string"},
                "description": (f"Object slugs, at most {MAX_SLUGS}. For a whole-night "
                                "plan across many targets use plan_night instead."),
            },
            "date": {"type": "string",
                     "description": "Night to evaluate, YYYY-MM-DD. Defaults to today."},
            "site_profile": {"type": "string",
                             "description": "Site profile name. Defaults to the active one."},
            "include_season_scan": {
                "type": "boolean",
                "description": ("Also compute nights_to_close via a forward season scan. "
                                "Significantly slower — only when the user asks how long "
                                "a target remains available."),
            },
        },
    },
    cost="seconds",
    engine=("m110.planning.night_track", "m110.planning.observability",
            "m110.planning_config.load_active_site"),
)
def object_observability(slugs: list, date: str | None = None,
                         site_profile: str | None = None,
                         include_season_scan: bool = False) -> ToolResult:
    require_store()
    if not slugs:
        raise ToolError("slugs must not be empty")
    if len(slugs) > MAX_SLUGS:
        raise ToolError(
            f"At most {MAX_SLUGS} slugs per call (got {len(slugs)}); each one runs a "
            "full astronomy pass. Use plan_night for a whole night's worth of targets."
        )

    day = _parse_day(date)
    site = _site(site_profile)
    started = time.monotonic()

    results = []
    for slug in slugs:
        slug = slug.strip().lower()
        track = planning_engine.night_track(slug, day, site)
        row = {"slug": slug}
        if track is None:
            # No coordinates — the object isn't resolvable, which is a different
            # fact from "not up tonight" and must not be reported as one.
            row["resolved"] = False
            row["note"] = (f"{slug!r} has no coordinates in this library, so no "
                           "observability can be computed for it.")
        else:
            row["resolved"] = True
            row.update(track)
            row["up_tonight"] = track.get("up_start") is not None
        if include_season_scan:
            row["season"] = planning_engine.observability(slug, day, site)
        results.append(row)

    return ToolResult(
        {"date": day, "site": {"name": site.name, "timezone": site.timezone},
         "objects": results,
         "elapsed_s": round(time.monotonic() - started, 2)},
        tz=site.tz, drop_keys=_CHART_KEYS,
    )


@register(
    name="plan_night",
    title="Plan a night",
    description=(
        "The full observing plan for one night: the dark window, moon conditions, the "
        "ranked targets that are actually up, and a non-overlapping schedule of which "
        "to shoot when — plus a printable field guide in markdown. This is the whole "
        "engine pipeline (rank, plan, sequence, render) in one call; do not try to "
        "assemble a schedule yourself from other tools. Runs real astronomy over every "
        "candidate — usually a second or two, longer for a large library. For a "
        "multi-night trip, call once per night. Read-only: this does NOT save the field "
        "guide; offer the markdown to the user, who can save it from M110's Planning page."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "date": {"type": "string",
                     "description": "Night to plan, YYYY-MM-DD. Defaults to today."},
            "count": {"type": "integer", "minimum": 1, "maximum": 12,
                      "description": ("How many targets to schedule (default 4). Sizes "
                                      "the slots; the sequencer still fills leftover "
                                      "dark time past this number.")},
            "targets": {
                "type": "array", "items": {"type": "string"},
                "description": (f"Restrict to these slugs (at most {MAX_CANDIDATES}). "
                                "Omit to use the prioritizer's own ranking, which is "
                                "the normal case."),
            },
            "site_profile": {"type": "string",
                             "description": "Site profile name. Defaults to the active one."},
            "include_field_guide": {"type": "boolean",
                                    "description": "Include the markdown field guide (default true)."},
        },
    },
    cost="slow",
    engine=("m110.prioritize.load_contexts", "m110.prioritize.rank",
            "m110.prioritize.filter_for_type", "m110.planning.plan_night",
            "m110.planning.sequence_plan", "m110.fieldguide.render_markdown",
            "m110.planning_config.load_active_site"),
)
def plan_night(date: str | None = None, count: int = 4, targets: list | None = None,
               site_profile: str | None = None,
               include_field_guide: bool = True) -> ToolResult:
    require_store()
    day = _parse_day(date)
    site = _site(site_profile)
    started = time.monotonic()

    contexts = prioritize.load_contexts()
    if not contexts:
        raise ToolError(
            "No cached ranking contexts, so there is nothing to plan from. The user "
            "needs to open M110's Planning page and Recompute — this server is "
            "read-only and cannot build them (the astropy pass takes minutes)."
        )

    ranked = prioritize.rank(contexts, prioritize.load_weights(),
                             prioritize.load_strategy(), pins.load())
    scores = {r["slug"]: r["score"] for r in ranked}
    filters = {r["slug"]: prioritize.filter_for_type(r.get("type", "")) for r in ranked}

    if targets:
        wanted = [t.strip().lower() for t in targets][:MAX_CANDIDATES]
        known = {r["slug"] for r in ranked}
        missing = [t for t in wanted if t not in known]
        candidates = [t for t in wanted if t in known]
        if not candidates:
            raise ToolError(
                "None of those targets are in the ranking. Unknown: "
                f"{', '.join(missing)}. They may be deprioritized, or absent from the "
                "Library. Use rank_targets to see what is available."
            )
    else:
        missing = []
        candidates = [r["slug"] for r in ranked][:MAX_CANDIDATES]

    plan = planning_engine.plan_night(site, day, candidates, scores=scores,
                                      filters=filters)
    schedule = planning_engine.sequence_plan(plan, count=count, scores=scores,
                                             filters=filters)
    plan_with_schedule = {**plan, "schedule": schedule}

    out = {
        "date": day,
        "site": {"name": site.name, "timezone": site.timezone,
                 "latitude_deg": site.latitude_deg, "longitude_deg": site.longitude_deg},
        "window": _window(plan),
        "moon": plan.get("moon", {}),
        "schedule": schedule,
        "entries": plan.get("entries", []),
        "start_ceiling_deg": plan.get("start_ceiling_deg"),
        "ceiling_is_hard": plan.get("ceiling_is_hard"),
        "candidates_considered": len(candidates),
        "context_stale": prioritize.is_stale(),
        "elapsed_s": round(time.monotonic() - started, 2),
        "legend": {
            "entries": ("Every ranked candidate that is up tonight. A target absent "
                        "from this list is NOT up — say so rather than estimating."),
            "schedule": ("The non-overlapping slots to actually shoot. `marginal` "
                         "flags a slot cut short by the target setting; "
                         "`over_ceiling` flags one above the mount's start-altitude "
                         "ceiling."),
        },
    }
    if missing:
        out["unavailable_targets"] = missing
    if prioritize.is_stale():
        out["note"] = ("The ranking contexts were not computed today, so target order "
                       "may be out of date. The astronomy in this plan is current.")
    if include_field_guide:
        out["field_guide_markdown"] = fieldguide.render_markdown(site, day,
                                                                 plan_with_schedule)

    return ToolResult(out, tz=site.tz, drop_keys=_CHART_KEYS)

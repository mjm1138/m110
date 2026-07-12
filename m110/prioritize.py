"""Deterministic target **prioritizer** — ranks catalog targets from the data the
app already holds plus the planning math, replacing the hand-edited
``priorities.toml`` (ROADMAP item 1, Checkpoint A / BUGS #21).

Qt-free and **deterministic** (same inputs → same ranking), so it's unit-testable
and the in-app assistant (item 4) can later *explain/tune* it rather than author a
list. The score is a **weighted sum** of named factors (all normalized to ~0..1):

* **goal** — membership in an active goal/catalog (pursued targets rank above the rest).
* **urgency** — seasonal closing pressure from ``observability()['nights_to_close']``,
  **coupled to completion** (``u = u_raw × completion_factor``) so a *finished* target
  gets no urgency credit — the Astronomy-prototype fix for "a done object closing in
  7 days outranking a real close-out."
* **completion** — interpreted through the **strategy** knob: *capture-many* favours
  uncaptured/under-threshold targets; *go-deep* favours started-but-shallow ones.
* **tonight** — feasibility now: transit altitude in the dark window + graded clear
  hours (a soft signal, not the season gate's hard drop).
* **per-type weight** — an optional multiplier by object type (user preference).

**Manual overrides** compose over the computed rank: a **pin** floats to the top, a
**deprioritize** is excluded (``m110/pins.py``).

Coordinates resolve via ``catalog.load_coords`` (canonical coords, never a display
id); the filter is derived from object type (emission/planetary → LP, else IRCUT) so
the glow floor is applied filter-aware. If no site profile or astropy is available,
:func:`build_prioritized` **degrades** to a goal+completion+pins ranking (no
season/tonight factors) rather than failing.

The weights and mapping constants below are **calibration defaults** — the intended
tuning surface (a persistent strategy slider + per-type weights on the Planning page)
and a "tune with the user against real data" follow-up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .build_derived import DEEP_STACK_MIN, deep_threshold

# ── strategy + calibration defaults ────────────────────────────────────────────
STRATEGY_CAPTURE = "capture"     # breadth — favour new / under-threshold targets
STRATEGY_DEEP = "deep"           # depth — favour started-but-shallow close-outs

URGENCY_HORIZON_DAYS = 60        # nights_to_close beyond this ⇒ no urgency pressure
TONIGHT_MIN_ALT = 20.0           # transit altitude that reads as "0" feasibility
TONIGHT_GOOD_ALT = 70.0          # …and the altitude that reads as "1"
TONIGHT_GOOD_HOURS = 4.0         # clear dark hours that read as full marks
GOAL_BASE = 0.2                  # score floor for a target not in any active goal
LP_TYPES = ("emission", "emission_snr", "planetary")   # narrowband/LP-friendly


@dataclass
class Weights:
    """Relative importance of each factor (the persistent tuning surface)."""
    goal: float = 1.0
    urgency: float = 1.2
    completion: float = 1.0
    tonight: float = 0.8
    type_weights: dict[str, float] = field(default_factory=dict)  # type → multiplier


def filter_for_type(obj_type: str) -> str:
    """Derive the capture filter from object type (emission/planetary punch through
    light pollution with an LP/narrowband filter; everything else is broadband
    IRCUT). Keeps the glow floor filter-aware."""
    return "LP" if (obj_type or "").lower() in LP_TYPES else "IRCUT"


# ── per-factor scores (each ~0..1) ─────────────────────────────────────────────

def completion_factor(integration_min: float, deep_min: float = DEEP_STACK_MIN) -> float:
    """1.0 for an uncaptured target → 0.0 once it reaches the deep-stack threshold.
    This is the *coupling* factor that zeroes urgency for finished targets."""
    return max(0.0, min(1.0, 1.0 - integration_min / deep_min))


def completion_score(integration_min: float, strategy: str,
                     deep_min: float = DEEP_STACK_MIN) -> float:
    """Strategy-dependent completion desirability. capture-many → high for
    uncaptured; go-deep → peaks for started-but-shallow (untouched *and* finished
    both score low, so a breadth night doesn't chase close-outs and a depth night
    doesn't chase brand-new targets)."""
    p = min(1.0, max(0.0, integration_min / deep_min))     # 0 new … 1 deep
    if strategy == STRATEGY_DEEP:
        return 4.0 * p * (1.0 - p)                          # peak 1.0 at p=0.5
    return 1.0 - p


def urgency_score(nights_to_close, observable, horizon_days: int = URGENCY_HORIZON_DAYS) -> float:
    """Seasonal closing pressure: rises as the observable window narrows. 0 when the
    target isn't currently observable (out of season → not a tonight/soon target)."""
    if not observable or nights_to_close is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - nights_to_close / horizon_days))


def tonight_score(transit_alt, hours_clear) -> float:
    """Feasibility tonight: half from transit altitude in the dark window, half from
    graded clear dark hours (a soft partner to the season gate)."""
    if transit_alt is None:
        alt = 0.0
    else:
        alt = (transit_alt - TONIGHT_MIN_ALT) / (TONIGHT_GOOD_ALT - TONIGHT_MIN_ALT)
        alt = max(0.0, min(1.0, alt))
    hrs = 0.0 if hours_clear is None else max(0.0, min(1.0, hours_clear / TONIGHT_GOOD_HOURS))
    return 0.5 * alt + 0.5 * hrs


# ── scoring + ranking ──────────────────────────────────────────────────────────

@dataclass
class TargetContext:
    """Everything the scorer needs about one target (assembled by
    :func:`build_prioritized`, or hand-built in tests)."""
    slug: str
    obj_type: str = "unknown"
    integration_min: float = 0.0
    in_active_goal: bool = False
    # observability() output (or None when unavailable → degraded ranking).
    obs: dict | None = None


def score_target(ctx: TargetContext, weights: Weights, strategy: str) -> dict:
    """Compute one target's factor scores + weighted total. Pure."""
    obs = ctx.obs or {}
    deep_min = deep_threshold(ctx.obj_type)     # type-aware: faint types need hours
    c = completion_factor(ctx.integration_min, deep_min)
    urgency = urgency_score(obs.get("nights_to_close"), obs.get("observable")) * c
    completion = completion_score(ctx.integration_min, strategy, deep_min)
    goal = 1.0 if ctx.in_active_goal else GOAL_BASE
    tonight = tonight_score(obs.get("transit_alt"), obs.get("hours_clear"))
    tw = weights.type_weights.get((ctx.obj_type or "").lower(), 1.0)
    raw = (weights.goal * goal + weights.urgency * urgency
           + weights.completion * completion + weights.tonight * tonight)
    return {
        "slug": ctx.slug,
        "score": round(raw * tw, 4),
        "type": ctx.obj_type,
        "integration_min": round(ctx.integration_min, 2),
        "season": obs.get("season", ""),
        "observable": obs.get("observable"),
        "nights_to_close": obs.get("nights_to_close"),
        "transit_alt": obs.get("transit_alt"),
        "factors": {"goal": round(goal, 3), "urgency": round(urgency, 3),
                    "completion": round(completion, 3), "tonight": round(tonight, 3),
                    "type_weight": tw},
    }


def rank(contexts, weights: Weights, strategy: str, pin_state: dict) -> list[dict]:
    """Score every context, drop deprioritized slugs, float pinned ones to the top,
    then order by score. Assigns a 1-based ``rank`` and a ``pinned`` flag."""
    from .pins import PIN, DEPRIORITIZE
    rows = [score_target(c, weights, strategy) for c in contexts]
    rows = [r for r in rows if pin_state.get(r["slug"]) != DEPRIORITIZE]
    for r in rows:
        r["pinned"] = pin_state.get(r["slug"]) == PIN
    rows.sort(key=lambda r: (0 if r["pinned"] else 1, -r["score"], r["slug"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


# ── orchestration (loads app data, computes observability) ─────────────────────

def build_prioritized(*, day: date | None = None, strategy: str = STRATEGY_CAPTURE,
                      weights: Weights | None = None, site=None,
                      observability_fn=None, limit: int | None = None) -> list[dict]:
    """Assemble target contexts from the live store and rank them.

    Scores the **union** of active-goal members + captured targets + pinned slugs
    (bounding the astropy work). Computes each target's observability from the active
    **site profile** unless ``site`` is passed; if no site/astropy is available it
    ranks on goal+completion+pins only. ``observability_fn`` is injectable for tests."""
    from . import catalog, derived, goals, pins
    weights = weights or Weights()
    day = day or date.today()
    pin_state = pins.load()

    try:
        lib = catalog.load_library()
    except Exception:
        lib = {}
    totals = derived.totals_by_slug()
    coords = catalog.load_coords()

    active_members: set[str] = set()
    for gid in goals.active_goal_ids():
        active_members |= set(goals.goal_members(gid))
    slugs = (active_members | set(totals) | pins.pinned_slugs()) - pins.deprioritized_slugs()

    # Resolve the site + observability function (degrade gracefully).
    obs_fn = observability_fn
    if obs_fn is None and site is None:
        try:
            from . import planning_config, planning
            site = planning_config.load_active_site()
            obs_fn = planning.observability
        except Exception:
            obs_fn = None
    elif obs_fn is None:
        try:
            from . import planning
            obs_fn = planning.observability
        except Exception:
            obs_fn = None

    contexts = []
    for slug in slugs:
        entry = lib.get(slug) or {}
        t = totals.get(slug)
        obj_type = entry.get("type", "unknown")
        obs = None
        if obs_fn is not None and site is not None and slug in coords:
            ra, dec = coords[slug]
            try:
                obs = obs_fn((ra, dec), day, site, filter=filter_for_type(obj_type))
            except Exception:
                obs = None
        contexts.append(TargetContext(
            slug=slug, obj_type=obj_type,
            integration_min=(t or {}).get("integration_min", 0.0),
            in_active_goal=slug in active_members, obs=obs))

    ranked = rank(contexts, weights, strategy, pin_state)
    return ranked[:limit] if limit else ranked


# ── persistence (a derived rollup the UI reads) ────────────────────────────────

def write_prioritized(rows: list[dict]) -> None:
    """Write the ranked list to ``derived/prioritized.json`` (a generated rollup;
    kept separate from the legacy `priorities.json` so it can't clobber it)."""
    import json
    from . import config
    d = config.DERIVED_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "prioritized.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def refresh_prioritized(**kwargs) -> list[dict]:
    """Build + persist the ranking (called from ``refresh.run_refresh``). Never
    raises — a scorer hiccup must not break a refresh."""
    try:
        rows = build_prioritized(**kwargs)
        write_prioritized(rows)
        return rows
    except Exception:
        return []

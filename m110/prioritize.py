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


# ── persistent tuning knobs (settings.json) ────────────────────────────────────
SETTING_STRATEGY = "prioritizer_strategy"
SETTING_WEIGHTS = "prioritizer_weights"
_FACTOR_KEYS = ("goal", "urgency", "completion", "tonight")


def load_strategy() -> str:
    from . import config
    s = config.get_setting(SETTING_STRATEGY, STRATEGY_CAPTURE)
    return s if s in (STRATEGY_CAPTURE, STRATEGY_DEEP) else STRATEGY_CAPTURE


def save_strategy(strategy: str) -> None:
    from . import config
    config.save_setting(SETTING_STRATEGY, strategy)


def load_weights() -> Weights:
    from . import config
    d = config.get_setting(SETTING_WEIGHTS, {}) or {}
    w = Weights()
    for k in _FACTOR_KEYS:
        try:
            if k in d:
                setattr(w, k, float(d[k]))
        except (TypeError, ValueError):
            pass
    if isinstance(d.get("type_weights"), dict):
        w.type_weights = {str(k): float(v) for k, v in d["type_weights"].items()}
    return w


def save_weights(w: Weights) -> None:
    from . import config
    config.save_setting(SETTING_WEIGHTS, {**{k: getattr(w, k) for k in _FACTOR_KEYS},
                                          "type_weights": w.type_weights})


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

def build_contexts(*, day: date | None = None, site=None,
                   observability_fn=None) -> list[TargetContext]:
    """Assemble per-target contexts from the live store — the **slow** part
    (astropy observability). Scores the **union** of active-goal members + captured
    targets + pinned slugs (bounding the work). Observability comes from the active
    **site profile** unless ``site`` is passed; with no site/astropy each ``obs`` is
    ``None`` (→ a degraded goal+completion+pins ranking). ``observability_fn`` is
    injectable for tests.

    Split from :func:`rank` on purpose: observability is **strategy-independent**, so
    the UI computes these once (on refresh) and re-ranks instantly as the user moves
    the strategy / weight controls."""
    from . import catalog, derived, goals, pins
    day = day or date.today()

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
    if obs_fn is None:
        try:
            from . import planning
            obs_fn = planning.observability
            if site is None:
                from . import planning_config
                site = planning_config.load_active_site()
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
    return contexts


def build_prioritized(*, day: date | None = None, strategy: str = STRATEGY_CAPTURE,
                      weights: Weights | None = None, site=None,
                      observability_fn=None, limit: int | None = None) -> list[dict]:
    """Convenience: build contexts + rank in one call (used by tests / one-shots)."""
    from . import pins
    contexts = build_contexts(day=day, site=site, observability_fn=observability_fn)
    ranked = rank(contexts, weights or Weights(), strategy, pins.load())
    return ranked[:limit] if limit else ranked


# ── persistence (contexts cached so the UI can re-rank without astropy) ─────────

def _context_to_dict(c: TargetContext) -> dict:
    return {"slug": c.slug, "type": c.obj_type, "integration_min": c.integration_min,
            "in_active_goal": c.in_active_goal, "obs": c.obs}


def context_from_dict(d: dict) -> TargetContext:
    return TargetContext(d["slug"], d.get("type", "unknown"),
                         d.get("integration_min", 0.0),
                         d.get("in_active_goal", False), d.get("obs"))


def write_contexts(contexts: list[TargetContext]) -> None:
    """Cache the (slow-to-compute) contexts to ``derived/prioritized.json`` so the
    Planning UI can re-rank them live. Kept separate from the legacy
    `priorities.json` so it can't clobber it."""
    import json
    from . import config
    d = config.DERIVED_DIR
    d.mkdir(parents=True, exist_ok=True)
    payload = {"generated": date.today().isoformat(),
               "contexts": [_context_to_dict(c) for c in contexts]}
    (d / "prioritized.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_contexts() -> list[TargetContext]:
    """Read the cached contexts back (empty if none/unreadable)."""
    import json
    from . import config
    p = config.DERIVED_DIR / "prioritized.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [context_from_dict(d) for d in data.get("contexts", [])]
    except Exception:
        return []


def is_stale(day: date | None = None) -> bool:
    """True if the cached contexts are missing or not from ``day`` (default today).
    Observability is date-based, so a once-a-day recompute is enough — the Planning
    page uses this to decide whether to kick off a background rebuild."""
    import json
    from . import config
    p = config.DERIVED_DIR / "prioritized.json"
    if not p.is_file():
        return True
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("generated") != (day or date.today()).isoformat()
    except Exception:
        return True


def refresh_prioritized(**kwargs) -> list[TargetContext]:
    """Build + cache the contexts (called from ``refresh.run_refresh``). Never
    raises — a scorer hiccup must not break a refresh."""
    try:
        contexts = build_contexts(**kwargs)
        write_contexts(contexts)
        return contexts
    except Exception:
        return []

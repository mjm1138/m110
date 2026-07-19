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

A **feasibility multiplier** (Phase 1.3 / BUGS #38) then scales the whole score:
non-DSO catalog-completion entries (asterisms/double stars — M40, M73) are
near-excluded, and faint diffuse targets are graded by **mean surface brightness**
derived from the catalog magnitude + size (missing data = neutral). A multiplier —
not a summed factor — because an infeasible target must not be rescued by urgency
or goal membership.

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

import logging
from dataclasses import dataclass, field
from datetime import date

from .build_derived import DEEP_STACK_MIN, deep_threshold

_log = logging.getLogger("m110")

# ── strategy + calibration defaults ────────────────────────────────────────────
STRATEGY_CAPTURE = "capture"     # breadth — favour new / under-threshold targets
STRATEGY_DEEP = "deep"           # depth — favour started-but-shallow close-outs

URGENCY_HORIZON_DAYS = 60        # nights_to_close beyond this ⇒ no urgency pressure
TONIGHT_MIN_ALT = 20.0           # transit altitude that reads as "0" feasibility
TONIGHT_GOOD_ALT = 70.0          # …and the altitude that reads as "1"
TONIGHT_GOOD_HOURS = 4.0         # clear dark hours that read as full marks
GOAL_BASE = 0.2                  # score floor for a target not in any active goal
LP_TYPES = ("emission", "emission_snr", "planetary")   # narrowband/LP-friendly

# Feasibility / worthiness gate (Phase 1.3 / BUGS #38). Catalog-completion entries
# that aren't deep-sky objects (M40 = a double star, M73 = an asterism) must not
# consume a dark-sky imaging slot; faint diffuse targets get graded by mean surface
# brightness so a showpiece outranks a stretch target on a small scope. Constants are
# S50-flavoured calibration defaults (like the tonight/urgency ones above).
NON_DSO_TYPES = ("asterism", "double_star")
NON_DSO_FACTOR = 0.05            # near-exclusion; a pin still floats one to the top
SB_GOOD = 22.0                   # mean SB (mag/arcsec²) at/below which feasibility = 1
SB_POOR = 25.0                   # …at/above which it bottoms out at SB_FLOOR
SB_FLOOR = 0.3                   # never zero — hours of integration can still win
# Diffuse nebulae with *no recorded magnitude* are more often a faint Sharpless
# stretch target than a showpiece (showpieces have data) — a mild prior, so a
# data-confirmed bright target outranks an unknown, which outranks a known-faint one.
DIFFUSE_TYPES = ("emission", "emission_snr", "reflection", "dark_nebula")
UNKNOWN_DIFFUSE_FACTOR = 0.8


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

# Object-type **groups** exposed as user weight controls (the Planning "Object
# types" sliders). Each maps to the underlying catalog types the scorer sees, so a
# single "Nebulae" control moves emission/planetary/reflection/dark together. Boost
# galaxies/nebulae + damp clusters to break up a cluster-heavy catalog like Messier.
TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "galaxy": ("galaxy",),
    "globular": ("globular",),
    "open_cluster": ("open_cluster",),
    "nebula": ("emission", "emission_snr", "planetary", "reflection", "dark_nebula"),
}
# Display labels for the groups (UI); ordered.
TYPE_GROUP_LABELS: list[tuple[str, str]] = [
    ("galaxy", "Galaxies"),
    ("globular", "Globular clusters"),
    ("open_cluster", "Open clusters"),
    ("nebula", "Nebulae"),
]


def type_weights_from_groups(group_vals: dict) -> dict[str, float]:
    """Expand per-group multipliers into the flat ``type → weight`` dict the scorer
    consumes. Only groups nudged off the 1.0 default contribute (keeps the stored
    dict small and a fresh install's weights empty)."""
    tw: dict[str, float] = {}
    for gid, types in TYPE_GROUPS.items():
        v = group_vals.get(gid)
        if v is None or abs(float(v) - 1.0) < 1e-9:
            continue
        for t in types:
            tw[t] = float(v)
    return tw


def groups_from_type_weights(type_weights: dict) -> dict[str, float]:
    """Collapse a flat ``type → weight`` dict back to per-group values (a group's
    first present member type, else 1.0) — to populate the group controls."""
    out: dict[str, float] = {}
    for gid, types in TYPE_GROUPS.items():
        vals = [type_weights[t] for t in types if t in type_weights]
        out[gid] = float(vals[0]) if vals else 1.0
    return out


SETTING_VISIBLE_TONIGHT = "planning_visible_tonight"


def load_visible_tonight() -> bool:
    """Whether the priority table hides objects not up tonight (default on)."""
    from . import config
    return bool(config.get_setting(SETTING_VISIBLE_TONIGHT, True))


def save_visible_tonight(on: bool) -> None:
    from . import config
    config.save_setting(SETTING_VISIBLE_TONIGHT, bool(on))


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


def is_non_dso(obj_type: str) -> bool:
    """True for catalog-completion entries that aren't imaging targets (asterisms,
    double stars — M40, M73). The reference *type* is the flag; no separate field."""
    return (obj_type or "").lower() in NON_DSO_TYPES


def surface_brightness(magnitude, size) -> float | None:
    """Mean surface brightness in **mag/arcsec²** from integrated magnitude +
    angular size (elliptical area, π/4·a·b). Higher = fainter. ``None`` when either
    input is missing/unparsable — the gate treats that as neutral, never a penalty.
    Sanity anchors: M31 ≈ 22.2, M33 ≈ 23.1 (famously hard), M57 ≈ 17.8 (easy)."""
    import math
    from .build_derived import parse_size_dims
    if magnitude is None:
        return None
    dims = parse_size_dims(size or "")
    if not dims:
        return None
    area_arcsec2 = math.pi / 4.0 * dims[0] * dims[1] * 3600.0
    if area_arcsec2 <= 0:
        return None
    return float(magnitude) + 2.5 * math.log10(area_arcsec2)


def feasibility_score(obj_type: str, magnitude=None, size=None) -> float:
    """0..1 **multiplier** on the whole score (like the per-type weight): a target a
    small scope can't do well shouldn't be rescued by urgency or goal membership.
    Non-DSO types → :data:`NON_DSO_FACTOR`; otherwise a soft surface-brightness ramp
    (1.0 at ≤ SB_GOOD, down to SB_FLOOR at ≥ SB_POOR). Unknown SB is neutral (1.0),
    except mag-less *diffuse* nebulae, which take the mild
    :data:`UNKNOWN_DIFFUSE_FACTOR` prior — the faint-Sharpless-on-a-50mm case the
    2026-07-13 review flagged (§5d); Simbad has no V-mag to backfill for most."""
    if is_non_dso(obj_type):
        return NON_DSO_FACTOR
    sb = surface_brightness(magnitude, size)
    if sb is None:
        return (UNKNOWN_DIFFUSE_FACTOR
                if (obj_type or "").lower() in DIFFUSE_TYPES else 1.0)
    if sb <= SB_GOOD:
        return 1.0
    if sb >= SB_POOR:
        return SB_FLOOR
    return 1.0 - (1.0 - SB_FLOOR) * (sb - SB_GOOD) / (SB_POOR - SB_GOOD)


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
    # Feasibility inputs (Phase 1.3): catalog magnitude + size string; None → the
    # surface-brightness gate is neutral (missing data never penalizes).
    magnitude: float | None = None
    size: str | None = None


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
    feas = feasibility_score(ctx.obj_type, ctx.magnitude, ctx.size)
    raw = (weights.goal * goal + weights.urgency * urgency
           + weights.completion * completion + weights.tonight * tonight)
    return {
        "slug": ctx.slug,
        "score": round(raw * tw * feas, 4),
        "type": ctx.obj_type,
        "integration_min": round(ctx.integration_min, 2),
        "season": obs.get("season", ""),
        "observable": obs.get("observable"),
        "nights_to_close": obs.get("nights_to_close"),
        "transit_alt": obs.get("transit_alt"),
        "non_dso": is_non_dso(ctx.obj_type),   # UI annotation ("not a DSO")
        "factors": {"goal": round(goal, 3), "urgency": round(urgency, 3),
                    "completion": round(completion, 3), "tonight": round(tonight, 3),
                    "type_weight": tw, "feasibility": round(feas, 3)},
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


def filter_visible_tonight(rows: list[dict]) -> list[dict]:
    """Keep only rows observable tonight — the "what should I shoot tonight" view,
    dropping out-of-season targets (M44 in July, etc.). A row whose observability
    is **unknown** (``None`` — no site/astropy, degraded ranking) is *kept*: we
    can't claim it's out. Only an explicit ``observable is False`` is hidden. The
    ``rank`` numbers are preserved (they still reflect the full ranking)."""
    return [r for r in rows if r.get("observable") is not False]


# ── orchestration (loads app data, computes observability) ─────────────────────

def build_contexts(*, day: date | None = None, site=None,
                   observability_fn=None) -> list[TargetContext]:
    """Assemble per-target contexts from the live store — the **slow** part
    (astropy observability). Scores the **union** of active-goal members + captured
    targets + pinned slugs (bounding the work), after rolling combined/mosaic folders
    up into their constituent catalog members (#39). Observability comes from the
    active **site profile** unless ``site`` is passed; with no site/astropy each
    ``obs`` is ``None`` (→ a degraded goal+completion+pins ranking). ``observability_fn``
    is injectable for tests.

    Split from :func:`rank` on purpose: observability is **strategy-independent**, so
    the UI computes these once (on refresh) and re-ranks instantly as the user moves
    the strategy / weight controls."""
    from . import catalog, derived, goals, pins
    day = day or date.today()

    try:
        lib = catalog.load_library()
    except Exception:
        lib = {}
    ref = catalog.load_reference()          # bundled type/coords for uncaptured goal members
    totals_all = derived.load_totals()
    by_slug = totals_all.get("by_slug", {}) if isinstance(totals_all, dict) else {}
    by_folder = totals_all.get("by_folder", {}) if isinstance(totals_all, dict) else {}
    coords = catalog.load_coords()

    # Combined/mosaic rollup (#39). A combined capture folder ("M81 M82") lands as a
    # synthetic slug ("m81-m82") that carries the pair's whole integration but isn't a
    # real catalog object and can't resolve to one coordinate (obs null). Credit each
    # combined folder's integration to its constituent catalog **members** (reusing the
    # canonical folder→slug split) and drop the synthetic slug from scoring — otherwise
    # a companion is scored as starved (M82 @13 min while the pair has ~29 h) and the
    # combined slug ranks with no observability.
    from .scan_sessions import folder_to_slugs
    ref_slugs = set(ref)
    member_integration: dict[str, float] = {}
    synthetic: set[str] = set()
    for folder, ft in by_folder.items():
        members = folder_to_slugs(folder, ref_slugs)
        if not members:
            continue                          # off-catalog target → keep its own slug
        imin = ft.get("integration_min", 0.0)
        for m in members:
            member_integration[m] = member_integration.get(m, 0.0) + imin
        for s in ft.get("slugs", []):         # the folder's own recorded slug(s)…
            if s not in ref_slugs and s not in members:
                synthetic.add(s)              # …e.g. m81-m82 → superseded by members

    def _integration(slug: str) -> float:
        if slug in member_integration:
            return member_integration[slug]
        return (by_slug.get(slug) or {}).get("integration_min", 0.0)

    active_members: set[str] = set()
    for gid in goals.active_goal_ids():
        active_members |= set(goals.goal_members(gid))
    slugs = ((active_members | set(by_slug) | pins.pinned_slugs())
             - pins.deprioritized_slugs() - synthetic)

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
            # planning/astropy or the site profile couldn't load — the ranking will
            # degrade to goal+completion+pins. Log it (with the traceback) so this
            # isn't a silent, unexplained downgrade of the whole Planning feature.
            _log.warning("prioritizer: planning engine or site profile unavailable — "
                         "ranking without season/tonight factors", exc_info=True)
            obs_fn = None

    obs_errors = 0
    first_obs_error: Exception | None = None
    contexts = []
    for slug in slugs:
        entry = lib.get(slug) or {}
        # Prefer a real library type; fall back to the bundled reference so an
        # uncaptured goal member (absent from the Library) still gets its true type
        # — which drives the filter (filter_for_type) and the deep threshold. Without
        # this the whole uncaptured sweep scored as type "unknown" → IRCUT + 90-min.
        obj_type = entry.get("type")
        if not obj_type or obj_type == "unknown":
            obj_type = ref.get(slug, {}).get("type") or "unknown"
        # Feasibility inputs, same lib→reference fallback as type.
        rentry = ref.get(slug, {})
        magnitude = entry.get("magnitude", rentry.get("magnitude"))
        size = entry.get("size") or rentry.get("size")
        obs = None
        if obs_fn is not None and site is not None and slug in coords:
            ra, dec = coords[slug]
            try:
                obs = obs_fn((ra, dec), day, site, filter=filter_for_type(obj_type))
            except Exception as exc:
                obs = None
                obs_errors += 1
                if first_obs_error is None:
                    first_obs_error = exc
        contexts.append(TargetContext(
            slug=slug, obj_type=obj_type,
            integration_min=_integration(slug),
            in_active_goal=slug in active_members, obs=obs,
            magnitude=magnitude, size=size))
    if obs_errors:
        # Every observability call throwing almost always means astropy failed to
        # import (e.g. an incompletely-bundled build). Surface it once, with the
        # first traceback, instead of returning a quietly degraded ranking — this is
        # exactly what hid the packaged-build astropy breakage. See planning.observability.
        _log.warning("prioritizer: observability failed for %d/%d target(s) — ranking "
                     "degraded (no season/tonight factors); this usually means the "
                     "astronomy engine (astropy) could not be loaded. First error: %r",
                     obs_errors, len(slugs), first_obs_error, exc_info=first_obs_error)
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
            "in_active_goal": c.in_active_goal, "obs": c.obs,
            "magnitude": c.magnitude, "size": c.size}


def context_from_dict(d: dict) -> TargetContext:
    return TargetContext(d["slug"], d.get("type", "unknown"),
                         d.get("integration_min", 0.0),
                         d.get("in_active_goal", False), d.get("obs"),
                         d.get("magnitude"), d.get("size"))


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

"""Deterministic prioritizer (m110/prioritize.py) — factor math + ranking, over
hand-built target contexts (no astropy / no live store)."""
import pytest

from m110 import prioritize as pr
from m110.prioritize import TargetContext, Weights
from m110.build_derived import DEEP_STACK_MIN


def _obs(**kw):
    base = {"observable": True, "hours_clear": 3.0, "transit_alt": 60.0,
            "nights_to_close": 30, "season": "spring"}
    base.update(kw)
    return base


# ── filter derivation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("t,f", [("emission", "LP"), ("planetary", "LP"),
                                 ("galaxy", "IRCUT"), ("", "IRCUT")])
def test_filter_for_type(t, f):
    assert pr.filter_for_type(t) == f


# ── completion ─────────────────────────────────────────────────────────────────

def test_completion_factor_zeroes_when_deep():
    assert pr.completion_factor(0) == 1.0
    assert pr.completion_factor(DEEP_STACK_MIN) == 0.0
    assert pr.completion_factor(DEEP_STACK_MIN * 10) == 0.0     # clamped


def test_completion_score_capture_favours_new():
    assert pr.completion_score(0, pr.STRATEGY_CAPTURE) > \
        pr.completion_score(DEEP_STACK_MIN, pr.STRATEGY_CAPTURE)


def test_completion_score_deep_peaks_at_partial():
    untouched = pr.completion_score(0, pr.STRATEGY_DEEP)
    half = pr.completion_score(DEEP_STACK_MIN / 2, pr.STRATEGY_DEEP)
    done = pr.completion_score(DEEP_STACK_MIN, pr.STRATEGY_DEEP)
    assert half > untouched and half > done           # started-but-shallow wins


# ── urgency (+ completion coupling) ────────────────────────────────────────────

def test_urgency_rises_as_window_closes():
    soon = pr.urgency_score(5, True)
    later = pr.urgency_score(45, True)
    assert soon > later > 0


def test_urgency_zero_when_not_observable():
    assert pr.urgency_score(3, False) == 0.0
    assert pr.urgency_score(None, True) == 0.0


def test_finished_target_gets_no_urgency_credit():
    """The Astronomy-prototype fix: a done object closing soon must NOT outrank a
    genuine close-out. urgency is scaled by completion_factor, which is 0 when deep."""
    w = Weights()
    # M81: 1834 min (finished), in-goal, closing in 7 nights.
    m81 = pr.score_target(TargetContext("m81", "galaxy", 1834, True,
                                        _obs(nights_to_close=7)), w, pr.STRATEGY_DEEP)
    # M12: 30 min (started, shallow), in-goal, same closing window.
    m12 = pr.score_target(TargetContext("m12", "globular", 30, True,
                                        _obs(nights_to_close=7)), w, pr.STRATEGY_DEEP)
    assert m81["factors"]["urgency"] == 0.0
    assert m12["factors"]["urgency"] > 0.0
    assert m12["score"] > m81["score"]                # the real close-out ranks higher


# ── strategy flips the ordering ────────────────────────────────────────────────

def test_strategy_flips_new_vs_nearly_complete():
    w = Weights()
    new = TargetContext("new", "galaxy", 0, True, _obs())
    almost = TargetContext("almost", "galaxy", 50, True, _obs())
    cap = {r["slug"]: r["rank"] for r in pr.rank([new, almost], w, pr.STRATEGY_CAPTURE, {})}
    deep = {r["slug"]: r["rank"] for r in pr.rank([new, almost], w, pr.STRATEGY_DEEP, {})}
    assert cap["new"] < cap["almost"]          # breadth night → new target on top
    assert deep["almost"] < deep["new"]        # depth night → the close-out on top


# ── manual overrides compose over the computed rank ────────────────────────────

def test_pin_floats_to_top_and_deprioritize_excluded():
    from m110.pins import PIN, DEPRIORITIZE
    w = Weights()
    ctxs = [TargetContext("a", "galaxy", 0, True, _obs(transit_alt=70)),   # high score
            TargetContext("b", "galaxy", 0, False, _obs(transit_alt=25)),  # low score
            TargetContext("c", "galaxy", 0, True, _obs())]
    ranked = pr.rank(ctxs, w, pr.STRATEGY_CAPTURE, {"b": PIN, "c": DEPRIORITIZE})
    slugs = [r["slug"] for r in ranked]
    assert slugs[0] == "b"          # pinned floats to the top despite a low score
    assert "c" not in slugs         # deprioritized excluded
    assert ranked[0]["pinned"] is True


# ── degraded ranking (no observability) still works ────────────────────────────

def test_degrades_without_observability():
    w = Weights()
    # obs=None (no site/astropy) → urgency/tonight are 0, but goal+completion rank.
    in_goal_new = TargetContext("x", "galaxy", 0, True, None)
    off_goal = TargetContext("y", "galaxy", 0, False, None)
    ranked = pr.rank([in_goal_new, off_goal], w, pr.STRATEGY_CAPTURE, {})
    assert ranked[0]["slug"] == "x"          # in-goal outranks off-goal on goal alone
    assert ranked[0]["factors"]["urgency"] == 0.0


def test_score_is_deterministic():
    w = Weights()
    c = TargetContext("m51", "galaxy", 25, True, _obs())
    assert pr.score_target(c, w, pr.STRATEGY_CAPTURE) == \
        pr.score_target(c, w, pr.STRATEGY_CAPTURE)


# ── orchestration over a seeded store (injected observability) ─────────────────

def test_build_prioritized_over_a_store(tmp_path, monkeypatch):
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, _tid = seed_capture(root)                    # a captured object

    def fake_obs(target, day, site, **kw):             # deterministic, no astropy
        return {"observable": True, "hours_clear": 3.0, "transit_alt": 55.0,
                "nights_to_close": 20, "season": "spring"}

    rows = pr.build_prioritized(observability_fn=fake_obs, site=object())
    assert rows, "expected at least the captured object ranked"
    assert slug in [r["slug"] for r in rows]
    assert all("score" in r and "rank" in r for r in rows)
    # ranks are dense + ordered
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_uncaptured_goal_member_gets_type_from_reference(tmp_path, monkeypatch):
    """An active-goal member that hasn't been captured is absent from the Library,
    so its type must come from the bundled reference — not default to "unknown".
    Otherwise the whole uncaptured sweep scored as IRCUT + the 90-min floor instead
    of its true filter + type-aware deep threshold (PLANNING_ROADMAP Phase 1.1)."""
    from tests._helpers import seed_root
    from m110.build_derived import deep_threshold
    seed_root(tmp_path, monkeypatch)      # empty Library, default Messier goal active

    def fake_obs(target, day, site, **kw):
        return {"observable": True, "hours_clear": 3.0, "transit_alt": 55.0,
                "nights_to_close": 20, "season": "summer"}

    contexts = pr.build_contexts(observability_fn=fake_obs, site=object())
    by_slug = {c.slug: c for c in contexts}
    assert "m8" in by_slug, "an uncaptured Messier member should still be scored"
    m8 = by_slug["m8"]
    assert m8.obj_type == "emission"                     # from the reference, not "unknown"
    assert pr.filter_for_type(m8.obj_type) == "LP"       # emission → narrowband
    assert deep_threshold(m8.obj_type) == 360            # type-aware, not the 90-min floor


def test_combined_folder_rolls_up_into_members(tmp_path, monkeypatch):
    """A combined capture folder ("M81 M82" → synthetic slug "m81-m82") must credit
    its integration to the constituent catalog members and drop the synthetic slug —
    otherwise the companion looks starved (M82 @13 min while the pair has ~29 h) and
    the combined slug ranks with no observability (PLANNING_ROADMAP Phase 1.2 / #39)."""
    from tests._helpers import seed_root
    from m110 import catalog, derived, goals, pins
    seed_root(tmp_path, monkeypatch)

    # Real M81/M82 exist in the bundled reference; the store has three folders: two
    # small solo captures plus the deep combined pair (a synthetic m81-m82 slug).
    totals = {
        "by_slug": {
            "m81": {"integration_min": 126.0},
            "m82": {"integration_min": 13.0},
            "m81-m82": {"integration_min": 1744.0},
        },
        "by_folder": {
            "M81": {"integration_min": 126.0, "slugs": ["m81"]},
            "M82": {"integration_min": 13.0, "slugs": ["m82"]},
            "M81 M82": {"integration_min": 1744.0, "slugs": ["m81-m82"]},
        },
    }
    monkeypatch.setattr(derived, "load_totals", lambda: totals)
    monkeypatch.setattr(goals, "active_goal_ids", lambda: [])   # score via totals alone
    monkeypatch.setattr(pins, "pinned_slugs", lambda: set())
    monkeypatch.setattr(pins, "deprioritized_slugs", lambda: set())

    contexts = pr.build_contexts(observability_fn=lambda *a, **k: _obs(), site=object())
    by = {c.slug: c for c in contexts}
    assert "m81-m82" not in by                     # synthetic combined slug dropped
    assert by["m81"].integration_min == 126.0 + 1744.0   # solo + combined
    assert by["m82"].integration_min == 13.0 + 1744.0    # no longer starved
    assert by["m81"].obj_type == "galaxy"          # from the reference


def test_contexts_cache_roundtrips_and_reranks(tmp_path, monkeypatch):
    """Contexts are cached (slow obs computed once) and re-ranked live — a strategy
    flip re-orders without recomputing observability."""
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    contexts = [TargetContext("new", "galaxy", 0, True, _obs()),
                TargetContext("almost", "galaxy", 120, True, _obs())]
    pr.write_contexts(contexts)
    got = pr.load_contexts()
    assert {c.slug for c in got} == {"new", "almost"}
    assert got[0].obs is not None                       # obs survived the round-trip
    # re-rank the cached contexts two ways — no astropy needed
    cap = {r["slug"]: r["rank"] for r in pr.rank(got, Weights(), pr.STRATEGY_CAPTURE, {})}
    deep = {r["slug"]: r["rank"] for r in pr.rank(got, Weights(), pr.STRATEGY_DEEP, {})}
    assert cap["new"] < cap["almost"] and deep["almost"] < deep["new"]


def test_strategy_and_weights_persist(tmp_path, monkeypatch):
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    assert pr.load_strategy() == pr.STRATEGY_CAPTURE          # default
    pr.save_strategy(pr.STRATEGY_DEEP)
    assert pr.load_strategy() == pr.STRATEGY_DEEP
    w = Weights(goal=2.0, urgency=0.5, tonight=1.5)
    pr.save_weights(w)
    got = pr.load_weights()
    assert got.goal == 2.0 and got.urgency == 0.5 and got.tonight == 1.5


# ── type-aware deep threshold (the Sharpless motivation) ───────────────────────

def test_deep_threshold_is_type_aware():
    from m110.build_derived import deep_threshold
    # 90-min SNR floor for bright/unlisted types; galaxies want more, nebulae most.
    assert deep_threshold("globular") == deep_threshold("open_cluster") == 90
    assert deep_threshold("planetary") < deep_threshold("galaxy") < deep_threshold("emission")
    assert deep_threshold("unknown") == 90          # default = the SNR floor


def test_scorer_uses_per_type_threshold():
    """90 min is 'deep' for a globular (thr 45) but barely started for an emission
    nebula (thr 240) — so the emission target keeps completion + urgency credit."""
    w = Weights()
    glob = pr.score_target(TargetContext("g", "globular", 90, True, _obs(nights_to_close=7)),
                           w, pr.STRATEGY_CAPTURE)
    neb = pr.score_target(TargetContext("n", "emission", 90, True, _obs(nights_to_close=7)),
                          w, pr.STRATEGY_CAPTURE)
    assert glob["factors"]["urgency"] == 0.0        # globular finished at 90 → no urgency
    assert neb["factors"]["urgency"] > 0.0          # emission still needs hours
    assert neb["factors"]["completion"] > glob["factors"]["completion"]


# ── feasibility / worthiness gate (Phase 1.3 / BUGS #38) ─────────────────────

def test_surface_brightness_anchors():
    """Formula sanity against published mean-SB values (mag/arcsec²)."""
    assert abs(pr.surface_brightness(3.4, "3°×1°") - 22.1) < 0.2      # M31
    assert abs(pr.surface_brightness(5.7, "73'×45'") - 23.1) < 0.2    # M33
    assert pr.surface_brightness(None, "10'") is None                 # no mag
    assert pr.surface_brightness(9.0, None) is None                   # no size
    assert pr.surface_brightness(9.6, '49"') is not None              # arcsec form


def test_feasibility_non_dso_and_sb_ramp():
    assert pr.feasibility_score("asterism") == pr.NON_DSO_FACTOR                 # M73
    assert pr.feasibility_score("double_star", 9.6, '49"') == pr.NON_DSO_FACTOR  # M40
    assert pr.feasibility_score("planetary", 8.8, "4'×3'") == 1.0     # bright → full
    assert pr.feasibility_score("galaxy", 3.4, "3°×1°") > 0.95        # M31: just on the ramp
    mid = pr.feasibility_score("galaxy", 5.7, "73'×45'")              # M33 → graded
    assert pr.SB_FLOOR < mid < 1.0
    assert pr.feasibility_score("galaxy", 14.4, "20'×4'") == pr.SB_FLOOR  # very faint
    # unknown SB: neutral for compact types, the mild prior for diffuse nebulae
    # (a mag-less emission target is more often a faint Sharpless than a showpiece)
    assert pr.feasibility_score("globular", None, None) == 1.0
    assert pr.feasibility_score("emission", None, None) == pr.UNKNOWN_DIFFUSE_FACTOR


def test_non_dso_ranks_below_an_identical_real_target():
    """A catalog-completion oddity (M40) must not out-rank a real galaxy in the same
    state — the completion goal surfaced M40 into a dark-sky slot (review §5d)."""
    w = Weights()
    dso = TargetContext("gal", "galaxy", 0, True, _obs())
    oddity = TargetContext("m40", "double_star", 0, True, _obs())
    ranked = pr.rank([oddity, dso], w, pr.STRATEGY_CAPTURE, {})
    assert ranked[0]["slug"] == "gal"
    assert ranked[-1]["non_dso"] is True
    assert ranked[-1]["factors"]["feasibility"] == pr.NON_DSO_FACTOR


def test_build_contexts_carries_feasibility_inputs(tmp_path, monkeypatch):
    """M40's type/magnitude/size flow from the bundled reference into the context,
    and the cache round-trip preserves them (feasibility survives a reload)."""
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)          # empty Library, Messier goal active
    contexts = pr.build_contexts(observability_fn=lambda *a, **k: _obs(), site=object())
    by = {c.slug: c for c in contexts}
    m40 = by["m40"]
    assert m40.obj_type == "double_star" and m40.magnitude is not None
    row = pr.score_target(m40, Weights(), pr.STRATEGY_CAPTURE)
    assert row["non_dso"] and row["factors"]["feasibility"] == pr.NON_DSO_FACTOR
    pr.write_contexts(contexts)
    got = {c.slug: c for c in pr.load_contexts()}
    assert got["m40"].magnitude == m40.magnitude and got["m40"].size == m40.size


def test_build_contexts_logs_when_observability_fails(tmp_path, monkeypatch, caplog):
    """If every observability call raises (the packaged-build astropy breakage — an
    incompletely-bundled astropy makes each transform throw), build_contexts must
    still return contexts with obs=None (degraded ranking, not dropped targets) AND
    log a warning carrying the first error — so the failure isn't silent."""
    import logging
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)          # empty Library, Messier goal active

    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'astropy.constants.codata2018'")

    # The m110 logger stops propagating once logsetup.setup_logging() has run (which
    # another test in the suite may have done), so attach caplog's handler directly —
    # otherwise capture is order-dependent.
    m110_log = logging.getLogger("m110")
    m110_log.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="m110")
    try:
        contexts = pr.build_contexts(observability_fn=boom, site=object())
    finally:
        m110_log.removeHandler(caplog.handler)
    assert contexts, "targets should still be scored (degraded), not dropped"
    assert all(c.obs is None for c in contexts)
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "observability failed" in msg
    assert "codata2018" in msg                # the first error's repr is surfaced


# ── visible-tonight filter (BUGS: out-of-season targets in the priority list) ───

def test_filter_visible_tonight_hides_only_explicit_false():
    rows = [{"slug": "up", "observable": True},
            {"slug": "out", "observable": False},
            {"slug": "unknown", "observable": None}]
    kept = [r["slug"] for r in pr.filter_visible_tonight(rows)]
    assert kept == ["up", "unknown"]        # False hidden; None (degraded) kept


# ── per-type group weights (the Planning "Object types" controls) ──────────────

def test_type_group_weight_roundtrip():
    groups = {"galaxy": 1.5, "open_cluster": 0.5, "globular": 1.0, "nebula": 2.0}
    tw = pr.type_weights_from_groups(groups)
    assert tw["galaxy"] == 1.5 and tw["open_cluster"] == 0.5
    assert "globular" not in tw                          # neutral 1.0 isn't stored
    assert tw["emission"] == 2.0 and tw["planetary"] == 2.0   # whole nebula group
    back = pr.groups_from_type_weights(tw)
    assert back == {"galaxy": 1.5, "globular": 1.0, "open_cluster": 0.5, "nebula": 2.0}


def test_type_weight_lifts_matching_type_score():
    ctx = TargetContext("g", obj_type="galaxy", integration_min=0.0, in_active_goal=True)
    s0 = pr.score_target(ctx, Weights(), pr.STRATEGY_CAPTURE)["score"]
    s1 = pr.score_target(ctx, Weights(type_weights={"galaxy": 2.0}),
                         pr.STRATEGY_CAPTURE)["score"]
    assert s1 > s0                                       # galaxy multiplier lifts it

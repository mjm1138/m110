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

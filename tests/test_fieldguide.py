"""Field-guide render + saved-guide store (m110/fieldguide.py)."""
from datetime import date, datetime

from m110 import fieldguide
from m110.planning_config import Site
from tests._helpers import seed_root

_SITE = Site(name="Dark Site", latitude_deg=40.0, longitude_deg=-105.0)
_DAY = date(2026, 7, 13)


def _plan():
    t0 = datetime(2026, 7, 13, 22, 30)
    t1 = datetime(2026, 7, 14, 3, 30)
    return {
        "window": (t0, datetime(2026, 7, 14, 3, 50)),
        "moon": {"illum": 0.12, "alt": -17.0},
        "entries": [
            {"slug": "m13", "transit_time": t0, "transit_alt": 85.0, "best_alt": 85.0,
             "up_start": t0, "up_end": t1, "moon_sep_deg": 70.0, "samples": []},
        ],
    }


def test_render_markdown_has_window_moon_and_targets(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(_SITE, _DAY, _plan())
    assert "# Observing plan — 2026-07-13" in md
    assert "Dark Site" in md
    assert "22:30 – 03:50" in md          # dark window
    assert "12% lit" in md                # moon
    assert "22:30" in md and "03:30" in md  # target best time + up-window
    assert "| # | Object |" in md         # the ordered table


def test_render_markdown_empty_plan(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(_SITE, _DAY,
                                    {"window": (None, None), "moon": {}, "entries": []})
    assert "No targets are up tonight" in md


def test_save_list_read_roundtrip(tmp_path, monkeypatch):
    from m110 import config
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(_SITE, _DAY, _plan())
    path = fieldguide.save(_DAY, "Backyard Friday", md)
    assert path.parent == config.PLANS_DIR
    assert path.name.startswith("2026-07-13_backyard-friday")
    guides = fieldguide.list_guides()
    assert len(guides) == 1
    assert guides[0]["date"] == "2026-07-13"
    assert guides[0]["title"] == "Observing plan — 2026-07-13"
    assert fieldguide.read(guides[0]["path"]) == md


def test_save_disambiguates_duplicate_names(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    a = fieldguide.save(_DAY, "Plan", "x")
    b = fieldguide.save(_DAY, "Plan", "y")
    assert a != b and len(fieldguide.list_guides()) == 2


def test_plans_dir_seeded(tmp_path, monkeypatch):
    from m110 import config
    root = seed_root(tmp_path, monkeypatch)
    assert config.PLANS_DIR.is_dir()          # ensure_data_root created Plans/


# ── per-slot moon rendering (Phase 2 / BUGS #36) ─────────────────────────────

def test_moon_headline_states():
    hm = fieldguide.moon_headline
    assert hm({"illum": 0.27, "alt": 5.8,
               "set_time": datetime(2026, 7, 18, 23, 5), "rise_time": None}) \
        == "27% lit · up at dusk (+6°) · sets 23:05"
    assert hm({"illum": 0.4, "alt": -12.0, "set_time": None,
               "rise_time": datetime(2026, 7, 19, 1, 20)}) \
        == "40% lit · down at dusk · rises 01:20"
    assert hm({"illum": 0.02, "alt": -30.0, "set_time": None, "rise_time": None}) \
        == "2% lit · down at dusk · down all night"
    assert hm({"illum": 0.99, "alt": 45.0, "set_time": None, "rise_time": None}) \
        == "99% lit · up at dusk (+45°) · up all night"


def test_moon_cell_gates_on_moon_up():
    # Moon down at the target's best time → no separation shown (it means nothing).
    assert fieldguide.moon_cell({"moon_sep_deg": 44.0, "moon_alt_at_best": -10.0,
                                 "moon_impact": None}) == "—"
    # Moon up → separation + impact.
    assert fieldguide.moon_cell({"moon_sep_deg": 44.0, "moon_alt_at_best": 20.0,
                                 "moon_impact": "low"}) == "44° · low"
    # A pre-annotation plan dict degrades to the bare separation.
    assert fieldguide.moon_cell({"moon_sep_deg": 44.0}) == "44°"


def test_render_markdown_moon_gating(tmp_path, monkeypatch):
    """The rendered table shows '—' for a moon-down slot, the separation+impact for a
    moon-up slot, and the headline describes the night, not one dusk snapshot."""
    seed_root(tmp_path, monkeypatch)
    t0 = datetime(2026, 7, 18, 22, 30)
    t1 = datetime(2026, 7, 19, 3, 30)
    plan = {
        "window": (t0, datetime(2026, 7, 19, 3, 50)),
        "moon": {"illum": 0.27, "alt": 5.8,
                 "set_time": datetime(2026, 7, 18, 23, 5), "rise_time": None,
                 "track": []},
        "entries": [
            {"slug": "m107", "transit_time": t0, "transit_alt": 37.0, "best_alt": 37.0,
             "up_start": t0, "up_end": datetime(2026, 7, 19, 0, 0),
             "moon_sep_deg": 44.0, "moon_alt_at_best": 4.0, "moon_impact": "low",
             "samples": []},
            {"slug": "m15", "transit_time": datetime(2026, 7, 19, 3, 0),
             "transit_alt": 62.0, "best_alt": 62.0,
             "up_start": datetime(2026, 7, 19, 0, 10), "up_end": t1,
             "moon_sep_deg": 44.0, "moon_alt_at_best": -40.0, "moon_impact": None,
             "samples": []},
        ],
    }
    md = fieldguide.render_markdown(_SITE, date(2026, 7, 18), plan)
    assert "27% lit · up at dusk (+6°) · sets 23:05" in md
    assert "| 44° · low |" in md          # moon-up slot: separation + impact
    assert "| — |" in md                  # moon-down slot: gated
    assert "below the horizon" in md      # the explanation footnote

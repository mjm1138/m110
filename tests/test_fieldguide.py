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

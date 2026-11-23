"""Planning follow-ups (Phase 8 feedback): Start · Duration · End in plans and
saved guides, Plan a night right under the location, and the telescope always
shown. Temp fixtures only."""
import json
from datetime import date, datetime

import pytest

from m110 import config, fieldguide
from m110.planning_config import Site
from tests._helpers import seed_root

_SITE = Site(name="Dark Site", latitude_deg=40.0, longitude_deg=-105.0)
_DAY = date(2026, 7, 13)


def _slot(slug, start, minutes, **kw):
    return dict({"slug": slug, "start": start, "duration_min": minutes,
                 "alt_start": 40.0, "moon_sep_deg": 70.0, "moon_alt_at_best": -5.0,
                 "moon_impact": None, "over_ceiling": False}, **kw)


def _schedule_plan():
    t0 = datetime(2026, 7, 13, 22, 30)
    return {"window": (t0, datetime(2026, 7, 14, 4, 0)), "moon": {},
            "entries": [{"slug": "m13"}, {"slug": "m57"}],
            "schedule": [_slot("m13", t0, 150),
                         _slot("m57", datetime(2026, 7, 14, 1, 0), 100,
                               marginal=True)]}


# ── engine ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("minutes,text", [
    (None, "—"), (0, "0m"), (40, "40m"), (60, "1h"), (90, "1h 30m"),
    (125, "2h 05m"), (89.6, "1h 30m")])
def test_duration_text(minutes, text):
    assert fieldguide.duration_text(minutes) == text


def test_time_cells_for_a_slot_and_an_unsequenced_entry():
    s = _slot("m13", datetime(2026, 7, 13, 23, 50), 40, marginal=True)
    assert fieldguide.time_cells(s) == ("23:50", "40m ⚠", "00:30")   # past midnight
    e = {"slug": "m13", "start_time": datetime(2026, 7, 13, 22, 30),
         "up_end": datetime(2026, 7, 14, 3, 30)}
    assert fieldguide.time_cells(e) == ("22:30", "5h", "03:30")
    old = {"slug": "m13", "transit_time": datetime(2026, 7, 13, 23, 0),
           "up_end": datetime(2026, 7, 14, 1, 15)}                      # pre-Phase-3
    assert fieldguide.time_cells(old) == ("23:00", "2h 15m", "01:15")
    none = {"slug": "m13", "start_time": None, "up_end": None}
    assert fieldguide.time_cells(none) == ("—", "—", "—")


def test_a_saved_schedule_has_start_duration_and_end(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(_SITE, _DAY, _schedule_plan())
    assert "| # | Object | Start | Duration | End | Alt | Filter | Moon |" in md
    rows = [ln for ln in md.splitlines() if ln.startswith("| 1 ") or
            ln.startswith("| 2 ")]
    assert "| 22:30 | 2h 30m | 01:00 |" in rows[0]
    assert "| 01:00 | 1h 40m ⚠ | 02:40 |" in rows[1]


def test_an_unsequenced_guide_has_the_same_columns(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    t0 = datetime(2026, 7, 13, 22, 30)
    plan = {"window": (t0, datetime(2026, 7, 14, 3, 50)), "moon": {},
            "entries": [{"slug": "m13", "start_time": t0, "start_alt": 60.0,
                         "up_start": t0, "up_end": datetime(2026, 7, 14, 3, 30),
                         "moon_sep_deg": 70.0, "samples": []}]}
    md = fieldguide.render_markdown(_SITE, _DAY, plan)
    assert "| # | Object | Start | Duration | End | Alt | Moon | Filter |" in md
    assert "| 22:30 | 5h | 03:30 | 60° |" in md
    assert "Up-window" not in md
    assert fieldguide.guide_span(md) is None          # no schedule → no span


def test_guide_span_reads_a_new_guide(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(_SITE, _DAY, _schedule_plan())
    assert fieldguide.guide_span(md) == {"start": "22:30", "duration": "4h 10m",
                                         "end": "02:40"}


OLD_GUIDE = """# Observing plan — 2026-07-13

**Site:** Dark Site

## Schedule (2 targets)

| # | Object | Start | Duration | Alt | Filter | Moon |
|---|--------|-------|----------|-----|--------|------|
| 1 | M13 | 21:40 | 150 min | 62° | IRCUT | — |
| 2 | M57 | 00:10 | 90 min ⚠ | 70° | LP | — |

<sub>notes</sub>
"""


def test_guide_span_reads_a_guide_saved_before_end_existed():
    assert fieldguide.guide_span(OLD_GUIDE) == {"start": "21:40", "duration": "4h",
                                                "end": "01:40"}


def test_guide_span_tolerates_odd_files():
    assert fieldguide.guide_span("") is None
    assert fieldguide.guide_span("# Just a title\n\nBody.\n") is None
    assert fieldguide.guide_span("## Schedule\n\n| # | Object |\n|---|---|\n") is None
    broken = OLD_GUIDE.replace("21:40", "soon")
    assert fieldguide.guide_span(broken) is None


def test_list_guides_carries_the_span(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    fieldguide.save(_DAY, "Old", OLD_GUIDE)
    fieldguide.save(date(2026, 7, 14), "Plain", "# Plain\n\nNo table.\n")
    spans = {g["title"]: g["span"] for g in fieldguide.list_guides()}
    assert spans["Observing plan — 2026-07-13"]["end"] == "01:40"
    assert spans["Plain"] is None


# ── the page ─────────────────────────────────────────────────────────────────

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

S50, DWARF = "S50_15e7e390", "DWARF 3"


def _devices_json(*entries):
    config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (config.DERIVED_DIR / "devices.json").write_text(json.dumps({"devices": [
        {"device": k, "label": lab, "retired": False} for k, lab in entries]}))


@pytest.fixture
def page(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110 import prioritize
    monkeypatch.setattr(prioritize, "load_contexts", lambda *a, **k: None)
    from m110.ui.pages import planning
    monkeypatch.setattr(planning.PlanningPage, "_maybe_recompute",
                        lambda self, force=False: None)
    p = planning.PlanningPage()
    qtbot.addWidget(p)
    return p


def _section_titles(page):
    from m110.ui.widgets import CollapsibleSection
    lay = page.widget().layout()
    out = []
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if isinstance(w, CollapsibleSection):
            out.append(w)
    return out


def test_plan_a_night_sits_right_under_the_location(page):
    secs = _section_titles(page)
    assert secs[:3] == [page._plan_sec, page._guides_sec, page._priority_sec]
    assert page._plan_sec._btn.isChecked()            # open: it's why you came


def test_the_telescope_is_always_shown(page):
    from m110.ui.pages.planning import NO_DEVICE_TEXT
    page.reload()                                     # no telescope yet
    assert not page.device_label.isHidden()
    assert page.device_picker.isHidden() and not page.device_name.isHidden()
    assert page.device_name.text() == NO_DEVICE_TEXT

    _devices_json((S50, "Backyard S50"))              # one telescope: its name
    page.reload()
    assert page.device_picker.isHidden()
    assert page.device_name.text() == "Backyard S50"

    _devices_json((DWARF, "DwarfLab Dwarf 3"), (S50, "Backyard S50"))   # a choice
    page.reload()
    assert not page.device_picker.isHidden() and page.device_name.isHidden()


def test_switching_telescope_reranks_for_its_model(page, monkeypatch):
    from m110 import integration_goals, prioritize
    _devices_json((DWARF, "DwarfLab Dwarf 3"), (S50, "Backyard S50"))
    page.reload()
    seen = []
    monkeypatch.setattr(prioritize, "rank_for_active",
                        lambda *a, **k: seen.append(integration_goals.active_model())
                        or [])
    monkeypatch.setattr(prioritize, "load_contexts", lambda *a, **k: [object()])
    page.device_picker.setCurrentIndex(page.device_picker.findData(S50))
    assert seen and seen[-1] == integration_goals.model_key(S50)
    page.device_picker.setCurrentIndex(page.device_picker.findData(DWARF))
    assert seen[-1] == integration_goals.model_key(DWARF)


def test_the_plan_table_has_start_duration_end(page):
    page._slots = _schedule_plan()["schedule"]
    page._plan_meta = {"window": (None, None)}
    page._render_plan()
    t = page._plan_table
    heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert heads == ["Include", "Object", "Start", "Duration", "End", "Alt", "Moon"]
    assert [t.item(0, c).text() for c in (2, 3, 4)] == ["22:30", "2h 30m", "01:00"]
    assert [t.item(1, c).text() for c in (2, 3, 4)] == ["01:00", "1h 40m ⚠", "02:40"]
    for c in (2, 3, 4):
        assert t.item(0, c).textAlignment() & Qt.AlignRight


def test_the_unsequenced_plan_table_says_duration_not_a_window(page):
    t0 = datetime(2026, 7, 13, 22, 30)
    page._slots = []
    page._entries = [{"slug": "m13", "start_time": t0, "start_alt": 60.0,
                      "up_start": t0, "up_end": datetime(2026, 7, 14, 3, 30),
                      "moon_sep_deg": 70.0}]
    page._included = {"m13"}
    page._plan_meta = {"window": (None, None)}
    page._render_plan()
    t = page._plan_table
    assert [t.item(0, c).text() for c in (2, 3, 4, 5)] == ["22:30", "5h", "03:30", "60°"]


def test_the_guides_list_shows_each_nights_span(page):
    fieldguide.save(_DAY, "Old", OLD_GUIDE)
    fieldguide.save(date(2026, 7, 14), "Plain", "# Plain\n\nNo table.\n")
    page._reload_guides()
    t = page._guides_table
    heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert heads == ["Date", "Start", "Duration", "End", "Title"]
    rows = {t.item(r, 4).text(): [t.item(r, c).text() for c in (1, 2, 3)]
            for r in range(t.rowCount())}
    assert rows["Observing plan — 2026-07-13"] == ["21:40", "4h", "01:40"]
    assert rows["Plain"] == ["—", "—", "—"]
    assert t.item(0, 1).textAlignment() & Qt.AlignRight

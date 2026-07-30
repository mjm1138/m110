"""Sky-map chart data (ROADMAP item 12a) — config building, status colors, render."""
from __future__ import annotations

import pytest

from m110 import skymap
from tests._helpers import add_library, seed_capture, seed_root

needs_uranometria = pytest.mark.skipif(
    not skymap.available(), reason="uranometria (the optional skymap extra) not installed"
)


def _library(root, **extra):
    """Two catalog objects with coordinates, plus whatever the test adds."""
    entries = {
        "m31": {"id": "M31", "name": "Andromeda Galaxy", "type": "galaxy",
                "ra_deg": "10.6847", "dec_deg": "41.2688"},
        "m42": {"id": "M42", "name": "Orion Nebula", "type": "emission",
                "ra_deg": "83.8221", "dec_deg": "-5.3911"},
    }
    entries.update(extra)
    add_library(root, entries)


def test_build_config_carries_coords_labels_and_colors(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    config, charted, skipped = skymap.build_config()
    assert skipped == []
    by_label = {o["label"]: o for o in config["objects"]}
    assert set(by_label) == {"M31", "M42"}
    assert by_label["M31"]["ra"] == pytest.approx(10.6847)
    assert by_label["M31"]["dec"] == pytest.approx(41.2688)
    assert by_label["M31"]["name"] == "Andromeda Galaxy"
    # Nothing captured yet, so everything reads as a Library member not yet shot.
    assert {o["color"] for o in config["objects"]} == {
        skymap.DEFAULT_COLORS[skymap.STATUS_UNCAPTURED]
    }


def test_build_config_skips_objects_without_coordinates(tmp_path, monkeypatch):
    # A real Library holds folder-derived entries with no position to plot.
    root = seed_root(tmp_path, monkeypatch)
    _library(root, unknown={"id": "Unknown", "type": "unknown"})
    config, charted, skipped = skymap.build_config()
    assert skipped == ["unknown"]
    assert len(config["objects"]) == 2  # the chartable two, not a failure


def test_build_config_honors_the_requested_slugs(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    config, _charted, _skipped = skymap.build_config(["m31"])
    assert [o["label"] for o in config["objects"]] == ["M31"]
    # An unknown slug is simply not charted; it is not an error.
    config, charted, skipped = skymap.build_config(["m31", "nope"])
    assert [o["label"] for o in config["objects"]] == ["M31"]
    assert skipped == []


def test_status_and_color_follow_the_derived_verdict(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    # `seed_capture` shoots a bundled Messier object and refreshes, which also
    # promotes it into the Library — so add a *different* object as the control.
    shot, _tid = seed_capture(root)
    unshot = "m42" if shot != "m42" else "m31"
    add_library(root, {unshot: {"id": unshot.upper(), "type": "emission",
                                "ra_deg": "83.8221", "dec_deg": "-5.3911"}})

    assert skymap.object_status(shot) == skymap.STATUS_INITIAL
    assert skymap.object_status(unshot) == skymap.STATUS_UNCAPTURED

    config, _charted, _skipped = skymap.build_config([shot, unshot])
    colors = [o["color"] for o in config["objects"]]
    assert colors == [
        skymap.DEFAULT_COLORS[skymap.STATUS_INITIAL],
        skymap.DEFAULT_COLORS[skymap.STATUS_UNCAPTURED],
    ]


def test_status_colors_are_overridable(tmp_path, monkeypatch):
    # The UI passes live theme tokens so the chart follows light/dark.
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    config, _charted, _skipped = skymap.build_config(colors={skymap.STATUS_UNCAPTURED: "#123456"})
    assert {o["color"] for o in config["objects"]} == {"#123456"}


def test_label_drops_the_capture_target_decoration(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m42_mosaic": {"id": "M42_mosaic", "type": "emission",
                                      "ra_deg": "83.8", "dec_deg": "-5.4"}})
    config, _charted, _skipped = skymap.build_config()
    assert [o["label"] for o in config["objects"]] == ["M42"]


def test_hero_is_offered_for_the_host_to_draw(tmp_path, monkeypatch):
    from m110 import config as cfg

    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    cfg.HERO_DIR.mkdir(parents=True, exist_ok=True)
    (cfg.HERO_DIR / "m31.jpg").write_bytes(b"\xff\xd8fake")
    config, _charted, _skipped = skymap.build_config()
    by_label = {o["label"]: o for o in config["objects"]}
    assert by_label["M31"]["image"].endswith("m31.jpg")
    assert "image" not in by_label["M42"]  # no hero rendered yet
    config, _charted, _skipped = skymap.build_config(heroes=False)
    assert all("image" not in o for o in config["objects"])


@needs_uranometria
def test_render_returns_hemispheres_with_marker_positions(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    charts, warnings = skymap.render()
    assert [c["hemisphere"] for c in charts] == ["north"]  # M42 rides the north disc
    assert warnings == []
    svg = charts[0]["svg"]
    assert svg.startswith("<svg xmlns=") and "var(--" not in svg
    placed = {o["disp"]: o for o in charts[0]["objects"]}
    assert set(placed) == {"M31", "M42"}
    for o in placed.values():
        assert 0 < o["x"] < 1000 and 0 < o["y"] < 1000
        assert f'id="{o["id"]}"' in svg


@needs_uranometria
def test_render_adds_a_southern_disc_only_when_needed(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root, ngc104={"id": "NGC 104", "type": "globular",
                           "ra_deg": "6.02", "dec_deg": "-72.08"})
    charts, _ = skymap.render()
    assert [c["hemisphere"] for c in charts] == ["north", "south"]
    uids = sorted(o["uid"] for c in charts for o in c["objects"])
    assert uids == [0, 1, 2]  # one key space across both discs


@needs_uranometria
def test_every_marker_carries_its_slug_across_a_skip(tmp_path, monkeypatch):
    # The click→object path. A marker's uid indexes the *charted* list, so an
    # object skipped for missing coordinates shifts every uid after it — a
    # caller mapping uids onto its own slug list would silently mis-key here.
    root = seed_root(tmp_path, monkeypatch)
    _library(root, unknown={"id": "Unknown", "type": "unknown"},
             ngc104={"id": "NGC 104", "type": "globular",
                     "ra_deg": "6.02", "dec_deg": "-72.08"})
    charts, _ = skymap.render(["m31", "unknown", "m42", "ngc104"])
    placed = {o["slug"]: o for c in charts for o in c["objects"]}
    assert set(placed) == {"m31", "m42", "ngc104"}
    assert placed["m31"]["disp"] == "M31"
    assert placed["m42"]["disp"] == "M42"
    assert placed["ngc104"]["disp"] == "NGC 104"
    # 'unknown' was requested second and dropped, so m42 is uid 1, not 2.
    assert placed["m42"]["uid"] == 1


@needs_uranometria
def test_render_warns_about_uncharted_objects(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root, unknown={"id": "Unknown", "type": "unknown"})
    charts, warnings = skymap.render()
    assert len(charts) == 1
    assert any("no coordinates" in w and "Unknown" in w for w in warnings)


@needs_uranometria
def test_an_empty_selection_returns_an_empty_sky(tmp_path, monkeypatch):
    # Nothing to plot still has a sky worth showing — the chart with no objects
    # on it, so a filter that matches nothing doesn't blank the view.
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    charts, warnings = skymap.render([])
    assert [c["hemisphere"] for c in charts] == ["north"]
    assert charts[0]["objects"] == []          # nothing clickable
    assert warnings == []
    svg = charts[0]["svg"]
    assert "constellations" in svg             # the sky itself is drawn
    # The marker that makes uranometria willing to render is painted in nothing.
    assert 'fill="transparent"' in svg and 'stroke="transparent"' in svg


@needs_uranometria
def test_empty_sky_can_be_declined(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    charts, warnings = skymap.render([], empty_sky=False)
    assert charts == [] and warnings == []


@needs_uranometria
def test_render_themes_the_chart_and_names_a_font(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    charts, _ = skymap.render(palette={"sky": "#ffffff"}, font_family="JetBrains Mono")
    svg = charts[0]["svg"]
    assert 'fill="#ffffff"' in svg and 'font-family="JetBrains Mono"' in svg


def test_missing_dependency_raises_deps_missing(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _library(root)
    monkeypatch.setattr(skymap, "_uranometria", _raise_deps)
    with pytest.raises(skymap.SkymapDepsMissing):
        skymap.render()


def _raise_deps():
    raise skymap.SkymapDepsMissing("not installed")

"""Night vision (UI Phase 8 · F): the mode, its toggle, and images in red.

The filter is checked on real pixels; the toggle is clicked through View ›
Night Vision and Settings › Appearance; the main window's image repaint is
driven, including its wait-out-a-modal rule.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402

from m110 import config  # noqa: E402
from m110.ui import theme  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


@pytest.fixture
def mgr(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    m = theme.install(qapp)
    m.set_mode("light")
    yield m
    m.set_mode("system")
    config.save_setting(theme.SETTING_KEY, None)
    config.save_setting(theme.NIGHT_PREV_KEY, None)


def _image(colors, w=3, h=1, fmt=QImage.Format.Format_RGB888):
    img = QImage(w, h, fmt)
    for i, c in enumerate(colors):
        img.setPixelColor(i % w, i // w, QColor(c))
    return img


# ── the filter ──────────────────────────────────────────────────────────────

def test_night_image_is_red_only_and_dimmed():
    # RGB888 at an odd width has padded scanlines — the reshape must not skew.
    img = _image(["#ffffff", "#00ff00", "#000000"])
    out = theme.night_image(img)
    assert (out.width(), out.height()) == (3, 1)
    px = [out.pixelColor(x, 0) for x in range(3)]
    assert all(c.green() == 0 and c.blue() == 0 for c in px)
    assert px[0].red() == pytest.approx(255 * theme.NIGHT_DIM, abs=1)    # white → half red
    assert px[1].red() == pytest.approx(255 * 0.7152 * theme.NIGHT_DIM, abs=1)
    assert px[2].red() == 0


def test_night_image_keeps_alpha_and_pixel_ratio():
    img = QImage(2, 2, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255, 0))
    img.setPixelColor(0, 0, QColor(255, 255, 255, 255))
    img.setDevicePixelRatio(2.0)
    out = theme.night_image(img)
    assert out.pixelColor(0, 0).alpha() == 255
    assert out.pixelColor(1, 1).alpha() == 0
    assert out.devicePixelRatio() == 2.0


def test_display_image_is_the_identity_outside_night(mgr):
    img = _image(["#3366cc", "#ffffff", "#123456"])
    assert theme.display_image(img) is img
    mgr.set_mode("night")
    shown = theme.display_image(img)
    assert all(shown.pixelColor(x, 0).blue() == 0 for x in range(3))
    pm = theme.display_pixmap(img)
    assert pm.toImage().pixelColor(0, 0).green() == 0


def test_thumbnails_come_out_red_from_the_same_cache(mgr, tmp_path, qapp):
    from m110.ui.widgets import ThumbnailLoader, drain_thumbnail_pool
    path = tmp_path / "hero.png"
    big = QImage(40, 40, QImage.Format.Format_RGB32)
    big.fill(QColor("#2060ff"))
    big.save(str(path))
    loader = ThumbnailLoader()
    got = []
    loader.request(path, 16, got.append, crop="square")
    drain_thumbnail_pool()
    for _ in range(20):
        qapp.processEvents()
        if got:
            break
    assert got and got[0].toImage().pixelColor(8, 8).blue() > 200   # colour by day
    mgr.set_mode("night")
    got.clear()
    loader.request(path, 16, got.append, crop="square")             # cache hit: sync
    c = got[0].toImage().pixelColor(8, 8)
    assert c.blue() == 0 and c.green() == 0 and c.red() > 0


# ── the mode ────────────────────────────────────────────────────────────────

def test_night_is_a_mode_and_resolves_to_itself(mgr):
    assert "night" in theme.MODES
    assert theme.resolve("night") == "night"
    mgr.set_mode("night")
    assert theme.active_tokens().name == "night" and theme.is_night()


def test_night_toggle_returns_to_the_mode_before_it(mgr):
    mgr.set_mode("dark")
    mgr.set_night(True)
    assert mgr.mode == "night"
    assert config.get_setting(theme.NIGHT_PREV_KEY) == "dark"
    mgr.set_night(False)
    assert mgr.mode == "dark" and theme.active_tokens().name == "dark"


def test_night_forces_the_native_scheme_dark_and_lets_it_go(mgr, qapp):
    hints = qapp.styleHints()
    if not hasattr(hints, "setColorScheme"):
        pytest.skip("Qt < 6.8 has no per-app colour scheme")
    calls = []
    real = hints.setColorScheme
    hints_cls = type(hints)
    orig = hints_cls.setColorScheme
    try:
        hints_cls.setColorScheme = lambda self, s: (calls.append(s), orig(self, s))[1]
        mgr.set_night(True)
        mgr.set_night(False)
    finally:
        hints_cls.setColorScheme = orig
    assert calls == [Qt.ColorScheme.Dark, Qt.ColorScheme.Unknown]
    del real


# ── the toggles: View menu and Settings ────────────────────────────────────

def _window():
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    return win


def test_view_night_vision_toggles_and_settings_follows(mgr, qapp):
    win = _window()
    try:
        assert win.night_action.isCheckable() and not win.night_action.isChecked()
        assert win.night_action.shortcut().toString() == "Ctrl+Shift+N"
        s = win._show_settings("appearance")
        win.night_action.trigger()
        assert mgr.mode == "night" and win.night_action.isChecked()
        assert s._theme_combo.currentData() == "night"
        win.night_action.trigger()
        assert mgr.mode == "light" and not win.night_action.isChecked()
        assert s._theme_combo.currentData() == "light"
        # …and the other way: Settings picks Night, the menu item checks.
        s._theme_combo.setCurrentIndex(s._theme_combo.findData("night"))
        assert win.night_action.isChecked()
        s.close()
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_toggling_night_reshows_every_pages_images(mgr, qapp, monkeypatch):
    win = _window()
    try:
        reloaded = []
        for p in win.pages:
            if not hasattr(p, "restyle"):
                monkeypatch.setattr(p, "reload", lambda p=p: reloaded.append(p))
        detail = []
        monkeypatch.setattr(win.catalog, "_refresh_open_detail", lambda: detail.append(1))
        win.night_action.trigger()
        qapp.processEvents()                       # the repaint is deferred
        assert reloaded and set(reloaded) == {p for p in win.pages
                                              if not hasattr(p, "restyle")}
        assert detail == [1]
        reloaded.clear()
        mgr.set_mode("night")                      # no flip → no repaint
        qapp.processEvents()
        assert reloaded == []
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_the_repaint_waits_out_a_modal(mgr, qapp, monkeypatch):
    from m110.ui import main as main_mod
    win = _window()
    try:
        calls = []
        monkeypatch.setattr(win.catalog, "_refresh_open_detail", lambda: calls.append(1))
        monkeypatch.setattr(main_mod, "modal_loop_active", lambda: True)
        retried = []
        monkeypatch.setattr(main_mod.QTimer, "singleShot",
                            lambda ms, ctx, fn: retried.append(ms))
        win._repaint_images()
        assert calls == [] and retried == [250]
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


# ── what else draws colour ──────────────────────────────────────────────────

def test_map_tooltip_drops_the_photo_at_night(mgr, tmp_path):
    from m110.ui.sky_map import _tooltip
    hero = tmp_path / "m42.jpg"
    QImage(4, 4, QImage.Format.Format_RGB32).save(str(hero))
    marker = {"disp": "M42", "name": "Orion Nebula", "image": str(hero)}
    assert "<img" in _tooltip(marker)
    mgr.set_mode("night")
    tip = _tooltip(marker)
    assert "<img" not in tip and "Orion Nebula" in tip


def test_planner_curves_are_reds_at_night(mgr):
    from m110.ui import night_timeline
    assert night_timeline._series() == night_timeline._SERIES
    mgr.set_mode("night")
    for hexcol in night_timeline._series():
        c = QColor(hexcol)
        # The night palette's own hue family: green and blue well under half the red.
        assert c.green() <= 0.45 * c.red() and c.blue() <= 0.45 * c.red(), hexcol


def test_banners_take_their_colours_from_the_app_sheet(mgr, qapp):
    """An inline sheet bakes in the colours of the theme it was built under — the
    banner stayed dark-mode grey after switching to night. Both banners now rely on
    `#assistantBanner` / `#updateBanner` in theme/qss.py."""
    from types import SimpleNamespace
    from m110.ui.assistant_review import AssistantBanner
    from m110.ui.update_notice import UpdateBanner
    a = AssistantBanner()
    u = UpdateBanner(SimpleNamespace(latest="9.9.9", current="0.1.0", url=""))
    try:
        assert a.styleSheet() == "" and u.styleSheet() == ""
        sheet = theme.build_qss(theme.NIGHT)
        assert "#assistantBanner" in sheet and "#updateBanner" in sheet
        assert theme.NIGHT.surface_alt in sheet
    finally:
        a.deleteLater()
        u.deleteLater()
        qapp.processEvents()


def test_map_stars_are_red_at_night(mgr):
    """uranometria tints stars blue/yellow/orange by temperature; at night those
    keys are overridden with the night reds, so the chart has no near-white."""
    from m110.ui.sky_map import chart_palette
    assert "star_blue" not in chart_palette()          # by day: its own colours
    mgr.set_mode("night")
    pal = chart_palette()
    for key in ("star", "star_blue", "star_yellow", "star_orange"):
        c = QColor(pal[key])
        assert c.green() <= 0.45 * c.red() and c.blue() <= 0.45 * c.red(), key

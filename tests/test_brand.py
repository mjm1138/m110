"""Branding assets — theme-aware logo, parchment app icon, About dialog.
qapp comes from pytest-qt; the live store is sealed by tests/conftest.py."""
from PySide6.QtGui import QColor


def _sample_differs(a, b, step=4):
    """Count sampled pixels where two same-size images differ (ink pixels only)."""
    ia, ib = a.toImage(), b.toImage()
    return sum(1 for x in range(0, ia.width(), step)
               for y in range(0, ia.height(), step)
               if ia.pixelColor(x, y) != ib.pixelColor(x, y))


def test_logo_recolors_with_ink(qapp):
    from m110.ui.theme import brand
    dark = brand.logo_pixmap(40, QColor("#101010"))
    light = brand.logo_pixmap(40, QColor("#f0f0f0"))
    assert not dark.isNull() and not light.isNull()
    assert dark.size() == light.size()          # same geometry, different ink
    assert _sample_differs(dark, light) > 0      # recolor actually changed pixels


def test_logo_is_tight_cropped_wordmark(qapp):
    from m110.ui.theme import brand
    pm = brand.logo_pixmap(40, QColor("#000000"))
    assert pm.height() == 40
    # The "M110" wordmark crops wider than it is tall (no square-viewBox whitespace).
    assert pm.width() > pm.height()


def test_logo_cache_is_shared_but_dpr_isolated(qapp):
    from m110.ui.theme import brand
    a = brand.logo_pixmap(30, QColor("#222222"), dpr=1.0)
    b = brand.logo_pixmap(30, QColor("#222222"), dpr=2.0)
    # Same color+pixel-height key underneath, but per-caller dpr doesn't cross-mutate.
    assert a.devicePixelRatio() == 1.0
    assert b.devicePixelRatio() == 2.0


def test_app_icon_renders_all_sizes(qapp):
    from m110.ui.theme import brand
    icon = brand.app_icon()
    for s in (16, 32, 128, 256, 512):
        pm = icon.pixmap(s, s)
        assert not pm.isNull()
        assert pm.width() == s and pm.height() == s


def test_about_dialog_builds_and_shows_version(qapp):
    from PySide6.QtWidgets import QLabel
    from m110.ui.about_dialog import AboutDialog, app_version
    dlg = AboutDialog()
    texts = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
    assert app_version() in texts
    assert AboutDialog.TAGLINE in texts
    assert any(not lbl.pixmap().isNull()
               for lbl in dlg.findChildren(QLabel) if lbl.pixmap() is not None)

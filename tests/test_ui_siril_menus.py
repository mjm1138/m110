"""Every "Process in Siril" entry point reaches the launcher — and a split sandbox
offers its job folders where the user clicked (a submenu, or the detail button's
own drop-down), never as a second popup after the first menu closes."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from m110 import config, launch, refresh

from tests._helpers import messier_member, seed_root, seed_sandbox


def _first_table(page):
    for i in range(page._lay.count()):
        w = page._lay.itemAt(i).widget()
        if hasattr(w, "rowCount"):
            return w
    raise AssertionError("no table on the Processing page")


def test_processing_right_click_launches_siril(tmp_path, monkeypatch, qapp, qtbot):
    seed_root(tmp_path, monkeypatch)
    _, tid = messier_member()
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    seed_sandbox(tid)
    refresh.run_refresh(render=False)

    launched = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, d: launched.append((tool, d)) or "siril")
    # PySide6's QMenu.exec can't be monkeypatched: click the real popup's first
    # entry once it is up.
    def pick_first():
        popup = QApplication.activePopupWidget()
        if isinstance(popup, QMenu):
            rect = popup.actionGeometry(popup.actions()[0])
            QTest.mouseClick(popup, Qt.LeftButton, pos=rect.center())
        else:
            QTimer.singleShot(20, pick_first)

    from m110.ui.pages.processing import ProcessingPage
    page = ProcessingPage()
    page.resize(1000, 600)
    page.show()
    qtbot.waitExposed(page)
    try:
        tbl = _first_table(page)
        assert tbl.item(0, 0).text() == tid
        pos = tbl.visualItemRect(tbl.item(0, 0)).center()
        QTimer.singleShot(20, pick_first)
        tbl.customContextMenuRequested.emit(pos)
        qtbot.waitUntil(lambda: bool(launched), timeout=2000)
        assert launched == [("siril", config.siril_dir(tid))]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_processing_right_click_split_sandbox_offers_job_dirs(
        tmp_path, monkeypatch, qapp, qtbot):
    """A target split into job folders (NGC 6543: LP + IRCUT) lists them in a
    "Process in Siril" submenu of the same right-click menu."""
    seed_root(tmp_path, monkeypatch)
    _, tid = messier_member()
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    sb = seed_sandbox(tid)
    for f in ("LP", "IRCUT"):
        (sb / f / "lights").mkdir(parents=True)
    refresh.run_refresh(render=False)

    launched = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, d: launched.append((tool, d)) or "siril")
    menus = []

    def pick_first():
        popup = QApplication.activePopupWidget()
        if isinstance(popup, QMenu) and popup not in menus:
            menus.append(popup)
            rect = popup.actionGeometry(popup.actions()[0])
            QTest.mouseClick(popup, Qt.LeftButton, pos=rect.center())
        if len(menus) < 2:
            QTimer.singleShot(20, pick_first)

    from m110.ui.pages.processing import ProcessingPage
    page = ProcessingPage()
    page.resize(1000, 600)
    page.show()
    qtbot.waitExposed(page)
    try:
        tbl = _first_table(page)
        pos = tbl.visualItemRect(tbl.item(0, 0)).center()
        QTimer.singleShot(20, pick_first)
        tbl.customContextMenuRequested.emit(pos)
        qtbot.waitUntil(lambda: bool(launched), timeout=3000)
        top, sub = menus
        assert top.actions()[0].text() == "Process in Siril"
        assert top.actions()[0].menu() is sub          # a submenu, not a 2nd popup
        assert sorted(a.text() for a in sub.actions()) == [f"{tid} · IRCUT",
                                                           f"{tid} · LP"]
        assert launched[0][1].parent == sb
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── the detail pane's button ─────────────────────────────────────────────────

def _detail_for(tid, slug):
    from m110.ui.detail import DetailPane
    d = DetailPane()
    d.show_object(slug, {"id": tid, "name": tid, "type": "galaxy"},
                  {"status": "initial", "integration_hms": "0:01",
                   "session_count": 1, "frames": 1})
    return d


def _siril_button(d):
    from PySide6.QtWidgets import QPushButton
    btns = [b for b in d.findChildren(QPushButton) if b.text() == "Process in Siril"]
    assert len(btns) == 1, "the button must render, or this test guards nothing"
    return btns[0]


def test_detail_button_single_dir_launches_on_click(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    seed_sandbox(tid)
    refresh.run_refresh(render=False)
    launched = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, d: launched.append((tool, d)) or "siril")

    d = _detail_for(tid, slug)
    try:
        btn = _siril_button(d)
        assert btn.menu() is None
        btn.click()
        qapp.processEvents()
        assert launched == [("siril", config.siril_dir(tid))]
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_detail_button_split_sandbox_has_a_dropdown(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    sb = seed_sandbox(tid)
    for f in ("LP", "IRCUT"):
        (sb / f / "lights").mkdir(parents=True)
    refresh.run_refresh(render=False)
    launched = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, d: launched.append((tool, d)) or "siril")

    d = _detail_for(tid, slug)
    try:
        btn = _siril_button(d)
        menu = btn.menu()
        assert menu is not None
        labels = {a.text(): a for a in menu.actions()}
        assert set(labels) == {f"{tid} · LP", f"{tid} · IRCUT"}
        labels[f"{tid} · IRCUT"].trigger()        # what choosing the entry does
        qapp.processEvents()                      # the launch is deferred a cycle
        assert launched == [("siril", sb / "IRCUT")]
    finally:
        d.deleteLater()
        qapp.processEvents()

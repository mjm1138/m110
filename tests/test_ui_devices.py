"""Tools → Devices…: the per-device library, captures and sensor-health views,
driven offscreen from a `derived/devices.json`-shaped rollup."""
import pytest

pytest.importorskip("PySide6")

from tests._helpers import seed_root

DEV = {
    "device": "S50_c0ffee00", "label": "ZWO Seestar S50 · c0ffee00",
    "darks_applied_on_device": True,
    "masters": [
        {"tier": "darks", "file": "MasterDark_5_20.0s_24.9C_20261015-192853.fit",
         "rel": "Calibration/S50_c0ffee00/darks/MasterDark_5_20.0s_24.9C_20261015-192853.fit",
         "preview": None, "exptime": 20.0, "gain": 80, "binning": 1, "temp_c": 24.9,
         "frames": 5, "made": "2026-10-15T19:28:53", "captures": 1,
         "median": 512.0, "hot_px": 140},
        {"tier": "darks", "file": "MasterDark_5_20.0s_13.9C_20261015-215239.fit",
         "rel": "Calibration/S50_c0ffee00/darks/MasterDark_5_20.0s_13.9C_20261015-215239.fit",
         "preview": None, "exptime": 20.0, "gain": 80, "binning": 1, "temp_c": 13.9,
         "frames": 5, "made": "2026-10-15T21:52:39", "captures": 1,
         "median": 480.0, "hot_px": 40},
    ],
    "captures": [
        {"date": "2026-10-15", "object_dir": "M 72", "slugs": ["m72"], "frames": 295,
         "temp_min": 14.4, "temp_max": 24.8, "dark_ref":
         "MasterDark_5_20.0s_24.9C_20261015-192853.fit", "dark_temp_c": 24.9,
         "dark_gap_c": 10.5, "dark_link": "confirmed", "dark_rule": "v1"},
        {"date": "2026-10-15", "object_dir": "C 6", "slugs": ["ngc-6543"], "frames": 300,
         "temp_min": 11.2, "temp_max": 13.6, "dark_ref":
         "MasterDark_5_20.0s_13.9C_20261015-215239.fit", "dark_temp_c": 13.9,
         "dark_gap_c": 2.7, "dark_link": "confirmed", "dark_rule": "v1"},
    ],
}


def test_dialog_shows_library_captures_and_health(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.devices_dialog import DevicesDialog
    dlg = DevicesDialog(devices=[DEV])
    qtbot.addWidget(dlg)
    assert dlg._picker.isHidden()                       # one device → no picker
    assert "ZWO Seestar S50 · c0ffee00" in dlg._heading.text()
    assert "never applied again" in dlg._heading.text()
    assert dlg.library_table.rowCount() == 2
    assert dlg.captures_table.rowCount() == 2
    dark_cells = {dlg.captures_table.item(r, 1).text(): dlg.captures_table.item(r, 4).text()
                  for r in range(2)}
    assert dark_cells["M 72"] == "24.9 °C · Δ10.5 ⚠"    # warned by text, not color alone
    assert dark_cells["C 6"] == "13.9 °C · Δ2.7"
    assert sorted(dlg.level_chart.points()) == [(13.9, 480.0), (24.9, 512.0)]
    assert sorted(dlg.hot_chart.points()) == [(13.9, 40.0), (24.9, 140.0)]
    dlg.resize(900, 680)
    dlg.level_chart.grab()                              # paints without raising


def test_double_clicking_a_capture_opens_the_object_out_of_the_handler(
        tmp_path, monkeypatch, qtbot, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.devices_dialog import DevicesDialog
    dlg = DevicesDialog(devices=[DEV])
    qtbot.addWidget(dlg)
    opened = []
    dlg.open_object.connect(opened.append)
    t = dlg.captures_table
    row = next(r for r in range(t.rowCount()) if t.item(r, 1).text() == "M 72")
    t.itemDoubleClicked.emit(t.item(row, 0))
    assert opened == []                                 # deferred…
    qapp.processEvents()
    assert opened == ["m72"] and dlg.result() == dlg.DialogCode.Accepted


def test_switching_devices_and_the_empty_state(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.devices_dialog import DevicesDialog
    other = {"device": "DWARF 3", "label": "DwarfLab Dwarf 3",
             "darks_applied_on_device": False, "masters": [], "captures": []}
    dlg = DevicesDialog(devices=[DEV, other])
    qtbot.addWidget(dlg)
    assert not dlg._picker.isHidden()
    dlg._picker.setCurrentIndex(1)
    assert dlg.library_table.rowCount() == 0 and "never applied" not in dlg._heading.text()
    assert dlg._lib_sec.isHidden() and dlg._health_sec.isHidden()
    assert dlg.captures_table.isColumnHidden(4)              # no dark link for a Dwarf
    dlg._picker.setCurrentIndex(0)
    assert not dlg._lib_sec.isHidden() and not dlg.captures_table.isColumnHidden(4)
    empty = DevicesDialog(devices=[])
    qtbot.addWidget(empty)
    assert "No devices yet" in empty._heading.text()


def test_tools_devices_action_opens_the_dialog(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui import devices_dialog
    from m110.ui.main import MainWindow
    shown = []
    monkeypatch.setattr(devices_dialog.DevicesDialog, "exec",
                        lambda self: shown.append(self) or 0)
    win = MainWindow()
    win._ready = False
    try:
        assert win.devices_action.text() == "Devices…"
        win.devices_action.trigger()
        assert len(shown) == 1
    finally:
        win.deleteLater(); qapp.processEvents()


def test_sessions_and_detail_show_the_dark_column(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.widgets import dark_gap_item
    it = dark_gap_item(DEV["captures"][0])
    assert it.text() == "24.9 °C · Δ10.5 ⚠" and "confirmed" in it.toolTip()
    assert dark_gap_item({"dark_ref": None}).text() == "—"
    from m110.ui.pages.sessions import _COLS
    assert _COLS[-1] == "Dark"

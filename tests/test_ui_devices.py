"""The Devices page (nav rail): the device list, a device's identity / objects /
dark library / captures / sensor health, dark ↔ capture cross-selection, and
the Reveal context menus — driven offscreen from a `derived/devices.json`-shaped
rollup."""
import pytest

pytest.importorskip("PySide6")

from tests._helpers import seed_root

D24 = "MasterDark_5_20.0s_24.9C_20261015-192853.fit"
D13 = "MasterDark_5_20.0s_13.9C_20261015-215239.fit"
D23 = "MasterDark_5_20.0s_23.2C_20261016-204959.fit"


def _master(file, temp, made, label, captures, median, hot):
    return {"tier": "darks", "file": file,
            "rel": f"Calibration/S50_c0ffee00/darks/{file}", "preview": None,
            "exptime": 20.0, "gain": 80, "binning": 1, "temp_c": temp, "frames": 5,
            "made": made, "label": label, "captures": captures,
            "median": median, "hot_px": hot}


S50 = {
    "device": "S50_c0ffee00", "label": "ZWO Seestar S50 · c0ffee00", "nickname": None,
    "retired": False, "preset": "seestar_s50", "model": "ZWO Seestar S50",
    "serial": "c0ffee00", "darks_applied_on_device": True,
    "totals": {"integration_min": 190.0, "sessions": 3, "nights": 2, "objects": 2,
               "first_capture": "2026-10-15", "last_capture": "2026-10-17"},
    "objects": [{"slug": "m72", "id": "M72", "integration_min": 98.3, "frames": 295,
                 "session_count": 1},
                {"slug": "ngc-6543", "id": "NGC 6543", "integration_min": 91.7,
                 "frames": 275, "session_count": 2}],
    "masters": [_master(D24, 24.9, "2026-10-15T19:28:53", "Oct 15 19:28 · 24.9 °C", 1, 512, 140),
                _master(D13, 13.9, "2026-10-15T21:52:39", "Oct 15 21:52 · 13.9 °C", 2, 480, 40),
                _master(D23, 23.2, "2026-10-16T20:49:59", "Oct 16 20:49 · 23.2 °C", 1, 502, 90)],
    "captures": [
        {"date": "2026-10-15", "object_dir": "M 72", "slugs": ["m72"], "frames": 295,
         "temp_min": 14.4, "temp_max": 24.8, "dark_ref": D24, "dark_refs": [D24],
         "dark_labels": ["Oct 15 19:28 · 24.9 °C"], "dark_temp_c": 24.9,
         "dark_gap_c": 10.5, "dark_link": "confirmed", "dark_rule": "v2",
         "lights_rel": "Images/M 72/lights"},
        {"date": "2026-10-15", "object_dir": "C 6", "slugs": ["ngc-6543"], "frames": 70,
         "temp_min": 11.2, "temp_max": 13.6, "dark_ref": D13, "dark_refs": [D13],
         "dark_labels": ["Oct 15 21:52 · 13.9 °C"], "dark_temp_c": 13.9,
         "dark_gap_c": 2.7, "dark_link": "confirmed", "dark_rule": "v2",
         "lights_rel": "Images/C 6/lights"},
        {"date": "2026-10-16", "object_dir": "C 6", "slugs": ["ngc-6543"], "frames": 205,
         "temp_min": 13.7, "temp_max": 23.3, "dark_ref": D23, "dark_refs": [D23, D13],
         "dark_labels": ["Oct 16 20:49 · 23.2 °C", "Oct 15 21:52 · 13.9 °C"],
         "dark_temp_c": 23.2, "dark_gap_c": 6.7, "dark_link": "confirmed",
         "dark_rule": "v2", "lights_rel": "Images/C 6/lights"},
    ],
}
DWARF = {"device": "DWARF 3", "label": "DwarfLab Dwarf 3", "nickname": None,
         "retired": False, "preset": "dwarf_3", "model": "DwarfLab Dwarf 3",
         "serial": None, "darks_applied_on_device": False,
         "totals": {"integration_min": 3.5, "sessions": 1, "nights": 1, "objects": 1,
                    "first_capture": "2026-05-30", "last_capture": "2026-05-30"},
         "objects": [{"slug": "m42", "id": "M42", "integration_min": 3.5, "frames": 14,
                      "session_count": 1}],
         "masters": [], "captures": [
             {"date": "2026-05-30", "object_dir": "M42", "slugs": ["m42"], "frames": 14,
              "temp_min": None, "temp_max": None, "dark_ref": None, "dark_refs": [],
              "dark_labels": [], "lights_rel": "Images/M42/lights"}]}
OLD = dict(DWARF, device="S30_0ld", label="Old S30", retired=True, model="ZWO Seestar S30",
           objects=[], captures=[], totals=dict(DWARF["totals"], last_capture="2025-01-01"))


def _page(qtbot, devices=None):
    from m110.ui.pages.devices import DevicesPage
    pool = [S50, DWARF, OLD] if devices is None else devices
    page = DevicesPage(devices_data=[dict(d) for d in pool])
    qtbot.addWidget(page)
    return page


def _rows(table, col):
    return [table.item(r, col).text() for r in range(table.rowCount())]


def _row_of(table, col, text):
    return next(r for r in range(table.rowCount()) if table.item(r, col).text() == text)


def _selected(table):
    return sorted(i.row() for i in table.selectionModel().selectedRows())


def test_the_list_and_a_device_detail(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    page = _page(qtbot)
    assert _rows(page.device_list, 0) == ["ZWO Seestar S50 · c0ffee00", "DwarfLab Dwarf 3"]
    page.show_retired.setChecked(True)                  # retired shown only on request
    assert "Old S30" in _rows(page.device_list, 0)
    page.show_retired.setChecked(False)
    assert "ZWO Seestar S50 · c0ffee00" in page._heading.text()
    assert "3 h 10 m over 2 nights, 2 objects" in page._heading.text()
    assert _rows(page.objects_table, 0) == ["M72", "NGC 6543"]
    # darks named the same way in both tables
    assert _rows(page.library_table, 0) == ["Oct 15 19:28 · 24.9 °C", "Oct 15 21:52 · 13.9 °C",
                                            "Oct 16 20:49 · 23.2 °C"]
    cells = _rows(page.captures_table, 4)
    assert "Oct 15 19:28 · 24.9 °C · Δ10.5 ⚠" in cells and "2 darks · Δ6.7 ⚠" in cells
    assert sorted(page.level_chart.points()) == [(13.9, 480.0), (23.2, 502.0), (24.9, 512.0)]
    page.resize(1000, 900)
    page.level_chart.grab()                               # paints without raising

    page.select_device("DWARF 3")                         # no library, no dark link
    assert page._lib_sec.isHidden() and page._health_sec.isHidden()
    assert page.captures_table.isColumnHidden(4)


def test_selecting_a_capture_highlights_its_darks_and_back(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    page = _page(qtbot)
    lib, caps = page.library_table, page.captures_table
    r = _row_of(caps, 0, "2026-10-16")                    # the run that switched darks
    caps.selectRow(r)
    assert sorted(_rows(lib, 0)[i] for i in _selected(lib)) == [
        "Oct 15 21:52 · 13.9 °C", "Oct 16 20:49 · 23.2 °C"]
    assert _selected(caps) == [r]                         # no ping-pong back
    lib.selectRow(_row_of(lib, 0, "Oct 15 21:52 · 13.9 °C"))
    assert sorted(caps.item(i, 0).text() for i in _selected(caps)) == [
        "2026-10-15", "2026-10-16"]                       # both captures it served
    assert all(caps.item(i, 1).text() == "C 6" for i in _selected(caps))


def test_reveal_menus(tmp_path, monkeypatch, qtbot):
    from m110 import config
    from m110.ui.pages import devices as page_mod
    seed_root(tmp_path, monkeypatch)
    revealed = []
    monkeypatch.setattr(page_mod, "reveal_in_manager", lambda p: revealed.append(str(p)))
    page = _page(qtbot)
    lib, caps = page.library_table, page.captures_table

    menu, acts = page._library_menu(_row_of(lib, 0, "Oct 15 21:52 · 13.9 °C"))
    assert acts["reveal"].text() == page_mod.reveal_label() and acts["reveal"].isEnabled()
    # the capture with two darks offers each, by label; plus its lights + the object
    r = _row_of(caps, 0, "2026-10-16")
    menu, acts = page._capture_menu(r)
    dark_acts = {k[1]: a for k, a in acts.items() if isinstance(k, tuple)}
    assert [a.text() for a in dark_acts.values()] == ["Oct 16 20:49 · 23.2 °C",
                                                      "Oct 15 21:52 · 13.9 °C"]
    page._run_capture_action(r, dark_acts[D13], acts)
    page._run_capture_action(r, acts["lights"], acts)
    opened = []
    page.open_object.connect(opened.append)
    page._run_capture_action(r, acts["open"], acts)
    root = str(config.DATA_ROOT)
    assert revealed == [f"{root}/Calibration/S50_c0ffee00/darks/{D13}",
                        f"{root}/Images/C 6/lights"]
    assert opened == ["ngc-6543"]


def test_identity_edits_save_to_the_registry(tmp_path, monkeypatch, qtbot):
    from m110 import devices
    seed_root(tmp_path, monkeypatch)
    page = _page(qtbot)
    assert not page.save_btn.isEnabled() and not page.revert_btn.isEnabled()
    page.nickname.setText("Backyard")
    assert page.save_btn.isEnabled()
    page.revert_btn.click()
    assert page.nickname.text() == "" and not page.save_btn.isEnabled()
    page.nickname.setText("Backyard")
    page.save_btn.click()
    assert devices.load_registry() == {"S50_c0ffee00": {"nickname": "Backyard"}}
    assert _rows(page.device_list, 0)[0] == "Backyard"
    page.retired.setChecked(True)
    page.save_btn.click()                                 # retired → leaves the list
    assert "Backyard" not in _rows(page.device_list, 0)
    assert devices.load_registry()["S50_c0ffee00"]["retired"] is True


def test_double_clicks_open_the_object_out_of_the_handler(tmp_path, monkeypatch, qtbot, qapp):
    seed_root(tmp_path, monkeypatch)
    page = _page(qtbot)
    opened = []
    page.open_object.connect(opened.append)
    t = page.objects_table
    t.itemDoubleClicked.emit(t.item(_row_of(t, 0, "M72"), 0))
    c = page.captures_table
    c.itemDoubleClicked.emit(c.item(_row_of(c, 1, "M 72"), 0))
    assert opened == []                                   # deferred…
    qapp.processEvents()
    assert opened == ["m72", "m72"]


def test_empty_state_and_reload_keep_the_selection(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    empty = _page(qtbot, devices=[])
    assert not empty._empty.isHidden() and empty._scroll.isHidden()
    page = _page(qtbot)
    page.select_device("DWARF 3")
    page.reload()
    assert page._current["device"] == "DWARF 3"


def test_devices_is_the_last_rail_page(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    try:
        assert win.NAV[-1] == "Devices" and win.pages[-1] is win.devices
        assert win._devices_index == len(win.NAV) - 1
        assert not hasattr(win, "devices_action")
    finally:
        win.deleteLater(); qapp.processEvents()


def test_dark_cells_and_device_columns(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.widgets import dark_gap_item
    it = dark_gap_item(S50["captures"][0])
    assert it.text() == "Oct 15 19:28 · 24.9 °C · Δ10.5 ⚠" and "confirmed" in it.toolTip()
    # a plain session row (no labels) is named the same way, from its filenames
    plain = {k: v for k, v in S50["captures"][0].items() if k != "dark_labels"}
    assert dark_gap_item(plain).text() == it.text()
    assert dark_gap_item({"dark_ref": None}).text() == "—"
    from m110.ui.pages.sessions import _COLS
    assert _COLS[-2:] == ["Device", "Dark"]


def test_a_rollup_from_an_older_version_does_not_crash_launch(tmp_path, monkeypatch, qapp):
    """The window builds the Devices page before the launch Sync rewrites
    derived/devices.json — so the page must read a rollup written by the
    previous version (#169's: no totals / objects / identity keys). A raw
    d["totals"] crashed launch on the first run after upgrading (2026-10-21)."""
    import json
    from m110 import config, derived
    seed_root(tmp_path, monkeypatch)
    old = {"devices": [{"device": "S50_15e7e390", "label": "ZWO Seestar S50 · 15e7e390",
                        "darks_applied_on_device": True,
                        "masters": [{"tier": "darks", "file": D13, "temp_c": 13.9,
                                     "made": "2026-10-15T21:52:39", "captures": 1}],
                        "captures": [{"date": "2026-10-15", "object_dir": "C 6",
                                      "slugs": ["ngc-6543"], "frames": 70,
                                      "dark_ref": D13, "dark_gap_c": 2.7}]},
                       {"label": "an entry with no device key"}]}
    config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (config.DERIVED_DIR / "devices.json").write_text(json.dumps(old))
    (d,) = derived.load_devices()
    assert d["totals"]["last_capture"] is None and d["objects"] == []
    from m110.ui.main import MainWindow
    win = MainWindow()                                   # used to raise KeyError
    win._ready = False
    try:
        assert win.devices.device_list.rowCount() == 1
        assert win.devices.library_table.rowCount() == 1
    finally:
        win.deleteLater(); qapp.processEvents()

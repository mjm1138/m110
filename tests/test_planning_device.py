"""Planning plans for a real telescope: the active device (per user, like the
active site), its preset limits + the user's per-device overrides from
devices.toml, the legacy profiles/device.toml as a fallback — and both pages'
controls for it. Temp fixtures only."""
import json

import pytest

from m110 import config, devices, fieldguide
from m110 import planning_config as pc
from tests._helpers import seed_root

S50, DWARF, OLD = "S50_15e7e390", "DWARF 3", "S30_0ld"


def _devices_json(*entries):
    """A minimal derived/devices.json: (key, label, retired) — most recent first."""
    config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (config.DERIVED_DIR / "devices.json").write_text(json.dumps({"devices": [
        {"device": k, "label": lab, "retired": ret} for k, lab, ret in entries]}))


def test_device_for_is_the_preset_plus_the_users_overrides(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    s50 = pc.device_for(S50)
    assert (s50.start_alt_ceiling_deg, s50.ceiling_is_hard) == (78.0, True)
    assert s50.name == "ZWO Seestar S50 · 15e7e390"
    dwarf = pc.device_for(DWARF)
    assert (dwarf.start_alt_ceiling_deg, dwarf.ceiling_is_hard) == (80.0, False)
    devices.save_device(S50, nickname="Backyard",
                        planning={"start_alt_ceiling_deg": 75.0, "gain": 100})
    s50 = pc.device_for(S50)
    assert (s50.name, s50.start_alt_ceiling_deg, s50.gain) == ("Backyard", 75.0, 100)
    assert s50.max_exposure_s == 30                       # untouched → preset
    assert pc.DEVICE_PRESETS["seestar_s50"].start_alt_ceiling_deg == 78.0   # not mutated


def test_the_active_device_follows_the_user_then_recency(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    assert pc.active_device_key() is None
    _devices_json((DWARF, "DwarfLab Dwarf 3", False), (S50, "S50", False),
                  (OLD, "Old", True))
    assert [d["device"] for d in pc.planning_devices()] == [DWARF, S50]   # no retired
    assert pc.active_device_key() == DWARF                # most recent by default
    pc.set_active_device(S50)
    assert pc.active_device_key() == S50
    pc.set_active_device(OLD)                             # retired → not plannable
    assert pc.active_device_key() == DWARF


def test_load_device_resolves_active_then_legacy_then_defaults(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    assert pc.load_device().name == "ZWO Seestar S50"     # nothing known → S50
    legacy = pc.profile_path(pc.LEGACY_DEVICE_PROFILE)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('[device]\nname = "Hand-written"\nstart_alt_ceiling_deg = 70.0\n')
    assert pc.load_device().start_alt_ceiling_deg == 70.0
    assert "device" not in pc.list_profiles()             # never offered as a site
    _devices_json((DWARF, "DwarfLab Dwarf 3", False))
    dev = pc.load_device()                                # the active telescope wins
    assert (dev.name, dev.start_alt_ceiling_deg, dev.ceiling_is_hard) == \
        ("DwarfLab Dwarf 3", 80.0, False)
    assert pc.load_device(path=legacy).name == "Hand-written"   # explicit path


def test_a_field_guide_names_the_telescope(tmp_path, monkeypatch):
    from datetime import date
    seed_root(tmp_path, monkeypatch)
    md = fieldguide.render_markdown(pc.load_site(), date(2026, 10, 21),
                                    {"entries": [], "device": "Backyard"})
    assert "**Telescope:** Backyard" in md


# ── the two pages ─────────────────────────────────────────────────────────────

pytest.importorskip("PySide6")


def test_planning_page_offers_a_telescope_only_when_there_is_a_choice(
        tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    from m110 import prioritize
    monkeypatch.setattr(prioritize, "load_contexts", lambda *a, **k: None)
    _devices_json((S50, "S50", False))
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    qtbot.addWidget(page)
    assert page.device_picker.isHidden()
    _devices_json((DWARF, "DwarfLab Dwarf 3", False), (S50, "S50", False))
    page.reload()
    assert not page.device_picker.isHidden() and page.device_picker.currentData() == DWARF
    page.device_picker.setCurrentIndex(page.device_picker.findData(S50))
    assert pc.active_device_key() == S50


def test_devices_page_sets_the_planning_telescope_and_its_limits(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _devices_json((DWARF, "DwarfLab Dwarf 3", False), (S50, "S50", False))
    from tests.test_ui_devices import S50 as S50_ROLLUP, _page
    page = _page(qtbot, devices=[dict(S50_ROLLUP, device=S50, label="S50")])
    assert "another telescope" in page.planning_state.text()
    told = []
    page.devices_changed.connect(lambda: told.append(True))
    page.use_for_planning.click()
    assert told                                  # the shell re-reads Planning's picker
    assert pc.active_device_key() == S50 and page.use_for_planning.isHidden()
    assert page.ceiling.value() == 78.0 and not page.limits_defaults_btn.isEnabled()
    page.ceiling.setValue(74.0)
    page.gain.setValue(120)
    page.limits_save_btn.click()
    assert devices.load_registry()[S50]["planning"] == {
        "start_alt_ceiling_deg": 74.0, "gain": 120}       # only what differs
    assert pc.load_device().start_alt_ceiling_deg == 74.0
    page.limits_defaults_btn.click()
    page.limits_save_btn.click()
    assert "planning" not in devices.load_registry().get(S50, {})


def test_a_telescope_chosen_on_devices_reaches_planning(tmp_path, monkeypatch, qapp):
    """Found in the 2026-10-27 GUI pass: "Use for planning" (and a rename) on the
    Devices page changed the setting, but Planning's picker kept showing the old
    telescope — while its ranking and night plan already used the new one."""
    seed_root(tmp_path, monkeypatch)
    from m110 import prioritize
    monkeypatch.setattr(prioritize, "load_contexts", lambda *a, **k: None)
    _devices_json((S50, "S50", False), (DWARF, "DwarfLab Dwarf 3", False))
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    try:
        assert win.planning.device_picker.currentData() == S50     # most recent
        win.devices.select_device(DWARF)
        win.devices.use_for_planning.click()
        qapp.processEvents()
        assert win.planning.device_picker.currentData() == DWARF
        # a rename shows in the picker too
        win.devices.select_device(S50)
        win.devices.nickname.setText("Backyard S50")
        win.devices.save_btn.click()
        qapp.processEvents()
        labels = [win.planning.device_picker.itemText(i)
                  for i in range(win.planning.device_picker.count())]
        assert "Backyard S50" in labels
    finally:
        win.deleteLater(); qapp.processEvents()

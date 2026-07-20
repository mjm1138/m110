"""Offscreen wiring test for the Preferences dialog.

The dialog is the write-path for several settings whose *engine* halves are
tested but whose *wiring* was not (a control that silently stopped persisting
would be invisible to the suite). Each test toggles a control and asserts the
setting landed. Temp store + settings via `tests/_helpers.seed_root`; the
`qapp` fixture comes from pytest-qt.
"""
import pytest

pytest.importorskip("PySide6")

from m110 import config, hints, ingest, launch, processing, updates  # noqa: E402
from m110.ui import theme  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _prefs():
    from m110.ui.preferences import PreferencesDialog
    return PreferencesDialog()


def test_workflow_toggle_persists(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        enabled = [wid for wid, cb in d._wf_checks.items() if cb.isEnabled()]
        assert enabled, "expected at least one enabled workflow (Siril)"
        for cb in d._wf_checks.values():
            if cb.isEnabled():
                cb.setChecked(False)         # fires _save_workflows
        assert config.get_setting(processing.SETTING_KEY) == []
        d._wf_checks[enabled[0]].setChecked(True)
        assert enabled[0] in config.get_setting(processing.SETTING_KEY)
    finally:
        d.deleteLater(); qapp.processEvents()


def test_siril_path_override_persists_and_clears(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        d._siril_edit.setText("/opt/Siril.app")
        d._siril_edit.editingFinished.emit()
        assert (config.get_setting(launch.APP_PATHS_SETTING) or {}).get("siril") \
            == "/opt/Siril.app"
        d._siril_edit.setText("")            # clearing removes the override
        d._siril_edit.editingFinished.emit()
        assert "siril" not in (config.get_setting(launch.APP_PATHS_SETTING) or {})
    finally:
        d.deleteLater(); qapp.processEvents()


def test_finished_hints_persist(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        d._finished_edit.setText("processed, final, keeper")
        d._intermediate_edit.setText("starless, scratch")
        d._finished_edit.editingFinished.emit()
        d._intermediate_edit.editingFinished.emit()
        cur = hints.get_hints()
        assert "keeper" in cur["finished"] and "scratch" in cur["intermediate"]
        assert hints.is_finished_name("M42_keeper.png")   # read live at classify time
    finally:
        d.deleteLater(); qapp.processEvents()


def test_sub_previews_toggle_persists(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        assert not config.get_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, False)
        d._sub_previews_cb.setChecked(True)
        assert config.get_setting(ingest.IMPORT_SUB_PREVIEWS_KEY) is True
    finally:
        d.deleteLater(); qapp.processEvents()


def test_update_check_toggle_persists(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        d._update_cb.setChecked(False)
        assert updates.check_enabled() is False
        d._update_cb.setChecked(True)
        assert updates.check_enabled() is True
    finally:
        d.deleteLater(); qapp.processEvents()


def test_theme_combo_applies_mode(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(theme, "set_mode", lambda m: calls.append(m))
    d = _prefs()                             # initial setCurrentIndex is pre-connect
    try:
        d._theme_combo.setCurrentIndex(d._theme_combo.findData("dark"))
        assert calls and calls[-1] == "dark"
    finally:
        d.deleteLater(); qapp.processEvents()

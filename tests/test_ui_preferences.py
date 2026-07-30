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


# ── AI assistant section ─────────────────────────────────────────────────────

def test_assistant_section_reports_not_connected(tmp_path, monkeypatch, qapp):
    """The status line is the only feedback the user gets, so it must be right."""
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "desktop_config_path",
                        lambda: tmp_path / "claude_desktop_config.json")
    d = _prefs()
    try:
        assert "Not connected" in d._assistant_status.text()
        assert d._connect_btn.text().startswith("Connect")
        assert not d._disconnect_btn.isEnabled()
    finally:
        d.deleteLater()


def test_assistant_section_reports_connected(tmp_path, monkeypatch, qapp):
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(cc, "desktop_config_path", lambda: cfg)
    cc.write_desktop_config(cfg)
    d = _prefs()
    try:
        assert "Connected" in d._assistant_status.text()
        assert d._connect_btn.text().startswith("Update")
        assert d._disconnect_btn.isEnabled()
    finally:
        d.deleteLater()


def test_connect_requires_confirmation_and_writes_nothing_on_cancel(
        tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QMessageBox
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(cc, "desktop_config_path", lambda: cfg)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Cancel)

    d = _prefs()
    try:
        d._connect_desktop()
        assert not cfg.exists(), "cancelling must not touch another app's config"
    finally:
        d.deleteLater()


def test_connect_writes_after_confirmation(tmp_path, monkeypatch, qapp):
    import json
    from PySide6.QtWidgets import QMessageBox
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(cc, "desktop_config_path", lambda: cfg)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    d = _prefs()
    try:
        d._connect_desktop()
        entry = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["m110"]
        assert entry["env"]["M110_DATA_ROOT"] == str(config.DATA_ROOT)
        assert "Connected" in d._assistant_status.text()   # status refreshed
    finally:
        d.deleteLater()


def test_connect_surfaces_a_broken_config_instead_of_clobbering_it(
        tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QMessageBox
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ broken", encoding="utf-8")
    monkeypatch.setattr(cc, "desktop_config_path", lambda: cfg)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))

    d = _prefs()
    try:
        d._connect_desktop()
        assert warned, "the user must be told, not silently ignored"
        assert cfg.read_text(encoding="utf-8") == "{ broken"
    finally:
        d.deleteLater()


def test_copy_cli_command_puts_it_on_the_clipboard(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QApplication, QMessageBox
    seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = _prefs()
    try:
        d._copy_cli_command()
        assert "claude mcp add m110" in QApplication.clipboard().text()
    finally:
        d.deleteLater()


def test_direct_save_toggle_persists(tmp_path, monkeypatch, qapp):
    from m110.assistant.tools.saving import SETTING_DIRECT_SAVE, direct_save_enabled
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        assert direct_save_enabled() is False          # conservative default
        d._direct_save_cb.setChecked(True)
        assert config.get_setting(SETTING_DIRECT_SAVE) is True
        assert direct_save_enabled() is True
    finally:
        d.deleteLater()

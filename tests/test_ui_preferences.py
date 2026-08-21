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
        # Asserted through the reader, not the stored shape: the setting is a
        # {id: bool} map so a workflow added later can tell "never asked" from
        # "switched off", and the test should not re-pin the storage format.
        assert processing.enabled_workflow_ids() == []
        d._wf_checks[enabled[0]].setChecked(True)
        assert enabled[0] in processing.enabled_workflow_ids()
    finally:
        d.deleteLater(); qapp.processEvents()


@pytest.mark.parametrize("tool_id", launch.tool_ids())
def test_tool_path_override_persists_and_clears(tool_id, tmp_path, monkeypatch, qapp):
    """Parametrized over the registry, so a newly registered tool is covered
    without anyone remembering to add a case."""
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        edit = d._tool_edits[tool_id]
        edit.setText(f"/opt/{tool_id}.app")
        edit.editingFinished.emit()
        assert (config.get_setting(launch.APP_PATHS_SETTING) or {}).get(tool_id) \
            == f"/opt/{tool_id}.app"
        edit.setText("")                     # clearing removes the override
        edit.editingFinished.emit()
        assert tool_id not in (config.get_setting(launch.APP_PATHS_SETTING) or {})
    finally:
        d.deleteLater(); qapp.processEvents()


def test_one_tools_path_does_not_clobber_anothers(tmp_path, monkeypatch, qapp):
    """`_save_app_paths` writes every row at once, so a per-row save could drop a
    sibling's override. And each Browse button must carry its own tool id — a bare
    closure over the loop variable would give them all the last one."""
    seed_root(tmp_path, monkeypatch)
    ids = launch.tool_ids()
    if len(ids) < 2:
        pytest.skip("needs two registered tools")
    d = _prefs()
    try:
        for tool_id in ids:
            d._tool_edits[tool_id].setText(f"/opt/{tool_id}")
            d._tool_edits[tool_id].editingFinished.emit()
        saved = config.get_setting(launch.APP_PATHS_SETTING) or {}
        assert saved == {t: f"/opt/{t}" for t in ids}
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
        assert "isn't set up yet" in d._assistant_status.text()
        assert d._connect_btn.text().startswith("Set up")
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
        assert "is set up" in d._assistant_status.text()
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
        assert "is set up" in d._assistant_status.text()   # status refreshed
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


def test_connection_details_copy_puts_the_config_on_the_clipboard(
        tmp_path, monkeypatch, qapp):
    """Copying moved out of a Claude-Code-only button into the client-neutral
    details dialog, where each shape has its own Copy."""
    from PySide6.QtWidgets import QApplication, QTabWidget
    from m110.ui.mcp_details_dialog import ConnectionDetailsDialog
    seed_root(tmp_path, monkeypatch)
    dlg = ConnectionDetailsDialog()
    try:
        tabs = dlg.findChildren(QTabWidget)[0]
        tabs.widget(0)._on_copy()                      # JSON config
        assert '"mcpServers"' in QApplication.clipboard().text()
        tabs.widget(2)._on_copy()                      # Claude Code
        assert "claude mcp add m110" in QApplication.clipboard().text()
    finally:
        dlg.deleteLater()


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


# ── the assistant section is client-neutral ──────────────────────────────────

def test_no_explanatory_text_is_cut_off(tmp_path, monkeypatch, qapp):
    """Preferences grew a group at a time until it outgrew a laptop screen.
    Two failure modes, both of which showed up as sliced-off text rather than
    an obviously-too-small window:

    * vertical — Qt squeezes word-wrapped labels below their heightForWidth;
    * horizontal — an *unwrapped* label's single-line width becomes the
      dialog's minimum width, so everything else is clipped at the right edge.

    The scroll area fixes the first; wrapping every explanatory label fixes the
    second. Both are asserted, because the second is invisible to a
    heightForWidth check.
    """
    from PySide6.QtWidgets import QLabel, QScrollArea
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        d.show()
        for _ in range(4):
            qapp.processEvents()

        clipped = [lbl.text() for lbl in d.findChildren(QLabel)
                   if lbl.text() and lbl.wordWrap() and lbl.width() > 0
                   and lbl.heightForWidth(lbl.width()) > lbl.height()]
        assert not clipped, f"text cut off vertically: {clipped}"

        scroll = d.findChildren(QScrollArea)[0]
        need = scroll.widget().minimumSizeHint().width()
        assert need <= scroll.viewport().width(), (
            f"content needs {need}px in a {scroll.viewport().width()}px viewport — "
            "something isn't wrapping")

        wide = [lbl.text()[:60] for lbl in d.findChildren(QLabel)
                if lbl.text() and not lbl.wordWrap()
                and lbl.sizeHint().width() > scroll.viewport().width()]
        assert not wide, f"unwrapped labels force the dialog wide: {wide}"
    finally:
        d.deleteLater()


def test_assistant_section_does_not_present_itself_as_claude_only(
        tmp_path, monkeypatch, qapp):
    """The server is plain MCP over stdio; the UI shouldn't imply one vendor."""
    from PySide6.QtWidgets import QLabel
    seed_root(tmp_path, monkeypatch)
    d = _prefs()
    try:
        text = " ".join(lbl.text() for lbl in d.findChildren(QLabel) if lbl.text())
        assert "MCP" in text
        assert "any MCP-compatible client" in text.lower() or \
               "Works with any MCP" in text
        # Claude may be named as a convenience, never as the only route.
        assert d._details_btn.isEnabled()
    finally:
        d.deleteLater()


def test_connection_details_cover_the_shapes_clients_ask_for(
        tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QTabWidget
    from m110.ui.mcp_details_dialog import ConnectionDetailsDialog
    seed_root(tmp_path, monkeypatch)
    dlg = ConnectionDetailsDialog()
    try:
        tabs = dlg.findChildren(QTabWidget)[0]
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        assert labels == ["JSON config", "Command", "Claude Code"]
    finally:
        dlg.deleteLater()


def test_connection_details_are_client_neutral_and_pin_the_root(tmp_path, monkeypatch):
    from m110.assistant import client_config as cc
    seed_root(tmp_path, monkeypatch)
    d = cc.connection_details()
    assert d["transport"] == "stdio"
    assert d["env"]["M110_DATA_ROOT"] == str(config.DATA_ROOT)
    # The JSON block is the generic mcpServers format, not a vendor's own schema.
    import json as _json
    assert list(_json.loads(d["json"])["mcpServers"]) == ["m110"]
    assert d["command"] and isinstance(d["args"], list)

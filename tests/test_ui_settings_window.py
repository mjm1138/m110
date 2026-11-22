"""The Settings window (UI Phase 8 · E): a non-modal, single-instance window with a
pane bar, instant apply and no Close/OK/Save — plus the File menu's Back Up Now.

Every control is driven: each pane button is clicked, Change… is clicked, the
menu actions are triggered. Settings are sealed by conftest; `seed_root` gives
each test its own store.
"""
import pytest

pytest.importorskip("PySide6")

from m110 import backup, config  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _settings(**kw):
    from m110.ui.preferences import SettingsWindow
    return SettingsWindow(**kw)


def _window(qapp):
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    return win


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    for key in ("settings_pane", "data_root", backup.SETTING_DESTINATIONS,
                backup.SETTING_DEST):
        config.save_setting(key, None)
    yield


def _close(w, qapp):
    w.close()
    qapp.processEvents()


# ── the pane bar ─────────────────────────────────────────────────────────────

def test_every_pane_button_shows_its_pane_and_titles_the_window(qapp):
    from m110.ui.preferences import PANES
    w = _settings()
    try:
        assert [b.text() for b in w._tabs.values()] == [t for _k, t, _i in PANES]
        assert w.current_pane() == "general"           # the first time
        for key, title, _icon in PANES:
            w._tabs[key].click()
            assert w.current_pane() == key
            assert w.windowTitle() == title
            assert w._tabs[key].isChecked()
            shown = [k for k, page in w._panes.items() if page.isVisibleTo(w)]
            assert shown == [key]
            assert config.get_setting("settings_pane") == key
    finally:
        _close(w, qapp)


def test_reopens_on_the_last_pane(qapp):
    w = _settings()
    w._tabs["tools"].click()
    _close(w, qapp)
    w = _settings()
    try:
        assert w.current_pane() == "tools"
    finally:
        _close(w, qapp)


def test_the_window_fits_each_pane(qapp):
    """Mac settings windows resize to the pane; a short pane isn't padded out
    to the tallest one."""
    w = _settings()
    try:
        w.show()
        qapp.processEvents()
        cap = int(w.screen().availableGeometry().height() * 0.85)
        heights = {}
        for key in ("appearance", "backup"):
            w._tabs[key].click()
            qapp.processEvents()
            heights[key] = w.needed_height()
            assert w.height() == min(max(heights[key], w.minimumHeight()), cap)
        assert heights["appearance"] < heights["backup"]
        # Switching the backup segment refits too (the cloud slot is taller).
        w._backup._seg_btns[backup.SLOT_CLOUD].click()
        qapp.processEvents()
        assert w.needed_height() > heights["backup"]
        assert w.height() == min(max(w.needed_height(), w.minimumHeight()), cap)
    finally:
        _close(w, qapp)


def test_there_is_no_ok_close_save_or_cancel(qapp):
    """Changes apply at once; the window closes with ⌘W / the close box."""
    from PySide6.QtWidgets import QPushButton
    w = _settings()
    try:
        texts = {b.text() for b in w.findChildren(QPushButton)}
        assert not texts & {"OK", "Close", "Save", "Cancel", "Apply"}
    finally:
        _close(w, qapp)


def test_restyle_retints_the_pane_icons(qapp):
    w = _settings()
    try:
        before = w._tabs["general"].icon().cacheKey()
        w._restyle()
        assert w._tabs["general"].icon().cacheKey() != before
    finally:
        _close(w, qapp)


def test_closing_tears_down_the_backup_workers(qapp, monkeypatch):
    w = _settings()
    torn = []
    monkeypatch.setattr(w._backup, "teardown", lambda: torn.append(1))
    w.show()
    _close(w, qapp)
    assert torn == [1]


# ── General › Data folder ────────────────────────────────────────────────────

def test_change_data_folder_saves_at_once_and_says_when(tmp_path, monkeypatch, qapp):
    chosen = tmp_path / "elsewhere"
    chosen.mkdir()
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(chosen))
    w = _settings()
    try:
        assert not w._root_note.isVisibleTo(w)
        w._root_btn.click()
        assert config.get_setting("data_root") == str(chosen)
        assert (chosen / ".m110_internal_data").is_dir()     # seeded, ready on restart
        assert w._root_edit.text() == str(chosen)
        assert w._root_note.isVisibleTo(w)
        assert "until you restart" in w._root_note.text()
    finally:
        _close(w, qapp)


def test_choosing_the_current_folder_changes_nothing(monkeypatch, qapp):
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(config.DATA_ROOT))
    w = _settings()
    try:
        w._root_btn.click()
        assert config.get_setting("data_root") is None
        assert not w._root_note.isVisibleTo(w)
    finally:
        _close(w, qapp)


def test_tool_browse_buttons_save_their_own_tool(tmp_path, monkeypatch, qapp):
    from m110 import launch
    w = _settings()
    try:
        for tool_id, btn in w._tool_browse.items():
            monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName",
                                lambda *a, t=tool_id, **k: (f"/opt/{t}", ""))
            btn.click()
        saved = config.get_setting(launch.APP_PATHS_SETTING) or {}
        assert saved == {t: f"/opt/{t}" for t in w._tool_browse}
    finally:
        _close(w, qapp)


# ── the main window: one Settings window, Back Up Now ───────────────────────

def test_settings_is_one_window_and_opens_at_a_pane(qapp):
    win = _window(qapp)
    try:
        win.prefs_action.trigger()
        first = win._settings_window
        assert first is not None and first.isVisible() and not first.isModal()
        win.prefs_action.trigger()
        assert win._settings_window is first           # brought forward, not a second
        win._show_settings("backup")
        assert first.current_pane() == "backup"
        first.close()
        qapp.processEvents()
        qapp.sendPostedEvents(None, 0)                  # deleteLater → destroyed
        qapp.processEvents()
        assert win._settings_window is None
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_close_window_reaches_the_settings_window(qapp, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    win = _window(qapp)
    try:
        assert (win.close_window_action.shortcutContext()
                == Qt.ShortcutContext.ApplicationShortcut)
        w = win._show_settings()
        monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: w))
        win.close_window_action.trigger()
        assert not w.isVisible()
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_back_up_now_with_nothing_set_up_opens_backup_settings(qapp):
    win = _window(qapp)
    try:
        assert win.backup_action.text() == "Back Up Now"
        win.backup_action.trigger()
        assert win._settings_window is not None
        assert win._settings_window.current_pane() == "backup"
        assert win._backup_worker is None
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_back_up_now_runs_every_configured_slot_in_turn(tmp_path, qapp, monkeypatch):
    """Both slots configured → both run, one at a time, through the same
    background queue as automatic backups — no dialog."""
    from m110.ui import main as main_mod
    started = []

    class _Stub:
        def __init__(self, slot, cancel, parent=None):
            self.slot = slot
            started.append(slot)
            self.done = self.failed = type("S", (), {"connect": lambda *_: None})()

        def start(self):
            pass

        def deleteLater(self):
            pass

    monkeypatch.setattr(main_mod, "_BackupBgWorker", _Stub)
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path / "b"))
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://bucket/m110")
    win = _window(qapp)
    try:
        win.backup_action.trigger()
        assert started == [backup.SLOT_LOCAL]
        assert win._backup_queue == [backup.SLOT_CLOUD]
        assert win._settings_window is None
        win.backup_action.trigger()                     # already running → no second run
        assert started == [backup.SLOT_LOCAL]
        win._on_auto_backup_done({"file_count": 3})     # first finishes → next starts
        assert started == [backup.SLOT_LOCAL, backup.SLOT_CLOUD]
        win._on_auto_backup_done({"file_count": 3})
        assert win._backup_worker is None and win._backup_queue == []
    finally:
        win._backup_worker = None
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_the_backup_nudge_opens_backup_settings(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tests._helpers import seed_capture
    seed_capture(config.DATA_ROOT)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert win._settings_window is not None
        assert win._settings_window.current_pane() == "backup"
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()

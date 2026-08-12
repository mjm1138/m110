"""Offscreen shell tests: the Help → Report a problem action, the backup nudge
(BETA §5), the menubar IA, the brand mark, and the status line. qapp comes from
pytest-qt."""
import pytest

pytest.importorskip("PySide6")

from m110 import config
from tests._helpers import seed_root, seed_capture


def _window(qapp):
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False    # neuter the deferred launch refresh + update-check threads
                          # (a leaked network QThread at teardown aborts the process)
    return win


def test_report_action_opens_dialog(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui import error_report
    built = []
    monkeypatch.setattr(error_report, "ErrorReportDialog",
                        lambda *a, **k: type("D", (), {"exec": lambda self: built.append(k)})())
    win = _window(qapp)
    try:
        assert win.report_action.text() == "Report a problem…"
        win._open_report()
        assert built and built[0].get("is_crash") is False
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_fires_once_when_captured(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                          # now there's something worth backing up
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        assert config.get_setting("backup_nudge_seen") in (None, False)
        win._maybe_backup_nudge()
        assert asked == [1]                     # nudged
        assert config.get_setting("backup_nudge_seen") is True
        win._maybe_backup_nudge()               # already seen → no second nudge
        assert asked == [1]
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_silent_when_backups_configured(tmp_path, monkeypatch, qapp):
    """Regression: a returning user who already set up backups must not be nudged."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                          # has captures…
    from m110 import backup
    config.save_setting(backup.SETTING_DEST, str(tmp_path / "dest"))  # …but backups configured
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert asked == []                      # already backing up → no nag
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_silent_without_captures(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)            # empty store — nothing captured
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert asked == []                      # nothing to lose → no nag
        assert config.get_setting("backup_nudge_seen") in (None, False)
    finally:
        win.deleteLater(); qapp.processEvents()


def test_launch_update_check_skipped_when_not_ready(tmp_path, monkeypatch, qapp):
    """Regression: the launch update-check must NOT spawn its network QThread when the
    window isn't `_ready` (tests/screenshots set _ready=False to neuter launch work) —
    a leaked network thread aborts the process at teardown (macOS crash dialog)."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)                 # _window sets _ready = False
    try:
        win._maybe_check_updates()
        assert win._update_worker is None
    finally:
        win.deleteLater(); qapp.processEvents()


# ---- menubar IA ----

def test_menubar_structure(tmp_path, monkeypatch, qapp):
    """One structure on every platform — the macOS MenuRoles do the hoisting, so
    there is no per-platform branch to drift."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        titles = [a.menu().title() for a in win.menuBar().actions() if a.menu()]
        assert titles == ["File", "View", "Library", "Tools", "Help"]
    finally:
        win.deleteLater(); qapp.processEvents()


def test_every_action_is_reachable_from_exactly_one_menu(tmp_path, monkeypatch, qapp):
    """Guards the re-home: an action must not be orphaned or listed twice."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        menus = [win.file_menu, win.view_menu, win.lib_menu,
                 win.tools_menu, win.help_menu]
        homes = {}
        for m in menus:
            for a in m.actions():
                if not a.isSeparator():
                    homes.setdefault(a, []).append(m.title())
        assert all(len(v) == 1 for v in homes.values())

        expected = [win.ingest_action, win.publish_action, win.quit_action,
                    win.refresh_action, win.add_object_action, win.fill_meta_action,
                    win.enrich_online_action, win.prep_action, win.backup_action,
                    win.restore_action, win.prefs_action, win.user_guide_action,
                    win.check_updates_action, win.report_action, win.about_action]
        assert all(a in homes for a in expected)
    finally:
        win.deleteLater(); qapp.processEvents()


def test_menu_roles_fold_into_the_macos_app_menu(tmp_path, monkeypatch, qapp):
    """Preferences / About / Quit must carry their roles — that hoisting is the whole
    reason one structure can read native on macOS as well as Windows and Linux."""
    from PySide6.QtGui import QAction
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        assert win.prefs_action.menuRole() == QAction.MenuRole.PreferencesRole
        assert win.about_action.menuRole() == QAction.MenuRole.AboutRole
        assert win.quit_action.menuRole() == QAction.MenuRole.QuitRole
    finally:
        win.deleteLater(); qapp.processEvents()


def test_no_separator_is_stranded_by_a_hoisted_action(tmp_path, monkeypatch, qapp):
    """A role action introduced by a separator leaves that separator behind as a
    dangling rule at the foot of the menu once macOS hoists it (Qt keeps it in the
    NSMenu, unhidden). Off macOS the separator is wanted — nothing is hoisted."""
    import sys
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        for menu, role_action in ((win.file_menu, win.quit_action),
                                  (win.tools_menu, win.prefs_action)):
            acts = menu.actions()
            before = acts[acts.index(role_action) - 1]
            assert before.isSeparator() is not (sys.platform == "darwin")
    finally:
        win.deleteLater(); qapp.processEvents()


def test_view_menu_drives_and_follows_the_nav_rail(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        assert [a.text() for a in win.view_actions] == win.NAV
        win.view_actions[2].trigger()                   # menu → rail
        assert win.nav.currentRow() == 2
        assert win.view_actions[2].isChecked()

        win.nav.setCurrentRow(4)                        # rail → menu
        assert win.view_actions[4].isChecked()
        assert not win.view_actions[2].isChecked()      # exclusive group
    finally:
        win.deleteLater(); qapp.processEvents()


def test_edit_lock_disables_the_view_menu(tmp_path, monkeypatch, qapp):
    """The journal-edit lock disables the rail; Ctrl+1..5 must not walk around it."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win._on_editing_changed(True)
        assert not win.nav.isEnabled()
        assert all(not a.isEnabled() for a in win.view_actions)
        win._on_editing_changed(False)
        assert all(a.isEnabled() for a in win.view_actions)
    finally:
        win.deleteLater(); qapp.processEvents()


# ---- brand mark + status line ----

def test_logo_sits_at_the_foot_of_the_nav_column(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        col = win.logo.parentWidget().layout()
        assert col.itemAt(col.count() - 1).widget() is win.logo
        assert col.indexOf(win.nav) < col.indexOf(win.logo)
    finally:
        win.deleteLater(); qapp.processEvents()


def test_logo_click_opens_about_out_of_the_mouse_handler(tmp_path, monkeypatch, qapp):
    """`clicked` fires from `mouseReleaseEvent`, so About must open *after* that C++
    handler returns — a modal exec() inside it is the 0.3.0b3 use-after-free."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    opened = []
    monkeypatch.setattr(win, "_open_about", lambda: opened.append(1))
    try:
        win.logo.clicked.emit()
        assert opened == []             # deferred…
        qapp.processEvents()
        assert opened == [1]            # …then opened
    finally:
        win.deleteLater(); qapp.processEvents()


def test_status_bar_shows_the_data_root_without_a_capture_count(tmp_path,
                                                                monkeypatch, qapp):
    """The captured/total ratio duplicated the Library's own stat row."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win._update_status()
        msg = win.statusBar().currentMessage()
        assert str(config.DATA_ROOT) in msg
        assert "captured" not in msg
        win._update_status("  ·  Syncing…")     # extras still append
        assert win.statusBar().currentMessage().endswith("Syncing…")
    finally:
        win.deleteLater(); qapp.processEvents()

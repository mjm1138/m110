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
        assert win.report_action.text() == "Report a Problem…"
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


def test_backup_nudge_silent_when_only_cloud_is_configured(tmp_path, monkeypatch, qapp):
    """A cloud-only user has backups too — "configured" means either slot."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110 import backup
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://bucket/m110")
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert asked == []
    finally:
        win.deleteLater(); qapp.processEvents()


class _FakeBgWorker:
    """Stands in for `_BackupBgWorker`: records which slot it was started for
    and lets the test deliver the result itself."""
    started: list = []

    def __init__(self, slot, cancel_event, parent=None):
        self.slot = slot
        self.done = self.failed = type("Sig", (), {"connect": lambda *_: None})()

    def start(self):
        _FakeBgWorker.started.append(self.slot)

    def isRunning(self):
        return False

    def deleteLater(self):
        pass


def _auto_window(qapp, monkeypatch, due):
    from m110 import backup
    import m110.ui.main as main_mod
    _FakeBgWorker.started = []
    monkeypatch.setattr(main_mod, "_BackupBgWorker", _FakeBgWorker)
    monkeypatch.setattr(backup, "due_for_auto_backup", lambda slot: slot in due)
    monkeypatch.setattr(backup, "due_for_scheduled_backup",
                        lambda slot, now=None: slot in due)
    return _window(qapp)


def test_auto_backup_runs_due_slots_one_at_a_time(tmp_path, monkeypatch, qapp):
    """Both slots due: local first, and cloud only once local has finished —
    the engine allows one run per process, so starting both would fail one."""
    seed_root(tmp_path, monkeypatch)
    from m110 import backup
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path), auto=True)
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://b/c", auto=True)
    win = _auto_window(qapp, monkeypatch, due={"local", "cloud"})
    try:
        win._maybe_auto_backup()
        assert _FakeBgWorker.started == ["local"]
        assert "Backing up to Local" in win.statusBar().currentMessage()

        win._maybe_auto_backup(scheduled=True)     # a tick mid-run starts nothing
        assert _FakeBgWorker.started == ["local"]

        win._on_auto_backup_done({"file_count": 7})
        assert _FakeBgWorker.started == ["local", "cloud"]

        win._on_auto_backup_done({"file_count": 3})
        assert "Backed up 3 files to Cloud" in win.statusBar().currentMessage()
        assert win._backup_worker is None and win._backup_queue == []
    finally:
        win.deleteLater(); qapp.processEvents()


def test_one_slot_failing_does_not_stop_the_other(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110 import backup
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path), auto=True)
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://b/c", auto=True)
    win = _auto_window(qapp, monkeypatch, due={"local", "cloud"})
    try:
        win._maybe_auto_backup()
        win._on_auto_backup_failed("offline")
        assert _FakeBgWorker.started == ["local", "cloud"]
        assert "Local backup skipped" in win.statusBar().currentMessage()
        win._on_auto_backup_done({"file_count": 1})
    finally:
        win.deleteLater(); qapp.processEvents()


def test_only_the_due_slot_runs(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110 import backup
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path), auto=True)
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://b/c", auto=True)
    win = _auto_window(qapp, monkeypatch, due={"cloud"})
    try:
        win._maybe_auto_backup(scheduled=True)
        assert _FakeBgWorker.started == ["cloud"]
        win._on_auto_backup_done({"file_count": 1})
        assert _FakeBgWorker.started == ["cloud"]
    finally:
        win.deleteLater(); qapp.processEvents()


def test_restore_offers_both_configured_slots(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110 import backup
    import m110.ui.restore_dialog as rd
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path / "l"))
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://b/c")
    seen = []
    monkeypatch.setattr(rd, "RestoreDialog",
                        lambda sources, parent=None: seen.append(sources) or
                        type("D", (), {"exec": lambda self: None})())
    win = _window(qapp)
    try:
        win._open_restore()
        assert seen == [[("Local", str(tmp_path / "l")), ("Cloud", "s3://b/c")]]
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
    there is no per-platform branch to drift. The Tools menu is gone (1.0)."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        titles = [a.menu().title() for a in win.menuBar().actions() if a.menu()]
        assert titles == ["File", "Edit", "View", "Object", "Library", "Window", "Help"]
    finally:
        win.deleteLater(); qapp.processEvents()


def _menus(win):
    return [win.file_menu, win.edit_menu, win.view_menu, win.object_menu,
            win.lib_menu, win.window_menu, win.help_menu]


def test_every_action_is_reachable_from_exactly_one_menu(tmp_path, monkeypatch, qapp):
    """Guards the re-home: an action must not be orphaned or listed twice."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        homes = {}
        for m in _menus(win):
            for a in m.actions():
                if not a.isSeparator():
                    homes.setdefault(a, []).append(m.title())
        assert all(len(v) == 1 for v in homes.values()), homes
        expected = [win.ingest_action, win.publish_action, win.backup_action,
                    win.restore_action, win.close_window_action, win.prefs_action,
                    win.quit_action, win.undo_action, win.redo_action,
                    win.copy_action, win.select_all_action, win.find_action,
                    *win.view_actions, *win.view_mode_actions.values(),
                    win.toggle_sidebar_action, win.toggle_inspector_action,
                    win.full_screen_action, *win.object_actions,
                    win.refresh_action, win.add_object_action, win.fill_meta_action,
                    win.enrich_online_action, win.prep_action,
                    win.media_cleanup_action, win.minimize_action, win.zoom_action,
                    win.bring_all_action, win.user_guide_action, win.report_action,
                    win.check_updates_action, win.about_action]
        missing = [a.text() for a in expected if a not in homes]
        assert not missing, missing
    finally:
        win.deleteLater(); qapp.processEvents()


def test_menu_labels_are_title_case_with_consistent_ellipses(tmp_path, monkeypatch, qapp):
    """Mac menus use title case; an ellipsis means "a dialog follows" and never
    trails a verb that acts at once."""
    import re
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
             "or", "the", "to", "with"}
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        for m in _menus(win):
            for a in m.actions():
                text = a.text().replace("&", "")
                if a.isSeparator() or not text or a.menu() is None and \
                        a in win.window_menu.actions()[5:]:
                    continue                       # window-list entries are titles
                words = re.findall(r"[A-Za-z][\w'-]*", text)
                for i, w in enumerate(words):
                    if w == "as" and i == 0:
                        continue                   # Finder's "as List" convention
                    if i and w.lower() in small:
                        continue
                    assert w[0].isupper() or w[0].isdigit(), f"{text!r} in {m.title()}"
                assert not text.endswith("...") and "  " not in text
    finally:
        win.deleteLater(); qapp.processEvents()


def test_menu_roles_fold_into_the_macos_app_menu(tmp_path, monkeypatch, qapp):
    """Settings / About / Check for Updates / Quit carry their roles — that hoisting
    is why one structure reads native on macOS as well as Windows and Linux."""
    from PySide6.QtGui import QAction
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        assert win.prefs_action.menuRole() == QAction.MenuRole.PreferencesRole
        assert win.about_action.menuRole() == QAction.MenuRole.AboutRole
        assert win.quit_action.menuRole() == QAction.MenuRole.QuitRole
        assert (win.check_updates_action.menuRole()
                == QAction.MenuRole.ApplicationSpecificRole)
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
        acts = win.file_menu.actions()
        before = acts[acts.index(win.prefs_action) - 1]
        assert before.isSeparator() is not (sys.platform == "darwin")
        assert acts[-1] is win.quit_action
    finally:
        win.deleteLater(); qapp.processEvents()


def test_view_menu_drives_and_follows_the_sidebar(tmp_path, monkeypatch, qapp):
    """Ctrl+1…8 are built from the same place list as the sidebar, in page indices —
    the section headers in the list must not shift which page a shortcut opens."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        assert [a.text() for a in win.view_actions] == win.NAV
        win.view_actions[2].trigger()                   # menu → sidebar
        assert win.current_page() == 2 == win._media_index
        assert win.nav.current_page() == 2
        assert win.view_actions[2].isChecked()
        assert win.header.title.text() == "Media"

        win.go_to(win._processing_index)                # sidebar → menu
        assert win.view_actions[win._processing_index].isChecked()
        assert not win.view_actions[2].isChecked()      # exclusive group
    finally:
        win.deleteLater(); qapp.processEvents()


def test_header_bar_shows_each_pages_own_controls(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win.go_to(win._catalog_index)
        assert win.header.current_controls() is win.catalog.header_controls
        assert win.header.title.text() == "Deep Sky"
        win.go_to(win._journal_index)
        assert win.header.current_controls() is win.journal.header_controls
        win.go_to(win._planning_index)
        assert win.header.current_controls() is None
        assert win.catalog.header_controls.isHidden()
    finally:
        win.deleteLater(); qapp.processEvents()


def test_sidebar_toggles_from_the_header_button(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        assert win.sidebar_visible()
        win.header.sidebar_btn.click()
        assert not win.sidebar_visible()
        win.header.sidebar_btn.click()
        assert win.sidebar_visible()
    finally:
        win.deleteLater(); qapp.processEvents()


def test_sidebar_counts_and_section_headers(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from m110.ui.sidebar import HEADER_ROLE
    root = seed_root(tmp_path, monkeypatch)
    from tests._helpers import seed_capture
    seed_capture(root)
    win = _window(qapp)
    try:
        headers = [win.nav.item(r) for r in range(win.nav.count())
                   if win.nav.item(r).data(HEADER_ROLE)]
        assert [h.text() for h in headers] == ["Library", "Workflow", "Observing"]
        assert all(h.flags() == Qt.ItemFlag.NoItemFlags for h in headers)
        assert win.nav.count_text("deepsky") == str(len(win.catalog._cat))
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
        assert not win.undo_action.isEnabled()
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


def test_status_bar_is_transient_only(tmp_path, monkeypatch, qapp):
    """1.0: no permanent data-root path (it leaked into every screenshot); the bar
    speaks only while an operation runs or just finished."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win._update_status()
        msg = win.statusBar().currentMessage()
        assert str(config.DATA_ROOT) not in msg and "captured" not in msg
        win._update_status("  ·  Syncing…")
        assert win.statusBar().currentMessage() == "Syncing…"
        win._update_status()                            # done → cleared
        assert win.statusBar().currentMessage() == ""
    finally:
        win.deleteLater(); qapp.processEvents()


def test_data_folder_is_shown_in_about(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QLabel
    seed_root(tmp_path, monkeypatch)
    from m110.ui.about_dialog import AboutDialog
    dlg = AboutDialog()
    try:
        texts = " ".join(l.text() for l in dlg.findChildren(QLabel))
        assert config.DATA_ROOT.name in texts and "Data folder" in texts
    finally:
        dlg.deleteLater(); qapp.processEvents()


# ---- Edit › Undo, Object menu, Find, Window ----

def _select(win, qapp, slug):
    win.open_object(slug)
    qapp.processEvents()
    assert win.catalog.selected_slug() == slug


def test_object_menu_follows_the_selection(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    from tests._helpers import seed_capture
    slug, _tid = seed_capture(root)
    win = _window(qapp)
    try:
        win._update_object_menu()
        assert not win.remove_action.isEnabled() and not win.pin_action.isEnabled()
        _select(win, qapp, slug)
        assert win.remove_action.isEnabled() and win.pin_action.isEnabled()
        assert win.set_goal_action.isEnabled()          # captured → has goal rows
        assert win.publish_flag_action.isChecked()      # published by default
    finally:
        win.deleteLater(); qapp.processEvents()


def test_pin_from_the_object_menu_is_undoable(tmp_path, monkeypatch, qapp):
    from m110 import pins
    root = seed_root(tmp_path, monkeypatch)
    from tests._helpers import seed_capture
    slug, _tid = seed_capture(root)
    win = _window(qapp)
    try:
        _select(win, qapp, slug)
        win.pin_action.trigger()
        assert pins.get_state(slug) == pins.PIN
        assert win.undo_action.isEnabled() and "Pin" in win.undo_action.text()
        win.undo_action.trigger()
        assert pins.get_state(slug) is None
        win.redo_action.trigger()
        assert pins.get_state(slug) == pins.PIN
        win._update_object_menu()
        assert win.pin_action.isChecked()
        win.depri_action.trigger()                      # pin → deprioritize
        assert pins.get_state(slug) == pins.DEPRIORITIZE
        win.undo_action.trigger()
        assert pins.get_state(slug) == pins.PIN
    finally:
        win.deleteLater(); qapp.processEvents()


def test_remove_from_library_is_undoable_without_a_confirm(tmp_path, monkeypatch, qapp):
    """HIG: Undo replaces the "are you sure?". The same entry comes back."""
    from PySide6.QtWidgets import QMessageBox
    from m110 import catalog
    from tests._helpers import add_library
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m57": {"id": "M57", "name": "Ring Nebula",
                               "type": "planetary_nebula"}})
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.Yes)
    win = _window(qapp)
    try:
        win.catalog.reload()
        before = dict(catalog.load_library()["m57"])
        _select(win, qapp, "m57")
        win.remove_action.trigger()
        assert "m57" not in catalog.load_library()
        assert "m57" not in win.catalog._cat
        assert asked == []
        win.undo_action.trigger()
        assert catalog.load_library()["m57"] == before
        assert "m57" in win.catalog._cat
    finally:
        win.deleteLater(); qapp.processEvents()


def test_find_focuses_the_places_search_field(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win.show()
        win.go_to(win._journal_index)
        win.find_action.trigger()
        qapp.processEvents()
        assert QApplication_focus() is win.journal._search
        win.go_to(win._planning_index)                 # no search here → Deep Sky's
        win.find_action.trigger()
        qapp.processEvents()
        assert win.current_page() == win._catalog_index
        assert QApplication_focus() is win.catalog._search
    finally:
        win.close(); win.deleteLater(); qapp.processEvents()


def QApplication_focus():
    from PySide6.QtWidgets import QApplication
    return QApplication.focusWidget()


def test_view_modes_and_chrome_actions(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    from tests._helpers import seed_capture
    slug, _tid = seed_capture(root)
    win = _window(qapp)
    try:
        win.go_to(win._catalog_index)
        win.view_mode_actions["list"].trigger()
        assert win.catalog.view_mode() == "list"
        win.view_mode_actions["map"].trigger()
        assert win.catalog.view_mode() == "map"
        win.go_to(win._media_index)
        win._update_view_menu()
        assert not win.view_mode_actions["map"].isEnabled()
        win.view_mode_actions["list"].trigger()
        assert win.media_page.view_mode() == "list"
        win.go_to(win._overview_index)
        win._update_view_menu()
        assert not any(a.isEnabled() for a in win.view_mode_actions.values())

        win.toggle_sidebar_action.trigger()
        assert not win.sidebar_visible()
        assert win.toggle_sidebar_action.text() == "Show Sidebar"
        win.toggle_sidebar_action.trigger()
        assert win.sidebar_visible()

        win.go_to(win._catalog_index)
        win.view_mode_actions["grid"].trigger()
        _select(win, qapp, slug)
        win.toggle_inspector_action.trigger()
        assert win.catalog.detail.isHidden()
        win.toggle_inspector_action.trigger()
        assert not win.catalog.detail.isHidden()
    finally:
        win.deleteLater(); qapp.processEvents()


def test_copy_puts_the_selected_designation_on_the_clipboard(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QApplication
    root = seed_root(tmp_path, monkeypatch)
    from tests._helpers import seed_capture
    slug, _tid = seed_capture(root)
    win = _window(qapp)
    try:
        _select(win, qapp, slug)
        win.catalog.grid_view.setFocus()
        win.copy_action.trigger()
        assert QApplication.clipboard().text() == (win.catalog._cat[slug].get("id")
                                                   or slug)
        win.select_all_action.trigger()                 # no crash without a target
    finally:
        win.deleteLater(); qapp.processEvents()


def test_window_menu_lists_the_apps_windows(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        win.show()
        qapp.processEvents()
        win._rebuild_window_menu()
        titles = [a.text() for a in win.window_menu.actions() if not a.isSeparator()]
        assert titles[:3] == ["Minimize", "Zoom", "Bring All to Front"]
        assert "M110" in titles
        listed = next(a for a in win.window_menu.actions() if a.text() == "M110")
        listed.trigger()                                # raise: no crash
        win.bring_all_action.trigger()
        win.zoom_action.trigger()
        qapp.processEvents()
        win.zoom_action.trigger()
    finally:
        win.close(); win.deleteLater(); qapp.processEvents()

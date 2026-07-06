"""M110 — PySide6 desktop shell.

A left nav rail switches between the Library pages (Summary · Catalog ·
Processing — Sessions/Journal coming) in a stacked content area. Summary is the
landing page. The Catalog page hosts the shared per-object detail; object links
on the other pages route there via `open_object`. The shell keeps everything in
sync with disk: it refreshes on launch, on window-focus, and after ingest
(threaded), and backfills any missing processing working folders.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QStackedWidget, QMessageBox,
)

from m110 import config, derived
from m110.catalog import object_count
from m110.ui.pages.summary import SummaryPage
from m110.ui.pages.goals import GoalsPage
from m110.ui.pages.catalog import CatalogPage
from m110.ui.pages.processing import ProcessingPage
from m110.ui.pages.sessions import SessionsPage
from m110.ui.pages.journal import JournalPage
from m110.ui.pages.media import MediaPage
from m110.ui.pages.import_page import ImportPage
from m110.ui import theme


class RefreshWorker(QThread):
    """Runs the (potentially slow) scan+derive+prepare-missing off the UI thread."""
    done = Signal(dict)
    failed = Signal(str)

    def run(self):
        try:
            from m110.refresh import run_refresh
            from m110 import processing
            summary = run_refresh()
            prep = processing.prepare_missing()   # heal missing working folders
            summary["prepared"] = sum(len(r.get("prepared", []))
                                      for r in prep.values())
            self.done.emit(summary)
        except Exception as exc:  # surface to the UI rather than crash
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _BackupBgWorker(QThread):
    """Launch-time auto-backup, off the UI thread. Cancellable via a shared event
    so quit doesn't hang on a large snapshot (create_snapshot aborts + cleans up)."""
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, dest, cancel_event, parent=None):
        super().__init__(parent)
        self._dest = dest
        self._cancel = cancel_event

    def run(self):
        try:
            from m110 import backup
            self.done.emit(backup.create_snapshot(
                backup.options_from_settings(self._dest),
                should_cancel=self._cancel.is_set))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _EnrichWorker(QThread):
    """Online (Simbad) bulk enrichment off the UI thread."""
    done = Signal(dict)
    failed = Signal(str)

    def run(self):
        try:
            from m110 import catalog
            self.done.emit(catalog.enrich_online())
        except Exception as exc:
            from m110 import catalog
            if isinstance(exc, catalog.OnlineLookupError):
                self.failed.emit(str(exc))
            else:
                self.failed.emit(f"{type(exc).__name__}: {exc}")


class _LogoLabel(QLabel):
    """Nav-rail brand mark — the M110 wordmark in the active theme's ink. Call
    `refresh()` when the theme changes to recolor it."""
    _HEIGHT = 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navLogo")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh()

    def refresh(self):
        dpr = self.devicePixelRatioF() or 1.0
        self.setPixmap(theme.logo_pixmap(self._HEIGHT, theme.ink_color(), dpr))


class MainWindow(QMainWindow):
    NAV = ["Summary", "Goals", "Library", "Processing", "Sessions", "Journal",
           "Media", "Import"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("M110")
        self.setWindowIcon(theme.app_icon())
        self._worker = None
        self._enrich_worker = None
        self._ready = False
        self._refreshing = False
        self._last_refresh = 0.0
        self._prep_feedback = False
        self._backup_worker = None
        self._backup_cancel = None
        self._auto_backup_checked = False

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No library found at:\n{config.LIBRARY_TOML}\n\n"
                f"Set M110_DATA_ROOT to your data folder."))
            self.resize(560, 160)
            return

        # Pages (order matches the nav rail + stack).
        self.summary = SummaryPage()
        self.goals = GoalsPage()
        self.catalog = CatalogPage()
        self.processing = ProcessingPage()
        self.sessions = SessionsPage()
        self.journal = JournalPage()
        self.media = MediaPage()
        self.import_page = ImportPage()
        self.pages = [self.summary, self.goals, self.catalog, self.processing,
                      self.sessions, self.journal, self.media, self.import_page]
        self._catalog_index = self.pages.index(self.catalog)
        self._import_index = self.pages.index(self.import_page)

        self.stack = QStackedWidget()
        # Uniform breathing room around every page (token-driven), so content isn't
        # flush against the nav rail / window edges.
        s = theme.tokens.SPACE
        self.stack.setContentsMargins(s["lg"], s["md"], s["lg"], s["lg"])
        for p in self.pages:
            self.stack.addWidget(p)

        self.nav = QListWidget()
        self.nav.setObjectName("navRail")
        self.nav.addItems(self.NAV)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        # Left column: brand mark above the nav rail (a persistent mark on every screen).
        self.logo = _LogoLabel()
        left = QWidget()
        left.setObjectName("navColumn")
        left.setMaximumWidth(160)
        left.setMinimumWidth(130)
        col = QVBoxLayout(left)
        col.setContentsMargins(0, s["md"], 0, 0)
        col.setSpacing(s["sm"])
        col.addWidget(self.logo)
        col.addWidget(self.nav, 1)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(left)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Routing + locking.
        self.catalog.editing_changed.connect(self._on_editing_changed)
        self.catalog.dirty.connect(self._do_refresh)
        self.catalog.notes_saved.connect(self._on_notes_saved)
        self.summary.open_object.connect(self.open_object)
        self.goals.open_object.connect(self.open_object)
        self.goals.dirty.connect(self._do_refresh)
        self.processing.open_object.connect(self.open_object)
        self.sessions.open_object.connect(self.open_object)
        self.journal.open_object.connect(self.open_object)
        self.import_page.imported.connect(
            lambda moved: self._do_refresh() if moved else None)

        # Wait for any in-flight refresh thread before teardown — otherwise quit
        # (incl. Cmd+Q from a modal viewer → app.quit()) destroys a running
        # QThread and Qt aborts ("QThread: Destroyed while thread is still
        # running"). aboutToQuit covers app.quit(); closeEvent covers window close.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)

        # Theme: repaint programmatic (non-QSS) colors when the palette changes.
        if theme.manager() is not None:
            theme.manager().changed.connect(self._restyle_pages)

        # Global actions + menu. Import is reached via the nav rail (the toolbar
        # button was redundant); the Ctrl+I shortcut stays, registered on the window.
        self.ingest_action = QAction("Import…", self)
        self.ingest_action.setShortcut("Ctrl+I")
        self.ingest_action.triggered.connect(self._open_ingest)
        self.addAction(self.ingest_action)

        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setShortcut("Ctrl+R")
        self.refresh_action.triggered.connect(self._do_refresh)
        self.prep_action = QAction("Prepare working folders", self)
        self.prep_action.triggered.connect(self._prepare_working_folders)
        self.add_object_action = QAction("Add object…", self)
        self.add_object_action.triggered.connect(self._add_object)
        self.fill_meta_action = QAction("Fill missing metadata…", self)
        self.fill_meta_action.triggered.connect(self._fill_missing_metadata)
        self.enrich_online_action = QAction("Enrich online…", self)
        self.enrich_online_action.triggered.connect(self._enrich_online_all)
        self.publish_action = QAction("Publish / share…", self)
        self.publish_action.triggered.connect(self._open_publish)
        self.backup_action = QAction("Back up…", self)
        self.backup_action.triggered.connect(self._open_backup)
        self.restore_action = QAction("Restore…", self)
        self.restore_action.triggered.connect(self._open_restore)
        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut(QKeySequence.Preferences)
        prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)  # → app menu on macOS
        prefs_action.triggered.connect(self._open_prefs)
        # Library menu — store-level operations (room to grow: open / archive / export).
        # (No separate "M110" menu: Preferences folds into the macOS app menu by role, and
        # Prepare lives here with the other maintenance actions.)
        self.lib_menu = self.menuBar().addMenu("Library")
        self.lib_menu.addAction(self.refresh_action)
        self.lib_menu.addAction(self.prep_action)
        self.lib_menu.addSeparator()
        self.lib_menu.addAction(self.add_object_action)
        self.lib_menu.addAction(self.fill_meta_action)
        self.lib_menu.addAction(self.enrich_online_action)
        self.lib_menu.addSeparator()
        self.lib_menu.addAction(self.publish_action)
        self.lib_menu.addSeparator()
        self.lib_menu.addAction(self.backup_action)
        self.lib_menu.addAction(self.restore_action)
        self.lib_menu.addSeparator()
        self.lib_menu.addAction(prefs_action)          # macOS: hops to the app menu
        # Help menu — About folds into the application menu on macOS (AboutRole).
        self.about_action = QAction("About M110", self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self._open_about)
        self.help_menu = self.menuBar().addMenu("Help")
        self.help_menu.addAction(self.about_action)

        # Hourly tick for the daily (02:00) auto backup while the app stays running.
        # Cheap: it only starts a snapshot when `due_for_scheduled_backup` says so.
        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(60 * 60 * 1000)   # 1 hour
        self._backup_timer.timeout.connect(
            lambda: self._maybe_auto_backup(scheduled=True))
        self._backup_timer.start()

        self.nav.setCurrentRow(0)          # Summary lands first
        self._update_status()
        self.resize(1180, 740)
        self._ready = True
        QTimer.singleShot(0, self._do_refresh)

    # ---- routing ----
    def open_object(self, slug: str):
        self.nav.setCurrentRow(self._catalog_index)
        self.catalog.select_object(slug)

    # ---- status ----
    def _update_status(self, extra: str = ""):
        captured = len(derived.totals_by_slug())
        note = "" if derived.derived_available() else " · derived rollups not found"
        self.statusBar().showMessage(
            f"{captured}/{object_count()} captured · {config.DATA_ROOT}{note}{extra}")

    # ---- import / prefs ----
    def _open_ingest(self):
        # Import is now a top-level page (was a modal dialog) — navigate to it and
        # let the user refresh the source list (a device may have just mounted).
        self.nav.setCurrentRow(self._import_index)
        self.import_page.reload()

    def _open_prefs(self):
        from m110.ui.preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    def _open_about(self):
        from m110.ui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def _open_publish(self):
        if self.catalog.is_editing() or self._refreshing:
            return
        from m110.ui.publish_dialog import PublishDialog
        PublishDialog(self).exec()

    def _open_backup(self):
        if self.catalog.is_editing():
            return
        from m110.ui.backup_dialog import BackupDialog
        BackupDialog(self).exec()

    def _open_restore(self):
        if self.catalog.is_editing():
            return
        from m110 import backup
        from m110.ui.restore_dialog import RestoreDialog
        RestoreDialog(config.get_setting(backup.SETTING_DEST, ""), self).exec()

    # ---- auto backup (opt-in; background; unobtrusive) ----
    # Two triggers, both off the UI thread and cancel-on-quit: a launch check
    # (back up if the last snapshot is older than the interval) and an hourly tick
    # that fires the daily 02:00 backup so a long-running session still gets daily
    # snapshots. Both share the single worker (guarded below).
    def _maybe_auto_backup(self, *, scheduled: bool = False):
        if self._backup_worker is not None:
            return
        from m110 import backup
        dest = config.get_setting(backup.SETTING_DEST)
        if not dest:
            return
        check = (backup.due_for_scheduled_backup if scheduled
                 else backup.due_for_auto_backup)
        try:
            if not check(Path(dest)):
                return
        except Exception:
            return
        self._backup_cancel = threading.Event()
        self._update_status(extra="  ·  Backing up…")
        self._backup_worker = _BackupBgWorker(Path(dest), self._backup_cancel, self)
        self._backup_worker.done.connect(self._on_auto_backup_done)
        self._backup_worker.failed.connect(self._on_auto_backup_failed)
        self._backup_worker.start()

    def _on_auto_backup_done(self, res: dict):
        self._clear_backup_worker()
        if res.get("cancelled"):
            self._update_status()
            return
        self._update_status(
            extra=f"  ·  Backed up {res.get('file_count', 0)} files")

    def _on_auto_backup_failed(self, msg: str):
        self._clear_backup_worker()
        self._update_status(extra="  ·  Backup skipped")

    def _clear_backup_worker(self):
        if self._backup_worker is not None:
            self._backup_worker.deleteLater()
            self._backup_worker = None

    # ---- editing lock ----
    def _on_editing_changed(self, editing: bool):
        # While the journal editor is open, lock navigation + global actions so a
        # page switch / auto-refresh can't discard in-progress edits. (The Catalog
        # page locks its own table.)
        self.nav.setEnabled(not editing)
        self.ingest_action.setEnabled(not editing)
        self.refresh_action.setEnabled(not editing)
        self.prep_action.setEnabled(not editing)

    def _on_notes_saved(self, _slug: str):
        # Object Notes were edited in the detail pane — reload the other views (the
        # Journal feed especially) so the new text shows without a manual Refresh.
        # Lightweight: no scan/derive/render worker (a text edit adds no images).
        for p in self.pages:
            if p is not self.catalog:        # the detail pane already re-rendered
                p.reload()

    def _prepare_working_folders(self):
        if self.catalog.is_editing() or self._refreshing:
            return
        self._prep_feedback = True
        self._do_refresh()

    def _fill_missing_metadata(self):
        """Backfill every Library entry's missing fields from the bundled reference
        (offline, non-destructive — fills blanks only). Reports what changed."""
        if self.catalog.is_editing() or self._refreshing:
            return
        from m110 import catalog
        try:
            lib = catalog.load_library()
        except catalog.LibraryParseError as e:
            QMessageBox.warning(self, "Library file error", str(e))
            return
        ref = catalog.load_reference()
        n_missing = sum(1 for s, e in lib.items()
                        if catalog._compute_fill(e, ref.get(s, {})))
        if not n_missing:
            QMessageBox.information(self, "Fill missing metadata",
                                   "Every Library object already has all available metadata.")
            return
        if QMessageBox.question(
                self, "Fill missing metadata",
                f"Fill in missing metadata for {n_missing} object(s) from the "
                f"bundled reference?") != QMessageBox.Yes:
            return
        filled = catalog.fill_all_missing_metadata()
        for p in self.pages:
            p.reload()
        QMessageBox.information(self, "Fill missing metadata",
                               f"Filled metadata for {len(filled)} object(s).")

    def _add_object(self):
        """Open the Add-object dialog; route to the new object on success."""
        if self.catalog.is_editing() or self._refreshing:
            return
        from m110.ui.add_object_dialog import AddObjectDialog
        dlg = AddObjectDialog(self)
        dlg.added.connect(self._on_object_added)
        dlg.exec()

    def _on_object_added(self, slug: str):
        for p in self.pages:
            p.reload()
        self._update_status()
        self.open_object(slug)

    def _enrich_online_all(self):
        """Online (Simbad) enrichment for every Library entry with remaining gaps,
        on a worker thread. Optional + graceful when astroquery/network is absent."""
        if self.catalog.is_editing() or self._refreshing or self._enrich_worker:
            return
        if QMessageBox.question(
                self, "Enrich online",
                "Look up missing metadata on Simbad for Library objects with gaps?\n"
                "This needs a network connection and the optional 'online' extra."
                ) != QMessageBox.Yes:
            return
        self.enrich_online_action.setEnabled(False)
        self._update_status(extra="  ·  Enriching online…")
        self._enrich_worker = _EnrichWorker(self)
        self._enrich_worker.done.connect(self._on_enrich_done)
        self._enrich_worker.failed.connect(self._on_enrich_failed)
        self._enrich_worker.start()

    def _on_enrich_done(self, filled: dict):
        self._enrich_worker = None
        self.enrich_online_action.setEnabled(True)
        for p in self.pages:
            p.reload()
        self._update_status()
        QMessageBox.information(self, "Enrich online",
                               f"Enriched {len(filled)} object(s) from Simbad.")

    def _on_enrich_failed(self, msg: str):
        self._enrich_worker = None
        self.enrich_online_action.setEnabled(True)
        self._update_status()
        QMessageBox.warning(self, "Online lookup unavailable", msg)

    # ---- auto-sync ----
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            # Fallback for Qt < 6.8 (no colorSchemeChanged signal): re-check the OS
            # appearance on focus-in so "follow system" still tracks a theme flip.
            if theme.manager() is not None:
                theme.manager().refresh_system()
            if (self._ready and not self._refreshing
                    and time.monotonic() - self._last_refresh > 2.0):
                self._do_refresh()

    def _restyle_pages(self):
        """Theme changed — re-apply programmatic colors QSS can't reach (table-item
        status/muted foregrounds, the ink logo). QSS-styled widgets repaint themselves."""
        self.logo.refresh()
        for p in self.pages:
            if hasattr(p, "restyle"):
                p.restyle()

    def _do_refresh(self):
        if not self._ready or self._refreshing or self.catalog.is_editing():
            return
        if getattr(self, "import_page", None) is not None and self.import_page.is_busy():
            return                         # don't race an in-progress import's autoprep
        self._refreshing = True
        self.refresh_action.setEnabled(False)
        self._update_status(extra="  ·  Syncing…")
        self._worker = RefreshWorker(self)
        self._worker.done.connect(self._on_refresh_done)
        self._worker.failed.connect(self._on_refresh_failed)
        self._worker.start()

    def _on_refresh_done(self, summary: dict):
        self._refreshing = False
        self._last_refresh = time.monotonic()
        if self.catalog.is_editing():
            return                         # don't disturb an open editor
        self.refresh_action.setEnabled(True)
        for p in self.pages:
            p.reload()
        self._update_status()
        if self._prep_feedback:
            self._prep_feedback = False
            n = summary.get("prepared", 0)
            QMessageBox.information(
                self, "Prepare working folders",
                f"{n} working folder(s) prepared." if n else
                "All objects already have their working folders.")
        # Once the store is consistent, consider a launch-time auto backup (opt-in).
        if not self._auto_backup_checked:
            self._auto_backup_checked = True
            self._maybe_auto_backup()

    def _on_refresh_failed(self, msg: str):
        self._refreshing = False
        self._last_refresh = time.monotonic()
        self.refresh_action.setEnabled(True)
        self._update_status(extra=f"  ·  Sync failed: {msg}")

    # ---- clean shutdown ----
    def _stop_worker(self) -> None:
        """Block until the refresh thread finishes, so teardown never destroys a
        running QThread (which Qt turns into a fatal abort). run_refresh isn't
        cancellable, so we wait it out — quit pauses briefly rather than crashing."""
        w = self._worker
        if w is not None and w.isRunning():
            w.wait()
        # Cancel + drain a background backup so teardown never destroys a live
        # QThread (create_snapshot aborts promptly and cleans up its temp dir).
        bw = self._backup_worker
        if bw is not None and bw.isRunning():
            if self._backup_cancel is not None:
                self._backup_cancel.set()
            bw.wait()

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)


def _set_macos_app_name(name: str) -> None:
    """Make the macOS app menu + dock tooltip show `name` instead of "Python" when
    running unbundled from source. The app-menu title comes from the bundle's
    CFBundleName (patched on NSBundle's info dict before AppKit builds the menu); the
    dock tooltip comes from the process name (NSProcessInfo). Qt can set neither. Needs
    pyobjc (a macOS-only dep); a no-op if it's missing or off-macOS. The durable fix is a
    packaged .app with CFBundleName=M110; this just bridges the run-from-source case.
    Must run before QApplication is created."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle, NSProcessInfo
    except Exception:
        return
    bundle = NSBundle.mainBundle()
    info = bundle and (bundle.localizedInfoDictionary() or bundle.infoDictionary())
    if info is not None:
        info["CFBundleName"] = name           # app-menu title
    try:
        NSProcessInfo.processInfo().setProcessName_(name)   # dock tooltip
    except Exception:
        pass


def main() -> None:
    _set_macos_app_name("M110")         # app-menu / dock name (before QApplication)
    app = QApplication(sys.argv)
    app.setApplicationName("M110")
    app.setApplicationDisplayName("M110")
    app.setOrganizationName("M110")
    theme.install(app)                  # design-system: tokens → QSS, follow system
    app.setWindowIcon(theme.app_icon())  # dock / taskbar icon (parchment tile)
    config.ensure_data_root()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

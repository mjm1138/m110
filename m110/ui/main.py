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
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QLabel, QListWidget,
    QStackedWidget, QMessageBox,
)

from m110 import config, derived
from m110.catalog import object_count
from m110.ui.pages.summary import SummaryPage
from m110.ui.pages.catalog import CatalogPage
from m110.ui.pages.processing import ProcessingPage
from m110.ui.pages.sessions import SessionsPage
from m110.ui.pages.journal import JournalPage
from m110.ui.pages.media import MediaPage


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


class MainWindow(QMainWindow):
    NAV = ["Summary", "Library", "Processing", "Sessions", "Journal", "Media"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("M110")
        self._worker = None
        self._ready = False
        self._refreshing = False
        self._last_refresh = 0.0
        self._prep_feedback = False

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No library found at:\n{config.LIBRARY_TOML}\n\n"
                f"Set M110_DATA_ROOT to your data folder."))
            self.resize(560, 160)
            return

        # Pages (order matches the nav rail + stack).
        self.summary = SummaryPage()
        self.catalog = CatalogPage()
        self.processing = ProcessingPage()
        self.sessions = SessionsPage()
        self.journal = JournalPage()
        self.media = MediaPage()
        self.pages = [self.summary, self.catalog, self.processing,
                      self.sessions, self.journal, self.media]
        self._catalog_index = self.pages.index(self.catalog)

        self.stack = QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)

        self.nav = QListWidget()
        self.nav.addItems(self.NAV)
        self.nav.setMaximumWidth(160)
        self.nav.setMinimumWidth(130)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.nav)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Routing + locking.
        self.catalog.editing_changed.connect(self._on_editing_changed)
        self.catalog.dirty.connect(self._do_refresh)
        self.summary.open_object.connect(self.open_object)
        self.processing.open_object.connect(self.open_object)
        self.sessions.open_object.connect(self.open_object)
        self.journal.open_object.connect(self.open_object)

        # Toolbar + menu (global).
        toolbar = self.addToolBar("Main")
        self.ingest_action = QAction("Ingest…", self)
        self.ingest_action.setShortcut("Ctrl+I")
        self.ingest_action.triggered.connect(self._open_ingest)
        toolbar.addAction(self.ingest_action)

        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setShortcut("Ctrl+R")
        self.refresh_action.triggered.connect(self._do_refresh)
        self.prep_action = QAction("Prepare working folders", self)
        self.prep_action.triggered.connect(self._prepare_working_folders)
        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut(QKeySequence.Preferences)
        prefs_action.triggered.connect(self._open_prefs)
        menu = self.menuBar().addMenu("M110")
        menu.addAction(self.refresh_action)
        menu.addAction(self.prep_action)
        menu.addAction(prefs_action)

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

    # ---- ingest / prefs ----
    def _open_ingest(self):
        from m110.ui.ingest_dialog import IngestDialog
        dlg = IngestDialog(self)
        dlg.ingested.connect(lambda moved: self._do_refresh() if moved else None)
        dlg.exec()

    def _open_prefs(self):
        from m110.ui.preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    # ---- editing lock ----
    def _on_editing_changed(self, editing: bool):
        # While the journal editor is open, lock navigation + global actions so a
        # page switch / auto-refresh can't discard in-progress edits. (The Catalog
        # page locks its own table.)
        self.nav.setEnabled(not editing)
        self.ingest_action.setEnabled(not editing)
        self.refresh_action.setEnabled(not editing)
        self.prep_action.setEnabled(not editing)

    def _prepare_working_folders(self):
        if self.catalog.is_editing() or self._refreshing:
            return
        self._prep_feedback = True
        self._do_refresh()

    # ---- auto-sync ----
    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.ActivationChange and self.isActiveWindow()
                and self._ready and not self._refreshing
                and time.monotonic() - self._last_refresh > 2.0):
            self._do_refresh()

    def _do_refresh(self):
        if not self._ready or self._refreshing or self.catalog.is_editing():
            return
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

    def _on_refresh_failed(self, msg: str):
        self._refreshing = False
        self._last_refresh = time.monotonic()
        self.refresh_action.setEnabled(True)
        self._update_status(extra=f"  ·  Sync failed: {msg}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("M110")
    config.ensure_data_root()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

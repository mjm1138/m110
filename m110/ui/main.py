"""M110 — PySide6 desktop shell.

A grouped source-list sidebar (`sidebar.PLACES`: Overview · Library: Deep Sky,
Media, Journal · Workflow: Import, Processing · Observing: Planning, Devices)
switches the page stack; a header bar (`toolbar.HeaderBar`) names the place and
carries that page's controls. **Overview** is the landing page. The Deep Sky page
hosts the shared per-object detail; object links on the other pages route there
via `open_object`. The shell keeps
everything in sync with disk: it refreshes on launch, on window-focus, and after
ingest (threaded), and backfills any missing processing working folders.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent, QTranslator
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QWidget, QVBoxLayout, QLabel, QSplitter,
    QStackedWidget, QMessageBox,
)

from m110 import config, derived, updates
from m110.ui.update_notice import UpdateCheckWorker
from m110.ui.pages.overview import OverviewPage
from m110.ui.pages.catalog import CatalogPage
from m110.ui.pages.processing import ProcessingPage
from m110.ui.pages.import_page import ImportPage
from m110.ui.pages.planning import PlanningPage
from m110.ui.pages.devices import DevicesPage
from m110.ui.pages.media import MediaPage
from m110.ui.pages.journal import JournalPage
from m110.ui.sidebar import PLACES, Sidebar
from m110.ui.toolbar import HEIGHT as HEADER_HEIGHT, TRAFFIC_LIGHT_INSET, DragArea, HeaderBar
from m110.ui.widgets import modal_loop_active, defer
from m110.ui import theme

APP_NAME = "M110"
SIDEBAR_WIDTH_KEY = "sidebar_width"
SIDEBAR_HIDDEN_KEY = "sidebar_hidden"
SIDEBAR_MIN, SIDEBAR_MAX, SIDEBAR_DEFAULT = 170, 300, 210


def _expanded_chrome() -> bool:
    """Draw our own title-bar band (sidebar under the traffic lights, header bar in
    the title row) — macOS with Qt ≥ 6.9 only; elsewhere the platform title bar
    stays. See `toolbar.py` for the prototype that chose this."""
    return sys.platform == "darwin" and hasattr(Qt.WindowType, "ExpandedClientAreaHint")


def recalibrated_message(targets) -> str:
    """The status-bar line for a sync that re-matched calibration ("" for none)."""
    targets = list(targets or [])
    if not targets:
        return ""
    shown = ", ".join(targets[:3])
    more = f" (+{len(targets) - 3} more)" if len(targets) > 3 else ""
    return f"  ·  Calibration re-matched: {shown}{more}"


class RefreshWorker(QThread):
    """Runs the (potentially slow) scan+derive+prepare-missing off the UI thread.
    `cancel` stops it at the next safe point, emitting nothing (quit uses it)."""
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cancel = threading.Event()

    def run(self):
        from m110.refresh import RefreshCancelled
        try:
            from m110.refresh import run_refresh
            from m110 import processing
            summary = run_refresh(should_cancel=self.cancel.is_set)
            if self.cancel.is_set():
                return                          # quitting: skip the sandbox upkeep
            prep = processing.prepare_missing()   # heal missing working folders
            summary["prepared"] = sum(len(r.get("prepared", []))
                                      for r in prep.values())
            # …and drop working-folder links for subs excluded since prep (#110),
            # so a rejection takes effect without waiting for the next import.
            pruned = processing.reconcile_rejected()
            summary["pruned"] = sum(r.get("pruned", 0) for r in pruned.values())
            # …and re-match calibration where the library (or the matching rules)
            # changed since a sandbox was set up — new darks reach existing objects.
            remat = processing.rematch_calibration(should_cancel=self.cancel.is_set)
            if self.cancel.is_set():
                return
            summary["recalibrated"] = remat["updated"]
            self.done.emit(summary)
        except RefreshCancelled:
            return                              # nothing half-written; nothing to report
        except Exception as exc:  # surface to the UI rather than crash
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _BackupBgWorker(QThread):
    """Launch-time auto-backup, off the UI thread. Cancellable via a shared event
    so quit doesn't hang on a large snapshot (create_snapshot aborts + cleans up)."""
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, slot, cancel_event, parent=None):
        super().__init__(parent)
        self.slot = slot
        self._cancel = cancel_event

    def run(self):
        try:
            from m110 import backup
            self.done.emit(backup.create_snapshot(
                backup.options_from_settings(self.slot),
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
    """Brand mark at the foot of the nav column — the M110 wordmark in the active
    theme's ink. Click it to open About (`clicked`); call `refresh()` when the theme
    changes to recolor it."""
    _HEIGHT = 26

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navLogo")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("About M110")
        self.setAccessibleName("About M110")
        self.refresh()

    def refresh(self):
        dpr = self.devicePixelRatioF() or 1.0
        self.setPixmap(theme.logo_pixmap(self._HEIGHT, theme.ink_color(), dpr))

    def mouseReleaseEvent(self, event):
        # Press-then-drag-away must not count as a click (the button convention).
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    NAV = [p.label for p in PLACES]

    def __init__(self):
        super().__init__()
        self._expanded = _expanded_chrome()
        # In the expanded title-bar band AppKit would draw the title beside the
        # traffic lights, over the sidebar; the header bar names the place instead.
        # The Window menu and accessibility still call the window "M110".
        self.setWindowTitle("" if self._expanded else APP_NAME)
        self.setAccessibleName(APP_NAME)
        if self._expanded:
            # ExpandedClientAreaHint shares its value with the deprecated
            # MaximizeUsingFullscreenGeometryHint, so PySide warns on the lookup.
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                self.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, True)
            self.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, True)
            # Our widgets fill the title-bar band; don't let the layout pad it out.
            self.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
        self.setWindowIcon(theme.app_icon())
        self._worker = None
        self._enrich_worker = None
        self._ready = False
        self._refreshing = False
        self._last_refresh = 0.0
        self._prep_feedback = False
        self._backup_worker = None
        self._backup_cancel = None
        self._backup_queue: list[str] = []      # slots due, run one at a time
        self._backup_notes: list[str] = []      # this round's results so far
        self._auto_backup_checked = False
        self._update_worker = None
        self._banner = None
        # A finished sync rebuilds the pages — deferred while a modal/popup owns a
        # nested event loop (see `_apply_refresh`). Parented, so it dies with the
        # window rather than firing into a half-torn-down shell.
        self._pending_refresh = None
        self._reload_retry = QTimer(self)
        self._reload_retry.setInterval(250)
        self._reload_retry.setSingleShot(True)
        self._reload_retry.timeout.connect(self._retry_pending_refresh)

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No library found at:\n{config.LIBRARY_TOML}\n\n"
                f"Set M110_DATA_ROOT to your data folder."))
            self.resize(560, 160)
            return

        # Pages, in `sidebar.PLACES` order (the stack, the sidebar and the View
        # menu are all built from that one list).
        self.overview = OverviewPage()
        self.catalog = CatalogPage()
        self.media_page = MediaPage()
        self.journal = JournalPage()
        self.import_page = ImportPage()
        self.processing = ProcessingPage()
        self.planning = PlanningPage()
        self.devices = DevicesPage()
        self.pages = [self.overview, self.catalog, self.media_page, self.journal,
                      self.import_page, self.processing, self.planning, self.devices]
        assert len(self.pages) == len(PLACES)
        self._overview_index = self.pages.index(self.overview)
        self._catalog_index = self.pages.index(self.catalog)
        self._media_index = self.pages.index(self.media_page)
        self._journal_index = self.pages.index(self.journal)
        self._import_index = self.pages.index(self.import_page)
        self._processing_index = self.pages.index(self.processing)
        self._planning_index = self.pages.index(self.planning)
        self._devices_index = self.pages.index(self.devices)

        self.stack = QStackedWidget()
        # Uniform breathing room around every page (token-driven), so content isn't
        # flush against the sidebar / window edges.
        s = theme.tokens.SPACE
        self.stack.setContentsMargins(s["lg"], s["md"], s["lg"], s["lg"])
        for p in self.pages:
            self.stack.addWidget(p)

        # The header bar: place title + subtitle + the page's own controls.
        self.header = HeaderBar()
        self.header.toggle_sidebar.connect(self.toggle_sidebar)
        for p in self.pages:
            ctl = getattr(p, "header_controls", None)
            if ctl is not None:
                self.header.adopt(ctl)
            sig = getattr(p, "subtitle_changed", None)
            if sig is not None:
                sig.connect(lambda text, page=p: self._on_subtitle(page, text))

        self.nav = Sidebar(PLACES)
        self.nav.page_selected.connect(self.stack.setCurrentIndex)
        self.nav.page_selected.connect(self._on_nav_changed)

        # Left column: the sidebar, with the brand mark anchored at its foot (a
        # quiet mark on every screen, and the way in to About). On macOS the column
        # runs the full window height, under the traffic lights, so its top band is
        # window chrome: a drag area the height of the header bar.
        self.logo = _LogoLabel()
        self.logo.clicked.connect(lambda: defer(self, self._open_about))
        left = QWidget()
        left.setObjectName("navColumn")
        left.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left.setMinimumWidth(SIDEBAR_MIN)
        left.setMaximumWidth(SIDEBAR_MAX)
        col = QVBoxLayout(left)
        col.setContentsMargins(0, 0, 0, s["md"])
        col.setSpacing(s["sm"])
        self._sidebar_top = DragArea()
        self._sidebar_top.setFixedHeight(HEADER_HEIGHT if self._expanded else s["xs"])
        col.addWidget(self._sidebar_top)
        col.addWidget(self.nav, 1)
        col.addWidget(self.logo)
        self.sidebar_column = left

        # Content column: header bar, the (usually hidden) update + assistant
        # banners, then the page stack.
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.addWidget(self.header)
        # The assistant queue indicator. Persistent while the outbox is
        # non-empty — deliberately not a launch/foreground modal: the app
        # auto-syncs on every window focus, so that would fire constantly.
        from m110.ui.assistant_review import AssistantBanner
        self._assistant_banner = AssistantBanner(self)
        self._assistant_banner.review.connect(self._review_assistant_items)
        self._content_layout.addWidget(self._assistant_banner)
        self._content_layout.addWidget(self.stack, 1)

        # Sidebar | content, in a splitter: the sidebar is resizable (width
        # remembered) and collapsible (View › Hide Sidebar, the header's button).
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("shellSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(left)
        self.splitter.addWidget(content)
        self.splitter.setStretchFactor(1, 1)
        width = config.get_setting(SIDEBAR_WIDTH_KEY, SIDEBAR_DEFAULT)
        try:
            width = max(SIDEBAR_MIN, min(SIDEBAR_MAX, int(width)))
        except (TypeError, ValueError):
            width = SIDEBAR_DEFAULT
        self.splitter.setSizes([width, 1180 - width])
        self.splitter.splitterMoved.connect(self._on_sidebar_resized)
        self.setCentralWidget(self.splitter)
        if config.get_setting(SIDEBAR_HIDDEN_KEY, False):
            self.set_sidebar_visible(False)

        # Routing + locking.
        self.catalog.editing_changed.connect(self._on_editing_changed)
        self.catalog.dirty.connect(self._do_refresh)
        self.catalog.notes_saved.connect(self._on_notes_saved)
        self.catalog.pins_changed.connect(self._on_pins_changed)
        self.catalog.goals_changed.connect(self._on_goals_changed)
        self.overview.open_object.connect(self.open_object)
        self.overview.go_to_import.connect(self._open_ingest)   # empty-state CTA
        self.journal.open_object.connect(self.open_object)
        self.overview.pins_changed.connect(self._on_pins_changed)
        self.overview.dirty.connect(self._do_refresh)           # goal set changed
        self.overview.goals_changed.connect(self._on_goals_changed)
        self.planning.open_object.connect(self.open_object)
        self.planning.pins_changed.connect(self._on_pins_changed)
        self.processing.open_object.connect(self.open_object)
        self.devices.open_object.connect(self.open_object)
        self.devices.goals_changed.connect(self._on_goals_changed)
        self.devices.devices_changed.connect(self._on_devices_changed)
        self.import_page.imported.connect(
            lambda moved: self._do_refresh() if moved else None)

        # Wait for any in-flight refresh thread before teardown — otherwise quit
        # (incl. Cmd+Q from a modal viewer → app.quit()) destroys a running
        # QThread and Qt aborts ("QThread: Destroyed while thread is still
        # running"). aboutToQuit covers app.quit(); closeEvent covers window close.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)
            # Also wait for background thumbnail decodes (ThumbnailLoader → the
            # global QThreadPool): a decode still running on a pool thread when Qt
            # tears down segfaults on native image code (same crash class).
            from m110.ui.widgets import drain_thumbnail_pool
            app.aboutToQuit.connect(lambda: drain_thumbnail_pool(3000))

        # Theme: repaint programmatic (non-QSS) colors when the palette changes.
        if theme.manager() is not None:
            theme.manager().changed.connect(self._restyle_pages)

        self._build_menus()

        # Hourly tick for the daily (02:00) auto backup while the app stays running.
        # Cheap: it only starts a snapshot when `due_for_scheduled_backup` says so.
        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(60 * 60 * 1000)   # 1 hour
        self._backup_timer.timeout.connect(
            lambda: self._maybe_auto_backup(scheduled=True))
        self._backup_timer.start()

        # Land on Overview — the collection at a glance (and, on a fresh store, the
        # welcome/CTA that guides the first import).
        self.go_to(self._overview_index)
        self._update_counts()
        self._update_status()
        self.resize(1180, 740)
        self._ready = True
        QTimer.singleShot(0, self._do_refresh)
        QTimer.singleShot(0, self._maybe_check_updates)   # quiet launch update check

    # ---- menus ----
    def _build_menus(self):
        """File · Edit · View · Object · Library · Window · Help — one structure on
        every platform (UI_ROADMAP → 1.0 redesign → Menus).

        macOS needs no branch: the `MenuRole`s hoist About / Settings / Check for
        Updates / Quit into the application menu by themselves, and Windows/Linux
        get them in File and Help. Every per-object verb lives in **Object**; the
        context menus are shortcuts to the same handlers, never their only home.
        """
        bar = self.menuBar()
        # macOS hoists the role actions out of these menus, which would strand the
        # separator that introduced them as a dangling rule at the foot of the menu
        # (Qt leaves it in the NSMenu, unhidden). The *structure* stays identical on
        # every platform — only this rule is conditional.
        hoists_roles = sys.platform == "darwin"

        def act(text, slot=None, shortcut=None, *, checkable=False, tip=None):
            a = QAction(text, self)
            if shortcut is not None:
                if isinstance(shortcut, (list, tuple)):
                    a.setShortcuts([QKeySequence(k) for k in shortcut])
                else:
                    a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            if tip:
                a.setToolTip(tip)
                a.setStatusTip(tip)
            if slot is not None:
                a.triggered.connect(slot)
            return a

        def fill(menu, actions):
            for a in actions:
                if a is None:
                    menu.addSeparator()
                else:
                    menu.addAction(a)

        # ── File ── moving data in and out of the store, and the window itself.
        self.ingest_action = act("Import…", self._open_ingest, "Ctrl+I")
        self.publish_action = act("Publish…", self._open_publish)
        self.backup_action = act("Back Up…", self._open_backup)
        self.restore_action = act("Restore…", self._open_restore)
        self.close_window_action = act("Close Window", self._close_active_window,
                                       QKeySequence.StandardKey.Close)
        self.prefs_action = act("Settings…", self._open_prefs,
                                QKeySequence.StandardKey.Preferences)
        self.prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        # QuitRole merges with the macOS app-menu entry rather than duplicating it.
        self.quit_action = act("Quit M110", self._quit, QKeySequence.StandardKey.Quit)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.file_menu = bar.addMenu("File")
        fill(self.file_menu, (self.ingest_action, self.publish_action, None,
                              self.backup_action, self.restore_action, None,
                              self.close_window_action))
        if not hoists_roles:
            self.file_menu.addSeparator()
        fill(self.file_menu, (self.prefs_action, self.quit_action))

        # ── Edit ── a real Undo stack (Remove from Library, pin overrides), the
        # clipboard, and Find → the header bar's search field.
        from m110.ui import undo
        self.undo_stack = QUndoStack(self)
        undo.install(self.undo_stack)
        self.destroyed.connect(lambda *_: undo.install(None))
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.copy_action = act("Copy", self._edit_copy, QKeySequence.StandardKey.Copy)
        self.select_all_action = act("Select All", self._edit_select_all,
                                     QKeySequence.StandardKey.SelectAll)
        self.find_action = act("Find…", self.focus_search, QKeySequence.StandardKey.Find)
        self.edit_menu = bar.addMenu("Edit")
        fill(self.edit_menu, (self.undo_action, self.redo_action, None,
                              self.copy_action, self.select_all_action, None,
                              self.find_action))

        # ── View ── the places (built from sidebar.PLACES, so the menu and the
        # sidebar can't drift), view modes, and window chrome.
        self.view_menu = bar.addMenu("View")
        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)
        self.view_actions = []
        for i, place in enumerate(PLACES):
            a = act(place.label, lambda _c=False, page=i: self.go_to(page),
                    f"Ctrl+{i + 1}", checkable=True)
            self.view_group.addAction(a)
            self.view_menu.addAction(a)
            self.view_actions.append(a)
        self.view_menu.addSeparator()
        self.view_mode_group = QActionGroup(self)
        self.view_mode_group.setExclusive(True)
        self.view_mode_actions = {}
        for n, (mode, label) in enumerate((("list", "as List"), ("grid", "as Grid"),
                                           ("map", "as Map")), start=1):
            a = act(label, lambda _c=False, m=mode: self._set_view_mode(m),
                    f"Ctrl+Alt+{n}", checkable=True)
            self.view_mode_group.addAction(a)
            self.view_menu.addAction(a)
            self.view_mode_actions[mode] = a
        self.view_menu.addSeparator()
        self.toggle_sidebar_action = act(
            "Hide Sidebar" if self.sidebar_visible() else "Show Sidebar",
            self.toggle_sidebar, "Meta+Ctrl+S")
        self.toggle_inspector_action = act("Hide Inspector", self.toggle_inspector,
                                           "Ctrl+Alt+I")
        self.full_screen_action = act("Enter Full Screen", self._toggle_full_screen,
                                      QKeySequence.StandardKey.FullScreen)
        # AppKit appends its own "Enter Full Screen" to a menu titled View, so on
        # macOS ours would be the second one; elsewhere ours is the only one.
        self.full_screen_action.setVisible(not hoists_roles)
        fill(self.view_menu, (self.toggle_sidebar_action, self.toggle_inspector_action,
                              None, self.full_screen_action))
        self.view_menu.aboutToShow.connect(self._update_view_menu)
        self.catalog.view_mode_changed.connect(lambda _m: self._update_view_menu())
        self.media_page.view_mode_changed.connect(lambda _m: self._update_view_menu())
        self.nav.page_selected.connect(self._sync_view_menu)

        # ── Object ── every per-object verb, enabled on a Deep Sky selection.
        self._build_object_menu(bar, act, fill)

        # ── Library ── operations on the collection itself.
        self.refresh_action = act("Refresh", self._do_refresh, ["Ctrl+R", "F5"])
        self.add_object_action = act("Add Object…", self._add_object)
        self.fill_meta_action = act("Fill All Missing Metadata…",
                                    self._fill_missing_metadata)
        self.enrich_online_action = act("Enrich All Online…", self._enrich_online_all)
        # Processing-prep is automatic; this is the repair action for a working
        # folder deleted or damaged by hand (critique §1.2 — not a "Prepare" step).
        self.prep_action = act("Rebuild Working Folders", self._prepare_working_folders,
                               tip="Recreate any missing processing working folders")
        self.media_cleanup_action = act(
            "Clean Up Imported Sidecars…", self._open_media_cleanup,
            tip="Remove leftover device thumbnails and index files from your Media folder")
        self.lib_menu = bar.addMenu("Library")
        fill(self.lib_menu, (self.refresh_action, None, self.add_object_action,
                             self.fill_meta_action, self.enrich_online_action, None,
                             self.prep_action, self.media_cleanup_action))

        # ── Window ── Qt adds none; the image viewer is its own window, so the
        # list matters.
        self.minimize_action = act("Minimize", self._minimize_active_window, "Ctrl+M")
        self.zoom_action = act("Zoom", self._zoom_active_window)
        self.bring_all_action = act("Bring All to Front", self._bring_all_to_front)
        self.window_menu = bar.addMenu("Window")
        self.window_menu.aboutToShow.connect(self._rebuild_window_menu)
        self._rebuild_window_menu()

        # ── Help ── About and Check for Updates fold into the macOS app menu.
        self.user_guide_action = act("M110 Help", self._open_user_guide)
        self.report_action = act("Report a Problem…", self._open_report)
        self.check_updates_action = act("Check for Updates…", self._check_updates)
        self.check_updates_action.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        self.about_action = act("About M110", self._open_about)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.help_menu = bar.addMenu("Help")
        fill(self.help_menu, (self.user_guide_action, None, self.report_action,
                              self.check_updates_action, self.about_action))

        self._sync_view_menu(self.nav.current_page())

    def _build_object_menu(self, bar, act, fill):
        cat = self.catalog
        self.show_object_action = act("Show in Library", self._show_selected_object)
        self.set_goal_action = act("Set Goal…", lambda: cat.detail.cmd_set_goal(),
                                   "Ctrl+Shift+G")
        self.pin_action = act("Pin as Priority",
                              lambda: self._with_selection(
                                  lambda s: cat.toggle_pin(s, "pin")),
                              "Ctrl+Shift+P", checkable=True)
        self.depri_action = act("Deprioritize",
                                lambda: self._with_selection(
                                    lambda s: cat.toggle_pin(s, "deprioritize")),
                                checkable=True)
        self.siril_menu = QMenu("Process in Siril", self)
        self.siril_menu.aboutToShow.connect(self._rebuild_siril_menu)
        self.astrowizard_action = act("Send to AstroWizard…",
                                      lambda: cat.detail.cmd_send_to_astrowizard())
        self.stackingwizard_action = act("Stack in StackingWizard…",
                                         lambda: cat.detail.cmd_stack_in_stackingwizard())
        self.import_finished_action = act("Import Finished Work…",
                                          lambda: cat.detail.cmd_import_finished())
        self.export_action = act("Export for Sharing…",
                                 lambda: cat.detail.cmd_export_for_sharing(),
                                 "Ctrl+Shift+E")
        self.reveal_action = act("Reveal Working Folder",
                                 lambda: cat.detail.cmd_reveal_working_folder(),
                                 "Ctrl+Shift+R")
        self.publish_flag_action = act(
            "Include in Publishing",
            lambda checked: self._with_selection(
                lambda s: cat._toggle_publish(s, checked)),
            checkable=True)
        self.fill_one_action = act("Fill In Missing Metadata",
                                   lambda: self._with_selection(cat._fill_one))
        self.enrich_one_action = act("Enrich Online",
                                     lambda: self._with_selection(cat._enrich_one_online))
        self.remove_action = act("Remove from Library",
                                 lambda: self._with_selection(cat._remove_one),
                                 "Ctrl+Backspace")
        self.object_menu = bar.addMenu("Object")
        m = self.object_menu
        fill(m, (self.show_object_action, self.set_goal_action, None,
                 self.pin_action, self.depri_action, None))
        m.addMenu(self.siril_menu)
        fill(m, (self.astrowizard_action, self.stackingwizard_action,
                 self.import_finished_action, None, self.export_action,
                 self.reveal_action, self.publish_flag_action, None,
                 self.fill_one_action, self.enrich_one_action, None,
                 self.remove_action))
        self.object_actions = [
            self.show_object_action, self.set_goal_action, self.pin_action,
            self.depri_action, self.siril_menu.menuAction(), self.astrowizard_action,
            self.stackingwizard_action, self.import_finished_action,
            self.export_action, self.reveal_action, self.publish_flag_action,
            self.fill_one_action, self.enrich_one_action, self.remove_action]
        m.aboutToShow.connect(self._update_object_menu)
        cat.selection_changed.connect(lambda _s: self._update_object_menu())
        cat.selection_changed.connect(lambda _s: self._update_view_menu())
        self._update_object_menu()

    # ---- menu state + handlers ----
    def _selected_slug(self) -> str | None:
        return self.catalog.selected_slug()

    def _with_selection(self, fn) -> None:
        slug = self._selected_slug()
        if slug and not self.catalog.is_editing():
            fn(slug)

    def _update_object_menu(self) -> None:
        """Enable the Object menu for the Deep Sky selection, verb by verb."""
        from m110 import catalog as catalog_mod, pins
        slug = self._selected_slug()
        if not slug or self.catalog.is_editing() or slug not in self.catalog._cat:
            for a in self.object_actions:
                a.setEnabled(False)
            for a in (self.pin_action, self.depri_action, self.publish_flag_action):
                a.setChecked(False)
            return
        have = self.catalog.detail.available_commands()
        entry = self.catalog._cat.get(slug, {})
        state = pins.get_state(slug)
        for a in (self.show_object_action, self.pin_action, self.depri_action,
                  self.publish_flag_action, self.remove_action):
            a.setEnabled(True)
        self.pin_action.setChecked(state == pins.PIN)
        self.depri_action.setChecked(state == pins.DEPRIORITIZE)
        self.publish_flag_action.setChecked(entry.get("publish", True) is not False)
        self.set_goal_action.setEnabled("set_goal" in have)
        self.siril_menu.menuAction().setEnabled("siril" in have)
        self.astrowizard_action.setEnabled("astrowizard" in have)
        self.stackingwizard_action.setEnabled("stackingwizard" in have)
        self.import_finished_action.setEnabled("import_finished" in have)
        self.export_action.setEnabled("export" in have)
        self.reveal_action.setEnabled("reveal" in have)
        ref = catalog_mod.load_reference().get(slug, {})
        filled = catalog_mod._compute_fill(entry, ref)
        self.fill_one_action.setEnabled(bool(filled))
        self.enrich_one_action.setEnabled(
            catalog_mod._has_gaps({**entry, **filled})
            and self.catalog._enrich_worker is None)

    def _rebuild_siril_menu(self) -> None:
        from m110.ui.widgets import add_siril_actions, launch_siril
        self.siril_menu.clear()
        dirs = self.catalog.detail.siril_dirs()
        acts = add_siril_actions(self.siril_menu, dirs) if dirs else {}
        for a, d in acts.items():
            # Deferred: `triggered` fires inside the menu's own loop, and the launch
            # can open a fallback dialog.
            a.triggered.connect(
                lambda _=False, d=d: defer(self, lambda: launch_siril(self, d)))
        if not acts:
            self.siril_menu.addAction("No Working Folder").setEnabled(False)

    def _show_selected_object(self) -> None:
        if self._selected_slug():
            self.go_to(self._catalog_index)

    def _view_mode_host(self):
        page = self.stack.currentWidget()
        return page if page in (self.catalog, self.media_page) else None

    def _set_view_mode(self, mode: str) -> None:
        host = self._view_mode_host()
        if host is not None:
            host.set_view_mode(mode)
        self._update_view_menu()

    def _update_view_menu(self) -> None:
        host = self._view_mode_host()
        modes = (("list", "grid", "map") if host is self.catalog
                 else ("list", "grid") if host is self.media_page else ())
        current = host.view_mode() if host is not None else None
        for mode, a in self.view_mode_actions.items():
            a.setEnabled(mode in modes)
            a.setChecked(mode == current)
        self.toggle_inspector_action.setEnabled(host is self.catalog
                                                and self._selected_slug() is not None)
        self.toggle_inspector_action.setText(
            "Show Inspector" if self.catalog.detail.isHidden() else "Hide Inspector")
        self.full_screen_action.setText(
            "Exit Full Screen" if self.isFullScreen() else "Enter Full Screen")

    def toggle_inspector(self) -> None:
        """The Deep Sky detail pane (the inspector) — hide it, or bring it back."""
        d = self.catalog.detail
        if d.isHidden() and self._selected_slug():
            d.show()
        else:
            d.hide()
        self._update_view_menu()

    def focus_search(self) -> None:
        """Edit › Find: focus this place's search field (Deep Sky's, if it has none)."""
        from PySide6.QtWidgets import QLineEdit
        ctl = getattr(self.stack.currentWidget(), "header_controls", None)
        field = ctl.findChild(QLineEdit, "searchField") if ctl is not None else None
        if field is None:
            self.go_to(self._catalog_index)
            field = self.catalog._search
        field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        field.selectAll()

    def _edit_copy(self) -> None:
        """Copy: the focused text, else the focused table's selected cells, else the
        selected object's designation."""
        from PySide6.QtWidgets import QAbstractItemView, QTableWidget
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, "copy") and not isinstance(w, QAbstractItemView):
            w.copy()
            return
        text = ""
        if isinstance(w, QTableWidget) and w.selectedItems():
            rows: dict[int, list[str]] = {}
            for it in sorted(w.selectedItems(), key=lambda i: (i.row(), i.column())):
                rows.setdefault(it.row(), []).append(it.text())
            text = "\n".join("\t".join(r) for r in rows.values())
        elif self._selected_slug():
            slug = self._selected_slug()
            text = self.catalog._cat.get(slug, {}).get("id") or slug
        if text:
            QApplication.clipboard().setText(text)

    def _edit_select_all(self) -> None:
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, "selectAll"):
            w.selectAll()

    def _close_active_window(self) -> None:
        (QApplication.activeWindow() or self).close()

    def _minimize_active_window(self) -> None:
        (QApplication.activeWindow() or self).showMinimized()

    def _zoom_active_window(self) -> None:
        w = QApplication.activeWindow() or self
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def _toggle_full_screen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _bring_all_to_front(self) -> None:
        for w in self._app_windows():
            w.raise_()

    @staticmethod
    def _window_label(w) -> str:
        return w.windowTitle() or (APP_NAME if isinstance(w, QMainWindow) else "")

    @classmethod
    def _app_windows(cls) -> list:
        """The app's own visible windows (main window, image viewers, dialogs)."""
        return [w for w in QApplication.topLevelWidgets()
                if w.isWindow() and w.isVisible() and cls._window_label(w)
                and not isinstance(w, QMenu)]

    def _rebuild_window_menu(self) -> None:
        m = self.window_menu
        m.clear()
        for a in (self.minimize_action, self.zoom_action, None, self.bring_all_action):
            if a is None:
                m.addSeparator()
            else:
                m.addAction(a)
        wins = self._app_windows()
        if wins:
            m.addSeparator()
        active = QApplication.activeWindow()
        for w in wins:
            a = m.addAction(self._window_label(w))
            a.setCheckable(True)
            a.setChecked(w is active)
            a.triggered.connect(lambda _=False, w=w: self._raise_window(w))

    @staticmethod
    def _raise_window(w) -> None:
        if w.isMinimized():
            w.showNormal()
        w.raise_()
        w.activateWindow()

    def _sync_view_menu(self, page: int):
        if 0 <= page < len(self.view_actions):
            self.view_actions[page].setChecked(True)
        self._update_view_menu()

    def _quit(self):
        app = QApplication.instance()
        if app is not None:      # aboutToQuit drains the refresh worker + thumb pool
            app.quit()

    def _on_nav_changed(self, page: int):
        self._show_header_for(page)
        # Opening Planning kicks off the (lazy, once/day) prioritizer recompute —
        # only in a live, ready window, never during construction/tests.
        if self._ready and page == self._planning_index:
            self.planning.ensure_ranking()

    # ---- routing ----
    def go_to(self, page: int) -> None:
        """Show page `page` (an index into `self.pages` / `sidebar.PLACES`)."""
        self.nav.select_page(page)

    def current_page(self) -> int:
        return self.stack.currentIndex()

    def open_object(self, slug: str):
        self.go_to(self._catalog_index)
        self.catalog.select_object(slug)

    # ---- header bar + sidebar ----
    def _show_header_for(self, page: int) -> None:
        p = self.pages[page]
        sub = p.subtitle() if hasattr(p, "subtitle") else ""
        self.header.set_place(PLACES[page].label, sub,
                              getattr(p, "header_controls", None))

    def _on_subtitle(self, page_widget, text: str) -> None:
        if self.stack.currentWidget() is page_widget:
            self.header.set_subtitle(text)
        self._update_counts()

    def _update_counts(self) -> None:
        """The sidebar's live counts — read from what the pages already loaded and
        the derived rollups; nothing here touches disk beyond those reads."""
        nav = getattr(self, "nav", None)
        if nav is None:
            return
        nav.set_count("deepsky", len(getattr(self.catalog, "_cat", {}) or {}))
        nav.set_count("media", self.media_page.item_count())
        counts = derived.load_processing().get("counts", {})
        queue = derived.load_processing().get("queue", [])
        ready = sum(1 for f in queue if f.get("ready_for_import"))
        nav.set_count("processing", ready + counts.get("out_of_date", 0)
                      + counts.get("not_processed", 0))
        nav.set_count("devices", sum(1 for d in derived.load_devices()
                                     if not d.get("retired")))

    def sidebar_visible(self) -> bool:
        return not self.sidebar_column.isHidden()

    def set_sidebar_visible(self, visible: bool) -> None:
        self.sidebar_column.setVisible(visible)
        # With the sidebar gone, the header bar is what sits under the traffic lights.
        self.header.set_leading_inset(0 if visible or not self._expanded
                                      else TRAFFIC_LIGHT_INSET)
        if getattr(self, "toggle_sidebar_action", None) is not None:
            self.toggle_sidebar_action.setText(
                "Hide Sidebar" if visible else "Show Sidebar")
        if self._ready:
            config.save_setting(SIDEBAR_HIDDEN_KEY, not visible)

    def toggle_sidebar(self) -> None:
        self.set_sidebar_visible(not self.sidebar_visible())

    def _on_sidebar_resized(self, *_):
        if self._ready and self.sidebar_visible():
            config.save_setting(SIDEBAR_WIDTH_KEY, self.splitter.sizes()[0])

    # ---- status ----
    STATUS_LINGER_MS = 8000     # how long a finished operation's result stays up

    def _update_status(self, extra: str = ""):
        """The status bar is **transient only** (1.0 redesign): empty unless a sync,
        backup, import or lookup has something to say. The data-root path that used
        to sit here permanently is in Settings and About.

        `extra` is what's running or just finished (callers prefix it with " · ",
        from when it trailed the path). A message ending in "…" is in progress and
        stays until replaced; a result lingers briefly, then clears."""
        # (The old "derived rollups not found" note is gone too: launch syncs, and
        # the sync rebuilds them, so it only ever flashed on a fresh store.)
        msg = "  ·  ".join(p.strip() for p in extra.split("·") if p.strip())
        bar = self.statusBar()
        if not msg:
            bar.clearMessage()
        elif msg.endswith("…"):
            bar.showMessage(msg)
        else:
            bar.showMessage(msg, self.STATUS_LINGER_MS)

    # ---- import / prefs ----
    def _open_ingest(self):
        # Import is now a top-level page (was a modal dialog) — navigate to it and
        # let the user refresh the source list (a device may have just mounted).
        self.go_to(self._import_index)
        self.import_page.reload()

    def _open_prefs(self):
        from m110.ui.preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    def _open_about(self):
        from m110.ui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def _open_report(self):
        from m110.ui.error_report import ErrorReportDialog, build_report
        ErrorReportDialog(build_report(), is_crash=False, parent=self).exec()

    def _open_user_guide(self):
        """Help → User guide — open the guide **for this build** in the browser.

        Pinned to the release tag, not `main`: `docs/` on main describes unshipped
        work, so a user following it hits features they do not have."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(updates.user_guide_url()))

    # ---- update check ----
    def _maybe_check_updates(self):
        """Quiet launch check — only when the window is live (`_ready`) and enabled
        and not run within ~24h. The `_ready` gate matters: this is a **network**
        QThread, so a short-lived window (a test or an offscreen screenshot that sets
        `_ready = False` to neuter launch work) must not spawn it — otherwise the
        process can exit with the thread still running and Qt aborts (SIGABRT →
        macOS "Python quit unexpectedly"). Mirrors the `_do_refresh` guard."""
        if self._ready and updates.should_check():
            self._start_update_check(record=True, manual=False)

    def _check_updates(self):
        """Help → Check for updates — always runs, ignores throttle + skip."""
        self._start_update_check(record=False, manual=True)

    def _start_update_check(self, *, record: bool, manual: bool):
        if self._update_worker is not None:      # one at a time
            return
        self._update_worker = UpdateCheckWorker(self, record=record)
        self._update_worker.done.connect(
            lambda info: self._on_update_checked(info, manual))
        self._update_worker.start()

    def _on_update_checked(self, info, manual: bool):
        self._update_worker = None
        if manual:
            from m110.ui.update_notice import show_manual_result
            show_manual_result(self, info)
            return
        # Launch check: only nudge for a newer, non-skipped release.
        if info is not None and info.is_newer and not updates.is_skipped(info.latest):
            self._show_update_banner(info)

    def _show_update_banner(self, info):
        from m110.ui.update_notice import UpdateBanner
        if self._banner is not None:
            self._banner.deleteLater()
        self._banner = UpdateBanner(info, self)
        self._content_layout.insertWidget(0, self._banner)

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
        slots = backup.load_slots()
        RestoreDialog([(backup.SLOT_LABELS[n], slots[n].destination)
                       for n in backup.SLOTS], self).exec()

    # ---- auto backup (opt-in; background; unobtrusive) ----
    # Two triggers, both off the UI thread and cancel-on-quit: a launch check
    # (back up if the last snapshot is older than the interval) and an hourly tick
    # that fires the daily 02:00 backup so a long-running session still gets daily
    # snapshots. Each checks both slots; the due ones queue and run **one at a
    # time** — the engine allows a single run per process (`backup._RUN_LOCK`), so
    # starting the cloud run beside the local one would just fail it.
    def _maybe_auto_backup(self, *, scheduled: bool = False):
        if self._backup_worker is not None or self._backup_queue:
            return
        from m110 import backup
        check = (backup.due_for_scheduled_backup if scheduled
                 else backup.due_for_auto_backup)
        due = []
        for slot in backup.configured_slots():
            try:
                if check(slot):
                    due.append(slot)
            except Exception:
                continue
        self._backup_queue = due
        self._backup_notes = []
        self._run_next_auto_backup()

    def _run_next_auto_backup(self):
        if not self._backup_queue:
            return
        from m110 import backup
        slot = self._backup_queue.pop(0)
        self._backup_cancel = threading.Event()
        self._show_backup_status(f"Backing up to {backup.SLOT_LABELS[slot]}…")
        self._backup_worker = _BackupBgWorker(slot, self._backup_cancel, self)
        self._backup_worker.done.connect(self._on_auto_backup_done)
        self._backup_worker.failed.connect(self._on_auto_backup_failed)
        self._backup_worker.start()

    def _on_auto_backup_done(self, res: dict):
        from m110 import backup
        label = backup.SLOT_LABELS.get(self._backup_worker.slot, "")
        self._clear_backup_worker()
        if res.get("cancelled"):
            self._backup_queue = []
            self._update_status()
            return
        self._backup_notes.append(
            f"Backed up {res.get('file_count', 0)} files to {label}")
        self._show_backup_status()
        self._run_next_auto_backup()

    def _on_auto_backup_failed(self, msg: str):
        from m110 import backup
        label = backup.SLOT_LABELS.get(self._backup_worker.slot, "")
        self._clear_backup_worker()
        self._backup_notes.append(f"{label} backup skipped")
        self._show_backup_status()
        # One slot failing (a bucket unreachable offline) says nothing about the
        # other; carry on with the queue.
        self._run_next_auto_backup()

    def _show_backup_status(self, running: str = ""):
        """This round's results so far, then what's running — so "Local backup
        skipped" isn't overwritten the instant the cloud run starts."""
        parts = self._backup_notes + ([running] if running else [])
        self._update_status(extra="".join(f"  ·  {p}" for p in parts))

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
        # Undo must not rewrite the store under the open editor.
        self.undo_action.setEnabled(not editing and self.undo_stack.canUndo())
        self.redo_action.setEnabled(not editing and self.undo_stack.canRedo())
        for act in self.view_actions:      # else Ctrl+1..8 walks around the lock
            act.setEnabled(not editing)
        self._update_object_menu()

    def _on_notes_saved(self, _slug: str):
        # Object Notes were edited in the detail pane — reload the other views (the
        # Journal feed especially) so the new text shows without a manual Refresh.
        # Lightweight: no scan/derive/render worker (a text edit adds no images).
        self._reload_secondary_pages()

    def _reload_secondary_pages(self):
        # Lightweight reload of every page but the Catalog (which updates itself in
        # place) — used for changes with no image impact (notes edit).
        for p in self.pages:
            if p is not self.catalog:
                p.reload()

    def _on_devices_changed(self):
        # The Devices page renamed or retired a telescope, made one the planning
        # telescope, or changed its limits — every other page re-reads telescopes
        # (Planning's picker and ranking, the session tables' Device column).
        for p in self.pages:
            if p is not self.devices:
                p.reload()

    def _on_goals_changed(self):
        # An integration goal or a goal's telescope changed. Derived data was already
        # rebuilt (no scan), so every page — the Library's pills included — reloads.
        for p in self.pages:
            p.reload()

    def _on_pins_changed(self):
        # A Pin/Deprioritize override toggled (Library, Goals, or the Summary priority
        # view). No scan/derive — just
        # refresh the markers/priority list everywhere. Catalog.reload() would no-op
        # (cat/totals unchanged), so refresh its markers explicitly (#3).
        for p in self.pages:
            if p is self.catalog:
                self.catalog.reload_pins()
            else:
                p.reload()

    def _prepare_working_folders(self):
        if self.catalog.is_editing() or self._refreshing:
            return
        self._prep_feedback = True
        self._do_refresh()

    def _open_media_cleanup(self):
        """Library › Clean Up Imported Sidecars. Preview-then-confirm; the Media
        scope reloads afterwards only if something was actually removed."""
        if self.catalog.is_editing() or self._refreshing:
            return
        from m110.ui.media_cleanup_dialog import MediaCleanupDialog
        dlg = MediaCleanupDialog(self)
        dlg.exec()
        if dlg.removed_count():
            self.media_page.reload()

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
                "This sends each object's name to Simbad and needs a network "
                "connection."
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
        self.nav.restyle()
        self.header.restyle()
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
        self._apply_refresh(summary)

    def _apply_refresh(self, summary: dict):
        """Rebuild every page from the refreshed store — but **never** while a modal
        dialog or popup menu is up.

        `reload()` deletes and re-creates widgets (the Library table, the whole
        detail pane incl. its gallery views). A modal runs a nested event loop, so
        a `deleteLater()` issued from inside one takes effect while the C++ handler
        that opened it is still on the stack — Qt then resumes in a freed widget.
        That is the 0.3.0b3 crash: click back into a backgrounded window (which
        starts this sync), double-click a gallery thumbnail, and the sync lands
        while the image viewer's loop is spinning inside the gallery's own
        `mouseDoubleClickEvent`. Re-check on a timer instead; the pages are only
        rebuilt once the user is back at the main window."""
        if modal_loop_active():
            self._pending_refresh = summary
            self._reload_retry.start()
            return
        self._pending_refresh = None
        if self.catalog.is_editing():
            return                         # editor opened while we waited
        for p in self.pages:
            p.reload()
        self._update_status(extra=recalibrated_message(summary.get("recalibrated")))
        if self._prep_feedback:
            self._prep_feedback = False
            n = summary.get("prepared", 0)
            QMessageBox.information(
                self, "Prepare working folders",
                f"{n} working folder(s) prepared." if n else
                "All objects already have their working folders.")
        # Once the store is consistent, consider a launch-time auto backup (opt-in)
        # and a one-time backup nudge. Both can pop a modal, so only fire them when
        # there's a visible window to show it in — a refresh that completes with no
        # window shown (headless tests) must not open a stray modal (it double-frees
        # on Linux Qt). Production always show()s the window before events pump.
        self._refresh_assistant_banner()
        if self.isVisible():
            if not self._auto_backup_checked:
                self._auto_backup_checked = True
                self._maybe_auto_backup()
            self._maybe_backup_nudge()

    def _retry_pending_refresh(self):
        """The deferred rebuild, re-attempted once the modal is (hopefully) gone."""
        if self._pending_refresh is not None:
            self._apply_refresh(self._pending_refresh)

    def _refresh_assistant_banner(self):
        """Re-read the assistant outbox; the banner shows itself if non-empty."""
        banner = getattr(self, "_assistant_banner", None)
        if banner is not None:
            banner.refresh()

    def _review_assistant_items(self):
        """The banner's Review — a modal, because applying a change deserves a
        focused confirm. Triggered by intent, never by the app's lifecycle."""
        from m110.ui.assistant_review import AssistantReviewDialog
        dlg = AssistantReviewDialog(self)
        dlg.changed.connect(self._refresh_assistant_banner)
        dlg.exec()
        self._refresh_assistant_banner()
        # Accepting a plan or applying a pin changes what the pages show.
        page = self.stack.currentWidget()
        if hasattr(page, "reload"):
            page.reload()

    def _maybe_backup_nudge(self):
        """Once ever (and only once the user has captures worth losing), nudge a
        fresh beta user to set up a backup — beta software + irreplaceable data.
        Skipped when a backup destination is already configured (nothing to nudge)."""
        if config.get_setting("backup_nudge_seen", False):
            return
        from m110 import backup
        if backup.configured_slots():           # backups already set up → no nudge
            return
        if not derived.totals_by_slug():        # nothing captured yet → nothing to lose
            return
        config.save_setting("backup_nudge_seen", True)   # show at most once
        resp = QMessageBox.question(
            self, "Back up your library",
            "M110 is beta software, and your captures are irreplaceable.\n\n"
            "Set up a backup of your library now? (You can also do this any time "
            "from File › Back Up….)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resp == QMessageBox.Yes:
            self._open_backup()

    def _on_refresh_failed(self, msg: str):
        self._refreshing = False
        self._last_refresh = time.monotonic()
        self.refresh_action.setEnabled(True)
        self._update_status(extra=f"  ·  Sync failed: {msg}")

    # ---- clean shutdown ----
    def _stop_worker(self) -> None:
        """Block until the refresh thread finishes, so teardown never destroys a
        running QThread (which Qt turns into a fatal abort). The sync is cancelled
        first and stops at its next safe point, so quit no longer waits out a whole
        scan — which every focus-in starts, so Cmd+Q right after clicking into the
        window used to stall for the length of a sync (18 s on a large library)."""
        w = self._worker
        if w is not None and w.isRunning():
            w.cancel.set()
            w.wait()
            if self._refreshing:                # cancelled: it emitted nothing
                self._refreshing = False
                self.refresh_action.setEnabled(True)
        # Cancel + drain a background backup so teardown never destroys a live
        # QThread (create_snapshot aborts promptly and cleans up its temp dir).
        self._backup_queue = []                 # no next slot after quit
        bw = self._backup_worker
        if bw is not None and bw.isRunning():
            if self._backup_cancel is not None:
                self._backup_cancel.set()
            bw.wait()
        # Drain the update-check thread (a quick network fetch) so teardown never
        # destroys a running QThread.
        uw = self._update_worker
        if uw is not None and uw.isRunning():
            uw.wait()

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)


class AppMenuTranslator(QTranslator):
    """Names the hoisted PreferencesRole item **Settings…**, as macOS 13+ does.

    Qt builds the macOS application menu itself and titles that item with its own
    translatable string ("Preferences...", context MAC_APPLICATION_MENU), whatever
    the action's text — so the rename has to happen in translation. Off macOS the
    context is never asked for, so this is inert there.

    Every other string must fall through as **None** (a null QString), never "":
    `QCoreApplication.translate` stops at the first non-*null* answer, so "" is taken
    as the translation and blanks every string Qt supplies itself — the standard
    dialog buttons (Yes/Cancel/OK…), text-field context menus, Hide/Quit M110."""

    def translate(self, context, source, disambiguation=None, n=-1):
        if context == "MAC_APPLICATION_MENU" and source == "Preferences...":
            return "Settings…"
        return None


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
    from m110 import logsetup
    logsetup.setup_logging()            # rotating log at ~/.m110/logs/ (before anything)
    _set_macos_app_name("M110")         # app-menu / dock name (before QApplication)
    app = QApplication(sys.argv)
    from m110.ui import error_report
    error_report.install_excepthook(app)  # crashes → dialog + log, not a hard abort
    app.setApplicationName("M110")
    app.setApplicationDisplayName("M110")
    app.setOrganizationName("M110")
    app.installTranslator(AppMenuTranslator(app))   # "Settings…" in the app menu
    theme.install(app)                  # design-system: tokens → QSS, follow system
    app.setWindowIcon(theme.app_icon())  # dock / taskbar icon (parchment tile)
    from m110.ui.first_run_dialog import run_first_run_if_needed
    run_first_run_if_needed()            # first launch: prompt for a data folder
    from m110 import running_app
    running_app.record()                 # so the assistant names THIS install's m110-stack
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

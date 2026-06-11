"""M110 — PySide6 desktop shell.

v0.1 Library. Left: the catalog joined with derived totals (capture status).
Right: detail pane for the selected object. The Library keeps itself in sync with
disk automatically — it refreshes on launch, after every ingest, and whenever the
window regains focus (so external changes, e.g. a Siril stack, show up too).
Refresh re-runs the ported scan+derive+render computation; there's a manual
Refresh (View menu / Ctrl+R) but you shouldn't normally need it.
"""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import (
    QColor, QPixmap, QIcon, QAction, QKeySequence, QFontDatabase,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QLabel,
    QSplitter, QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QListWidget,
    QListWidgetItem, QScrollArea, QPlainTextEdit, QPushButton, QMessageBox,
    QInputDialog,
)

from m110 import config, derived, objects
from m110.catalog import load_catalog, catalog_sort_key

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
STATUS_COLOR = {"deep_stack": QColor("#3fb950"), "initial": QColor("#d29922")}
MUTED = QColor("#8b949e")


def _status_label(status: str | None, captured: bool) -> str:
    if not captured:
        return "—"
    return STATUS_LABEL.get(status, status or "—")


class _NumItem(QTableWidgetItem):
    """Table item that sorts by an arbitrary key (number or tuple)."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self._key < other._key
        return super().__lt__(other)


class RefreshWorker(QThread):
    """Runs the (potentially slow) scan+derive off the UI thread."""
    done = Signal(dict)
    failed = Signal(str)

    def run(self):
        try:
            from m110.refresh import run_refresh
            self.done.emit(run_refresh())
        except Exception as exc:  # surface to the UI rather than crash
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DetailPane(QScrollArea):
    # Emitted when the journal editor opens/closes so the window can lock the
    # table + actions (prevents losing in-progress edits to a selection change
    # or an auto-refresh).
    editing_changed = Signal(bool)
    # Emitted when the user asks to prepare a captured object for processing;
    # the window resolves the capture target(s) and opens the dialog.
    prepare_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._current = None        # (slug, e, t) of the shown object
        self._editing = False
        self.placeholder()

    def is_editing(self) -> bool:
        return self._editing

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def placeholder(self):
        self._current = None
        self._clear()
        self._lay.addWidget(QLabel("Select an object to see details."))

    def show_object(self, slug: str, e: dict, t: dict):
        self._current = (slug, e, t)
        self._editing = False
        self._clear()
        captured = bool(t)

        title = QLabel(f"<h2>{e.get('id', '')} &mdash; {e.get('name') or ''}</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)

        bits = [str(e.get("type") or "").replace("_", " ")]
        if e.get("magnitude") is not None:
            bits.append(f"mag {e['magnitude']}")
        if e.get("size"):
            bits.append(str(e["size"]))
        if e.get("season"):
            bits.append(str(e["season"]))
        meta = QLabel(" · ".join(b for b in bits if b))
        meta.setStyleSheet("color:#8b949e")
        self._lay.addWidget(meta)

        if captured:
            self._lay.addWidget(QLabel(
                f"<b>{_status_label(t.get('status'), True)}</b> · "
                f"{t.get('integration_hms', '')} · "
                f"{t.get('session_count', '')} sessions · "
                f"{t.get('frames', '')} frames"))
            prep_btn = QPushButton("Prepare for processing…")
            prep_btn.setToolTip("Arrange a Siril working folder (per-filter split "
                                "+ Naztronomy preset) for this object")
            prep_btn.clicked.connect(lambda: self.prepare_requested.emit(slug))
            self._lay.addWidget(prep_btn, alignment=Qt.AlignLeft)
        else:
            self._lay.addWidget(QLabel("<i>not captured</i>"))

        hp = objects.hero_path(slug)
        if hp:
            pm = QPixmap(str(hp))
            if not pm.isNull():
                lbl = QLabel()
                lbl.setPixmap(pm.scaledToWidth(min(pm.width(), 520),
                                               Qt.SmoothTransformation))
                self._lay.addWidget(lbl)

        fm, body = objects.read_journal(slug)
        if fm.get("hero_caption"):
            cap = QLabel(fm["hero_caption"])
            cap.setWordWrap(True)
            cap.setStyleSheet("color:#8b949e; font-size:11px")
            self._lay.addWidget(cap)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Journal</b>"))
        header.addStretch(1)
        edit_btn = QPushButton("Edit")
        edit_btn.setToolTip("Edit this object's journal (Objects/<id>/journal.md)")
        edit_btn.clicked.connect(self._enter_edit)
        header.addWidget(edit_btn)
        self._lay.addLayout(header)
        if body.strip():
            tb = QTextBrowser()
            tb.setMarkdown(body)
            tb.setOpenExternalLinks(True)
            tb.setMinimumHeight(220)
            self._lay.addWidget(tb)
        else:
            empty = QLabel("<i>No notes yet — click Edit to start.</i>")
            empty.setStyleSheet("color:#8b949e")
            self._lay.addWidget(empty)

        # show anything we managed to thumbnail — including FITS stacks
        imgs = [im for im in derived.images_for(slug) if im.get("thumb")]
        if imgs:
            self._lay.addWidget(QLabel(f"<b>Gallery</b> ({len(imgs)})"))
            gallery = QListWidget()
            gallery.setViewMode(QListWidget.IconMode)
            gallery.setIconSize(QSize(140, 140))
            gallery.setResizeMode(QListWidget.Adjust)
            gallery.setMovement(QListWidget.Static)
            gallery.setMaximumHeight(190)
            for im in imgs:
                if not im.get("thumb"):
                    continue
                tp = config.RENDERS_DIR / im["thumb"]
                if tp.is_file():
                    gallery.addItem(QListWidgetItem(
                        QIcon(str(tp)), im.get("display_name") or im.get("name") or ""))
            self._lay.addWidget(gallery)

        self._lay.addStretch(1)

    # ---- journal editing ----
    def _enter_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        self._editing = True
        self.editing_changed.emit(True)
        self._clear()

        self._lay.addWidget(QLabel(
            f"<b>Editing journal</b> &mdash; {e.get('id', '')} "
            f"&middot; <code>Objects/{objects.object_folder_name(slug)}/journal.md</code>"))

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(objects.read_journal_text(slug))
        self._editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._editor.setMinimumHeight(360)
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._lay.addWidget(self._editor)

        hint = QLabel("Frontmatter between the <code>---</code> fences feeds the "
                      "gallery (name / hero_caption / hero); everything below is Markdown.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e; font-size:11px")
        self._lay.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel_edit)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save_edit)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        self._lay.addLayout(buttons)
        self._lay.addStretch(1)
        self._editor.setFocus()

    def _save_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        objects.write_journal(slug, self._editor.toPlainText())
        self._editing = False
        self.editing_changed.emit(False)
        self.show_object(slug, e, t)   # re-render with the saved notes

    def _cancel_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        self._editing = False
        self.editing_changed.emit(False)
        self.show_object(slug, e, t)


class MainWindow(QMainWindow):
    HEADERS = ["Object", "Name", "Type", "Season", "Mag",
               "Status", "Integration", "Sessions"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("M110 — Library")
        self._worker = None
        self._ready = False        # guards auto-refresh until init completes
        self._refreshing = False
        self._last_refresh = 0.0

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No catalog found at:\n{config.CATALOG_TOML}\n\n"
                f"Set M110_DATA_ROOT to your data folder."))
            self.resize(560, 160)
            return

        self._cat = load_catalog()
        self._totals = derived.totals_by_slug()

        self.table = self._build_table()
        self.table.itemSelectionChanged.connect(self._on_select)
        self.detail = DetailPane()
        self.detail.editing_changed.connect(self._on_editing_changed)
        self.detail.prepare_requested.connect(self._on_prepare)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([520, 440])
        self.setCentralWidget(self.splitter)

        toolbar = self.addToolBar("Main")
        self.ingest_action = QAction("Ingest…", self)
        self.ingest_action.setShortcut("Ctrl+I")
        self.ingest_action.triggered.connect(self._open_ingest)
        toolbar.addAction(self.ingest_action)

        # The Library auto-syncs (launch / focus / after ingest), so manual
        # Refresh lives in the menu as an override rather than a primary button.
        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setShortcut("Ctrl+R")
        self.refresh_action.triggered.connect(self._do_refresh)
        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut(QKeySequence.Preferences)  # Cmd+, on macOS
        prefs_action.triggered.connect(self._open_prefs)
        menu = self.menuBar().addMenu("M110")
        menu.addAction(self.refresh_action)
        menu.addAction(prefs_action)

        self._update_status()
        self.resize(1080, 700)
        self._ready = True
        QTimer.singleShot(0, self._do_refresh)  # auto-refresh on launch

    def _open_prefs(self):
        from m110.ui.preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    # ---- data / table ----
    def _build_table(self) -> QTableWidget:
        cat, totals = self._cat, self._totals
        table = QTableWidget(len(cat), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)

        rows = sorted(cat.items(), key=lambda kv: catalog_sort_key(kv[1].get("id", "")))
        for row, (slug, e) in enumerate(rows):
            t = totals.get(slug, {})
            captured = bool(t)

            obj = _NumItem(str(e.get("id", "")), catalog_sort_key(e.get("id", "")))
            obj.setData(Qt.UserRole, slug)
            table.setItem(row, 0, obj)
            table.setItem(row, 1, QTableWidgetItem(str(e.get("name") or "")))
            table.setItem(row, 2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            table.setItem(row, 3, QTableWidgetItem(str(e.get("season") or "")))

            mag = e.get("magnitude")
            table.setItem(row, 4, _NumItem("" if mag is None else f"{mag}",
                                           float(mag) if mag is not None else 99.0))

            status_item = QTableWidgetItem(_status_label(t.get("status"), captured))
            status_item.setForeground(STATUS_COLOR.get(t.get("status"), MUTED))
            table.setItem(row, 5, status_item)

            integ_min = float(t.get("integration_min", 0) or 0)
            table.setItem(row, 6, _NumItem(t.get("integration_hms", "") if captured else "", integ_min))
            sc = int(t.get("session_count", 0) or 0)
            table.setItem(row, 7, _NumItem(str(sc) if captured else "", float(sc)))

            if not captured:
                for c in range(len(self.HEADERS)):
                    if c != 5:
                        table.item(row, c).setForeground(MUTED)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.AscendingOrder)  # default: natural M1,M2,…
        return table

    def _rebuild_table(self):
        """Rebuild the table widget from current self._cat/_totals, preserving
        the user's selected object across the swap."""
        prev = self._selected_slug()
        new_table = self._build_table()
        new_table.itemSelectionChanged.connect(self._on_select)
        old = self.splitter.replaceWidget(0, new_table)
        self.table = new_table
        if old is not None:
            old.deleteLater()
        self.splitter.setSizes([520, 440])
        if not (prev and self._select_slug(prev)):
            self.detail.placeholder()
        self._update_status()

    def _selected_slug(self):
        items = self.table.selectedItems()
        return self.table.item(items[0].row(), 0).data(Qt.UserRole) if items else None

    def _select_slug(self, slug) -> bool:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == slug:
                self.table.selectRow(r)
                return True
        return False

    def _update_status(self, extra: str = ""):
        captured = sum(1 for s in self._cat if s in self._totals)
        note = "" if derived.derived_available() else " · derived rollups not found"
        self.statusBar().showMessage(
            f"{captured}/{len(self._cat)} captured · {config.DATA_ROOT}{note}{extra}")

    # ---- selection ----
    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        slug = self.table.item(items[0].row(), 0).data(Qt.UserRole)
        self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))

    # ---- ingest ----
    def _open_ingest(self):
        from m110.ui.ingest_dialog import IngestDialog
        dlg = IngestDialog(self)
        dlg.ingested.connect(self._on_ingested)
        dlg.exec()

    def _on_ingested(self, moved: int):
        # new files landed → recompute so they appear (guarded; no-op if already
        # refreshing). Runs even if moved==0 is harmless.
        if moved:
            self._do_refresh()

    # ---- auto-refresh (launch / focus / mutation) ----
    def changeEvent(self, event):
        super().changeEvent(event)
        # Window regained focus → sync with disk (catches external changes like a
        # Siril stack or a dropped Finished Image). Debounced so it doesn't fire
        # right after the launch refresh or on rapid window switches.
        if (event.type() == QEvent.ActivationChange and self.isActiveWindow()
                and self._ready and not self._refreshing
                and time.monotonic() - self._last_refresh > 2.0):
            self._do_refresh()

    def _on_editing_changed(self, editing: bool):
        # Lock the table + actions while a journal edit is open, so a selection
        # change or auto-refresh can't discard in-progress edits.
        self.table.setEnabled(not editing)
        self.ingest_action.setEnabled(not editing)
        self.refresh_action.setEnabled(not editing)

    # ---- processing-prep ----
    def _on_prepare(self, slug: str):
        totals = derived.load_totals()
        by_folder = totals.get("by_folder", {})
        targets = [f for f, info in by_folder.items()
                   if slug in info.get("slugs", [])]

        def _has_lights(t: str) -> bool:
            d = config.lights_dir(t)
            return d.is_dir() and any(p.suffix.lower() == ".fit" for p in d.iterdir())

        targets = [t for t in targets if _has_lights(t)]
        if not targets:
            QMessageBox.information(
                self, "Nothing to prepare",
                "This object has no raw light frames to arrange for Siril.\n"
                "(Targets with only Seestar in-app stacks can't be Siril-prepped.)")
            return
        if len(targets) == 1:
            target = targets[0]
        else:
            target, ok = QInputDialog.getItem(
                self, "Choose capture target",
                "This object maps to multiple capture targets:",
                sorted(targets), 0, False)
            if not ok:
                return

        proc = derived.load_processing().get("folders", {}).get(target, {})
        stack_meta = proc.get("stack_meta") or {}
        usable = stack_meta.get("stack_frames")
        star = bool(proc.get("star_removal"))

        from m110.ui.processing_dialog import ProcessingDialog
        ProcessingDialog(target, usable_frames=usable, star_removal=star,
                         parent=self).exec()

    def _do_refresh(self):
        if not self._ready or self._refreshing or self.detail.is_editing():
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
        if self.detail.is_editing():
            # A refresh that finished while the journal editor is open must not
            # rebuild the table / re-render the detail (it would discard edits).
            # Leave actions locked; the next sync after editing picks up changes.
            return
        self.refresh_action.setEnabled(True)
        new_cat = load_catalog()
        new_totals = derived.totals_by_slug()
        changed = (new_totals != self._totals) or (new_cat != self._cat)
        self._cat, self._totals = new_cat, new_totals
        if changed:
            self._rebuild_table()          # preserves selection
        else:
            self._refresh_open_detail()    # cheap: pick up image-only changes
            self._update_status()

    def _on_refresh_failed(self, msg: str):
        self._refreshing = False
        self._last_refresh = time.monotonic()
        self.refresh_action.setEnabled(True)
        self._update_status(extra=f"  ·  Sync failed: {msg}")

    def _refresh_open_detail(self):
        slug = self._selected_slug()
        if slug and slug in self._cat:
            self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("M110")
    config.ensure_data_root()  # create + seed the data folder if needed
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Restore dialog — pick a snapshot, select paths, and either extract them to a
folder (the safe default, never touches the live store) or restore them back into
the store behind a conflict preview + confirm. Also verifies snapshot integrity.

Preview-then-confirm, like ingest/import: a restore into the store never overwrites
an existing file without an explicit confirmation.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QProgressDialog, QPushButton, QRadioButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from m110 import backup, config

_REL_ROLE = Qt.ItemDataRole.UserRole + 1


class _Worker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, fn, cancel_event, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancel = cancel_event

    def run(self):
        try:
            res = self._fn(should_cancel=self._cancel.is_set,
                           progress=lambda i, t: self.progressed.emit(i, t))
            self.done.emit(res or {})
        except backup.BackupError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class RestoreDialog(QDialog):
    def __init__(self, destination: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore from backup")
        self._destination = Path(destination) if destination else None
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self.resize(620, 560)

        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        layout.setSpacing(s["md"])

        # ── snapshot picker ──
        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel("Snapshot:"))
        self._snap_combo = QComboBox()
        self._snapshots = backup.list_snapshots(self._destination) if self._destination else []
        for snap in self._snapshots:
            # Label how each snapshot is stored. Mixed histories are normal — the
            # format follows the destination, and a share can be remounted with
            # different capabilities. Either way it restores the same.
            if snap.format == backup.FORMAT_POOLED:
                kind = "  ·  pooled"
            elif not snap.hardlinks:
                kind = "  ·  full copy"
            else:
                kind = ""
            self._snap_combo.addItem(
                f"{snap.created:%Y-%m-%d %H:%M}  ·  {snap.file_count} files{kind}",
                snap.path)
        self._snap_combo.currentIndexChanged.connect(self._reload_tree)
        snap_row.addWidget(self._snap_combo, 1)
        self._verify_btn = QPushButton("Verify integrity")
        self._verify_btn.clicked.connect(self._do_verify)
        snap_row.addWidget(self._verify_btn)
        layout.addLayout(snap_row)

        layout.addWidget(QLabel("Choose what to restore:"))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        layout.addWidget(self._tree, 1)

        # ── target ──
        self._to_folder = QRadioButton("Extract to a folder (leaves your Library untouched)")
        self._to_folder.setChecked(True)
        self._to_store = QRadioButton("Restore into the Library store")
        layout.addWidget(self._to_folder)
        store_row = QHBoxLayout()
        store_row.addWidget(self._to_store)
        store_row.addStretch(1)
        layout.addLayout(store_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Folder:"))
        self._out = QLabel(str(Path.home() / "M110 Restore"))
        self._out.setProperty("muted", True)
        self._out_path = Path.home() / "M110 Restore"
        folder_row.addWidget(self._out, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        self._folder_widget = QWidget()
        self._folder_widget.setLayout(folder_row)
        layout.addWidget(self._folder_widget)
        self._to_store.toggled.connect(
            lambda on: self._folder_widget.setDisabled(on))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self._restore_btn = buttons.addButton("Restore", QDialogButtonBox.AcceptRole)
        self._restore_btn.clicked.connect(self._do_restore)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if not self._snapshots:
            self._restore_btn.setEnabled(False)
            self._verify_btn.setEnabled(False)
            layout.insertWidget(1, QLabel("<i>No backups found at this destination.</i>"))
        else:
            self._reload_tree()

    # ---- tree ----
    def _current_snapshot(self) -> Path | None:
        return self._snap_combo.currentData()

    def _reload_tree(self):
        self._tree.clear()
        snap = self._current_snapshot()
        if snap is None:
            return
        nodes: dict[str, QTreeWidgetItem] = {}
        for rel in sorted(backup.snapshot_files(snap)):
            parts = rel.split("/")
            parent = None
            path_so_far = ""
            for depth, part in enumerate(parts):
                path_so_far = f"{path_so_far}/{part}" if path_so_far else part
                key = path_so_far
                if key not in nodes:
                    item = (QTreeWidgetItem([part]) if parent is None
                            else QTreeWidgetItem(parent, [part]))
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable
                                  | Qt.ItemIsAutoTristate)
                    item.setCheckState(0, Qt.Unchecked)
                    is_file = depth == len(parts) - 1
                    if is_file:
                        item.setData(0, _REL_ROLE, rel)
                    if parent is None:
                        self._tree.addTopLevelItem(item)
                    nodes[key] = item
                parent = nodes[key]
        self._tree.expandToDepth(0)

    def _selected_relpaths(self) -> list[str]:
        out = []
        it = self._tree.invisibleRootItem()

        def walk(node):
            for i in range(node.childCount()):
                child = node.child(i)
                rel = child.data(0, _REL_ROLE)
                if rel and child.checkState(0) == Qt.Checked:
                    out.append(rel)
                walk(child)

        walk(it)
        return out

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Extract to folder", str(self._out_path))
        if d:
            self._out_path = Path(d)
            self._out.setText(d)

    # ---- verify ----
    def _do_verify(self):
        snap = self._current_snapshot()
        if snap is None:
            return
        self._run(lambda **kw: backup.verify(snap, **kw), self._on_verify_done,
                  "Verifying…")

    def _on_verify_done(self, res):
        if res.get("cancelled"):
            return
        if res.get("ok"):
            QMessageBox.information(self, "Integrity OK",
                                   f"All {res.get('checked', 0)} files match their "
                                   "checksums — this backup is intact.")
        else:
            bad = res.get("mismatched", [])
            miss = res.get("missing", [])
            QMessageBox.warning(
                self, "Integrity problems",
                f"{len(bad)} file(s) changed/corrupted, {len(miss)} missing.\n\n"
                + "\n".join((bad + miss)[:10])
                + ("\n…" if len(bad) + len(miss) > 10 else ""))

    # ---- restore ----
    def _do_restore(self):
        snap = self._current_snapshot()
        if snap is None:
            return
        rels = self._selected_relpaths()
        if not rels:
            QMessageBox.information(self, "Restore", "Select at least one file or folder.")
            return
        into_store = self._to_store.isChecked()
        target = config.DATA_ROOT if into_store else self._out_path

        prev = backup.preview_restore(snap, rels, target)
        overwrite = False
        if prev["overwrites"]:
            where = "your Library store" if into_store else "the target folder"
            n = len(prev["overwrites"])
            btn = QMessageBox.question(
                self, "Overwrite existing files?",
                f"{n} selected file(s) already exist in {where} and would be "
                f"overwritten. {len(prev['creates'])} would be newly created.\n\n"
                "Overwrite the existing files?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if btn == QMessageBox.Cancel:
                return
            overwrite = btn == QMessageBox.Yes

        self._run(lambda **kw: backup.restore(snap, rels, target, overwrite=overwrite, **kw),
                  self._on_restore_done, "Restoring…")

    def _on_restore_done(self, res):
        if res.get("cancelled"):
            return
        QMessageBox.information(
            self, "Restore complete",
            f"Restored {res.get('written', 0)} file(s)"
            + (f", skipped {res.get('skipped', 0)} existing." if res.get("skipped")
               else "."))

    # ---- worker plumbing (shared by verify + restore) ----
    def _run(self, fn, on_done, label):
        self._cancel_event = threading.Event()
        pd = QProgressDialog(label, "Cancel", 0, 0, self)
        pd.setWindowTitle(label.rstrip("…"))
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd
        self._set_busy(True)
        self._worker = _Worker(fn, self._cancel_event, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.done.connect(lambda res: self._finish(res, on_done))
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        pd.show()

    def _on_progress(self, i, total):
        if self._progress is not None:
            self._progress.setMaximum(total)
            self._progress.setValue(i)

    def _finish(self, res, on_done):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        on_done(res)

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        QMessageBox.warning(self, "Restore failed", message)

    def _set_busy(self, busy):
        self._restore_btn.setEnabled(not busy)
        self._verify_btn.setEnabled(not busy)

    def _close_progress(self):
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _finish_worker(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _stop_worker(self):
        if self._worker is not None:
            if self._cancel_event is not None:
                self._cancel_event.set()
            if self._worker.isRunning():
                self._worker.wait()
            self._worker.deleteLater()
            self._worker = None

    def reject(self):
        self._stop_worker()
        self._close_progress()
        super().reject()

    def closeEvent(self, event):
        self._stop_worker()
        self._close_progress()
        super().closeEvent(event)

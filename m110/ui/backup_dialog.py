"""Back up dialog — snapshot the store to a destination on a worker thread.

Mirrors `publish_dialog.py`: a `_BackupWorker` (QThread) emits progress/done/failed,
a `threading.Event` backs Cancel, the worker is torn down safely on close. The
destination is pre-seeded from the saved setting so the common case is one click;
Browse only overrides it for an ad-hoc destination, and a successful run saves the
chosen destination back as the new default.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
    QSpinBox, QVBoxLayout,
)

from m110 import backup, config


def _fmt_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit in ("B", "KB") else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


class _BackupWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, options, cancel_event, parent=None):
        super().__init__(parent)
        self._options = options
        self._cancel = cancel_event

    def run(self):
        try:
            res = backup.create_snapshot(
                self._options, should_cancel=self._cancel.is_set,
                progress=lambda i, t: self.progressed.emit(i, t))
            self.done.emit(res)
        except backup.BackupError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class BackupDialog(QDialog):
    backed_up = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Back up Library")
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self.resize(560, 0)

        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        layout.setSpacing(s["md"])
        intro = QLabel(
            "Back up your Library to another drive or folder. Each backup is a "
            "full, browsable copy; unchanged files (your raw frames) are shared "
            "with the previous backup, so repeat backups are fast and small.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ── destination ──
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destination:"))
        self._dest = QLineEdit(str(config.get_setting(backup.SETTING_DEST, "")))
        self._dest.textChanged.connect(self._refresh_status)
        dest_row.addWidget(self._dest, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dest_row.addWidget(browse)
        layout.addLayout(dest_row)

        self._status = QLabel()
        self._status.setProperty("muted", True)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # ── automation + retention ──
        settings_box = QGroupBox("Automation & retention")
        sl = QVBoxLayout(settings_box)
        auto_row = QHBoxLayout()
        self._auto = QCheckBox("Back up automatically")
        self._auto.setChecked(bool(config.get_setting(backup.SETTING_AUTO, False)))
        self._auto.setToolTip(
            "Backs up in the background: at launch if the last one is older than the "
            "interval below, and daily at 02:00 while the app stays running.")
        auto_row.addWidget(self._auto)
        auto_row.addStretch(1)
        self._backup_btn = QPushButton("Back up now")
        self._backup_btn.clicked.connect(self._do_backup)
        auto_row.addWidget(self._backup_btn)
        sl.addLayout(auto_row)

        auto_hint = QLabel("Runs at launch and daily at 02:00 while the app is open.")
        auto_hint.setProperty("muted", True)
        sl.addWidget(auto_hint)

        iv_row = QHBoxLayout()
        iv_row.addWidget(QLabel("…at most once every"))
        self._interval = QSpinBox()
        self._interval.setRange(1, 24 * 30)
        self._interval.setSuffix(" h")
        self._interval.setValue(int(config.get_setting(
            backup.SETTING_INTERVAL, backup.DEFAULT_INTERVAL_HOURS)))
        iv_row.addWidget(self._interval)
        iv_row.addStretch(1)
        sl.addLayout(iv_row)

        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Keep newest"))
        self._keep = QSpinBox()
        self._keep.setRange(0, 999)
        self._keep.setSpecialValueText("all")     # 0 → "all" (no limit)
        self._keep.setValue(int(config.get_setting(backup.SETTING_KEEP, 0) or 0))
        keep_row.addWidget(self._keep)
        keep_row.addWidget(QLabel("backups"))
        keep_row.addStretch(1)
        sl.addLayout(keep_row)

        free_row = QHBoxLayout()
        free_row.addWidget(QLabel("Keep at least"))
        self._min_free = QDoubleSpinBox()
        self._min_free.setRange(0.0, 1_000_000.0)
        self._min_free.setDecimals(0)
        self._min_free.setSpecialValueText("off")     # 0 → disabled
        self._min_free.setFixedWidth(90)
        self._min_free.setToolTip("Prune the oldest backups to maintain this much "
                                  "free space on the destination. 0 = off.")
        self._min_free.setValue(float(config.get_setting(
            backup.SETTING_MIN_FREE, backup.DEFAULT_MIN_FREE_GB)))
        free_row.addWidget(self._min_free)
        free_row.addWidget(QLabel("GB free on the destination volume"))
        free_row.addStretch(1)
        sl.addLayout(free_row)
        layout.addWidget(settings_box)

        buttons = QDialogButtonBox()
        self._restore_btn = buttons.addButton("Restore…", QDialogButtonBox.ActionRole)
        self._restore_btn.clicked.connect(self._open_restore)
        save_btn = buttons.addButton("Save", QDialogButtonBox.AcceptRole)
        save_btn.clicked.connect(self._save_and_close)
        buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_status()

    # ---- helpers ----
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose backup destination",
                                             self._dest.text() or str(Path.home()))
        if d:
            self._dest.setText(d)

    def _refresh_status(self):
        dest = self._dest.text().strip()
        if not dest or not Path(dest).is_dir():
            self._status.setText("Choose a destination folder (an external drive or "
                                 "network share).")
            return
        snaps = backup.list_snapshots(Path(dest))
        if not snaps:
            self._status.setText("No backups here yet.")
            return
        newest = snaps[0]
        note = "" if newest.hardlinks else "  ⚠ this destination can't share files " \
            "between backups — each backup will be a full copy."
        self._status.setText(
            f"{len(snaps)} backup(s) · latest {newest.created:%Y-%m-%d %H:%M} · "
            f"{_fmt_bytes(newest.total_bytes)}{note}")

    def _persist_settings(self, dest: str):
        config.save_setting(backup.SETTING_DEST, dest)
        config.save_setting(backup.SETTING_AUTO, self._auto.isChecked())
        config.save_setting(backup.SETTING_INTERVAL, self._interval.value())
        config.save_setting(backup.SETTING_KEEP, self._keep.value() or None)
        # Store 0 explicitly ("off"); an absent key is what triggers the 100 GB
        # default, so we must persist the user's 0 rather than collapse it to None.
        config.save_setting(backup.SETTING_MIN_FREE, self._min_free.value())

    def _open_restore(self):
        from m110.ui.restore_dialog import RestoreDialog
        RestoreDialog(self._dest.text().strip(), self).exec()
        self._refresh_status()

    def _save_and_close(self):
        """Persist the destination + automation/retention settings without running a
        backup, then close. (A manual "Back up now" also persists, but the user must
        be able to change the interval etc. without triggering a snapshot.)"""
        self._persist_settings(self._dest.text().strip())
        self.accept()

    # ---- run ----
    def _do_backup(self):
        dest = self._dest.text().strip()
        if not dest:
            QMessageBox.warning(self, "Back up", "Choose a destination folder.")
            return
        self._persist_settings(dest)
        options = backup.options_from_settings(Path(dest))

        self._cancel_event = threading.Event()
        pd = QProgressDialog("Backing up…", "Cancel", 0, 0, self)
        pd.setWindowTitle("Backing up")
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd

        self._backup_btn.setEnabled(False)
        self._worker = _BackupWorker(options, self._cancel_event, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        pd.show()

    def _on_progress(self, i, total):
        if self._progress is not None:
            self._progress.setLabelText(f"Backing up… {i}/{total} files")
            self._progress.setMaximum(total)
            self._progress.setValue(i)

    def _on_done(self, result):
        self._finish_worker()
        self._close_progress()
        if result.get("cancelled"):
            self._backup_btn.setEnabled(True)
            return
        self.backed_up.emit(result)
        self._refresh_status()
        self._backup_btn.setEnabled(True)
        new = result.get("bytes_new", 0)
        msg = QMessageBox(self)
        msg.setWindowTitle("Backed up")
        pruned = result.get("pruned", 0)
        extra = f"\nPruned {pruned} old backup(s)." if pruned else ""
        msg.setText(f"Backed up {result.get('file_count', 0)} files "
                    f"({_fmt_bytes(new)} new) to:\n{result.get('snapshot', '')}{extra}")
        open_btn = msg.addButton("Open folder", QMessageBox.AcceptRole)
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn:
            self._open_folder(result.get("snapshot", ""))

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        QMessageBox.warning(self, "Backup failed", message)
        self._backup_btn.setEnabled(True)

    @staticmethod
    def _open_folder(path: str):
        import subprocess
        import sys
        if not path:
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform.startswith("win"):
                import os
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    # ---- teardown ----
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

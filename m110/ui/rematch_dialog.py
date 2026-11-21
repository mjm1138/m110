"""Re-match Calibration — bring one object's Siril sandbox up to date with the
calibration library, on demand.

Sync does this by itself whenever the library (or the matching rules) changed
since a sandbox was set up (`processing.rematch_calibration`); this is the manual
way, for one target, and it always re-plans. Strictly preview-then-confirm: the
read-only `siril.plan_rematch` runs on a worker behind modal progress with Cancel,
the dialog lists what would change, and only **Re-match** writes
(`siril.apply_rematch`, on a worker too).
"""
from __future__ import annotations

import html
import threading

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)

from m110 import roundtrip, siril
from m110.ui.widgets import ProgressDialog, drain_worker


class _PlanWorker(QThread):
    done = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, target, cancel_event, parent=None):
        super().__init__(parent)
        self._target = target
        self._cancel = cancel_event

    def run(self):
        try:
            self.done.emit(siril.plan_rematch(self._target, force=True,
                                              should_cancel=self._cancel.is_set))
        except roundtrip.Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ApplyWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, rp, cancel_event, parent=None):
        super().__init__(parent)
        self._rp = rp
        self._cancel = cancel_event

    def run(self):
        try:
            self.done.emit(siril.apply_rematch(self._rp, user=True,
                                               should_cancel=self._cancel.is_set))
        except roundtrip.StackInProgress as exc:
            self.failed.emit(str(exc))       # already a sentence for the user
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def describe(rp) -> str:
    """The dialog's text for a `RematchPlan` (HTML)."""
    t = html.escape(rp.target)
    if rp.status == "none":
        return f"{t} has no Siril working folder with lights to re-match."
    if rp.status == "skipped":
        return (f"<b>{t} can't be re-matched right now:</b> a stack is running in "
                "its working folder, or finished output there is waiting to be "
                "imported. Finish or import it, then try again.")
    if rp.status == "unchanged":
        return (f"{t}'s calibration is already current: the library match is "
                "exactly what is linked. Re-match only records that it was checked.")
    lines = "".join(f"<li>{html.escape(c)}</li>" for c in rp.changes)
    return (f"Re-matching {t} against the calibration library would change:"
            f"<ul>{lines}</ul>Only links M110 made are replaced — the library, "
            "your lights, presets (apart from their darks/flats/biases switches), "
            "process/ and anything you put there are left alone.")


class RematchDialog(QDialog):
    rematched = Signal(str)   # target

    def __init__(self, target: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Re-match Calibration — {target}")
        self.resize(620, 360)
        self._target = target
        self._rp = None
        self._worker = None
        self._progress = None
        self._cancel_event = None

        lay = QVBoxLayout(self)
        self._info = QLabel("Matching against the calibration library…")
        self._info.setWordWrap(True)
        self._info.setTextFormat(Qt.RichText)
        lay.addWidget(self._info, 1)
        row = QHBoxLayout()
        self._apply_btn = QPushButton("Re-match")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._do_apply)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self._apply_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)
        QTimer.singleShot(0, self, self._plan)   # never after the dialog is gone

    # ---- plan (threaded, read-only) ----
    def _plan(self):
        self._make_progress("Matching against the calibration library…", "Re-match")
        self._worker = _PlanWorker(self._target, self._cancel_event, self)
        self._worker.done.connect(self._on_plan_done)
        self._worker.cancelled.connect(self._on_plan_cancelled)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._progress.show()

    def _on_plan_done(self, rp):
        self._finish()
        self._rp = rp
        self._info.setText(describe(rp))
        self._apply_btn.setEnabled(rp.due)

    def _on_plan_cancelled(self):
        self._finish()
        self._info.setText("Cancelled — nothing was changed.")

    def _on_failed(self, msg):
        self._finish()
        self._info.setText(f"Re-match failed: {html.escape(msg)}")

    # ---- apply (threaded, gated) ----
    def _do_apply(self):
        if self._rp is None or not self._rp.due:
            return
        self._apply_btn.setEnabled(False)
        self._make_progress("Re-matching calibration…", "Re-match")
        self._worker = _ApplyWorker(self._rp, self._cancel_event, self)
        self._worker.done.connect(self._on_apply_done)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_apply_done(self, res: dict):
        self._finish()
        if res.get("busy"):
            self._info.setText(describe(siril.RematchPlan(self._target, "skipped")))
            return
        notes = res.get("notes") or []
        if notes:
            self._info.setText("Re-matched. " + " ".join(html.escape(n) for n in notes))
        self.rematched.emit(self._target)
        if not notes:
            self.accept()

    def _on_apply_failed(self, msg):
        self._finish()
        self._apply_btn.setEnabled(True)
        QMessageBox.warning(self, "Re-match failed", msg)

    # ---- progress + worker lifecycle ----
    def _make_progress(self, label, title):
        self._cancel_event = threading.Event()
        pd = ProgressDialog(label, "Cancel", 0, 0, self)
        pd.setWindowTitle(title)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd

    def _close_progress(self):
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _finish(self):
        drain_worker(self._worker)
        self._worker = None
        self._close_progress()

    def _stop(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._finish()

    def reject(self):
        self._stop()
        super().reject()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)


def open_rematch(parent, target: str) -> None:
    """Preview, then confirm, re-matching one target's Siril calibration (the one
    entry point for the Processing page, the Deep Sky right-click menu and the
    Object menu)."""
    dlg = RematchDialog(target, parent)
    dlg.exec()
    dlg.deleteLater()

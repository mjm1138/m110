"""Processing-prep dialog — preview the Siril working layout, then arrange it.

Mirrors the ingest dialog's contract: the plan (`siril.plan_prep`) runs on a
background thread and is **read-only**; nothing is written until the user clicks
Prepare and confirms, at which point `siril.apply_prep` hardlinks the lights and
writes the Naztronomy preset + next-steps. Bundled guidance is viewable inline.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QProgressDialog, QListWidget, QListWidgetItem, QTextBrowser, QGroupBox,
)

from m110 import siril


def _fmt_gb(n: int) -> str:
    gb = n / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{n / (1024 ** 2):.0f} MB"


class _PlanWorker(QThread):
    done = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, target, usable_frames, star_removal, cancel_event, parent=None):
        super().__init__(parent)
        self._args = (target, usable_frames, star_removal)
        self._cancel = cancel_event

    def run(self):
        target, usable, star = self._args
        try:
            plan = siril.plan_prep(target, usable_frames=usable,
                                   star_removal=star,
                                   should_cancel=self._cancel.is_set)
            self.done.emit(plan)
        except siril.PrepCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ApplyWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, plan, cancel_event, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._cancel = cancel_event

    def run(self):
        try:
            res = siril.apply_prep(
                self._plan,
                progress=lambda i, t: self.progressed.emit(i, t),
                should_cancel=self._cancel.is_set)
            self.done.emit(res)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class GuidanceViewer(QDialog):
    """Render a bundled playbook (Markdown) for reference."""

    def __init__(self, doc_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(siril.guidance_title(doc_id))
        self.resize(720, 640)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        p = siril.guidance_path(doc_id)
        tb.setMarkdown(p.read_text() if p.is_file() else "_Guidance not found._")
        tb.setOpenExternalLinks(True)
        lay.addWidget(tb)


class ProcessingDialog(QDialog):
    prepared = Signal(str)   # target name (main window may refresh)

    def __init__(self, target: str, usable_frames=None, star_removal=False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Prepare for processing — {target}")
        self.resize(640, 560)
        self._target = target
        self._usable_frames = usable_frames
        self._star_removal = star_removal
        self._plan = None
        self._worker = None
        self._progress = None
        self._cancel_event = None

        lay = QVBoxLayout(self)
        self._path_lbl = QLabel()
        self._path_lbl.setStyleSheet("color:#8b949e")
        self._path_lbl.setWordWrap(True)
        lay.addWidget(self._path_lbl)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.RichText)
        lay.addWidget(self._summary)

        gbox = QGroupBox("Workflow guidance (double-click to read)")
        gl = QVBoxLayout(gbox)
        self._guidance = QListWidget()
        self._guidance.itemDoubleClicked.connect(self._open_guidance)
        gl.addWidget(self._guidance)
        lay.addWidget(gbox, 1)

        row = QHBoxLayout()
        self._prepare_btn = QPushButton("Prepare…")
        self._prepare_btn.clicked.connect(self._do_prepare)
        self._prepare_btn.setEnabled(False)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self._prepare_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)

        QTimer.singleShot(0, self._scan)

    # ---- plan (threaded, read-only) ----
    def _scan(self):
        self._make_progress("Scanning lights…", 0, "Planning")
        self._worker = _PlanWorker(self._target, self._usable_frames,
                                   self._star_removal, self._cancel_event, self)
        self._worker.done.connect(self._on_plan_done)
        self._worker.cancelled.connect(self._on_plan_cancelled)
        self._worker.failed.connect(self._on_plan_failed)
        self._worker.start()
        self._progress.show()

    def _on_plan_done(self, plan):
        self._finish_worker()
        self._close_progress()
        self._plan = plan
        p = plan.preset
        drizz = (f"drizzle <b>{p['drizzle_amount']}×</b> / pixel "
                 f"<b>{p['pixel_fraction']}</b>" if p["drizzle"]
                 else "<b>no drizzle</b> (1.0×)")
        star = "recommended" if plan.star_removal else "not needed"
        self._path_lbl.setText(f"Working dir: {plan.process_dir}")
        if plan.total_lights == 0:
            self._summary.setText(
                "<b>No raw light frames</b> in this target's <code>lights/</code> "
                "— nothing to prepare. (Seestar-stack-only targets can't be "
                "Siril-prepped.)")
            self._prepare_btn.setEnabled(False)
        else:
            filt_bits = " · ".join(f"{f}: {len(plan.groups[f])}" for f in plan.filters)
            self._summary.setText(
                f"<b>{plan.total_lights}</b> light frame(s) · {_fmt_gb(plan.total_bytes)} "
                f"→ hardlinked, split per filter ({filt_bits}).<br>"
                f"Usable frames: <b>{plan.usable_frames}</b> ({plan.frame_basis}) "
                f"→ {drizz}.<br>"
                f"Naztronomy preset → <code>presets/{siril.PRESET_NAME}</code> "
                f"(auto-loaded by the script).<br>"
                f"Star removal: <b>{star}</b> for this target.")
            self._prepare_btn.setEnabled(True)
        self._guidance.clear()
        for doc_id in plan.guidance:
            it = QListWidgetItem(siril.guidance_title(doc_id))
            it.setData(Qt.UserRole, doc_id)
            self._guidance.addItem(it)

    def _on_plan_cancelled(self):
        self._finish_worker()
        self._close_progress()
        self._summary.setText("Scan cancelled.")

    def _on_plan_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._summary.setText(f"Scan failed: {msg}")

    def _open_guidance(self, item):
        GuidanceViewer(item.data(Qt.UserRole), self).exec()

    # ---- apply (threaded, writes process/, gated) ----
    def _do_prepare(self):
        if not self._plan or self._plan.total_lights == 0:
            return
        n = self._plan.total_lights
        if QMessageBox.question(
                self, "Confirm prepare",
                f"Arrange {n} light frame(s) into a Siril working folder?\n\n"
                f"This hardlinks lights into Images/{self._target}/process/ and "
                f"writes a Naztronomy preset there. Reversible — delete process/.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._prepare_btn.setEnabled(False)
        self._make_progress("Arranging lights…", n, "Preparing")
        self._worker = _ApplyWorker(self._plan, self._cancel_event, self)
        self._worker.progressed.connect(self._on_apply_progress)
        self._worker.done.connect(self._on_apply_done)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_apply_progress(self, i, total):
        if self._progress is not None:
            self._progress.setValue(i)

    def _on_apply_done(self, result: dict):
        self._finish_worker()
        self._close_progress()
        self.prepared.emit(self._target)
        linked = result.get("linked", 0)
        skipped = result.get("skipped", 0)
        cancelled = result.get("cancelled", False)
        bits = [f"{linked} light(s) arranged"]
        if skipped:
            bits.append(f"{skipped} already present")
        prefix = "Cancelled — " if cancelled else ""
        suffix = ("" if cancelled else
                  "  Open Siril in the process/ folder and run the Naztronomy "
                  "script (Load preset). See next-steps.md.")
        self._summary.setText(prefix + ", ".join(bits) + "." + suffix)

    def _on_apply_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._prepare_btn.setEnabled(True)
        QMessageBox.warning(self, "Prepare failed", msg)
        self._summary.setText(f"Prepare failed: {msg}")

    # ---- progress + worker lifecycle (same pattern as ingest) ----
    def _make_progress(self, label, maximum, title):
        self._cancel_event = threading.Event()
        pd = QProgressDialog(label, "Cancel", 0, maximum, self)
        pd.setWindowTitle(title)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd
        return pd

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

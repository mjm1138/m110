"""Export-for-sharing dialog — size a finished image for Reddit/Discord/forums.

Pick a preset (size budget) + a strategy (lossless PNG, or full-resolution
JPEG), then **Export…** opens the native OS save panel so you rename the file
and choose any destination. The size-fitting work runs on a `QThread` worker
behind a modal progress dialog with Cancel; the engine is `m110.webexport`.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QRadioButton, QButtonGroup, QDoubleSpinBox, QProgressDialog, QMessageBox,
    QFileDialog, QWidget,
)

from m110 import config, webexport
from m110.ui.widgets import open_in_default, reveal_in_manager

_MB = 1024 * 1024
_FILTERS = {"png": "PNG image (*.png)", "jpeg": "JPEG image (*.jpg *.jpeg)"}


def _source_info(src: Path) -> str:
    size_mb = src.stat().st_size / _MB
    dims = ""
    try:
        from PIL import Image
        with Image.open(src) as im:
            dims = f"{im.width}×{im.height} · "
    except Exception:
        pass  # FITS / unreadable here — the engine renders it; show size + type
    return f"{dims}{size_mb:.1f} MB · {src.suffix.lstrip('.').upper()}"


class _ExportWorker(QThread):
    done = Signal(object)          # ExportResult
    failed = Signal(str)
    cancelled = Signal()
    status = Signal(str)
    progressed = Signal(int, int)

    def __init__(self, src, preset, dest, strategy, max_bytes, cancel_event,
                 parent=None):
        super().__init__(parent)
        self._src, self._preset, self._dest = src, preset, dest
        self._strategy, self._max_bytes = strategy, max_bytes
        self._cancel = cancel_event

    def run(self):
        try:
            res = webexport.export_for_sharing(
                self._src, self._preset, self._dest, strategy=self._strategy,
                max_bytes=self._max_bytes,
                status=self.status.emit,
                progress=lambda d, t: self.progressed.emit(d, t),
                should_cancel=self._cancel.is_set)
            self.done.emit(res)
        except webexport.ExportError as e:
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(e))
        except Exception as e:  # pragma: no cover - defensive
            self.failed.emit(f"{type(e).__name__}: {e}")


class ExportShareDialog(QDialog):
    """Modal export dialog for a single source image."""

    def __init__(self, src_path, parent=None, *, default_stem: str | None = None):
        super().__init__(parent)
        self._src = Path(src_path)
        self._stem = default_stem or self._src.stem
        self._worker = None
        self._progress = None
        self._cancel_event = None

        self.setWindowTitle("Export for sharing")
        self.setModal(True)
        self.setFixedWidth(480)              # long filenames wrap, don't widen
        lay = QVBoxLayout(self)

        # Filenames are long and space-free (can't word-wrap) — elide the middle,
        # keeping the start + extension; full name in the tooltip.
        name_lbl = QLabel()
        f = name_lbl.font()
        f.setBold(True)
        name_lbl.setFont(f)
        name_lbl.setText(QFontMetrics(f).elidedText(self._src.name, Qt.ElideMiddle, 430))
        name_lbl.setToolTip(self._src.name)
        lay.addWidget(name_lbl)
        info = QLabel(_source_info(self._src))
        info.setProperty("muted", True)
        lay.addWidget(info)

        # --- preset ---
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Share to:"))
        self._preset = QComboBox()
        for p in webexport.PRESETS:
            self._preset.addItem(p.label, p.id)
        prow.addWidget(self._preset, 1)
        lay.addLayout(prow)

        # Custom MB row (hidden unless the Custom preset is picked).
        self._custom_row = QWidget()
        crow = QHBoxLayout(self._custom_row)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.addWidget(QLabel("Max size:"))
        self._custom_mb = QDoubleSpinBox()
        self._custom_mb.setRange(0.5, 500.0)
        self._custom_mb.setDecimals(1)
        self._custom_mb.setSingleStep(1.0)
        self._custom_mb.setSuffix(" MB")
        self._custom_mb.setValue(float(config.get_setting("webexport_custom_mb", 20.0)))
        crow.addWidget(self._custom_mb)
        crow.addStretch(1)
        lay.addWidget(self._custom_row)

        # --- strategy ---
        self._lossless = QRadioButton("Keep lossless (may reduce resolution)")
        self._quality = QRadioButton("Keep full resolution (high-quality JPEG)")
        self._strategy_group = QButtonGroup(self)
        self._strategy_group.addButton(self._lossless)
        self._strategy_group.addButton(self._quality)
        self._lossless.setChecked(True)
        lay.addWidget(self._lossless)
        lay.addWidget(self._quality)

        self._note = QLabel()
        self._note.setWordWrap(True)
        self._note.setProperty("muted", True)
        lay.addWidget(self._note)

        # --- buttons ---
        brow = QHBoxLayout()
        brow.addStretch(1)
        self._export_btn = QPushButton("Export…")
        self._export_btn.setDefault(True)
        self._export_btn.clicked.connect(self._do_export)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        brow.addWidget(self._export_btn)
        brow.addWidget(cancel_btn)
        lay.addLayout(brow)

        # Restore last-used choices.
        i = self._preset.findData(config.get_setting("webexport_last_preset", "reddit"))
        if i >= 0:
            self._preset.setCurrentIndex(i)
        if config.get_setting("webexport_strategy", "lossless") == "quality":
            self._quality.setChecked(True)

        self._preset.currentIndexChanged.connect(self._sync_preset)
        self._sync_preset()

    # ---- reactive UI ----
    def _current_preset(self):
        return webexport.PRESETS_BY_ID[self._preset.currentData()]

    def _sync_preset(self):
        p = self._current_preset()
        self._custom_row.setVisible(p.id == "custom")
        self._note.setText(p.note)
        self._note.setVisible(bool(p.note))
        self.adjustSize()

    def _strategy(self) -> str:
        return "quality" if self._quality.isChecked() else "lossless"

    def _max_bytes(self):
        p = self._current_preset()
        return int(self._custom_mb.value() * _MB) if p.id == "custom" else None

    # ---- export (native save panel, then threaded fit) ----
    def _do_export(self):
        preset, strategy = self._current_preset(), self._strategy()
        suggested = webexport.suggested_name(self._stem, preset, strategy)
        fmt = webexport.format_for(strategy, preset)
        last_dir = config.get_setting("webexport_last_dir", "") or str(Path.home())
        start = str(Path(last_dir) / suggested)
        # Native OS save panel — the user renames + picks any destination here.
        path, _ = QFileDialog.getSaveFileName(
            self, "Export image", start, _FILTERS.get(fmt, ""))
        if not path:
            return                                  # user cancelled the panel
        dest = webexport.normalize_dest(path, strategy, preset)

        config.save_setting("webexport_last_preset", preset.id)
        config.save_setting("webexport_strategy", strategy)
        config.save_setting("webexport_last_dir", str(dest.parent))
        if preset.id == "custom":
            config.save_setting("webexport_custom_mb", self._custom_mb.value())

        self._export_btn.setEnabled(False)
        self._make_progress("Preparing export…")
        self._cancel_event = self._cancel_event or threading.Event()
        self._worker = _ExportWorker(self._src, preset, dest, strategy,
                                     self._max_bytes(), self._cancel_event, self)
        self._worker.status.connect(
            lambda m: self._progress.setLabelText(m) if self._progress else None)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()
        self._progress.show()

    def _on_done(self, res):
        self._finish_worker()
        self._close_progress()
        kind = "lossless" if res.lossless else "JPEG"
        summary = (f"Exported {res.width}×{res.height} {res.format.upper()} · "
                   f"{res.size_mb:.1f} MB · {kind}"
                   + (" · downscaled" if res.downscaled else ""))
        box = QMessageBox(self)
        box.setWindowTitle("Export complete")
        box.setText(summary)
        box.setInformativeText(str(res.dest))
        reveal_btn = box.addButton("Reveal", QMessageBox.ActionRole)
        open_btn = box.addButton("Open", QMessageBox.ActionRole)
        box.addButton("Done", QMessageBox.AcceptRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is reveal_btn:
            reveal_in_manager(res.dest)
        elif clicked is open_btn:
            open_in_default(res.dest)
        self.accept()

    def _on_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._export_btn.setEnabled(True)
        QMessageBox.warning(self, "Export failed", msg)

    def _on_cancelled(self):
        self._finish_worker()
        self._close_progress()
        self._export_btn.setEnabled(True)

    # ---- progress + worker lifecycle (same pattern as ingest/import) ----
    def _make_progress(self, label):
        self._cancel_event = threading.Event()
        pd = QProgressDialog(label, "Cancel", 0, 0, self)   # 0,0 = busy indicator
        pd.setWindowTitle("Exporting")
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
            # done/failed/cancelled fires from run() *as it returns*, so the
            # QThread may not have fully finished yet. Wait for it before
            # deleting, or the deferred ~QThread can run on a still-running
            # thread and crash (SIGSEGV in ~QThread during event delivery).
            if self._worker.isRunning():
                self._worker.wait()
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

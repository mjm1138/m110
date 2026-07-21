"""Offscreen UI smoke for the export-for-sharing dialog.

The size-fitting ladder is covered in test_webexport.py; here we drive the
dialog: preset reactivity, and one end-to-end export (native save panel +
result message box stubbed) that actually writes a file via the worker."""
import numpy as np
import pytest

pytest.importorskip("PySide6")
from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from m110 import webexport  # noqa: E402
from m110.ui.export_dialog import ExportShareDialog  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _png(path, w=200, h=200):
    arr = np.random.default_rng(0).integers(0, 256, (h, w, 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(path, "PNG")
    return path


def test_dialog_constructs_and_custom_reveals_spinbox(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    dlg = ExportShareDialog(str(_png(tmp_path / "src.png")))
    qtbot.addWidget(dlg)
    ids = [dlg._preset.itemData(i) for i in range(dlg._preset.count())]
    assert ids == [p.id for p in webexport.PRESETS]
    assert not dlg._custom_row.isVisibleTo(dlg)          # hidden by default
    dlg._preset.setCurrentIndex(dlg._preset.findData("custom"))
    assert dlg._custom_row.isVisibleTo(dlg)              # revealed for Custom


def test_dialog_export_writes_a_file(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    src = _png(tmp_path / "src.png")
    dest = tmp_path / "shared.png"
    # Stub the native save panel + the result message box (both would block).
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(dest), ""))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)

    dlg = ExportShareDialog(str(src), default_stem="M101")
    qtbot.addWidget(dlg)
    dlg._do_export()
    qtbot.waitUntil(lambda: dlg._worker is None, timeout=5000)   # export finished
    assert dest.exists() and dest.stat().st_size > 0
    # Last choices were persisted for next time.
    from m110 import config
    assert config.get_setting("webexport_last_dir") == str(dest.parent)

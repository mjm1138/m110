#!/usr/bin/env python3
"""Reproduce the "sync landed under an open modal" use-after-free (0.3.0b3 SIGSEGV).

    QT_QPA_PLATFORM=offscreen python tools/repro_modal_uaf.py buggy   # → exit 139
    QT_QPA_PLATFORM=offscreen python tools/repro_modal_uaf.py fixed   # → exit 0

A 40-line stand-in for the real path (`DetailPane` gallery → `ImageViewer.exec()` →
`MainWindow._on_refresh_done` → `_clear()`): a `QListWidget` opens a modal straight
from `itemDoubleClicked`, and a "refresh" `deleteLater()`s the list *inside* that
modal's nested loop. **buggy** dies exactly where the crash report did — resuming
`QAbstractItemView::mouseDoubleClickEvent` on a freed view, so it never prints
"returned from the double-click dispatch". **fixed** routes the open through
`widgets.defer`, so the handler returns before any nested loop starts.

This is a *manual* diagnostic, deliberately **not** a pytest case: a regression here
segfaults the interpreter rather than failing an assertion, which would take a whole
CI run down. The policy assertions live in `tests/test_ui_modal_safety.py`; run this
by hand when changing how modals are opened from item views.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QTimer                                 # noqa: E402
from PySide6.QtTest import QTest                                      # noqa: E402
from PySide6.QtWidgets import (                                       # noqa: E402
    QApplication, QDialog, QListWidget, QVBoxLayout, QWidget,
)

from m110.ui.widgets import defer                                     # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "fixed"
if MODE not in ("buggy", "fixed"):
    sys.exit("usage: repro_modal_uaf.py [buggy|fixed]")

app = QApplication([])
host = QWidget()
lay = QVBoxLayout(host)
lst = QListWidget()
lst.addItem("tile")
lay.addWidget(lst)
host.resize(300, 200)
host.show()
QTest.qWaitForWindowExposed(host)


def fake_refresh():
    """What `reload()` → `DetailPane._clear()` does to the gallery."""
    lay.removeWidget(lst)
    lst.setParent(None)
    lst.deleteLater()
    print("  refresh: gallery deleteLater()'d (inside the modal's loop)")


def open_viewer():
    dlg = QDialog(host)
    dlg.resize(120, 80)
    QTimer.singleShot(50, fake_refresh)      # the sync lands inside the loop
    QTimer.singleShot(150, dlg.accept)       # the user closes the viewer
    dlg.exec()
    print("  viewer closed")


# The whole difference: a nested loop under the view's C++ mouse handler, or not.
lst.itemDoubleClicked.connect(
    (lambda _item: open_viewer()) if MODE == "buggy" else
    (lambda _item: defer(lst, open_viewer)))

print(f"mode={MODE}: double-clicking…")
app.processEvents()
center = lst.visualItemRect(lst.item(0)).center()
QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, center)
QTest.mouseDClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, center)
print("  returned from the double-click dispatch")   # buggy never gets here
QTimer.singleShot(400, app.quit)
app.exec()
print(f"mode={MODE}: SURVIVED")

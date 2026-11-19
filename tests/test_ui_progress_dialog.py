"""The app's progress dialog keeps room between the bar and Cancel.

QProgressDialog has no layout: it places Cancel `PM_LayoutVerticalSpacing` below
the bar, and the macOS style reports -1 there, so on a Mac the two touched (the
Import progress window). `widgets.ProgressDialog` swaps in a bar that reserves a
gap in its size hint and paints only above it.
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QProgressBar, QPushButton  # noqa: E402

from m110.ui.theme.tokens import SPACE  # noqa: E402
from m110.ui.widgets import ProgressDialog  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "m110" / "ui"


def _shown(qtbot, *args):
    pd = ProgressDialog(*args)
    qtbot.addWidget(pd)
    pd.setMinimumDuration(0)
    pd.show()
    qtbot.waitExposed(pd)
    return pd


def test_painted_bar_clears_cancel(qtbot):
    pd = _shown(qtbot, "Copying 12 of 48 frames…", "Cancel", 0, 48)
    pd.setValue(12)
    bar, btn = pd.findChild(QProgressBar), pd.findChild(QPushButton)
    painted_bottom = bar.geometry().bottom() - SPACE["md"]
    # Even with a -1 layout spacing (macOS) the gap is at least SPACE['md'] - 1.
    assert btn.geometry().top() - painted_bottom - 1 >= SPACE["md"] - 1


@pytest.mark.parametrize("lo,hi", [(0, 48), (0, 0)])
def test_range_survives_the_bar_swap(qtbot, lo, hi):
    pd = _shown(qtbot, "Working…", "Cancel", lo, hi)
    # setBar resets the range to 0..100; (0, 0) is the busy indicator.
    assert (pd.minimum(), pd.maximum()) == (lo, hi)


def test_no_bare_qprogressdialog_in_the_ui():
    offenders = [
        str(p.relative_to(UI)) for p in UI.rglob("*.py")
        if p.name != "widgets.py" and re.search(r"\bQProgressDialog\(", p.read_text())
    ]
    assert offenders == [], f"use widgets.ProgressDialog instead: {offenders}"

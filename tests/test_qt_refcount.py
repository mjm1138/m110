"""PySide6 must not leak a reference to None out of void Qt calls.

PySide6 6.12.0 returns ``None`` from a void method without taking a reference,
so every such call costs ``None`` one refcount. On Python 3.11 — still in our
``requires-python`` range, and where ``None`` is an ordinary refcounted object —
enough calls (a per-pixel ``QImage.setPixel`` loop in test_thumbnail_aspect.py
was enough) deallocate ``None`` and the interpreter aborts with
``Fatal Python error: none_dealloc``: CI's 3.11 leg core-dumped mid-suite with no
test named. Python 3.12+ made ``None`` immortal (PEP 683), which hides it there.

pyproject.toml excludes that release on 3.11; this test turns a regression (a
future PySide6 with the same bug, or the exclusion being dropped too early) into
a plain failure instead of a crash.
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="None is immortal on 3.12+ (PEP 683), so its refcount cannot move")


def test_void_qt_calls_keep_their_reference_to_none():
    from PySide6.QtGui import QImage
    img = QImage(1, 1, QImage.Format_RGB32)
    before = sys.getrefcount(None)
    for _ in range(10_000):
        img.setPixel(0, 0, 0xFFFFFFFF)          # a void call: returns None
    lost = before - sys.getrefcount(None)
    import PySide6
    assert lost < 100, (
        f"PySide6 {PySide6.__version__} dropped {lost} references to None over "
        "10,000 void calls — on Python 3.11 that aborts the interpreter "
        "(none_dealloc). Exclude this PySide6 release in pyproject.toml.")

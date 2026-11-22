"""The traffic-light fix (`m110/ui/macos_chrome.py`) is AppKit-only and best-effort:
everywhere else — another OS, or the offscreen test platform on a Mac, whose
`winId()` is not an NSView — it must do nothing rather than touch pyobjc."""
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget  # noqa: E402

from m110.ui import macos_chrome  # noqa: E402


def test_noop_off_cocoa(qapp):
    w = QWidget()
    try:
        w.show()
        assert macos_chrome.center_traffic_lights(w) is False
        assert macos_chrome.traffic_light_center_y(w) is None
    finally:
        w.deleteLater()


def test_noop_off_macos(qapp, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    w = QWidget()
    try:
        assert macos_chrome.center_traffic_lights(w) is False
    finally:
        w.deleteLater()


def test_main_window_applies_it_when_shown(tmp_path, monkeypatch, qapp):
    """MainWindow asks for the fix on show, only with the expanded title-bar band."""
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(macos_chrome, "center_traffic_lights", lambda w: calls.append(w))
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    try:
        win._expanded = True
        win.show()
        qapp.processEvents()
        assert calls == [win]
    finally:
        win.close(); win.deleteLater(); qapp.processEvents()

"""macOS window chrome that Qt doesn't expose: centre the traffic lights on the
header bar.

With `Qt.ExpandedClientAreaHint` our header bar (`toolbar.HEIGHT` = 52 pt, a unified
toolbar's height) fills the title-bar band, but AppKit still lays the window
buttons out for a plain ~28 pt title strip, so they sat ~12 pt above the header's
centre line. Qt has no API for the buttons' position (Qt 6.12: no toolbar-style
window property, `QNativeInterface` exposes no NSWindow).

The fix is AppKit's own: give the NSWindow an **empty `NSToolbar`** with the
unified style and a hidden title. AppKit then makes the title-bar band 52 pt tall
and centres the buttons in it itself — through resizes, full screen and
appearance changes — the way Finder and Photos look. No buttons are moved by hand.

Needs pyobjc (`pyobjc-framework-Cocoa`, a core darwin dependency). Everything here is
best-effort: off macOS, without pyobjc, or on any AppKit error it does nothing and the
window keeps the old (working, slightly high) button position.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

TOOLBAR_ID = "org.m110.titlebar"


def _on_cocoa() -> bool:
    """Only the cocoa platform plugin's `winId()` is an NSView. Under `offscreen`
    (the test suite, also on a Mac) it is not, and handing it to pyobjc would crash."""
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.platformName() == "cocoa"


def _ns_window(widget):
    """The NSWindow behind a shown top-level QWidget, or None."""
    import objc
    view = objc.objc_object(c_void_p=int(widget.winId()))
    return view.window() if view is not None else None


def center_traffic_lights(widget) -> bool:
    """Give `widget`'s window an empty unified NSToolbar so AppKit centres the
    traffic lights in a 52 pt band. Idempotent; returns True if the toolbar is in
    place. Call after the window is shown (its NSWindow must exist)."""
    if not _on_cocoa():
        return False
    try:
        from AppKit import NSToolbar, NSWindowTitleHidden, NSWindowToolbarStyleUnified
        win = _ns_window(widget)
        if win is None:
            return False
        tb = win.toolbar()
        fresh = tb is None or tb.identifier() != TOOLBAR_ID
        # Adding a toolbar makes AppKit re-fit the window, which shrank it to its
        # minimum size when this ran on show (the restored/saved geometry was lost).
        # Keep the frame the window had.
        frame = win.frame()
        if fresh:
            tb = NSToolbar.alloc().initWithIdentifier_(TOOLBAR_ID)
            tb.setAllowsUserCustomization_(False)
            win.setToolbar_(tb)
        win.setToolbarStyle_(NSWindowToolbarStyleUnified)
        win.setTitleVisibility_(NSWindowTitleHidden)
        if win.frame() != frame:
            win.setFrame_display_(frame, True)
        if fresh:      # once per native window: the frozen-build check reads this
            log.info("title bar: unified toolbar set, window buttons centred at %s pt",
                     traffic_light_center_y(widget))
        return True
    except Exception:                                    # noqa: BLE001 — cosmetic
        log.debug("couldn't centre the traffic lights", exc_info=True)
        return False


def traffic_light_center_y(widget) -> float | None:
    """Vertical centre of the close button, in points from the window's top edge
    (diagnostics/tests; None off macOS or without pyobjc)."""
    if not _on_cocoa():
        return None
    try:
        from AppKit import NSWindowCloseButton
        win = _ns_window(widget)
        btn = win.standardWindowButton_(NSWindowCloseButton) if win else None
        if btn is None:
            return None
        r = btn.convertRect_toView_(btn.bounds(), None)  # window coords, origin bottom-left
        frame_h = win.frame().size.height
        return frame_h - (r.origin.y + r.size.height / 2)
    except Exception:                                    # noqa: BLE001
        return None

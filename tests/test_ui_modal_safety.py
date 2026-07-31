"""Offscreen regression: never destroy widgets from under a nested event loop.

The 0.3.0b3 crash (`QAbstractItemView::mouseDoubleClickEvent` → SIGSEGV): click a
backgrounded window back into focus — which starts the auto-sync — then
double-click a gallery thumbnail. The viewer's modal loop keeps the gallery's C++
mouse handler on the stack; the sync finishes inside that loop and rebuilds the
detail pane, so the `deleteLater()` fires while Qt is still mid-dispatch and the
handler resumes on a freed view.

Two guards, one test each side of it:
  * `MainWindow._apply_refresh` — no page rebuild while a modal/popup is up.
  * `widgets.defer` — item-view signals never open a nested loop in-handler.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem  # noqa: E402

from m110.ui import widgets  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _window(qapp):
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False    # neuter the deferred launch refresh + update-check threads
    return win


def _modal(parent):
    """A modal dialog that is *live* without running its own loop — `show()` puts
    it in Qt's modal stack, so `activeModalWidget()` sees it (exec() would block
    the test instead)."""
    dlg = QDialog(parent)
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.show()
    return dlg


def test_modal_loop_active_tracks_modal_dialogs(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    assert widgets.modal_loop_active() is False
    win = _window(qapp)
    try:
        dlg = _modal(win)
        qapp.processEvents()
        assert widgets.modal_loop_active() is True
        dlg.close()
        qapp.processEvents()
        assert widgets.modal_loop_active() is False
    finally:
        win.deleteLater(); qapp.processEvents()


def test_refresh_does_not_rebuild_pages_under_a_modal(tmp_path, monkeypatch, qapp):
    """The crash's root cause: `reload()` deletes the widget Qt is dispatching on."""
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        reloads = []
        for p in win.pages:
            monkeypatch.setattr(p, "reload", lambda p=p: reloads.append(p))

        dlg = _modal(win)
        qapp.processEvents()
        win._on_refresh_done({})                 # a sync lands while the modal is up
        assert reloads == []                     # …and must not tear anything down
        assert win._pending_refresh is not None  # it's queued, not dropped
        assert win._reload_retry.isActive()

        dlg.close()
        qapp.processEvents()
        win._retry_pending_refresh()             # (the retry timer's slot)
        assert len(reloads) == len(win.pages)    # applied once the modal is gone
        assert win._pending_refresh is None
    finally:
        win.deleteLater(); qapp.processEvents()


def test_refresh_rebuilds_immediately_with_no_modal(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    win = _window(qapp)
    try:
        reloads = []
        for p in win.pages:
            monkeypatch.setattr(p, "reload", lambda p=p: reloads.append(p))
        win._on_refresh_done({})
        assert len(reloads) == len(win.pages)
        assert win._pending_refresh is None
    finally:
        win.deleteLater(); qapp.processEvents()


def test_defer_runs_after_the_current_handler(qapp):
    calls = []
    lst = QListWidget()
    try:
        widgets.defer(lst, lambda: calls.append(1))
        assert calls == []          # not synchronously — the handler must return first
        qapp.processEvents()
        assert calls == [1]
    finally:
        lst.deleteLater(); qapp.processEvents()


def test_context_menu_is_opened_out_of_the_mouse_handler(qapp):
    """`connect_context_menu` must not run the handler inside the signal emission
    — a `QMenu.exec()` there spins its loop inside the view's C++ mouse handler."""
    opened = []
    lst = QListWidget()
    try:
        widgets.connect_context_menu(lst, lambda pos: opened.append(pos))
        assert lst.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        lst.customContextMenuRequested.emit(lst.rect().center())
        assert opened == []         # deferred…
        qapp.processEvents()
        assert len(opened) == 1     # …then opened
    finally:
        lst.deleteLater(); qapp.processEvents()


def test_gallery_double_click_defers_the_viewer(tmp_path, monkeypatch, qapp):
    """The exact crash path: the viewer must not open while the gallery's
    `mouseDoubleClickEvent` is still on the stack."""
    seed_root(tmp_path, monkeypatch)
    from m110.ui import detail as detail_mod

    shown = []

    class _FakeViewer:
        def __init__(self, items, idx, **kw):
            self._args = (items, idx)

        def exec(self):
            shown.append(self._args)

    monkeypatch.setattr(detail_mod, "ImageViewer", _FakeViewer)

    pane = detail_mod.DetailPane()
    try:
        pane._current = ("m1", {"id": "M1"}, {})
        pane._gallery_items = [{"name": "a.jpg", "path": "/a.jpg", "src": "/a.jpg"}]
        item = QListWidgetItem("a.jpg")
        item.setData(Qt.UserRole, 0)

        pane._open_gallery_item(item)
        assert shown == []                  # nothing modal inside the handler
        qapp.processEvents()
        assert len(shown) == 1 and shown[0][1] == 0

        # The deferred call works off a snapshot, so a rebuild landing in between
        # can't shift the index out from under it.
        shown.clear()
        pane._open_gallery_item(item)
        pane._gallery_items = []            # e.g. a sync rebuilt the pane
        qapp.processEvents()
        assert len(shown) == 1 and shown[0][0] == [{"name": "a.jpg", "path": "/a.jpg",
                                                    "src": "/a.jpg"}]
    finally:
        pane.deleteLater(); qapp.processEvents()

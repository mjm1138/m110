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


def test_hero_double_click_opens_the_viewer_at_the_heros_own_image(
        tmp_path, monkeypatch, qapp):
    """Double-clicking the hero opens the viewer exactly as double-clicking that
    image in the gallery does: the **same item list**, positioned at the hero, so
    Prev/Next carry on from there rather than restarting at the first tile.

    Same deferral requirement as the gallery — `ScalableImage.doubleClicked` is
    emitted from inside `mouseDoubleClickEvent`, so a modal opened there would keep
    that C++ frame alive underneath it (the 0.3.0b3 crash shape)."""
    root = seed_root(tmp_path, monkeypatch)
    from m110 import objects
    from m110.ui import detail as detail_mod

    shown = []

    class _FakeViewer:
        def __init__(self, items, idx, **kw):
            self._args = (items, idx)

        def exec(self):
            shown.append(self._args)

    monkeypatch.setattr(detail_mod, "ImageViewer", _FakeViewer)
    # The hero is the SECOND gallery image, so "opens at the hero" can't be
    # confused with "opens at index 0".
    objects.write_journal("m1", "---\nhero: b.jpg\n---\n\nnotes\n")

    pane = detail_mod.DetailPane()
    try:
        pane._current = ("m1", {"id": "M1"}, {})
        pane._gallery_items = [
            {"name": "a.jpg", "path": "/a.jpg", "src": "/a.jpg"},
            {"name": "b.jpg", "path": "/b.jpg", "src": "/b.jpg"},
        ]
        assert pane._hero_gallery_index("m1") == 1
        # …and the dict helper the hero's context menu uses still agrees.
        assert pane._hero_gallery_item("m1")["name"] == "b.jpg"

        pane._open_hero_viewer()
        assert shown == []                      # nothing modal inside the handler
        qapp.processEvents()
        assert len(shown) == 1
        items, idx = shown[0]
        assert idx == 1                         # positioned on the hero
        assert [i["name"] for i in items] == ["a.jpg", "b.jpg"]   # whole gallery

        # A hero that isn't one of the gallery's images opens nothing, rather than
        # opening the viewer on some other picture.
        shown.clear()
        objects.write_journal("m1", "---\nhero: gone.jpg\n---\n\nnotes\n")
        monkeypatch.setattr(detail_mod.build_images, "hero_source_path",
                            lambda slug: None)
        pane._open_hero_viewer()
        qapp.processEvents()
        assert shown == []
    finally:
        pane.deleteLater(); qapp.processEvents()


def test_drain_worker_waits_before_dropping(qapp):
    """`drain_worker` must not release a QThread that is still running.

    The failure mode is a **qFatal**, not an exception: destroying a live QThread
    prints "QThread: Destroyed while thread is still running" and calls abort().
    A test can't catch that, so assert the property instead — after draining, the
    thread has finished."""
    import time
    from PySide6.QtCore import QThread
    from m110.ui.widgets import drain_worker

    class _Slow(QThread):
        def run(self):
            time.sleep(0.2)

    w = _Slow()
    w.start()
    assert w.isRunning()
    assert drain_worker(w) is None
    assert w.isFinished(), "drain_worker returned while the thread was still running"
    qapp.processEvents()


def test_drain_worker_tolerates_none(qapp):
    from m110.ui.widgets import drain_worker
    assert drain_worker(None) is None


def test_every_worker_dialog_drains_instead_of_bare_deletelater():
    """The bug that caused the Backup-dialog SIGABRT was a `_finish_worker` that
    called `deleteLater()` and cleared the reference *without waiting* — invoked
    from a slot connected to a signal emitted **inside** `run()`, so the thread was
    still alive. `export_dialog` had already learned this and fixed it locally;
    three sibling dialogs kept the unsafe copy for months.

    So assert the shape across all of them rather than trusting each to remember:
    a dialog that owns a QThread drops it through `drain_worker`."""
    import re
    from pathlib import Path

    ui = Path(__file__).resolve().parents[1] / "m110" / "ui"
    offenders = []
    for name in ("backup_dialog", "export_dialog", "restore_dialog", "publish_dialog"):
        src = (ui / f"{name}.py").read_text(encoding="utf-8")
        for m in re.finditer(r"def (_finish_worker|_stop_worker|_finish_probe|_stop_probe)"
                             r"\(self[^)]*\):(.*?)(?=\n    def |\n\nclass |\Z)",
                             src, re.S):
            body = m.group(2)
            if "drain_worker" not in body:
                offenders.append(f"{name}.{m.group(1)}")
    assert not offenders, (
        "these drop a QThread without going through widgets.drain_worker, which is "
        "how a still-running thread reaches ~QThread and aborts the process:\n  "
        + "\n  ".join(offenders))

"""Shared UI helpers used across the Library pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Qt, QObject, QRectF, QRunnable, QSize, QThreadPool, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QIcon, QImage, QImageReader, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QMenu, QMessageBox,
    QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QToolButton,
)

from m110 import derived, objects, siril
from m110.ui.theme import muted_color, status_color, mono_font  # theme-driven (re-exported)
from m110.ui.theme.tokens import SPACE

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
# Per-cell role carrying the raw status key (e.g. "deep_stack") so the pill delegate
# can pick a theme color while the cell still sorts by its visible text.
STATUS_ROLE = Qt.ItemDataRole.UserRole + 7


def status_label(status: str | None, captured: bool) -> str:
    if not captured:
        return "—"
    return STATUS_LABEL.get(status, status or "—")


def paint_status_chip(painter: QPainter, rect: QRectF, text: str, color: QColor):
    """Fill `rect` with the app's tasteful tinted-rounded status-chip look
    (alpha-tinted background, colored text, fully rounded) — the caller sizes
    and positions `rect`; this just paints into it. Shared by the Library
    table's `StatusPillDelegate` and the grid's `TileDelegate`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor(color); bg.setAlpha(38)
    painter.setBrush(bg); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()


class StatusPillDelegate(QStyledItemDelegate):
    """Paints the capture status as a tasteful tinted rounded chip (color from the
    active theme via `STATUS_ROLE`), keeping the cell sortable by its plain text."""
    _HPAD = 10

    def paint(self, painter, option, index):
        # Let the base style paint the row/selection background (text suppressed).
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        status = index.data(STATUS_ROLE)
        if not text or text == "—" or not status:
            painter.save()
            painter.setPen(muted_color())
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text or "—")
            painter.restore()
            return
        color = status_color(status)
        fm = opt.fontMetrics
        h = fm.height() + 4
        w = fm.horizontalAdvance(text) + self._HPAD * 2
        rect = QRectF(option.rect.left() + 8, option.rect.center().y() - h / 2 + 1, w, h)
        paint_status_chip(painter, rect, text, color)

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width() + self._HPAD * 2 + 16, max(s.height(), 24))


class NumItem(QTableWidgetItem):
    """Table item that sorts by an arbitrary key (number or tuple)."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other):
        if isinstance(other, NumItem):
            return self._key < other._key
        return super().__lt__(other)


def make_numeric(item: QTableWidgetItem, mono: bool = True) -> QTableWidgetItem:
    """Right-align a numeric/data cell and (default) give it the bundled tabular
    monospace, so columns of numbers line up. Returns the item for chaining."""
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if mono:
        item.setFont(mono_font())
    return item


def targets_for_slug(slug: str) -> list[str]:
    """Capture targets (Images/<target>/) that feed this catalog object."""
    by_folder = derived.load_totals().get("by_folder", {})
    return [f for f, info in by_folder.items() if slug in info.get("slugs", [])]


# ── external-app launch (#19: Process in… / Open In…) ────────────────────────

def working_dirs_for_slug(slug: str) -> list[tuple[str, Path]]:
    """(label, dir) for every Siril working directory across an object's capture
    targets — one (target, sandbox) for the common case, or one row per
    per-filter job folder when the sandbox is split. Single-filter sandbox dirs
    are named "siril"; per-filter job dirs carry the filter name."""
    out: list[tuple[str, Path]] = []
    for tgt in targets_for_slug(slug):
        out.extend(_labelled_dirs(tgt))
    return out


def can_process_slug(slug: str) -> bool:
    """True if the object has a processing working folder to launch/reveal."""
    return bool(working_dirs_for_slug(slug))


def _labelled_dirs(target: str) -> list[tuple[str, Path]]:
    """(label, dir) for one capture target's Siril working dirs."""
    return [(target if d.name == "siril" else f"{target} · {d.name}", d)
            for d in siril.working_dirs(target)]


def process_in_siril(parent, slug: str) -> None:
    """Launch Siril pointed at the object's working folder (across all its
    capture targets)."""
    _process_dirs(parent, working_dirs_for_slug(slug))


def process_target_in_siril(parent, target: str) -> None:
    """Launch Siril pointed at one capture target's working folder."""
    _process_dirs(parent, _labelled_dirs(target))


def _process_dirs(parent, dirs: list[tuple[str, Path]]) -> None:
    """Launch Siril for a set of candidate working dirs. Multiple job folders →
    a chooser; not-found/launch-error → offer to reveal the folder instead."""
    if not dirs:
        QMessageBox.information(
            parent, "Process in Siril",
            "No processing working folder exists yet — it's created "
            "automatically after you import captures.")
        return
    if len(dirs) == 1:
        _launch_siril(parent, dirs[0][1])
        return
    menu = QMenu(parent)
    acts = {menu.addAction(f"Open {lbl} in Siril"): d for lbl, d in dirs}
    chosen = menu.exec(QCursor.pos())
    if chosen is not None:
        _launch_siril(parent, acts[chosen])


def _launch_siril(parent, working_dir: Path) -> None:
    from m110 import launch
    try:
        launch.launch_processing("siril", working_dir)
    except launch.LaunchError as exc:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Process in Siril")
        box.setText(str(exc))
        box.setInformativeText(
            "Opening the working folder instead — set it as Siril's working "
            "directory. You can set Siril's location in Preferences → "
            "Processing tools.")
        reveal_btn = box.addButton("Reveal folder", QMessageBox.AcceptRole)
        box.addButton("OK", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is reveal_btn:
            reveal_in_manager(working_dir)


def open_in_default(path) -> None:
    """Open a file/dir with the OS default application."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal_in_manager(path) -> None:
    """Show a file/dir in the OS file manager (for a file, opens its folder)."""
    p = Path(path)
    target = p if p.is_dir() else p.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def make_table(headers: list[str], stretch_last: bool = False) -> QTableWidget:
    """A read-only, row-selectable, sortable table (vertical header hidden)."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.setSortingEnabled(True)
    t.setAlternatingRowColors(True)
    if stretch_last:
        t.horizontalHeader().setStretchLastSection(True)
    return t


def fit_table_height(tbl: QTableWidget, max_rows: int | None = None,
                     half_row_pad: bool = True) -> None:
    """Size a populated table to its content so it neither truncates a row nor
    leaves dead space. Call **after** rows are inserted.

    `header + frame + Σ row heights` (+ ½ a row when `half_row_pad`, which both
    stops the last row clipping and — when capped — peeks the next row as a scroll
    hint). With `max_rows`, height caps at that many rows and the vertical scrollbar
    turns on for the rest; otherwise the whole table is shown with no inner scroll."""
    tbl.resizeRowsToContents()
    n = tbl.rowCount()
    default_h = tbl.verticalHeader().defaultSectionSize()
    row_h = tbl.rowHeight(0) if n else default_h
    shown = n if (max_rows is None or n <= max_rows) else max_rows
    body = sum(tbl.rowHeight(i) for i in range(shown)) if n else default_h
    pad = row_h // 2 if half_row_pad else 0
    capped = max_rows is not None and n > max_rows
    tbl.setVerticalScrollBarPolicy(
        Qt.ScrollBarAsNeeded if capped else Qt.ScrollBarAlwaysOff)
    header = tbl.horizontalHeader().height() + 2 * tbl.frameWidth()
    tbl.setFixedHeight(header + body + pad)


# The app QSS pads table items — `QTableView::item { padding: xs sm }` in
# `theme/qss.py` — and Qt lays a cell **widget** out inside that padded rect too.
# Nothing else knows about it: `resizeColumnsToContents` measures *items* and skips
# cell widgets entirely, and the default row height is sized for one line of text.
# So a row of buttons gets clipped in both directions at once — horizontally into a
# column sized for an empty item, vertically into a ~24 px row when the buttons need
# 30. Kept in the same units the stylesheet uses (not hardcoded pixels) so the two
# can't drift; `tests/test_ui_cell_widgets.py::test_padding_constants_match_the_stylesheet`
# fails the build if they ever do.
#
# These two lines and the `QTableView::item` rule in `theme/qss.py` are ONE edit, and
# the failure is asymmetric: lowering these WITHOUT the QSS hands a cell widget less
# room than it needs and clips it (measured: a 30px button given 26px), while lowering
# the QSS without these only wastes a few pixels. That regex test is the guard —
# don't "simplify" it away.
CELL_WIDGET_PAD_H = 2 * (SPACE["sm"] - 2)
CELL_WIDGET_PAD_V = 2 * (SPACE["xs"] // 2)


def drain_worker(worker):
    """Wait for a QThread to genuinely finish, then schedule its deletion. Returns
    None so a caller clears its reference in one line: `self._w = drain_worker(self._w)`.

    **Every** drop of a worker reference should go through here, because the unsafe
    version is not obviously unsafe. Our workers emit their result signals from
    *inside* `run()` (`done`/`failed`/`probed`), so a slot connected to them runs on
    the GUI thread while the worker thread is still executing its last statements.
    Dropping the reference there with a bare `deleteLater()` leaves a **live QThread
    parented to the dialog with nobody holding it**: closing the dialog then runs
    `QObjectPrivate::deleteChildren()` over a running thread, which is a qFatal —
    "QThread: Destroyed while thread is still running" — and an instant SIGABRT, not
    a catchable exception.

    Worse, it slips past the `_stop_worker`-style teardown guards, which check
    `is not None` after the reference has already been cleared. The guard looks
    present and does nothing.

    The `wait()` costs nothing on the finish path (`run()` is one statement from
    returning) and is the entire point on the teardown path. `export_dialog` learned
    this in isolation; three other dialogs kept the unsafe version until a user hit
    it by closing the Backup dialog while a slow destination probe was mid-flight."""
    if worker is None:
        return None
    if worker.isRunning():
        worker.wait()
    worker.deleteLater()
    return None


def fit_cell_widgets(tbl: QTableWidget, *cols: int) -> None:
    """Size `cols` — and every row — so no cell **widget** is clipped.

    Call **after** the rows are populated and **before** `fit_table_height`, which
    sums row heights and would otherwise bake in the pre-growth ones.

    Rows are measured across *all* columns, not just `cols`: a combo box in an
    un-listed column raises the row just as a button does. Widths are only touched
    for the columns you name, so a stretch column stays stretchy.

    This replaces per-page magic numbers. The Import page's holding table carried
    hand-tuned widths (150/130/210) from the first time this bit — issue #65, the
    *Assign* button clipped to *ssig* — which fixed that row and nothing else, and
    silently goes stale the moment a label, the font, or the padding changes."""
    rows, cols_n = tbl.rowCount(), tbl.columnCount()
    grid = 1 if tbl.showGrid() else 0       # the grid line eats a pixel of the cell
    for c in cols:
        need = max((tbl.cellWidget(r, c).sizeHint().width()
                    for r in range(rows) if tbl.cellWidget(r, c) is not None),
                   default=0)
        if need:
            tbl.setColumnWidth(c, need + CELL_WIDGET_PAD_H + grid)
    tallest = max((tbl.cellWidget(r, c).sizeHint().height()
                   for r in range(rows) for c in range(cols_n)
                   if tbl.cellWidget(r, c) is not None), default=0)
    if tallest:
        # Set the *minimum section size*, not per-row heights: `fit_table_height`
        # (and any later reload) calls `resizeRowsToContents`, which re-measures
        # from the items and would drop a row straight back to one line of text —
        # cell widgets aren't consulted. A minimum is a floor Qt won't resize below,
        # so it survives, and it keeps the rows uniform rather than only growing
        # whichever ones happen to hold a widget.
        tbl.verticalHeader().setMinimumSectionSize(
            tallest + CELL_WIDGET_PAD_V + grid)
        for r in range(rows):
            tbl.setRowHeight(r, max(tbl.rowHeight(r),
                                    tallest + CELL_WIDGET_PAD_V + grid))


class CollapsibleSection(QWidget):
    """A titled group whose body toggles open/closed via its header — the
    macOS-native disclosure-triangle pattern (a rotating arrow beside a bold
    title). `on_toggle(expanded)` fires on every change so the owning page can
    persist the open/closed state across a rebuild (pages reload on window focus,
    which would otherwise reset every section to its default). Add content to
    `.body` (a QVBoxLayout)."""

    def __init__(self, title: str, expanded: bool = True, on_toggle=None, parent=None):
        super().__init__(parent)
        self._on_toggle = on_toggle
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._btn = QToolButton()
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._btn.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._btn.toggled.connect(self._on_toggled)
        lay.addWidget(self._btn)
        self._body = QWidget()
        self.body = QVBoxLayout(self._body)
        self.body.setContentsMargins(18, 2, 0, 6)
        lay.addWidget(self._body)
        self._body.setVisible(expanded)

    def _on_toggled(self, on: bool):
        self._btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self._body.setVisible(on)
        if self._on_toggle is not None:
            self._on_toggle(on)


# ── async row thumbnails (Library / Sessions / Processing) ──────────────────

ROW_THUMB_SIZE = 20   # matches StatusPillDelegate's sizeHint floor — no row growth

# Two center-crop tunings, keyed alongside (path, size) in the cache since the
# same source decoded for a tiny row icon vs. a bigger grid/gallery tile wants
# a different crop. "row": aggressive half-width square, tuned for ~20px icons
# where a full-frame squash reads as noise. "square": a milder min(w, h) crop
# (matches detail._square_icon()'s tuning) for tiles big enough to keep more
# of the frame.
_thumb_cache: dict[tuple[str, int, str], tuple[float, QImage]] = {}
_THUMB_CACHE_CAP = 512


class _ThumbSignals(QObject):
    done = Signal(str, int, str, object)   # path, size, crop, QImage | None


class _ThumbLoadTask(QRunnable):
    """Decodes one image at a target size off the UI thread, then crops to a
    center square before the final scale-down. Smart-scope frames put the
    subject dead-center, and heroes aren't square (often letterboxed) — at
    icon size a full-frame squash reads as noise, while a tight center crop
    reads as the object. Builds a QImage (thread-safe), never a QPixmap
    (main-thread only)."""

    def __init__(self, path: str, size: int, crop: str, signals: _ThumbSignals):
        super().__init__()
        self._path, self._size, self._crop, self._signals = path, size, crop, signals

    def run(self):
        img = QImageReader(self._path).read()
        if img.isNull():
            self._signals.done.emit(self._path, self._size, self._crop, None)
            return
        w, h = img.width(), img.height()
        side = max(min(w, h) if self._crop == "square" else min(w // 2, h), 1)
        crop = img.copy((w - side) // 2, (h - side) // 2, side, side)
        scaled = crop.scaled(self._size, self._size,
                              Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._signals.done.emit(self._path, self._size, self._crop, scaled)


class ThumbnailLoader(QObject):
    """Async, cached small-image loader for table/grid icon cells. Decodes off
    the UI thread and memo-caches by (path, size, crop, mtime) so re-sorts/
    rebuilds don't redecode; a re-render (mtime change) invalidates the entry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _ThumbSignals()
        self._signals.done.connect(self._on_done)
        self._pending: dict[tuple[str, int, str], tuple[float, list]] = {}

    def request(self, path: Path, size: int, callback, crop: str = "row"):
        """callback(QPixmap | None) — called immediately on a cache hit, else
        once the background decode completes. `crop`: "row" (aggressive,
        tiny row icons) or "square" (milder, bigger tiles)."""
        key = (str(path), size, crop)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            callback(None)
            return
        cached = _thumb_cache.get(key)
        if cached and cached[0] == mtime:
            callback(QPixmap.fromImage(cached[1]))
            return
        pending = self._pending.get(key)
        if pending is not None:
            pending[1].append(callback)
            return
        self._pending[key] = (mtime, [callback])
        QThreadPool.globalInstance().start(_ThumbLoadTask(key[0], size, crop, self._signals))

    def _on_done(self, path: str, size: int, crop: str, img):
        key = (path, size, crop)
        entry = self._pending.pop(key, None)
        if entry is None:
            return
        mtime, callbacks = entry
        pm = None
        if img is not None:
            if len(_thumb_cache) > _THUMB_CACHE_CAP:
                _thumb_cache.clear()
            _thumb_cache[key] = (mtime, img)
            pm = QPixmap.fromImage(img)
        for cb in callbacks:
            cb(pm)


def modal_loop_active() -> bool:
    """True while a modal dialog or a popup (menu, combo drop-down) is up.

    Those run a **nested event loop**, and anything `deleteLater()`'d inside one
    is destroyed as soon as that loop iterates — i.e. while the C++ event handler
    that opened it is still on the stack. Rebuilding a page from under a nested
    loop therefore frees the very widget Qt is mid-dispatch on
    (`QAbstractItemView::mouseDoubleClickEvent` resuming on a deleted view = the
    0.3.0b3 SIGSEGV). Callers that tear down widgets must wait this out."""
    return (QApplication.activeModalWidget() is not None
            or QApplication.activePopupWidget() is not None)


def defer(widget, fn) -> None:
    """Run `fn` after the current Qt event handler has returned.

    For anything opening a modal/popup out of an item-view signal
    (`itemDoubleClicked`, `customContextMenuRequested`, …): those are emitted
    from inside the view's own C++ mouse handler, so a nested loop started there
    keeps that frame alive across every event it pumps. Deferring by one event
    cycle means no nested loop ever runs beneath an item-view frame. `widget` is
    the context object — if it's destroyed first, `fn` never runs."""
    QTimer.singleShot(0, widget, fn)


def connect_context_menu(view, handler) -> None:
    """Wire a custom context menu on `view`, opened **after** the mouse handler
    returns (`defer`). Every right-click menu goes through here: a `QMenu.exec()`
    called straight from `customContextMenuRequested` runs its nested loop inside
    the view's C++ mouse handler, so any rebuild that lands meanwhile deletes the
    view mid-dispatch. `handler` takes the click position."""
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    view.customContextMenuRequested.connect(
        lambda pos: defer(view, lambda: handler(pos)))


def drain_thumbnail_pool(msecs: int = 5000) -> None:
    """Block until background thumbnail decodes finish.

    `ThumbnailLoader` decodes images on the **global** `QThreadPool`. A task still
    running on a pool thread when Qt is torn down — app quit, or a test's
    QApplication teardown — runs native Qt image code against a half-destroyed Qt
    and **segfaults**: the intermittent CI SIGSEGV (exit 139) that passes on
    re-run, and a rare crash on quit mid-load. Call this before teardown so no
    decode outlives Qt. Best-effort — returns after `msecs` even if one is stuck."""
    QThreadPool.globalInstance().waitForDone(msecs)


class RowThumbnails:
    """Wires a table's rows to async hero thumbnails (`objects.hero_path`).
    Call `reset()` at the start of each table (re)build, `add(slug, item)` per
    captured row. A completed decode is applied to whichever item(s) are
    current for that slug — since `reset()` replaces the tracking dict on every
    rebuild, a callback that lands after a rebuild simply finds nothing (or the
    current row) for a stale slug, never a deleted Qt item."""

    def __init__(self, loader: ThumbnailLoader, size: int = ROW_THUMB_SIZE):
        self._loader = loader
        self._size = size
        self._items: dict[str, list] = {}

    def reset(self):
        self._items = {}

    def add(self, slug: str, item: QTableWidgetItem):
        hp = objects.hero_path(slug)
        if hp is None:
            return
        self._items.setdefault(slug, []).append(item)
        self._loader.request(hp, self._size, lambda pm, slug=slug: self._apply(slug, pm))

    def _apply(self, slug: str, pm):
        if pm is None:
            return
        icon = QIcon(pm)
        for item in self._items.get(slug, []):
            item.setIcon(icon)


class SegmentStack(QStackedWidget):
    """A QStackedWidget that sizes to its **current** page, not its widest one.

    A plain stack reports `max(page.sizeHint())` and stretches the current page
    to that, so parking a 2-button segment next to a 4-button one hands the short
    control ~100px of surplus. `make_segment`'s buttons are Fixed-width, and a
    QBoxLayout with nowhere to put surplus spreads it *between* the items — which
    is how "List | Grid" ended up drawn as two detached buttons rather than one
    joined pill.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


def make_segment(items, active_key):
    """A joined macOS-style segmented control: exclusive checkable buttons packed
    into a bordered frame (`#segControl` / `#segButton` in the QSS). `items` =
    [(key, label)]. Returns (frame, group, {key: button}).

    Shared so every segment in the app is the same control — the Library's
    Deep-sky|Media and List|Grid|Feed|Map rows, and the sky map's N|S toggle.
    """
    frame = QFrame()
    frame.setObjectName("segControl")
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    group = QButtonGroup(frame)
    group.setExclusive(True)
    btns: dict[str, QToolButton] = {}
    n = len(items)
    for i, (key, label) in enumerate(items):
        b = QToolButton()
        b.setObjectName("segButton")
        # Position so the QSS can round only the outer corners of the end buttons.
        b.setProperty("segpos", "solo" if n == 1 else
                      "first" if i == 0 else "last" if i == n - 1 else "mid")
        b.setText(label)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        group.addButton(b)
        btns[key] = b
        row.addWidget(b)
    btns[active_key].setChecked(True)
    return frame, group, btns

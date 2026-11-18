"""The grouped source-list sidebar (UI_ROADMAP → 1.0 redesign → Sidebar).

Overview, then three titled groups — **Library** (Deep Sky · Media · Journal),
**Workflow** (Import · Processing), **Observing** (Planning · Devices) — each row a
Lucide icon, a label and an optional live count, as in Finder, Mail or Lightroom.

It is a QListWidget with two kinds of row: *section headers* (not selectable, not
enabled, so keyboard navigation steps over them) and *page rows*, which carry the
index of the page they show. The shell talks to it in page indices
(`select_page`, `page_selected`), never in list rows, so adding a header can't
shift what Ctrl+1 opens.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate

from m110.ui import theme
from m110.ui.theme import icons
from m110.ui.theme.fonts import section_font, tabular

PAGE_ROLE = Qt.ItemDataRole.UserRole + 1     # page index (page rows only)
COUNT_ROLE = Qt.ItemDataRole.UserRole + 2    # live count text, "" for none
HEADER_ROLE = Qt.ItemDataRole.UserRole + 3   # True on section-header rows


@dataclass(frozen=True)
class Place:
    """One sidebar destination: a page of the shell."""
    key: str          # stable id ("deepsky", "media", …)
    label: str        # the sidebar label == the toolbar title
    icon: str         # Lucide icon name
    section: str      # group header ("" = ungrouped, at the top)


# The one list of places. The page stack, the sidebar rows and the View menu's
# Ctrl+1…8 shortcuts are all built from this, so they can't drift apart.
PLACES = [
    Place("overview", "Overview", "house", ""),
    Place("deepsky", "Deep Sky", "layout-grid", "Library"),
    Place("media", "Media", "film", "Library"),
    Place("journal", "Journal", "book-open", "Library"),
    Place("import", "Import", "download", "Workflow"),
    Place("processing", "Processing", "layers", "Workflow"),
    Place("planning", "Planning", "moon", "Observing"),
    Place("devices", "Devices", "telescope", "Observing"),
]

ROW_HEIGHT = 26          # a macOS sidebar row (Finder/Mail run 24–28)
HEADER_HEIGHT = 30       # extra air above each group title


class _SidebarDelegate(QStyledItemDelegate):
    """Default row painting, plus a right-aligned tabular count; headers drawn as
    tracked small caps."""

    def sizeHint(self, option, index):
        h = HEADER_HEIGHT if index.data(HEADER_ROLE) else ROW_HEIGHT
        return QSize(option.rect.width(), h)

    def paint(self, painter, option, index):
        t = theme.active_tokens()
        if index.data(HEADER_ROLE):
            painter.save()
            painter.setFont(section_font())
            painter.setPen(theme.muted_color())
            r = option.rect.adjusted(theme.tokens.SPACE["md"], 0, 0,
                                     -theme.tokens.SPACE["xs"])
            painter.drawText(r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                             index.data(Qt.ItemDataRole.DisplayRole))
            painter.restore()
            return
        super().paint(painter, option, index)
        count = index.data(COUNT_ROLE)
        if count:
            painter.save()
            painter.setFont(tabular(option.font))
            from PySide6.QtGui import QColor
            painter.setPen(QColor(t.text_secondary))
            r = QRect(option.rect).adjusted(0, 0, -theme.tokens.SPACE["md"], 0)
            painter.drawText(r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(count))
            painter.restore()


class Sidebar(QListWidget):
    """The source list. Emits `page_selected(page_index)`."""

    page_selected = Signal(int)

    def __init__(self, places=PLACES, parent=None):
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setItemDelegate(_SidebarDelegate(self))
        self.setIconSize(QSize(16, 16))
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Sidebar")
        self._places = list(places)
        self._rows: dict[int, int] = {}          # page index → list row
        section = None
        for i, p in enumerate(self._places):
            if p.section and p.section != section:
                hdr = QListWidgetItem(p.section)
                hdr.setData(HEADER_ROLE, True)
                hdr.setFlags(Qt.ItemFlag.NoItemFlags)
                self.addItem(hdr)
            section = p.section
            it = QListWidgetItem(p.label)
            it.setData(PAGE_ROLE, i)
            it.setData(COUNT_ROLE, "")
            it.setToolTip(f"{p.label} ({_shortcut_text(i)})")
            self._rows[i] = self.count()
            self.addItem(it)
        self.restyle()
        self.currentRowChanged.connect(self._on_row)

    # ---- API in page indices ----
    @property
    def places(self) -> list[Place]:
        return list(self._places)

    def select_page(self, page: int) -> None:
        row = self._rows.get(page)
        if row is not None and row != self.currentRow():
            self.setCurrentRow(row)

    def current_page(self) -> int:
        it = self.currentItem()
        v = it.data(PAGE_ROLE) if it is not None else None
        return -1 if v is None else int(v)

    def page_item(self, page: int) -> QListWidgetItem:
        return self.item(self._rows[page])

    def set_count(self, key: str, count) -> None:
        """Show a live count beside a place ('' / None / 0 hides it)."""
        for i, p in enumerate(self._places):
            if p.key == key:
                self.page_item(i).setData(COUNT_ROLE, str(count) if count else "")
                return

    def count_text(self, key: str) -> str:
        i = next(i for i, p in enumerate(self._places) if p.key == key)
        return self.page_item(i).data(COUNT_ROLE) or ""

    def restyle(self) -> None:
        """Re-tint the icons from the current tokens (theme change)."""
        for i, p in enumerate(self._places):
            self.page_item(i).setIcon(icons.icon(p.icon, "text_secondary",
                                                 selected_role="selection_text"))

    def _on_row(self, row: int) -> None:
        it = self.item(row) if row >= 0 else None
        v = it.data(PAGE_ROLE) if it is not None else None
        if v is not None:
            self.page_selected.emit(int(v))


def _shortcut_text(page: int) -> str:
    from PySide6.QtGui import QKeySequence
    return QKeySequence(f"Ctrl+{page + 1}").toString(
        QKeySequence.SequenceFormat.NativeText)

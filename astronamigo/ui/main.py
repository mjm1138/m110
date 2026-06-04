"""Astronamigo — PySide6 desktop shell.

v0.1 Library (read-only) with object detail/gallery. Left: the catalog joined
with derived totals (capture status). Right: detail pane for the selected
object — metadata, hero image, journal text, and a thumbnail gallery, all read
from the live data store / generated site.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QLabel,
    QSplitter, QWidget, QVBoxLayout, QTextBrowser, QListWidget, QListWidgetItem,
    QScrollArea,
)

from astronamigo import config, derived, objects
from astronamigo.catalog import load_catalog, catalog_sort_key

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
STATUS_COLOR = {"deep_stack": QColor("#3fb950"), "initial": QColor("#d29922")}
MUTED = QColor("#8b949e")


def _status_label(status: str | None, captured: bool) -> str:
    if not captured:
        return "—"
    return STATUS_LABEL.get(status, status or "—")


class _NumItem(QTableWidgetItem):
    """Table item that sorts by an arbitrary key (number or tuple) while
    displaying text."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self._key < other._key
        return super().__lt__(other)


class DetailPane(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._placeholder()

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _placeholder(self):
        self._clear()
        self._lay.addWidget(QLabel("Select an object to see details."))

    def show_object(self, slug: str, e: dict, t: dict):
        self._clear()
        captured = bool(t)

        title = QLabel(f"<h2>{e.get('id', '')} &mdash; {e.get('name') or ''}</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)

        bits = [str(e.get("type") or "").replace("_", " ")]
        if e.get("magnitude") is not None:
            bits.append(f"mag {e['magnitude']}")
        if e.get("size"):
            bits.append(str(e["size"]))
        if e.get("season"):
            bits.append(str(e["season"]))
        meta = QLabel(" · ".join(b for b in bits if b))
        meta.setStyleSheet("color:#8b949e")
        self._lay.addWidget(meta)

        if captured:
            self._lay.addWidget(QLabel(
                f"<b>{_status_label(t.get('status'), True)}</b> · "
                f"{t.get('integration_hms', '')} · "
                f"{t.get('session_count', '')} sessions · "
                f"{t.get('frames', '')} frames"))
        else:
            self._lay.addWidget(QLabel("<i>not captured</i>"))

        hp = objects.hero_path(slug)
        if hp:
            pm = QPixmap(str(hp))
            if not pm.isNull():
                lbl = QLabel()
                lbl.setPixmap(pm.scaledToWidth(min(pm.width(), 520),
                                               Qt.SmoothTransformation))
                self._lay.addWidget(lbl)

        fm, body = objects.read_journal(slug)
        if fm.get("hero_caption"):
            cap = QLabel(fm["hero_caption"])
            cap.setWordWrap(True)
            cap.setStyleSheet("color:#8b949e; font-size:11px")
            self._lay.addWidget(cap)
        if body.strip():
            tb = QTextBrowser()
            tb.setMarkdown(body)
            tb.setOpenExternalLinks(True)
            tb.setMinimumHeight(220)
            self._lay.addWidget(tb)

        imgs = [im for im in derived.images_for(slug)
                if im.get("viewable") and im.get("thumb")]
        if imgs:
            self._lay.addWidget(QLabel(f"<b>Gallery</b> ({len(imgs)})"))
            gallery = QListWidget()
            gallery.setViewMode(QListWidget.IconMode)
            gallery.setIconSize(QSize(140, 140))
            gallery.setResizeMode(QListWidget.Adjust)
            gallery.setMovement(QListWidget.Static)
            gallery.setMaximumHeight(190)
            for im in imgs:
                tp = config.SITE_DIR / im["thumb"]
                if tp.is_file():
                    gallery.addItem(QListWidgetItem(
                        QIcon(str(tp)), im.get("display_name") or im.get("name") or ""))
            self._lay.addWidget(gallery)

        self._lay.addStretch(1)


class MainWindow(QMainWindow):
    HEADERS = ["Object", "Name", "Type", "Season", "Mag",
               "Status", "Integration", "Sessions"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Astronamigo — Library")

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No catalog found at:\n{config.CATALOG_TOML}\n\n"
                f"Set ASTRONAMIGO_DATA_ROOT to your Astronomy folder."))
            self.resize(560, 160)
            return

        self._cat = load_catalog()
        self._totals = derived.totals_by_slug()
        captured = sum(1 for s in self._cat if s in self._totals)

        self.table = self._build_table()
        self.detail = DetailPane()
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setSizes([520, 440])
        self.setCentralWidget(splitter)

        self.table.itemSelectionChanged.connect(self._on_select)

        note = "" if derived.derived_available() else " · derived rollups not found (run rebuild.sh)"
        self.statusBar().showMessage(
            f"{captured}/{len(self._cat)} captured · reading {config.DATA_ROOT}{note}")
        self.resize(1080, 680)

    def _build_table(self) -> QTableWidget:
        cat, totals = self._cat, self._totals
        table = QTableWidget(len(cat), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)

        # default order = natural catalog order (M1, M2, … M10), like the site
        rows = sorted(cat.items(), key=lambda kv: catalog_sort_key(kv[1].get("id", "")))
        for row, (slug, e) in enumerate(rows):
            t = totals.get(slug, {})
            captured = bool(t)

            obj = _NumItem(str(e.get("id", "")), catalog_sort_key(e.get("id", "")))
            obj.setData(Qt.UserRole, slug)
            table.setItem(row, 0, obj)
            table.setItem(row, 1, QTableWidgetItem(str(e.get("name") or "")))
            table.setItem(row, 2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            table.setItem(row, 3, QTableWidgetItem(str(e.get("season") or "")))

            mag = e.get("magnitude")
            table.setItem(row, 4, _NumItem("" if mag is None else f"{mag}",
                                           float(mag) if mag is not None else 99.0))

            status_item = QTableWidgetItem(_status_label(t.get("status"), captured))
            status_item.setForeground(STATUS_COLOR.get(t.get("status"), MUTED))
            table.setItem(row, 5, status_item)

            integ_min = float(t.get("integration_min", 0) or 0)
            table.setItem(row, 6, _NumItem(t.get("integration_hms", "") if captured else "", integ_min))
            sc = int(t.get("session_count", 0) or 0)
            table.setItem(row, 7, _NumItem(str(sc) if captured else "", float(sc)))

            if not captured:
                for c in range(len(self.HEADERS)):
                    if c != 5:
                        table.item(row, c).setForeground(MUTED)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.AscendingOrder)  # default: natural M1,M2,…
        return table

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        slug = self.table.item(items[0].row(), 0).data(Qt.UserRole)
        self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Astronamigo")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

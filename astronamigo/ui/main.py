"""Astronamigo — PySide6 desktop shell.

v0.1 Library (read-only). Joins the live catalog with the derived totals so each
object shows capture status, integration, and session count. Proves the loop:
separate repo → engine reads live Astronomy data (catalog + derived rollups) →
PySide6 renders it. Mutating features (Refresh, Ingest, edits) come later.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QLabel,
)

from astronamigo import config, derived
from astronamigo.catalog import load_catalog

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
STATUS_COLOR = {
    "deep_stack": QColor("#3fb950"),   # green
    "initial": QColor("#d29922"),      # amber
}
MUTED = QColor("#8b949e")


class _NumItem(QTableWidgetItem):
    """Table item that sorts by a numeric key while displaying text."""

    def __init__(self, text: str, sort_key: float):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self._key < other._key
        return super().__lt__(other)


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

        cat = load_catalog()
        totals = derived.totals_by_slug()
        captured = sum(1 for s in cat if s in totals)

        table = QTableWidget(len(cat), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)  # populate first, then enable

        for row, (slug, e) in enumerate(sorted(cat.items())):
            t = totals.get(slug, {})
            status = t.get("status")

            def put(col, item):
                table.setItem(row, col, item)

            put(0, QTableWidgetItem(str(e.get("id", ""))))
            put(1, QTableWidgetItem(str(e.get("name") or "")))
            put(2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            put(3, QTableWidgetItem(str(e.get("season") or "")))

            mag = e.get("magnitude")
            put(4, _NumItem("" if mag is None else f"{mag}",
                            float(mag) if mag is not None else 99.0))

            label = STATUS_LABEL.get(status, "—" if not t else status or "—")
            status_item = QTableWidgetItem(label)
            status_item.setForeground(STATUS_COLOR.get(status, MUTED))
            put(5, status_item)

            integ_min = t.get("integration_min", 0) or 0
            put(6, _NumItem(t.get("integration_hms", "") if t else "", float(integ_min)))

            sc = t.get("session_count", 0) or 0
            put(7, _NumItem(str(sc) if t else "", float(sc)))

            if not t:  # uncaptured → mute the whole row
                for c in range(len(self.HEADERS)):
                    it = table.item(row, c)
                    if c != 5:
                        it.setForeground(MUTED)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        self.setCentralWidget(table)

        derived_note = "" if derived.derived_available() else " · derived rollups not found (run rebuild.sh)"
        self.statusBar().showMessage(
            f"{captured}/{len(cat)} captured · reading {config.DATA_ROOT}{derived_note}")
        self.resize(900, 620)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Astronamigo")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

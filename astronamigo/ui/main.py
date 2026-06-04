"""Astronamigo — PySide6 desktop shell.

v0.1 skeleton (step 0.1b): a read-only Library window over the live catalog.
Proves the loop: separate repo → engine reads live Astronomy data via config →
PySide6 renders it. Mutating features come in later 0.1 steps.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QLabel,
)

from astronamigo import config
from astronamigo.catalog import load_catalog

# (catalog key, column header)
COLUMNS = [
    ("id", "Object"),
    ("name", "Name"),
    ("type", "Type"),
    ("season", "Season"),
    ("magnitude", "Mag"),
    ("size", "Size"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Astronamigo — Library (v0.1 skeleton)")

        if not config.data_root_ok():
            self.setCentralWidget(QLabel(
                f"No catalog found at:\n{config.CATALOG_TOML}\n\n"
                f"Set ASTRONAMIGO_DATA_ROOT to your Astronomy folder."
            ))
            self.resize(560, 160)
            return

        cat = load_catalog()
        table = QTableWidget(len(cat), len(COLUMNS))
        table.setHorizontalHeaderLabels([h for _, h in COLUMNS])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)

        for row, (_slug, entry) in enumerate(sorted(cat.items())):
            for col, (key, _h) in enumerate(COLUMNS):
                val = entry.get(key, "")
                table.setItem(row, col, QTableWidgetItem("" if val is None else str(val)))

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        self.setCentralWidget(table)
        self.statusBar().showMessage(f"{len(cat)} objects · reading {config.DATA_ROOT}")
        self.resize(820, 600)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Astronamigo")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

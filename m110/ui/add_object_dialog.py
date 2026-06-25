"""Add-object dialog — add an arbitrary object to the Library.

Type a name or catalog designation; M110 resolves its fields offline against the
bundled reference instantly and shows an **editable** preview. "Look up online"
enriches gaps via Simbad (optional `online` extra) on a worker thread. Preview-then-
confirm: nothing is written until Add. The committed entry is appended to
`library.toml` and gets a journal stub (engine `catalog.add_library_entry`).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)

from m110 import catalog


_FIELDS = ["name", "type", "magnitude", "size", "season", "ra_deg", "dec_deg"]
_LABELS = {"name": "Name", "type": "Type", "magnitude": "Magnitude", "size": "Size",
           "season": "Season", "ra_deg": "RA (deg)", "dec_deg": "Dec (deg)"}


class _OnlineWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, identifier, parent=None):
        super().__init__(parent)
        self._identifier = identifier

    def run(self):
        try:
            self.done.emit(catalog.resolve_new_object(self._identifier, online=True))
        except catalog.OnlineLookupError as e:
            self.failed.emit(str(e))
        except Exception as e:                           # pragma: no cover - defensive
            self.failed.emit(f"{type(e).__name__}: {e}")


class AddObjectDialog(QDialog):
    added = Signal(str)              # slug of the newly added object

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add object")
        self._slug = None
        self._worker = None

        lay = QVBoxLayout(self)
        # Identifier row.
        idrow = QHBoxLayout()
        idrow.addWidget(QLabel("Name / designation:"))
        self._ident = QLineEdit()
        self._ident.setPlaceholderText("e.g. NGC 7000, C20, Barnard 33")
        self._ident.textChanged.connect(self._on_ident_changed)
        self._ident.returnPressed.connect(self._resolve_offline)
        idrow.addWidget(self._ident, 1)
        lay.addLayout(idrow)

        # Editable preview.
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for f in _FIELDS:
            e = QLineEdit()
            self._edits[f] = e
            form.addRow(_LABELS[f], e)
        lay.addLayout(form)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#8b949e")
        lay.addWidget(self._status)

        # Buttons.
        btns = QHBoxLayout()
        self._online_btn = QPushButton("Look up online")
        self._online_btn.clicked.connect(self._resolve_online)
        self._add_btn = QPushButton("Add")
        self._add_btn.setDefault(True)
        self._add_btn.clicked.connect(self._do_add)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(self._online_btn)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(self._add_btn)
        lay.addLayout(btns)

        self._sync_enabled()
        self.resize(420, 320)

    # ---- resolution ----
    def _on_ident_changed(self, _text):
        self._resolve_offline()

    def _resolve_offline(self):
        ident = self._ident.text().strip()
        if not ident:
            self._slug = None
            self._sync_enabled()
            self._status.setText("")
            return
        r = catalog.resolve_new_object(ident)            # offline: reference + derived
        self._apply_resolution(r)
        srcs = set(r["source"].values())
        self._status.setText(
            f"Resolved from the bundled reference ({r['slug']})." if "reference" in srcs
            else f"Not in the bundled reference ({r['slug']}) — fill manually or look "
                 "up online.")
        self._sync_enabled()

    def _resolve_online(self):
        ident = self._ident.text().strip()
        if not ident or self._worker is not None:
            return
        self._online_btn.setEnabled(False)
        self._status.setText("Looking up online…")
        self._worker = _OnlineWorker(ident, self)
        self._worker.done.connect(self._on_online_done)
        self._worker.failed.connect(self._on_online_failed)
        self._worker.finished.connect(self._clear_worker)
        self._worker.start()

    def _on_online_done(self, r):
        self._apply_resolution(r)
        srcs = r["source"]
        n = sum(1 for v in srcs.values() if v == "online")
        self._status.setText(f"Online lookup filled {n} field(s)." if n
                             else "Online lookup found nothing to add.")
        self._sync_enabled()

    def _on_online_failed(self, msg):
        self._status.setText("")
        QMessageBox.warning(self, "Online lookup unavailable", msg)

    def _clear_worker(self):
        self._worker = None
        self._online_btn.setEnabled(bool(self._ident.text().strip()))

    def _apply_resolution(self, r: dict):
        self._slug = r["slug"]
        entry = r["entry"]
        for f, e in self._edits.items():
            v = entry.get(f)
            e.setText("" if v is None else str(v))

    # ---- commit ----
    def _do_add(self):
        if not self._slug:
            return
        entry = {"id": self._ident.text().strip()}
        for f, e in self._edits.items():
            txt = e.text().strip()
            if not txt:
                continue
            if f in ("magnitude", "ra_deg", "dec_deg"):
                try:
                    entry[f] = float(txt)
                except ValueError:
                    QMessageBox.warning(self, "Invalid value",
                                        f"{_LABELS[f]} must be a number.")
                    return
            else:
                entry[f] = txt
        try:
            catalog.add_library_entry(self._slug, entry)
        except ValueError as e:
            QMessageBox.warning(self, "Can't add object", str(e))
            return
        self.added.emit(self._slug)
        self.accept()

    def _sync_enabled(self):
        has = bool(self._ident.text().strip())
        self._online_btn.setEnabled(has and self._worker is None)
        self._add_btn.setEnabled(bool(self._slug))

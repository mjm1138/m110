"""Clean up imported media sidecars — preview, then confirm.

Ingest used to copy *every* file out of a `Media/<Category>_photo|_video` device
folder, so stores filled with two kinds of file nothing reads: the redundant
`<stem>_thn.jpg` beside a **photo** (the original is right there at full size),
and the Seestar's `.avi.idx`/`.avi.txt` companions. Import no longer takes them;
this removes the ones already on disk.

Destructive, so it follows the store's write rule: the scan is read-only and the
engine (`media.discard`) re-checks every path against a freshly computed
candidate set before unlinking. A sidecar serving as a **video poster** is never
a candidate — it is the only still that video has.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from m110 import config, media
from m110.ui.media_detail import fmt_size

_PATH_ROLE = Qt.ItemDataRole.UserRole + 1


class MediaCleanupDialog(QDialog):
    """Checkable tree of removable files, grouped by folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clean up imported sidecars")
        self.setModal(True)
        self.resize(620, 460)
        self._removed = 0

        lay = QVBoxLayout(self)
        self._intro = QLabel(
            "These files were copied in by earlier imports and nothing in M110 "
            "reads them: the small <b>_thn.jpg</b> duplicate beside a photo, and "
            "the Seestar's <b>.avi.idx</b>/<b>.avi.txt</b> companions.<br><br>"
            "Thumbnails that a <b>video</b> depends on are not listed — they're "
            "the only preview frame those clips have.")
        self._intro.setTextFormat(Qt.RichText)
        self._intro.setWordWrap(True)
        lay.addWidget(self._intro)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["File", "Size"])
        self._tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self._tree, 1)

        self._summary = QLabel()
        self._summary.setProperty("muted", True)
        lay.addWidget(self._summary)

        row = QHBoxLayout()
        self._all_btn = QPushButton("Select all")
        self._all_btn.clicked.connect(lambda: self._set_all(True))
        self._none_btn = QPushButton("Select none")
        self._none_btn.clicked.connect(lambda: self._set_all(False))
        row.addWidget(self._all_btn)
        row.addWidget(self._none_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self._buttons = QDialogButtonBox()
        self._delete_btn = self._buttons.addButton(
            "Delete selected", QDialogButtonBox.AcceptRole)
        self._buttons.addButton("Close", QDialogButtonBox.RejectRole)
        self._delete_btn.clicked.connect(self._on_delete)
        self._buttons.rejected.connect(self.reject)
        lay.addWidget(self._buttons)

        self._populate()

    def removed_count(self) -> int:
        return self._removed

    # ---- content ----
    def _populate(self):
        self._tree.blockSignals(True)
        self._tree.clear()
        candidates = media.cleanup_candidates()
        by_dir: dict[str, list] = {}
        for p in candidates:
            try:
                rel = str(p.parent.relative_to(config.DATA_ROOT))
            except ValueError:
                rel = str(p.parent)
            by_dir.setdefault(rel, []).append(p)
        for folder in sorted(by_dir):
            files = sorted(by_dir[folder], key=lambda f: f.name.lower())
            total = sum(self._size(f) for f in files)
            parent = QTreeWidgetItem(
                self._tree, [f"{folder}  ({len(files)} files)", fmt_size(total)])
            parent.setFlags(parent.flags() | Qt.ItemIsUserCheckable
                            | Qt.ItemIsAutoTristate)
            parent.setCheckState(0, Qt.Unchecked)
            for f in files:
                child = QTreeWidgetItem(parent, [f.name, fmt_size(self._size(f))])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, _PATH_ROLE, str(f))
            parent.setExpanded(len(by_dir) == 1)
        self._tree.blockSignals(False)
        self._tree.resizeColumnToContents(0)
        if not candidates:
            self._intro.setText("Nothing to clean up — no leftover sidecars "
                                "were found in your Media folder.")
            self._all_btn.setEnabled(False)
            self._none_btn.setEnabled(False)
            self._tree.hide()
        self._update_summary()

    @staticmethod
    def _size(p) -> int:
        try:
            return p.stat().st_size
        except OSError:
            return 0

    def _checked_paths(self) -> list[str]:
        out = []
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    out.append(child.data(0, _PATH_ROLE))
        return out

    def _set_all(self, on: bool):
        state = Qt.Checked if on else Qt.Unchecked
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            parent.setCheckState(0, state)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, state)
        self._tree.blockSignals(False)
        self._update_summary()

    def _on_item_changed(self, *_):
        self._update_summary()

    def _update_summary(self):
        paths = self._checked_paths()
        from pathlib import Path
        total = sum(self._size(Path(p)) for p in paths)
        self._summary.setText(
            f"{len(paths)} files selected · {fmt_size(total)} to free"
            if paths else "Nothing selected.")
        self._delete_btn.setEnabled(bool(paths))

    # ---- action ----
    def _on_delete(self):
        paths = self._checked_paths()
        if not paths:
            return
        if QMessageBox.warning(
                self, "Delete files",
                f"Permanently delete {len(paths)} file"
                f"{'s' if len(paths) != 1 else ''} from your Media folder?\n\n"
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        result = media.discard(paths)
        self._removed += result["deleted"]
        msg = (f"Deleted {result['deleted']} files, freeing "
               f"{fmt_size(result['bytes'])}.")
        if result["skipped"]:
            msg += (f"\n\n{result['skipped']} were skipped — they were no longer "
                    "safe to remove (a file is never deleted if it has since "
                    "become a video's only preview frame).")
        QMessageBox.information(self, "Clean up", msg)
        self._populate()

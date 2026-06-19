"""Shared per-object detail pane (used by the Catalog page; opened from anywhere).

Header + status + hero (scales to the pane) + journal (view/edit the raw
`journal.md`) + gallery (double-click → image viewer) + an Import-finished-work
entry when a processing sandbox has output to bring back.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QFontDatabase
from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QListWidget,
    QListWidgetItem, QScrollArea, QPlainTextEdit, QPushButton,
)

from m110 import config, derived, objects, siril
from m110.ui.image_viewer import ScalableImage, ImageViewer
from m110.ui.widgets import status_label, targets_for_slug


class DetailPane(QScrollArea):
    # Opens/closes the journal editor → the shell locks nav + actions so a
    # selection change or auto-refresh can't discard in-progress edits.
    editing_changed = Signal(bool)
    # The user asks to import finished processing output for an object.
    import_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._current = None        # (slug, e, t) of the shown object
        self._editing = False
        self._gallery = None
        self._gallery_items = []    # parallel [(name, view_path)] for the viewer
        self.placeholder()

    def is_editing(self) -> bool:
        return self._editing

    @staticmethod
    def _has_finished_work(slug: str) -> bool:
        return any(siril.has_unimported_output(t) for t in targets_for_slug(slug))

    def _clear(self):
        self._gallery = None
        self._clear_layout(self._lay)

    @staticmethod
    def _clear_layout(layout):
        # Recurse: takeAt on a nested layout (addLayout) returns a layout item
        # whose child widgets must be deleted too — otherwise buttons added via
        # sub-layouts (Edit / Save+Cancel) leak and pile up on every re-render
        # (and clicking a stale one can crash on teardown).
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                DetailPane._clear_layout(sub)
                sub.deleteLater()

    def placeholder(self):
        self._current = None
        self._clear()
        self._lay.addWidget(QLabel("Select an object to see details."))

    def show_object(self, slug: str, e: dict, t: dict):
        self._current = (slug, e, t)
        self._editing = False
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
                f"<b>{status_label(t.get('status'), True)}</b> · "
                f"{t.get('integration_hms', '')} · "
                f"{t.get('session_count', '')} sessions · "
                f"{t.get('frames', '')} frames"))
            # Processing-prep happens automatically (per the Preferences workflow
            # setting), so no manual "Prepare" button — only offer import when a
            # sandbox has finished output to bring back.
            if self._has_finished_work(slug):
                btn_row = QHBoxLayout()
                imp_btn = QPushButton("Import finished work…")
                imp_btn.setToolTip("Bring your processed renders/stack into the "
                                   "Library and tidy the working folder")
                imp_btn.clicked.connect(lambda: self.import_requested.emit(slug))
                btn_row.addWidget(imp_btn)
                btn_row.addStretch(1)
                self._lay.addLayout(btn_row)
        else:
            self._lay.addWidget(QLabel("<i>not captured</i>"))

        hp = objects.hero_path(slug)
        if hp:
            pm = QPixmap(str(hp))
            if not pm.isNull():
                self._lay.addWidget(ScalableImage(pm, max_height=460))

        fm, body = objects.read_journal(slug)
        if fm.get("hero_caption"):
            cap = QLabel(fm["hero_caption"])
            cap.setWordWrap(True)
            cap.setStyleSheet("color:#8b949e; font-size:11px")
            self._lay.addWidget(cap)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Journal</b>"))
        header.addStretch(1)
        edit_btn = QPushButton("Edit")
        edit_btn.setToolTip("Edit this object's journal (Objects/<id>/journal.md)")
        edit_btn.clicked.connect(self._enter_edit)
        header.addWidget(edit_btn)
        self._lay.addLayout(header)
        if body.strip():
            tb = QTextBrowser()
            tb.setMarkdown(objects.journal_to_markdown(body))
            tb.setOpenExternalLinks(True)
            tb.setMinimumHeight(220)
            self._lay.addWidget(tb)
        else:
            empty = QLabel("<i>No notes yet — click Edit to start.</i>")
            empty.setStyleSheet("color:#8b949e")
            self._lay.addWidget(empty)

        imgs = [im for im in derived.images_for(slug) if im.get("thumb")]
        if imgs:
            self._lay.addWidget(QLabel(f"<b>Gallery</b> ({len(imgs)}) — "
                                       "<span style='color:#8b949e'>double-click to view</span>"))
            gallery = QListWidget()
            gallery.setViewMode(QListWidget.IconMode)
            gallery.setIconSize(QSize(160, 160))
            gallery.setResizeMode(QListWidget.Adjust)
            gallery.setMovement(QListWidget.Static)
            gallery.setMinimumHeight(360)
            gallery.setSpacing(6)
            self._gallery_items = []
            for im in imgs:
                tp = config.RENDERS_DIR / im["thumb"]
                if not tp.is_file():
                    continue
                name = im.get("name") or ""
                gallery.addItem(QListWidgetItem(QIcon(str(tp)), name))
                full = im.get("full")
                view = str(config.DATA_ROOT / full) if full else str(tp)
                self._gallery_items.append((name, view))
            gallery.itemDoubleClicked.connect(self._open_gallery_item)
            self._gallery = gallery
            self._lay.addWidget(gallery)

        self._lay.addStretch(1)

    def _open_gallery_item(self, item):
        if not self._gallery:
            return
        row = self._gallery.row(item)
        if 0 <= row < len(self._gallery_items):
            ImageViewer(list(self._gallery_items), row, parent=self).exec()

    # ---- journal editing ----
    def _enter_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        self._editing = True
        self.editing_changed.emit(True)
        self._clear()

        self._lay.addWidget(QLabel(
            f"<b>Editing journal</b> &mdash; {e.get('id', '')} "
            f"&middot; <code>Objects/{objects.object_folder_name(slug)}/journal.md</code>"))

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(objects.read_journal_text(slug))
        self._editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._editor.setMinimumHeight(360)
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._lay.addWidget(self._editor)

        hint = QLabel("Frontmatter between the <code>---</code> fences feeds the "
                      "gallery (name / hero_caption / hero); everything below is Markdown.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e; font-size:11px")
        self._lay.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel_edit)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save_edit)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        self._lay.addLayout(buttons)
        self._lay.addStretch(1)
        self._editor.setFocus()

    def _save_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        objects.write_journal(slug, self._editor.toPlainText())
        self._editing = False
        self.editing_changed.emit(False)
        self.show_object(slug, e, t)

    def _cancel_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        self._editing = False
        self.editing_changed.emit(False)
        self.show_object(slug, e, t)

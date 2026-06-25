"""Shared per-object detail pane (used by the Catalog page; opened from anywhere).

Header + status + hero (scales to the pane) + **Object Notes** (view/edit the raw
`journal.md` — the object's entry in the Journal) + gallery (double-click → image
viewer) + an Import-finished-work entry when a processing sandbox has output to
bring back.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QFontDatabase
from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QListWidget,
    QListWidgetItem, QScrollArea, QPlainTextEdit, QPushButton, QTableWidgetItem,
)

from m110 import config, derived, objects, siril
from m110.ui.image_viewer import ScalableImage, ImageViewer
from m110.ui.widgets import status_label, targets_for_slug, make_table


def _section_label(text: str) -> QLabel:
    lbl = QLabel(f"<b>{text}</b>")
    lbl.setTextFormat(Qt.RichText)
    lbl.setStyleSheet("margin-top:8px")
    return lbl


def _fmt_hm(minutes: float) -> str:
    m = int(round(minutes or 0))
    return f"{m // 60}:{m % 60:02d}"


# The bundled season strings are hand-set for ~40°N (the reference site). Real
# latitude-aware season derivation arrives with the planning phase (ROADMAP item 1);
# until then we label the implied latitude rather than imply universality.
_SEASON_LATITUDE = "40°N"


def _ra_hms(deg: float) -> str:
    """RA decimal degrees → sexagesimal hours, e.g. 202.4696 → '13h29m52.7s'."""
    h = float(deg) / 15.0
    hh = int(h)
    mm = int((h - hh) * 60)
    ss = (h - hh - mm / 60) * 3600
    return f"{hh:02d}h{mm:02d}m{ss:04.1f}s"


def _dec_dms(deg: float) -> str:
    """Dec decimal degrees → signed sexagesimal, e.g. 47.1952 → '+47°11′43″'."""
    d = float(deg)
    sign = "-" if d < 0 else "+"
    d = abs(d)
    dd = int(d)
    mm = int((d - dd) * 60)
    ss = (d - dd - mm / 60) * 3600
    return f"{sign}{dd:02d}°{mm:02d}′{ss:02.0f}″"


class DetailPane(QScrollArea):
    # Opens/closes the journal editor → the shell locks nav + actions so a
    # selection change or auto-refresh can't discard in-progress edits.
    editing_changed = Signal(bool)
    # The user asks to import finished processing output for an object.
    import_requested = Signal(str)
    # Object Notes were saved → other views (e.g. the Journal feed) should reload.
    saved = Signal(str)

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

        from m110 import catalog
        ids = catalog.object_identifiers(slug, e)
        title = QLabel(f"<h2>{' · '.join(ids)} &mdash; {e.get('name') or ''}</h2>")
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
        header.addWidget(QLabel("<b>Object Notes</b>"))
        header.addStretch(1)
        edit_btn = QPushButton("Edit")
        edit_btn.setToolTip("Edit this object's notes (Objects/<id>/journal.md)")
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

        if captured:
            self._add_processing_section(slug)
            self._add_sessions_section(slug)
        self._add_metadata_section(slug, e)

        self._lay.addStretch(1)

    # ---- enrichment sections (Phase 3) ----
    def _section_table(self, title: str, headers: list[str], rows: list[list[str]]):
        self._lay.addWidget(_section_label(title))
        tbl = make_table(headers)
        tbl.setSortingEnabled(False)
        for r in rows:
            i = tbl.rowCount()
            tbl.insertRow(i)
            for c, val in enumerate(r):
                tbl.setItem(i, c, QTableWidgetItem(val))
        tbl.resizeColumnsToContents()
        tbl.setMinimumHeight(min(280, 28 * (len(rows) + 1) + 6))
        tbl.setMaximumHeight(28 * (len(rows) + 1) + 12)
        self._lay.addWidget(tbl)

    def _add_processing_section(self, slug: str):
        queue = [f for f in derived.load_processing().get("queue", [])
                 if slug in f.get("slugs", [])]
        if not queue:
            return
        rows = []
        for f in queue:
            sm = f.get("stack_meta")
            nl = f.get("new_lights_since_stack", 0)
            latest = f.get("latest_processed")
            rows.append([
                f.get("folder", ""),
                status_label(f.get("status"), True),
                f"{f.get('integration_hms', '')} ({f.get('frames', 0)} fr)",
                f"{sm['stack_integration_hms']} ({sm['stack_frames']} fr)" if sm else "—",
                f"+{nl}" if nl else "—",
                f"{latest} · {f.get('latest_processed_at', '')}" if latest else "—",
            ])
        self._section_table(
            "Processing",
            ["Target", "Status", "Raw integ", "In stack", "+ new", "Latest stack"],
            rows)

    def _add_sessions_section(self, slug: str):
        rows = [s for s in derived.load_sessions() if slug in s.get("slugs", [])]
        if not rows:
            return
        rows.sort(key=lambda s: s.get("date", ""), reverse=True)
        out = [[
            s.get("date", ""),
            str(s.get("frames", 0)),
            str(s.get("exposure_s", "")),
            s.get("filter", ""),
            _fmt_hm(s.get("integration_min", 0.0)),
            s.get("mount_mode", ""),
        ] for s in rows]
        self._section_table(
            "Sessions", ["Date", "Frames", "Exp (s)", "Filter", "Integration", "Mount"], out)

    def _add_metadata_section(self, slug: str, e: dict):
        from m110 import catalog
        targets = targets_for_slug(slug)
        rows = []
        cats = catalog.catalogs_for_slug(slug)
        if cats:
            rows.append(("Catalogs", ", ".join(f"{n} ({d})" for n, d in cats)))
        if e.get("type"):
            rows.append(("Type", str(e["type"]).replace("_", " ")))
        if e.get("magnitude") is not None:
            rows.append(("Magnitude", str(e["magnitude"])))
        if e.get("size"):
            rows.append(("Size", str(e["size"])))
        if e.get("season"):
            rows.append((f"Season (at {_SEASON_LATITUDE})", str(e["season"])))

        # Coordinates: prefer the Library entry, else the bundled reference (so a
        # migrated store without per-entry coords still shows them). Both decimal
        # degrees and sexagesimal (HMS/DMS) — the latter for mounts that want it.
        ra, dec = e.get("ra_deg"), e.get("dec_deg")
        if ra is None or dec is None:
            from m110 import catalog
            rd = catalog.load_coords().get(slug)
            if rd:
                ra, dec = rd
        if ra is not None and dec is not None:
            rows.append(("RA", f"{_ra_hms(ra)}  ({float(ra):.4f}°)"))
            rows.append(("Dec", f"{_dec_dms(dec)}  ({float(dec):+.4f}°)"))

        if e.get("filter"):
            rows.append(("Filter rule", str(e["filter"])))
        rows.append(("Slug", slug))
        if targets:
            rows.append(("Capture targets", ", ".join(sorted(targets))))
        if e.get("notes"):
            rows.append(("Remarks", str(e["notes"])))
        self._lay.addWidget(_section_label("Object details"))
        body = "<br>".join(
            f"<b>{k}:</b> {v}" for k, v in rows)
        lbl = QLabel(body)
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#8b949e")
        self._lay.addWidget(lbl)

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
            f"<b>Editing Object Notes</b> &mdash; {e.get('id', '')} "
            f"&middot; <code>Objects/{objects.object_folder_name(slug)}/journal.md</code>"))

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(objects.read_journal_text(slug))
        self._editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._editor.setMinimumHeight(360)
        self._editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)   # wrap to pane width
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
        self.saved.emit(slug)        # let the shell reload other views (Journal feed)

    def _cancel_edit(self):
        if not self._current:
            return
        slug, e, t = self._current
        self._editing = False
        self.editing_changed.emit(False)
        self.show_object(slug, e, t)

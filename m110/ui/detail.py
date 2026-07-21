"""Shared per-object detail pane (used by the Catalog page; opened from anywhere).

Header + status + hero (scales to the pane) + **Object Notes** (view/edit the raw
`journal.md` — the object's entry in the Journal) + gallery (double-click → image
viewer) + an Import-finished-work entry when a processing sandbox has output to
bring back.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QSize, QUrl, Signal
from PySide6.QtGui import QPixmap, QIcon, QImageReader, QDesktopServices
from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QListWidget,
    QListWidgetItem, QScrollArea, QPlainTextEdit, QPushButton, QTableWidgetItem,
    QToolButton, QMenu, QMessageBox,
)

from m110 import build_images, config, derived, objects, siril
from m110.ui import theme
from m110.ui.image_viewer import ScalableImage, ImageViewer
from m110.ui.widgets import (
    status_label, targets_for_slug, make_table, fit_table_height,
    process_in_siril, open_in_default, reveal_in_manager,
)


_GALLERY_TILE = 120   # px — square icon size for the object-page contact sheet


def _status_pill(status) -> QLabel:
    """A small tinted rounded status chip (matches the Library table pill), colored
    from the active theme. Built per render, so it re-themes on reload."""
    lbl = QLabel(status_label(status, True))
    c = theme.status_color(status)
    lbl.setStyleSheet(
        f"color:{c.name()}; "
        f"background-color: rgba({c.red()},{c.green()},{c.blue()},0.16); "
        f"border-radius: 9px; padding: 1px 9px;")
    return lbl


def _section_label(text: str) -> QLabel:
    lbl = QLabel(f"<b>{text}</b>")
    lbl.setTextFormat(Qt.RichText)
    lbl.setStyleSheet("margin-top:8px")
    return lbl


def _fmt_hm(minutes: float) -> str:
    m = int(round(minutes or 0))
    return f"{m // 60}:{m % 60:02d}"


def _gallery_meta(slug: str, im: dict) -> dict[str, str]:
    """Best-effort display metadata for one gallery image, for the viewer's
    info overlay — derived only from what's already computed in derived.py,
    never guessed beyond what the data model actually supports (e.g. filter
    is only included when every session for this object agrees on one)."""
    meta: dict[str, str] = {}
    if im.get("label"):
        meta["Source"] = im["label"]
    if im.get("mtime"):
        meta["Date"] = datetime.fromtimestamp(im["mtime"]).strftime("%Y-%m-%d")
    if im.get("size_mb") is not None:
        meta["Size"] = f"{im['size_mb']:.1f} MB"
    for f in derived.load_processing().get("queue", []):
        if slug in f.get("slugs", []) and f.get("latest_processed") == im.get("name"):
            sm = f.get("stack_meta")
            if sm:
                meta["Integration"] = f"{sm['stack_integration_hms']} ({sm['stack_frames']} fr)"
            break
    filters = derived.totals_by_slug().get(slug, {}).get("filters", [])
    if len(filters) == 1:
        meta["Filter"] = filters[0]
    return meta


def _square_icon(path, size: int) -> QIcon:
    """A center-cropped-to-square QIcon for the gallery grid. Cached thumbs
    aren't square (aspect-preserved from the source frame), so letterboxing
    them inside a square icon leaves dead space on two sides — crop first."""
    img = QImageReader(str(path)).read()
    if img.isNull():
        return QIcon()
    w, h = img.width(), img.height()
    side = min(w, h)
    crop = img.copy((w - side) // 2, (h - side) // 2, side, side)
    scaled = crop.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(QPixmap.fromImage(scaled))


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
    # The user dismissed the pane (✕) — the host page decides what that means
    # (e.g. clear the table selection, go back to a full-width table).
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        s = theme.tokens.SPACE
        self._lay.setContentsMargins(s["md"], s["md"], s["md"], s["md"])
        self._lay.setSpacing(s["sm"])
        self.setWidget(self._content)
        self._current = None        # (slug, e, t) of the shown object
        self._editing = False
        self._gallery = None
        self._galleries = []        # one QListWidget per finished/working group
        self._gallery_items = []    # [{name, path, meta}, ...] for the viewer
        self.placeholder()

    def is_editing(self) -> bool:
        return self._editing

    @staticmethod
    def _has_finished_work(slug: str) -> bool:
        return any(siril.has_unimported_output(t) for t in targets_for_slug(slug))

    @staticmethod
    def _has_working_folder(slug: str) -> bool:
        return any(config.siril_dir(t).is_dir() for t in targets_for_slug(slug))

    def _reveal_working_folder(self, slug: str):
        """Open the object's Siril sandbox(es) in the file manager, so the user
        sets Siril's working directory to the sandbox itself (not the object dir
        one level up, where output goes unnoticed by the importer)."""
        opened = False
        for tgt in targets_for_slug(slug):
            sb = config.siril_dir(tgt)
            if sb.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(sb)))
                opened = True
        if not opened:
            QMessageBox.information(
                self, "Reveal working folder",
                "No processing working folder exists yet for this object — it's "
                "created automatically after you import captures.")

    def _clear(self):
        self._gallery = None
        self._galleries = []
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
        self._close_btn = QToolButton()
        self._close_btn.setText("✕")
        self._close_btn.setAutoRaise(True)
        self._close_btn.setToolTip("Close")
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.closed.emit)
        header_row = QHBoxLayout()
        header_row.addWidget(title, 1)
        header_row.addWidget(self._close_btn, 0, Qt.AlignTop)
        self._lay.addLayout(header_row)

        bits = [str(e.get("type") or "").replace("_", " ")]
        if e.get("magnitude") is not None:
            bits.append(f"mag {e['magnitude']}")
        if e.get("size"):
            bits.append(str(e["size"]))
        if e.get("season"):
            bits.append(str(e["season"]))
        meta = QLabel(" · ".join(b for b in bits if b))
        meta.setProperty("muted", True)
        self._lay.addWidget(meta)

        if captured:
            stat_row = QHBoxLayout()
            stat_row.setSpacing(theme.tokens.SPACE["sm"])
            stat_row.addWidget(_status_pill(t.get("status")))
            stats = QLabel(f"{t.get('integration_hms', '')} · "
                           f"{t.get('session_count', '')} sessions · "
                           f"{t.get('frames', '')} frames")
            stats.setProperty("muted", True)
            stat_row.addWidget(stats)
            stat_row.addStretch(1)
            self._lay.addLayout(stat_row)
            # Processing-prep happens automatically (per the Preferences workflow
            # setting), so no manual "Prepare" button — offer import when a
            # sandbox has finished output to bring back, and a Reveal that opens
            # the sandbox so Siril's working directory is set to the right place.
            btn_row = QHBoxLayout()
            if self._has_finished_work(slug):
                imp_btn = QPushButton("Import finished work…")
                imp_btn.setToolTip("Bring your processed renders/stack into the "
                                   "Library and tidy the working folder")
                imp_btn.clicked.connect(lambda: self.import_requested.emit(slug))
                btn_row.addWidget(imp_btn)
            if self._has_working_folder(slug):
                proc_btn = QPushButton("Process in Siril")
                proc_btn.setToolTip("Launch Siril with this object's working "
                                    "folder set as the working directory")
                proc_btn.clicked.connect(
                    lambda _=False, s=slug: process_in_siril(self, s))
                btn_row.addWidget(proc_btn)
                rev_btn = QPushButton("Reveal working folder")
                rev_btn.setToolTip("Open this object's Siril working folder "
                                   "(Images/<target>/siril/). Point Siril's "
                                   "working directory here — not the folder above it.")
                rev_btn.clicked.connect(
                    lambda _=False, s=slug: self._reveal_working_folder(s))
                btn_row.addWidget(rev_btn)
            if btn_row.count():
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
            cap.setProperty("caption", True)
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
            empty.setProperty("muted", True)
            self._lay.addWidget(empty)

        imgs = [im for im in derived.images_for(slug) if im.get("thumb")]
        if imgs:
            # Per-image state = the tier (finished/ folder → "finished", stacks /
            # seestar-stacks → "working"), overridden by the user's curation (#17).
            curation = objects.get_curation(slug)
            self._gallery_items = []
            self._galleries = []
            finished = [im for im in imgs if self._img_state(im, curation) == "finished"]
            working = [im for im in imgs if self._img_state(im, curation) == "working"]
            self._lay.addWidget(QLabel(
                f"<b>Gallery</b> ({len(imgs)}) — <span style='color:"
                f"{theme.active_tokens().text_secondary}'>double-click to view · "
                f"right-click to curate</span>"))
            if finished:
                self._add_gallery_group("Finished", finished, slug)
            if working:
                # Label the working group only when there's also a finished one to
                # distinguish (a fresh object is all "working" — no need to shout).
                self._add_gallery_group("Working files" if finished else None,
                                        working, slug)
            self._gallery = self._galleries[0] if self._galleries else None

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
        fit_table_height(tbl, max_rows=6)      # whole row fits; scroll past 6 rows
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
        lbl.setProperty("muted", True)
        self._lay.addWidget(lbl)

    @staticmethod
    def _img_state(im: dict, curation: dict) -> str:
        """"finished" | "working" for a gallery image (`objects.image_state` —
        shared with the publish finished-only filter)."""
        return objects.image_state(im.get("name") or "", im.get("label") or "",
                                   curation)

    def _add_gallery_group(self, title, imgs: list, slug: str):
        """One labelled icon-grid of gallery images; items index into the shared
        `_gallery_items` (so the viewer navigates across both groups)."""
        if title:
            lbl = QLabel(title)
            lbl.setProperty("caption", True)
            self._lay.addWidget(lbl)
        gallery = QListWidget()
        gallery.setViewMode(QListWidget.IconMode)
        gallery.setIconSize(QSize(_GALLERY_TILE, _GALLERY_TILE))
        gallery.setResizeMode(QListWidget.Adjust)
        gallery.setMovement(QListWidget.Static)
        gallery.setUniformItemSizes(True)
        gallery.setTextElideMode(Qt.ElideMiddle)
        pad = theme.tokens.SPACE["sm"]
        cell_h = _GALLERY_TILE + pad * 2 + gallery.fontMetrics().height()
        gallery.setGridSize(QSize(_GALLERY_TILE + pad * 2, cell_h))
        gallery.setSpacing(4)
        rows = (len(imgs) + 2) // 3
        gallery.setMinimumHeight(cell_h * min(max(rows, 1), 3) + 16)
        for im in imgs:
            tp = config.RENDERS_DIR / im["thumb"]
            if not tp.is_file():
                continue
            name = im.get("name") or ""
            idx = len(self._gallery_items)         # global index across both groups
            item = QListWidgetItem(_square_icon(tp, _GALLERY_TILE), name)
            item.setToolTip(name)
            item.setData(Qt.UserRole, idx)
            gallery.addItem(item)
            full = im.get("full")
            view = str(config.DATA_ROOT / full) if full else str(tp)
            self._gallery_items.append({
                "name": name, "path": view, "meta": _gallery_meta(slug, im),
                "_state": self._img_state(im, objects.get_curation(slug)),
            })
        gallery.itemDoubleClicked.connect(self._open_gallery_item)
        gallery.setContextMenuPolicy(Qt.CustomContextMenu)
        gallery.customContextMenuRequested.connect(
            lambda pos, g=gallery: self._gallery_context_menu(g, pos))
        self._galleries.append(gallery)
        self._lay.addWidget(gallery)

    def _open_gallery_item(self, item):
        idx = item.data(Qt.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self._gallery_items):
            ImageViewer(list(self._gallery_items), idx, parent=self).exec()

    def _gallery_context_menu(self, gallery, pos):
        item = gallery.itemAt(pos)
        if item is None or not self._current:
            return
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int) or idx >= len(self._gallery_items):
            return
        gi = self._gallery_items[idx]
        name, state = gi["name"], gi.get("_state")
        menu = QMenu(self)
        hero_act = menu.addAction("Set as hero")
        menu.addSeparator()
        if state == "finished":
            mark_act = menu.addAction("Mark as working")
            target = "working"
        else:
            mark_act = menu.addAction("Mark as finished")
            target = "finished"
        menu.addSeparator()
        export_act = menu.addAction("Export for sharing…")
        menu.addSeparator()
        open_act = menu.addAction("Open in default app")
        reveal_act = menu.addAction("Reveal in file manager")
        chosen = menu.exec(gallery.viewport().mapToGlobal(pos))
        if chosen is hero_act:
            self._set_hero(name)
        elif chosen is mark_act:
            self._set_curation(name, target)
        elif chosen is export_act:
            self._export_for_sharing(gi["path"])
        elif chosen is open_act:
            open_in_default(gi["path"])
        elif chosen is reveal_act:
            reveal_in_manager(gi["path"])

    def _export_for_sharing(self, path):
        from m110.ui.export_dialog import ExportShareDialog   # lazy: avoid cycle
        slug = self._current[0] if self._current else None
        ExportShareDialog(path, self, default_stem=slug).exec()

    def _set_hero(self, name: str):
        slug, e, t = self._current
        objects.set_frontmatter_key(slug, "hero", name)
        build_images.rebuild_hero(slug)          # re-render now (identity cache fix)
        self.show_object(slug, e, t)             # reflect the new hero
        self.saved.emit(slug)                    # shell reloads other views' thumbnails

    def _set_curation(self, name: str, state):
        slug, e, t = self._current
        objects.set_curation(slug, name, state)
        self.show_object(slug, e, t)             # regroup finished/working in place

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
        self._editor.setFont(theme.mono_font())
        self._editor.setMinimumHeight(360)
        self._editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)   # wrap to pane width
        self._lay.addWidget(self._editor)

        hint = QLabel("Frontmatter between the <code>---</code> fences feeds the "
                      "gallery (name / hero_caption / hero); everything below is Markdown.")
        hint.setWordWrap(True)
        hint.setProperty("caption", True)
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

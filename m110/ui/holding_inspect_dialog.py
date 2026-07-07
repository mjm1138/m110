"""Holding-area file inspector (#26) — a read-only look at a held file to help
figure out what it is: the FITS header facts (OBJECT/IMAGETYP/FILTER/RA/Dec), a
rendered thumbnail preview, and the suggested identity. Opened by double-clicking
a row in the Import page's holding panel.
"""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox,
)

from m110.ui import theme
from m110.ui.widgets import make_table
from PySide6.QtWidgets import QTableWidgetItem


def _ra_hms(deg: float) -> str:
    h = float(deg) / 15.0
    hh = int(h); mm = int((h - hh) * 60); ss = (h - hh - mm / 60) * 3600
    return f"{hh:02d}h{mm:02d}m{ss:04.1f}s"


def _dec_dms(deg: float) -> str:
    d = float(deg); sign = "-" if d < 0 else "+"; d = abs(d)
    dd = int(d); mm = int((d - dd) * 60); ss = (d - dd - mm / 60) * 3600
    return f"{sign}{dd:02d}°{mm:02d}′{ss:02.0f}″"


def _preview_pixmap(sample: str | None, box: int = 320) -> QPixmap | None:
    """A thumbnail QPixmap for a held file (FITS rendered via the image pipeline,
    rasters loaded directly). None when it can't be read."""
    if not sample:
        return None
    p = Path(sample)
    try:
        from m110 import build_images
        img = build_images._open_image(p)   # handles FITS (stretch) + rasters
    except Exception:
        img = None
    if img is None:
        return None
    try:
        img.thumbnail((box, box))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")
        return pm if not pm.isNull() else None
    except Exception:
        return None


class HoldingInspectDialog(QDialog):
    def __init__(self, group, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Inspect — {group.group}")
        self.setModal(True)
        self.setMinimumWidth(460)
        s = theme.tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["md"])
        lay.setSpacing(s["sm"])

        header = info.get("header") or {}
        sample = info.get("sample")
        if sample:
            cap = QLabel(Path(sample).name)
            cap.setProperty("caption", True)
            cap.setWordWrap(True)
            lay.addWidget(cap)

        row = QHBoxLayout()
        pm = _preview_pixmap(sample)
        if pm is not None:
            thumb = QLabel()
            thumb.setPixmap(pm)
            thumb.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            row.addWidget(thumb, 0)
        row.addLayout(self._facts(header), 1)
        lay.addLayout(row)

        sug_id, reason = info.get("suggested_id"), info.get("reason")
        sug = QLabel(f"<b>Suggested:</b> {sug_id}  <span style='color:"
                     f"{theme.active_tokens().text_secondary}'>({reason})</span>"
                     if sug_id else "No suggestion — no readable FITS header / pointing.")
        sug.setTextFormat(Qt.RichText)
        sug.setWordWrap(True)
        lay.addSpacing(s["xs"])
        lay.addWidget(sug)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    def _facts(self, header: dict):
        col = QVBoxLayout()
        if not header:
            lbl = QLabel("No FITS header (not a FITS file, or unreadable).")
            lbl.setProperty("muted", True)
            lbl.setWordWrap(True)
            col.addWidget(lbl)
            return col
        rows = [
            ("Object", header.get("object") or "—"),
            ("Type", header.get("imagetyp") or "—"),
            ("Filter", header.get("filter") or "—"),
        ]
        ra, dec = header.get("ra_deg"), header.get("dec_deg")
        if ra is not None and dec is not None:
            rows.append(("RA", f"{ra:.4f}°  ({_ra_hms(ra)})"))
            rows.append(("Dec", f"{dec:+.4f}°  ({_dec_dms(dec)})"))
        else:
            rows.append(("RA/Dec", "—"))
        tbl = make_table(["Field", "Value"])
        tbl.setSortingEnabled(False)
        for k, v in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)
            tbl.setItem(r, 0, QTableWidgetItem(k))
            tbl.setItem(r, 1, QTableWidgetItem(str(v)))
        tbl.resizeColumnsToContents()
        col.addWidget(tbl)
        return col

"""About M110 — a small branded dialog (logo · tagline · version · credits · license).

Reached via Help → About M110 (macOS folds it into the application menu). Colors come
from the theme tokens; the logo is the theme-aware wordmark from `theme.brand`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox,
)

from m110.ui import theme


def app_version() -> str:
    """Installed distribution version, or a dev fallback.

    Delegates to :func:`m110.updates.current_version` — the single source of the
    running version (kept as a thin wrapper here since ``error_report`` and the
    About dialog import it)."""
    from m110 import updates
    return updates.current_version()


class AboutDialog(QDialog):
    TAGLINE = "Complete the catalog."
    SOURCE_URL = "https://github.com/mjm1138/m110"
    URANOMETRIA_URL = "https://github.com/devonjones/uranometria"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About M110")
        self.setModal(True)
        t = theme.active_tokens()
        s = theme.tokens.SPACE

        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["xxl"], s["xl"], s["xxl"], s["lg"])
        lay.setSpacing(s["sm"])
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dpr = self.devicePixelRatioF() or 1.0
        logo.setPixmap(theme.logo_pixmap(72, theme.ink_color(), dpr))
        lay.addWidget(logo)

        tagline = QLabel(self.TAGLINE)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color:{t.text_secondary}; font-style:italic; "
            f"font-size:{theme.tokens.FONT_SIZE['section']}px; margin-top:{s['sm']}px;")
        lay.addWidget(tagline)

        version = QLabel(f"Version {app_version()}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFont(theme.mono_font(theme.tokens.FONT_SIZE["small"]))
        version.setStyleSheet(f"color:{t.text_secondary}; margin-top:{s['md']}px;")
        lay.addWidget(version)

        blurb = QLabel(
            "Catalog, capture tracking, ingest, and Siril processing-prep "
            "for your deep-sky imaging collection.")
        blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color:{t.text_secondary}; margin-top:{s['md']}px;")
        lay.addWidget(blurb)

        # The sky map is drawn by someone else's library, and it's one of the
        # most visible things in the app — say so where people look for it.
        credit = QLabel(
            'Map functionality thanks to <a style="color:%s;" href="%s">Uranometria</a>'
            % (t.accent, self.URANOMETRIA_URL))
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        credit.setStyleSheet(f"color:{t.text_secondary}; margin-top:{s['md']}px;")
        lay.addWidget(credit)

        license = QLabel(
            'Apache-2.0 · <a style="color:%s;" href="%s">source</a>'
            % (t.accent, self.SOURCE_URL))
        license.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license.setOpenExternalLinks(True)
        license.setStyleSheet(f"color:{t.text_disabled}; margin-top:{s['lg']}px;")
        lay.addWidget(license)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay.addSpacing(s["sm"])
        lay.addWidget(buttons)

"""About M110 — a small branded dialog (logo · tagline · version · update status ·
credits · license).

Reached via Help → About M110 (macOS folds it into the application menu), or by
clicking the brand mark at the foot of the nav column. Colors come from the theme
tokens; the logo is the theme-aware wordmark from `theme.brand`.

The version line answers "what am I running?", so the dialog answers the question
that follows it too: every time it appears it re-checks for a newer release on a
worker thread and says whether one is waiting.
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

    CHECKING = "Checking for updates…"
    UP_TO_DATE = "You're up to date."
    CHECK_FAILED = "Couldn't check for updates."

    def __init__(self, parent=None, *, check_updates: bool = True):
        super().__init__(parent)
        self.setWindowTitle("About M110")
        self.setModal(True)
        self._check_updates = check_updates
        self._worker = None
        t = theme.active_tokens()
        s = theme.tokens.SPACE
        self._accent = t.accent

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

        # Filled in by the update check fired from showEvent — empty until then, so a
        # dialog that is built but never shown carries no status text.
        self._status = QLabel()
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setOpenExternalLinks(True)
        self._status.setStyleSheet(f"color:{t.text_secondary};")
        lay.addWidget(self._status)

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

    # ---- update status ----
    def showEvent(self, event):
        """Re-check on every appearance — a stale answer is worse than none.

        Deliberately not fired from ``__init__``: workers start on an explicit action,
        never on construction (the rule `pages/planning.py` follows), which also keeps
        offscreen tests that only build the dialog off the network.
        """
        super().showEvent(event)
        self.start_update_check()

    def start_update_check(self):
        if not self._check_updates or self._worker is not None:
            return
        from m110.ui.update_notice import UpdateCheckWorker
        self._status.setText(self.CHECKING)
        # record=False: opening About is a deliberate look, not the daily throttled
        # check — it must not suppress the next launch check. It also runs regardless
        # of the launch-check preference, same as Help → Check for updates….
        self._worker = UpdateCheckWorker(self, record=False)
        self._worker.done.connect(self._on_update_checked)
        self._worker.start()

    def _on_update_checked(self, info):
        if info is None:
            self._status.setText(self.CHECK_FAILED)
        elif info.is_newer:
            self._status.setText(
                'Version %s is available — <a style="color:%s;" href="%s">Download</a>'
                % (info.latest, self._accent, info.url))
        else:
            self._status.setText(self.UP_TO_DATE)
        self.adjustSize()

    def done(self, result):
        # Drain before teardown: a QThread deleted while still running takes the
        # process with it (the export-dialog SIGSEGV).
        if self._worker is not None:
            self._worker.wait(3000)
            self._worker = None
        super().done(result)

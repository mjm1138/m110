"""Global error handling + the crash / "Report a problem" flow.

Without this, an uncaught exception in a Qt slot hits PySide6's default hook and
**aborts the process** — the error vanishes with no in-app trace (see the
committed `crash_dumps/`). `install_excepthook` replaces that with: log the
traceback, show an "M110 hit a problem" dialog carrying a copyable report, and
**return without aborting** so a non-fatal slot error doesn't take the app down.

The same dialog (minus the crash framing) backs the Help → "Report a problem…"
menu item. The report is always copyable; "Report a problem" also opens a
prefilled GitHub new-issue.
"""
from __future__ import annotations

import logging
import platform
import sys
import threading
import traceback
from urllib.parse import urlencode

from PySide6.QtCore import Qt, QObject, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton,
)

from m110 import config, logsetup
from m110.ui import theme

# The one knob to change when the public org/repo name is settled (mirrors
# about_dialog.SOURCE_URL). "Report a problem" opens <REPO_URL>/issues/new.
REPO_URL = "https://github.com/mjm1138/m110"
_MAX_URL_BODY = 4000        # keep the prefilled issue URL well under browser caps

_log = logging.getLogger("m110")
_showing = False            # re-entrancy guard: never stack crash dialogs
_dispatcher: "_Dispatcher | None" = None


# ── report text ───────────────────────────────────────────────────────────────

def _environment() -> str:
    try:
        from m110.ui.about_dialog import app_version
        version = app_version()
    except Exception:
        version = "?"
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    lines = [
        f"M110 {version}",
        f"OS: {platform.platform()}",
        f"Python {platform.python_version()} · PySide6 {pyside_version} · Qt {qVersion()}",
        f"Data root: {config.DATA_ROOT}",
        f"Log: {logsetup.log_path()}",
    ]
    return "\n".join(lines)


def build_report(exc_info=None) -> str:
    """The report shown/copied: environment, an optional traceback, and a tail of
    the log. `exc_info` is a (type, value, tb) tuple for a crash, else None."""
    parts = [_environment()]
    if exc_info:
        tb = "".join(traceback.format_exception(*exc_info)).strip()
        parts.append("--- Traceback ---\n" + tb)
    tail = logsetup.read_log_tail()
    if tail:
        parts.append("--- Recent log ---\n" + tail)
    return "\n\n".join(parts)


def issue_url(report: str) -> str:
    """A GitHub new-issue URL prefilled with a (length-capped) report body. The
    dialog's Copy button carries the full report; this is the convenience path."""
    body = report if len(report) <= _MAX_URL_BODY else report[:_MAX_URL_BODY] + "\n… (truncated — paste the copied report)"
    q = urlencode({"title": "M110 problem report", "body": body})
    return f"{REPO_URL}/issues/new?{q}"


# ── dialog ────────────────────────────────────────────────────────────────────

class ErrorReportDialog(QDialog):
    def __init__(self, report: str, *, is_crash: bool, parent=None):
        super().__init__(parent)
        self._report = report
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setWindowTitle("M110 hit a problem" if is_crash else "Report a problem")
        s = theme.tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["md"])
        lay.setSpacing(s["sm"])

        head = QLabel(
            "<b>M110 hit an unexpected problem.</b><br>The app can keep running, but "
            "the details below help fix it — copy them into a bug report."
            if is_crash else
            "<b>Report a problem.</b><br>Copy the details below into a bug report, or "
            "open a prefilled GitHub issue.")
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        lay.addWidget(head)

        self._view = QPlainTextEdit(report)
        self._view.setReadOnly(True)
        self._view.setFont(theme.mono_font(theme.tokens.FONT_SIZE["small"]))
        self._view.setMinimumHeight(240)
        lay.addWidget(self._view, 1)

        btns = QHBoxLayout()
        copy = QPushButton("Copy report")
        copy.clicked.connect(self._copy)
        report_btn = QPushButton("Report a problem…")
        report_btn.clicked.connect(self._open_issue)
        btns.addWidget(copy)
        btns.addWidget(report_btn)
        btns.addStretch(1)
        if is_crash:
            quit_btn = QPushButton("Quit M110")
            quit_btn.clicked.connect(self._quit)
            btns.addWidget(quit_btn)
            cont = QPushButton("Continue")
            cont.setDefault(True)
            cont.clicked.connect(self.accept)
            btns.addWidget(cont)
        else:
            close = QPushButton("Close")
            close.setDefault(True)
            close.clicked.connect(self.accept)
            btns.addWidget(close)
        lay.addLayout(btns)

    def _copy(self):
        app = QApplication.instance()
        if app is not None:
            app.clipboard().setText(self._report)

    def _open_issue(self):
        QDesktopServices.openUrl(QUrl(issue_url(self._report)))

    def _quit(self):
        self.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()


# ── global exception hook ─────────────────────────────────────────────────────

class _Dispatcher(QObject):
    """Marshals a crash report from any thread onto the GUI thread (queued)."""
    show_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.show_requested.connect(self._show, Qt.QueuedConnection)

    def _show(self, report: str):
        _show_crash_dialog(report)


def _show_crash_dialog(report: str):
    global _showing
    if _showing or QApplication.instance() is None:
        return
    _showing = True
    try:
        ErrorReportDialog(report, is_crash=True).exec()
    except Exception:            # never let the error handler itself crash
        _log.exception("error while showing the crash dialog")
    finally:
        _showing = False


def handle_exception(exctype, value, tb, *, thread_name: str | None = None) -> str | None:
    """Log an uncaught exception and (if the GUI is up) surface it. Returns the
    report text (for tests); None for KeyboardInterrupt (chained to the default)."""
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tb)
        return None
    where = f" (thread {thread_name})" if thread_name else ""
    _log.critical("Uncaught exception%s", where, exc_info=(exctype, value, tb))
    report = build_report((exctype, value, tb))
    if _dispatcher is not None:
        # Same thread as the GUI → show directly; worker thread → queue it.
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            _show_crash_dialog(report)
        else:
            _dispatcher.show_requested.emit(report)
    return report


def install_excepthook(app) -> None:
    """Route uncaught main-thread and worker-thread exceptions through
    `handle_exception`. Call once, after the QApplication exists."""
    global _dispatcher
    _dispatcher = _Dispatcher()          # created on (and thus lives on) the GUI thread

    def _hook(exctype, value, tb):
        handle_exception(exctype, value, tb)

    def _thread_hook(args):
        handle_exception(args.exc_type, args.exc_value, args.exc_traceback,
                         thread_name=getattr(args.thread, "name", None))

    sys.excepthook = _hook
    threading.excepthook = _thread_hook

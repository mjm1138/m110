"""Global error handling + report building (BETA §5). qapp comes from pytest-qt."""
import logging
import sys

import pytest

pytest.importorskip("PySide6")

from m110.ui import error_report


def _exc_info():
    try:
        raise RuntimeError("boom-xyz")
    except RuntimeError:
        return sys.exc_info()


def test_build_report_with_and_without_traceback(qapp):
    r = error_report.build_report(_exc_info())
    assert r.startswith("M110")                 # version/env header
    assert "OS:" in r
    assert "Traceback" in r and "boom-xyz" in r
    plain = error_report.build_report()
    assert "Traceback" not in plain


def test_issue_url_prefills_and_caps(qapp):
    url = error_report.issue_url("short report")
    assert url.startswith("https://github.com/mjm1138/m110/issues/new?")
    assert "title=" in url and "body=" in url
    # a giant report is truncated so the URL stays under browser caps
    big = "x" * 20000
    capped = error_report.issue_url(big)
    assert "truncated" in capped
    assert len(capped) < 6000


def test_handle_exception_logs_and_returns_report(qapp):
    # The `m110` logger sets propagate=False, so capture with our own handler.
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("m110")
    logger.addHandler(handler)
    try:
        report = error_report.handle_exception(*_exc_info())
    finally:
        logger.removeHandler(handler)
    assert report and "boom-xyz" in report
    assert any("Uncaught exception" in r.getMessage() for r in records)
    assert any(r.exc_info for r in records)     # traceback attached for the log file


def test_handle_exception_ignores_keyboard_interrupt(qapp):
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        assert error_report.handle_exception(*sys.exc_info()) is None


def test_crash_dialog_reentrancy_guard(qapp, monkeypatch):
    """A second crash while a dialog is up must not stack another dialog."""
    calls = []
    monkeypatch.setattr(error_report, "_showing", True)
    monkeypatch.setattr(error_report, "ErrorReportDialog",
                        lambda *a, **k: calls.append(1))
    error_report._show_crash_dialog("report")   # guarded → no dialog constructed
    assert calls == []


def test_crash_dialog_constructs_and_copies(qapp):
    dlg = error_report.ErrorReportDialog("the report text", is_crash=True)
    try:
        dlg._copy()
        assert qapp.clipboard().text() == "the report text"
        from PySide6.QtWidgets import QPushButton
        labels = {b.text() for b in dlg.findChildren(QPushButton)}
        assert {"Copy report", "Report a problem…", "Continue", "Quit M110"} <= labels
    finally:
        dlg.deleteLater()

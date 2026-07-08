"""Offscreen shell tests: the Help → Report a problem action + the backup nudge
(BETA §5). qapp comes from pytest-qt."""
import pytest

pytest.importorskip("PySide6")

from m110 import config
from tests._helpers import seed_root, seed_capture


def _window(qapp):
    from m110.ui.main import MainWindow
    return MainWindow()


def test_report_action_opens_dialog(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui import error_report
    built = []
    monkeypatch.setattr(error_report, "ErrorReportDialog",
                        lambda *a, **k: type("D", (), {"exec": lambda self: built.append(k)})())
    win = _window(qapp)
    try:
        assert win.report_action.text() == "Report a problem…"
        win._open_report()
        assert built and built[0].get("is_crash") is False
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_fires_once_when_captured(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                          # now there's something worth backing up
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        assert config.get_setting("backup_nudge_seen") in (None, False)
        win._maybe_backup_nudge()
        assert asked == [1]                     # nudged
        assert config.get_setting("backup_nudge_seen") is True
        win._maybe_backup_nudge()               # already seen → no second nudge
        assert asked == [1]
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_silent_when_backups_configured(tmp_path, monkeypatch, qapp):
    """Regression: a returning user who already set up backups must not be nudged."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                          # has captures…
    from m110 import backup
    config.save_setting(backup.SETTING_DEST, str(tmp_path / "dest"))  # …but backups configured
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert asked == []                      # already backing up → no nag
    finally:
        win.deleteLater(); qapp.processEvents()


def test_backup_nudge_silent_without_captures(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)            # empty store — nothing captured
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    win = _window(qapp)
    try:
        win._maybe_backup_nudge()
        assert asked == []                      # nothing to lose → no nag
        assert config.get_setting("backup_nudge_seen") in (None, False)
    finally:
        win.deleteLater(); qapp.processEvents()

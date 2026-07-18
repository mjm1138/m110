"""Offscreen tests for the Process-in-Siril UI helpers (widgets.py, #19).
The real launcher is monkeypatched — no external app is started; dialogs are
stubbed so nothing blocks."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from m110 import config, launch, siril  # noqa: E402
from m110.ui import widgets  # noqa: E402
from tests._helpers import add_library, seed_capture, seed_root  # noqa: E402


def test_working_dirs_and_can_process(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    siril.apply_prep(siril.plan_prep(tid))

    dirs = widgets.working_dirs_for_slug(slug)
    assert dirs == [(tid, config.siril_dir(tid))]
    assert widgets.can_process_slug(slug) is True


def test_process_in_siril_launches_single_dir(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    siril.apply_prep(siril.plan_prep(tid))

    calls = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, wd: calls.append((tool, str(wd))) or "/bin/siril")
    widgets.process_in_siril(None, slug)          # one dir → launches directly
    assert calls == [("siril", str(config.siril_dir(tid)))]


def test_process_in_siril_no_sandbox_informs(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m101": {"id": "M101", "name": "Pinwheel", "type": "galaxy"}})
    assert widgets.can_process_slug("m101") is False

    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: shown.append(a[2]))
    launched = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda *a, **k: launched.append(a))
    widgets.process_in_siril(None, "m101")
    assert shown and "working folder" in shown[0]
    assert launched == []                          # never tried to launch


def test_launch_error_falls_back_without_raising(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    siril.apply_prep(siril.plan_prep(tid))

    def boom(tool, wd):
        raise launch.LaunchError("Couldn't find Siril.")
    monkeypatch.setattr(launch, "launch_processing", boom)
    # Stub the fallback dialog so it neither blocks nor reveals.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    revealed = []
    monkeypatch.setattr(widgets, "reveal_in_manager", lambda p: revealed.append(p))

    widgets.process_in_siril(None, slug)           # must not raise
    assert revealed == []                          # user didn't pick "Reveal"

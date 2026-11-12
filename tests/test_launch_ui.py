"""Offscreen tests for the Process-in-Siril UI helpers (widgets.py, #19).
The real launcher is monkeypatched — no external app is started; dialogs are
stubbed so nothing blocks."""
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from m110 import config, launch, siril  # noqa: E402
from m110.ui import widgets  # noqa: E402
from tests._helpers import seed_capture, seed_root  # noqa: E402


def test_working_dirs_and_can_process(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    siril.apply_prep(siril.plan_prep(tid))

    dirs = widgets.working_dirs_for_slug(slug)
    assert dirs == [(tid, config.siril_dir(tid))]
    assert widgets.can_process_slug(slug) is True


def test_launch_siril_launches_the_dir(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    siril.apply_prep(siril.plan_prep(tid))

    calls = []
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, wd: calls.append((tool, str(wd))) or "/bin/siril")
    (_, d), = widgets.working_dirs_for_slug(slug)
    widgets.launch_siril(None, d)
    assert calls == [("siril", str(config.siril_dir(tid)))]


def test_add_siril_actions_one_dir_is_a_plain_entry(qapp):
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    acts = widgets.add_siril_actions(menu, [("M51", Path("/x/M51/siril"))])
    assert [a.text() for a in menu.actions()] == ["Process in Siril"]
    assert list(acts.values()) == [Path("/x/M51/siril")]
    assert menu.actions()[0].menu() is None


def test_add_siril_actions_split_is_a_submenu_in_the_same_menu(qapp):
    """Job folders are offered inside the menu the user opened — never a second
    popup after it closes, which read as "nothing happened"."""
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    dirs = [("NGC 6543 · LP", Path("/x/siril/LP")),
            ("NGC 6543 · IRCUT", Path("/x/siril/IRCUT"))]
    acts = widgets.add_siril_actions(menu, dirs)
    (top,) = menu.actions()
    assert top.text() == "Process in Siril" and top.menu() is not None
    assert [a.text() for a in top.menu().actions()] == [lbl for lbl, _ in dirs]
    assert [acts[a] for a in top.menu().actions()] == [d for _, d in dirs]


def test_add_siril_actions_no_dirs_adds_nothing(qapp):
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    assert widgets.add_siril_actions(menu, []) == {}
    assert menu.actions() == []


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

    (_, d), = widgets.working_dirs_for_slug(slug)
    widgets.launch_siril(None, d)                  # must not raise
    assert revealed == []                          # user didn't pick "Reveal"

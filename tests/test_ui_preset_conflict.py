"""The ask-before-replacing-a-preset dialog (#174): every button pressed."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt

from m110 import config, siril
from m110.ui import preset_conflict_dialog as pcd
from ._helpers import seed_root


def _conflicted_target(tmp_path, monkeypatch, target="M51"):
    seed_root(tmp_path, monkeypatch)
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    for i in range(720):
        if i == 120:
            siril.autoprep([target])            # first preset at 120 frames
        (d / f"Light_{target}_10.0s_IRCUT_20260101-{i:06d}.fit").write_text("x")
    return {"siril": siril.autoprep([target])}


def test_describe_changes():
    assert pcd.describe_changes([("roundness", 95.0, 92.0), ("spcc", True, False),
                                 ("black_frames_bug", False, None)]) == \
        "roundness: 95 → 92\nspcc: on → off\nblack_frames_bug: off → —"


def test_preset_conflicts_ignores_workflows_without_any():
    assert pcd.preset_conflicts({"astrowizard": {"prepared": []}}) == []
    assert pcd.preset_conflicts(None) == []


def test_replace_selected_returns_ticked_rows(qtbot, tmp_path, monkeypatch):
    result = _conflicted_target(tmp_path, monkeypatch)
    conflicts = pcd.preset_conflicts(result)
    dlg = pcd.PresetConflictDialog(conflicts)
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == 1
    assert "roundness: 95 → 92" in dlg.table.item(0, 3).text()
    dlg._replace_btn.click()
    assert dlg.result() == dlg.DialogCode.Accepted
    assert dlg.replace_paths() == {conflicts[0].preset_path}


def test_unticked_row_is_kept(qtbot, tmp_path, monkeypatch):
    result = _conflicted_target(tmp_path, monkeypatch)
    dlg = pcd.PresetConflictDialog(pcd.preset_conflicts(result))
    qtbot.addWidget(dlg)
    dlg.table.item(0, 0).setCheckState(Qt.Unchecked)
    dlg._replace_btn.click()
    assert dlg.replace_paths() == set()


def test_keep_existing_keeps_everything(qtbot, tmp_path, monkeypatch):
    result = _conflicted_target(tmp_path, monkeypatch)
    dlg = pcd.PresetConflictDialog(pcd.preset_conflicts(result))
    qtbot.addWidget(dlg)
    dlg._keep_btn.click()
    assert dlg.result() == dlg.DialogCode.Rejected
    assert dlg.replace_paths() == set()


def test_resolve_applies_the_answer(qtbot, tmp_path, monkeypatch):
    result = _conflicted_target(tmp_path, monkeypatch)
    [c] = pcd.preset_conflicts(result)
    monkeypatch.setattr(pcd.PresetConflictDialog, "exec",
                        lambda self: self._replace_btn.click())
    out = pcd.resolve_preset_conflicts(None, {"autoprep": result})
    assert out["replaced"] == [c.preset_path]
    assert json.loads(open(c.preset_path).read())["roundness"] == 92.0


def test_resolve_is_silent_without_conflicts(monkeypatch):
    def boom(self):
        raise AssertionError("no dialog expected")
    monkeypatch.setattr(pcd.PresetConflictDialog, "exec", boom)
    assert pcd.resolve_preset_conflicts(None, {"moved": 3}) is None
    assert pcd.resolve_preset_conflicts(None, {"autoprep": {"siril": {
        "preset_conflicts": []}}}) is None


def test_apply_worker_hands_autoprep_result_to_done_slot(qtbot, monkeypatch):
    from types import SimpleNamespace
    from m110 import ingest, processing
    from m110.ui.ingest_dialog import _ApplyWorker
    import threading

    monkeypatch.setattr(ingest, "apply_ops", lambda ops, **kw: {"moved": 1})
    monkeypatch.setattr(processing, "run_autoprep",
                        lambda targets, **kw: {"siril": {"seen": targets}})
    op = SimpleNamespace(kind="light", dest_rel="Images/M51/lights/a.fit")
    w = _ApplyWorker([op], threading.Event())
    got = []
    w.done.connect(got.append)
    w.run()                                     # synchronously, on this thread
    assert got == [{"moved": 1, "autoprep": {"siril": {"seen": ["M51"]}}}]

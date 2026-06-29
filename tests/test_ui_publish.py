"""Offscreen smoke for the Publish dialog — checkboxes map to PublishOptions."""
from m110 import config
from m110.ui.publish_dialog import PublishDialog
from tests._helpers import seed_root


def test_dialog_selection_maps_to_options(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    dlg = PublishDialog()
    # toggle: keep only library + sessions; exclude journals
    for sid, cb in dlg._sec_checks.items():
        cb.setChecked(sid in {"library", "sessions"})
    dlg._exclude_journals.setChecked(True)
    assert dlg._selected_sections() == {"library", "sessions"}
    # only the available target is checkable/checked
    assert dlg._selected_targets() == ["static-site"]


def test_dialog_targets_show_soon_for_unavailable(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    dlg = PublishDialog()
    assert dlg._tgt_checks["github-pages"].isEnabled() is False
    assert "soon" in dlg._tgt_checks["github-pages"].text()

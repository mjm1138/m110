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
    # default-enabled target only (github-pages is available but not on by default)
    assert dlg._selected_targets() == ["static-site"]


def test_dialog_targets_show_soon_for_unavailable(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    dlg = PublishDialog()
    assert dlg._tgt_checks["netlify"].isEnabled() is False
    assert "soon" in dlg._tgt_checks["netlify"].text()


def test_dialog_github_repo_field_follows_checkbox(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    config.save_setting("publish_github_repo", "mjm1138/astro-site")
    dlg = PublishDialog()
    cb = dlg._tgt_checks["github-pages"]
    assert cb.isEnabled() and not cb.isChecked()
    assert dlg._gh_repo.text() == "mjm1138/astro-site"   # persisted value loads
    assert dlg._gh_repo.isEnabled() is False             # target unchecked
    cb.setChecked(True)
    assert dlg._gh_repo.isEnabled() is True
    assert dlg._selected_targets() == ["static-site", "github-pages"]


def test_dialog_gallery_level_follows_galleries(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    dlg = PublishDialog()
    assert dlg._gallery_level.currentData() == "finished"   # default level
    assert dlg._gallery_level.isEnabled() is True           # galleries on by default
    dlg._sec_checks["galleries"].setChecked(False)
    assert dlg._gallery_level.isEnabled() is False


def test_dialog_save_persists_without_publishing(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    dlg = PublishDialog()
    dlg._title.setText("My Saved Site")
    dlg._gh_repo.setText("mjm1138/astro-site")
    dlg._gallery_level.setCurrentIndex(2)                   # "all"
    dlg._do_save()
    assert dlg._worker is None                              # nothing ran
    assert config.get_setting("publish_site_title") == "My Saved Site"
    assert config.get_setting("publish_github_repo") == "mjm1138/astro-site"
    assert config.get_setting("publish_gallery_level") == "all"
    from PySide6.QtWidgets import QDialog
    assert dlg.result() == QDialog.DialogCode.Accepted

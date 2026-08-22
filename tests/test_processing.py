"""Tests for the processing-workflow registry + preference-driven auto-prep."""
from m110 import config, processing


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "INTERNAL_DIR", root / ".m110_internal_data")
    return root


def _target_with_lights(name):
    d = config.lights_dir(name)
    d.mkdir(parents=True)
    (d / f"Light_{name}_a.fit").write_text("x")


def test_both_available_workflows_are_on_by_default(tmp_path, monkeypatch):
    """AstroWizard joined the defaults with 14b. Enabling it by default is what
    keeps Send-to/Import present for someone upgrading — see
    `processing.LEGACY_SETTING_IDS` for the matching rule on a saved list."""
    _isolate(tmp_path, monkeypatch)
    assert processing.enabled_workflow_ids() == ["siril", "astrowizard"]
    assert processing.WORKFLOWS_BY_ID["siril"].available is True
    assert processing.WORKFLOWS_BY_ID["astrowizard"].available is True
    assert processing.WORKFLOWS_BY_ID["pixinsight"].available is False


def test_a_saved_list_from_before_astrowizard_does_not_disable_it(
        tmp_path, monkeypatch):
    """The upgrade case: `["siril"]` was saved when AstroWizard did not exist, so
    its absence is not a choice and must not read as one."""
    _isolate(tmp_path, monkeypatch)
    config.save_setting(processing.SETTING_KEY, ["siril"])
    assert processing.enabled_workflow_ids() == ["siril", "astrowizard"]
    # …but an explicit map is a choice, and is honoured.
    processing.set_enabled_workflows(["siril"])
    assert processing.enabled_workflow_ids() == ["siril"]


def test_run_autoprep_siril(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _target_with_lights("M101")
    res = processing.run_autoprep(["M101"])
    assert "siril" in res
    assert (config.siril_dir("M101") / "lights").is_dir()


def test_run_autoprep_disabled_is_noop(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # Explicit map, not a legacy list: a bare list only enumerates the workflows
    # that were on offer when it was saved, so a later-added one reads as
    # *unanswered* and takes its default — see processing.LEGACY_SETTING_IDS.
    processing.set_enabled_workflows([])
    _target_with_lights("M101")
    assert processing.run_autoprep(["M101"]) == {}
    assert not config.siril_dir("M101").exists()


def test_run_autoprep_skips_unavailable_workflow(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    processing.set_enabled_workflows(["pixinsight"])   # disabled/“soon”
    _target_with_lights("M101")
    assert processing.run_autoprep(["M101"]) == {}
    assert not config.siril_dir("M101").exists()


def test_run_autoprep_respects_pending_output(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _target_with_lights("M101")
    processing.run_autoprep(["M101"])                 # builds the sandbox
    (config.siril_dir("M101") / "M101_processed.png").write_text("p")
    res = processing.run_autoprep(["M101"])           # must not disturb it
    assert res["siril"]["skipped"] == ["M101"]


def test_prepare_missing_creates_absent_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from m110 import siril
    _target_with_lights("M5")
    _target_with_lights("M51")
    siril.autoprep(["M5"])                             # M5 already prepped
    edited = config.siril_dir("M5") / "presets" / siril.PRESET_NAME
    edited.write_text('{"EDITED": true}')             # user hand-edit

    res = processing.prepare_missing()
    assert res["siril"]["prepared"] == ["M51"]        # only the absent one
    assert config.siril_dir("M51").exists()
    # the existing sandbox's preset is preserved (not rewritten)
    assert edited.read_text() == '{"EDITED": true}'


def test_prepare_missing_noop_when_disabled(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    processing.set_enabled_workflows([])
    _target_with_lights("M5")
    assert processing.prepare_missing() == {}
    assert not config.siril_dir("M5").exists()


def test_store_targets_lists_only_targets_with_lights(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _target_with_lights("M5")
    (config.IMAGES_DIR / "M99" / "seestar-stacks").mkdir(parents=True)  # no lights
    assert processing._store_targets() == ["M5"]

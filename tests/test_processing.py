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


def test_default_is_siril(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert processing.enabled_workflow_ids() == ["siril"]
    assert processing.WORKFLOWS_BY_ID["siril"].available is True
    assert processing.WORKFLOWS_BY_ID["pixinsight"].available is False


def test_run_autoprep_siril(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _target_with_lights("M101")
    res = processing.run_autoprep(["M101"])
    assert "siril" in res
    assert (config.siril_dir("M101") / "lights").is_dir()


def test_run_autoprep_disabled_is_noop(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    config.save_setting(processing.SETTING_KEY, [])
    _target_with_lights("M101")
    assert processing.run_autoprep(["M101"]) == {}
    assert not config.siril_dir("M101").exists()


def test_run_autoprep_skips_unavailable_workflow(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    config.save_setting(processing.SETTING_KEY, ["pixinsight"])   # disabled/“soon”
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

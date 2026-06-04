"""Tests for the derived-rollup reader (config-path overridable / testable)."""
import json

from astronamigo import config, derived


def _write_derived(tmp_path, monkeypatch, totals):
    d = tmp_path / "derived"
    d.mkdir()
    (d / "totals.json").write_text(json.dumps(totals))
    monkeypatch.setattr(config, "DERIVED_DIR", d)
    return d


def test_totals_by_slug(tmp_path, monkeypatch):
    _write_derived(tmp_path, monkeypatch, {
        "by_slug": {"m81": {"status": "deep_stack", "integration_hms": "26:22",
                             "integration_min": 1582.0, "session_count": 23,
                             "frames": 4340}},
        "by_folder": {},
    })
    bs = derived.totals_by_slug()
    assert bs["m81"]["status"] == "deep_stack"
    assert bs["m81"]["session_count"] == 23


def test_derived_available(tmp_path, monkeypatch):
    assert derived.derived_available() in (True, False)  # never raises
    _write_derived(tmp_path, monkeypatch, {"by_slug": {}})
    assert derived.derived_available() is True


def test_missing_files_return_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DERIVED_DIR", tmp_path / "nope")
    assert derived.totals_by_slug() == {}
    assert derived.load_priorities() == []
    assert derived.derived_available() is False

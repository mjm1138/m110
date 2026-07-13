"""Tests for the derived-rollup reader (config-path overridable / testable)."""
import json

from m110 import config, derived


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
    assert derived.load_summary() == {}
    assert derived.derived_available() is False


def test_load_sessions(tmp_path, monkeypatch):
    p = tmp_path / "sessions.jsonl"
    rows = [
        {"date": "2026-05-29", "object_dir": "M108 M97", "slugs": ["m108", "m97"],
         "frames": 106, "exposure_s": 30, "filter": "LP", "integration_min": 53.0,
         "mount_mode": "EQ", "pre_new_start": False},
        {"date": "2026-06-01", "object_dir": "M51", "slugs": ["m51"],
         "frames": 200, "exposure_s": 10, "filter": "OFF", "integration_min": 33.3,
         "mount_mode": "EQ", "pre_new_start": False},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(config, "SESSIONS_JSONL", p)
    out = derived.load_sessions()
    assert len(out) == 2 and out[0]["object_dir"] == "M108 M97"
    assert out[1]["slugs"] == ["m51"]


def test_load_sessions_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_JSONL", tmp_path / "nope.jsonl")
    assert derived.load_sessions() == []

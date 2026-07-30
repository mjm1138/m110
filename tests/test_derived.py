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


def _session(folder, slugs, date, minutes, frames=10):
    return {"date": date, "object_dir": folder, "slugs": slugs, "frames": frames,
            "exposure_s": 30, "filter": "LP", "integration_min": minutes}


def test_a_mosaic_is_tracked_apart_from_the_plain_capture():
    """A mosaic of M42 is M42's sky, but its frames don't stack with a
    single-frame capture — so summing them would claim a depth no single stack
    has. The plain framing is the headline; the mosaic is reported beside it."""
    from m110.build_derived import build_totals
    sessions = [
        _session("M42", ["m42"], "2026-03-13", 72.0),
        _session("M42_mosaic", ["m42"], "2026-03-20", 42.0),
    ]
    totals = build_totals({"m42": {"id": "M42", "type": "emission"}}, sessions)
    t = totals["by_slug"]["m42"]
    assert t["integration_min"] == 72.0            # not 114.0
    assert t["session_count"] == 1
    framings = t["framings"]
    assert framings["M42"]["counted"] is True
    assert framings["M42_mosaic"]["counted"] is False
    assert framings["M42_mosaic"]["integration_min"] == 42.0


def test_an_object_captured_only_as_a_mosaic_still_counts():
    """…but a mosaic is a real capture. With nothing to conflate it with, it is
    the object's integration — it must not read as zero hours."""
    from m110.build_derived import build_totals
    sessions = [_session("NGC 7000_mosaic", ["ngc-7000"], "2026-07-18", 240.0)]
    totals = build_totals({"ngc-7000": {"id": "NGC 7000", "type": "emission"}}, sessions)
    t = totals["by_slug"]["ngc-7000"]
    assert t["integration_min"] == 240.0
    assert t["framings"]["NGC 7000_mosaic"]["counted"] is True


def test_a_combined_target_still_credits_both_objects():
    """Only *decorated* framings are held apart. A combined capture is one
    dataset containing both objects and keeps crediting each of them."""
    from m110.build_derived import build_totals
    sessions = [
        _session("M81 M82", ["m81", "m82"], "2026-06-03", 60.0),
        _session("M81", ["m81"], "2026-06-10", 30.0),
    ]
    totals = build_totals({"m81": {"id": "M81", "type": "galaxy"},
                           "m82": {"id": "M82", "type": "galaxy"}}, sessions)
    assert totals["by_slug"]["m81"]["integration_min"] == 90.0   # both framings
    assert totals["by_slug"]["m82"]["integration_min"] == 60.0
    assert all(f["counted"] for f in totals["by_slug"]["m81"]["framings"].values())


def test_a_mosaic_cannot_promote_an_object_to_deep():
    """The reason this matters: two shallow framings summed could cross the
    deep-stack threshold that neither of them reaches."""
    from m110.build_derived import build_totals
    sessions = [
        _session("M42", ["m42"], "2026-03-13", 200.0),
        _session("M42_mosaic", ["m42"], "2026-03-20", 200.0),
    ]
    totals = build_totals({"m42": {"id": "M42", "type": "emission"}}, sessions)
    assert totals["by_slug"]["m42"]["status"] == "initial"   # 360 min threshold

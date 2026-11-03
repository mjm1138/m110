"""Cancelling a sync (quit does it) stops at a safe point and leaves the store as it was."""
import json

import pytest

from m110 import config, refresh
from tests._helpers import seed_capture, seed_root


def _derived_state():
    files = [config.SESSIONS_JSONL, *sorted(config.DERIVED_DIR.glob("*.json"))]
    # session_headers.json is the scan's per-file header cache, not a rollup: keyed
    # by file identity, so saving it from a scan that was then cancelled is harmless.
    out = {f.name: f.read_bytes() for f in files
           if f.is_file() and f.name != "session_headers.json"}
    if "processing.json" in out:                  # stamps generated_at on every write
        proc = json.loads(out["processing.json"])
        proc.pop("generated_at", None)
        out["processing.json"] = json.dumps(proc, sort_keys=True).encode()
    return out


def _cancel_after(n):
    """should_cancel that turns true on its n-th poll."""
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] >= n
    return should_cancel, calls


def test_cancel_during_the_scan_writes_nothing(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _, tid = seed_capture(root)
    refresh.run_refresh()                                  # a full sync, with images
    before = _derived_state()
    lights = config.lights_dir(tid)                        # new work the scan would record
    (lights / f"Light_{tid}_30.0s_LP_20260601-010101.fit").write_text("x")

    with pytest.raises(refresh.RefreshCancelled):
        refresh.run_refresh(should_cancel=lambda: True)
    assert _derived_state() == before                      # sessions + derived untouched


def test_sessions_and_derived_change_together_or_not_at_all(tmp_path, monkeypatch):
    """Cancel at every safe point in turn: the store is always wholly old or wholly
    new (sessions.jsonl and derived/*.json), never a mix."""
    root = seed_root(tmp_path, monkeypatch)
    _, tid = seed_capture(root)
    old = _derived_state()
    extra = config.lights_dir(tid) / f"Light_{tid}_30.0s_LP_20260601-010101.fit"
    extra.write_text("x")                                  # new work for the scan

    probe, calls = _cancel_after(10**9)
    refresh.run_refresh(render=False, should_cancel=probe)
    new, polls = _derived_state(), calls["n"]
    assert new != old and polls >= 3
    for k in range(1, polls + 1):
        extra.unlink()
        refresh.run_refresh(render=False)                  # back to the old store
        assert _derived_state() == old
        extra.write_text("x")
        should_cancel, _ = _cancel_after(k)
        with pytest.raises(refresh.RefreshCancelled):
            refresh.run_refresh(render=False, should_cancel=should_cancel)
        assert _derived_state() == old, f"cancelled at poll {k}/{polls}"


def test_cancel_during_rendering_keeps_the_old_manifest(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    refresh.run_refresh()
    images_json = config.DERIVED_DIR / "images.json"
    before = images_json.read_bytes()

    probe, calls = _cancel_after(10**9)                    # count the polls of a full sync
    refresh.run_refresh(should_cancel=probe)
    polls = calls["n"]
    assert polls >= 3                                      # scan + pre-write + render

    should_cancel, _ = _cancel_after(polls)                # true only at the render's poll
    with pytest.raises(refresh.RefreshCancelled):
        refresh.run_refresh(should_cancel=should_cancel)
    assert images_json.read_bytes() == before


def test_a_sync_nobody_cancels_still_completes(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    out = refresh.run_refresh(should_cancel=lambda: False)
    assert out["sessions"] >= 1

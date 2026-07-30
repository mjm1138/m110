"""Serialization of engine values into JSON-safe shapes.

The headline test runs a **real** `planning.plan_night` through the serializer
rather than a hand-built mock — a mock of the shape would drift from the shape,
and the datetimes are the whole point.
"""
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from m110 import config, planning, prioritize
from m110.assistant import serialize
from m110.assistant.serialize import ToolResult, to_json_safe
from m110.planning_config import Device, Site

_SITE = Site(name="Home", latitude_deg=40.015, longitude_deg=-105.27,
             elevation_m=1655, timezone="America/Denver")
_DAY = date(2026, 7, 13)          # the same real July night the planning tests use
_TZ = ZoneInfo("America/Denver")


def _walk(obj):
    """Yield every scalar in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


# ── hazard 1: naive-local datetimes ──────────────────────────────────────────

def test_naive_datetime_gets_the_site_offset():
    dt = datetime(2026, 7, 13, 22, 14)
    assert to_json_safe(dt, tz=_TZ) == "2026-07-13T22:14:00-06:00"


def test_naive_datetime_without_tz_states_no_offset_rather_than_implying_utc():
    out = to_json_safe(datetime(2026, 7, 13, 22, 14))
    assert out == "2026-07-13T22:14:00"
    assert not out.endswith("Z") and "+00:00" not in out


def test_aware_datetime_keeps_its_own_offset():
    dt = datetime(2026, 7, 13, 22, 14, tzinfo=ZoneInfo("UTC"))
    assert to_json_safe(dt, tz=_TZ) == "2026-07-13T22:14:00+00:00"


def test_date_and_time_and_timedelta():
    assert to_json_safe(date(2026, 7, 13)) == "2026-07-13"
    assert to_json_safe(timedelta(minutes=90)) == 5400.0


# ── hazard 2: Path ───────────────────────────────────────────────────────────

def test_path_inside_store_becomes_store_relative(tmp_path):
    root = tmp_path / "M110"
    (root / "Plans").mkdir(parents=True)
    p = root / "Plans" / "2026-07-13_summer.md"
    p.write_text("x", encoding="utf-8")
    assert to_json_safe(p, root=root) == "Plans/2026-07-13_summer.md"


def test_path_outside_store_collapses_to_basename(tmp_path):
    root = tmp_path / "M110"
    root.mkdir()
    outside = tmp_path / "somewhere" / "else" / "secret.fit"
    outside.parent.mkdir(parents=True)
    outside.write_text("x", encoding="utf-8")
    out = to_json_safe(outside, root=root)
    assert out == "secret.fit"
    assert "somewhere" not in out and str(tmp_path) not in out


def test_no_absolute_home_path_leaks(tmp_path):
    root = tmp_path / "M110"
    root.mkdir()
    payload = {"a": Path.home() / "Documents" / "private" / "notes.md",
               "b": root / "Objects" / "M101" / "journal.md"}
    out = to_json_safe(payload, root=root)
    assert str(Path.home()) not in json.dumps(out)
    assert out["b"] == "Objects/M101/journal.md"


# ── hazard 3: dataclasses ────────────────────────────────────────────────────

def test_site_dataclass_has_no_path_left(tmp_path):
    site = Site(profiles_dir=tmp_path / "profiles")
    out = to_json_safe(site, root=tmp_path)
    assert isinstance(out, dict)
    assert out["timezone"] == "America/Denver"       # the field tz is derived from
    assert not isinstance(out["profiles_dir"], Path)
    json.dumps(out)


def test_device_and_weights_dataclasses_round_trip():
    for obj in (Device(), prioritize.Weights()):
        out = to_json_safe(obj)
        assert isinstance(out, dict)
        json.dumps(out, allow_nan=False)


def test_target_context_via_public_context_to_dict():
    """context_to_dict was promoted from _context_to_dict; both names work."""
    assert prioritize.context_to_dict is prioritize._context_to_dict
    ctx = prioritize.TargetContext("m101", "galaxy", 120.0, True, None, 7.9, "28x27")
    out = to_json_safe(prioritize.context_to_dict(ctx))
    assert out["slug"] == "m101" and out["integration_min"] == 120.0
    json.dumps(out, allow_nan=False)


# ── the boring cases that break json.dumps ───────────────────────────────────

def test_nan_and_inf_become_null():
    out = to_json_safe({"a": float("nan"), "b": float("inf"), "c": 1.5})
    assert out == {"a": None, "b": None, "c": 1.5}
    json.dumps(out, allow_nan=False)      # would raise if nan survived


def test_sets_and_tuples_become_lists():
    assert to_json_safe(("a", "b")) == ["a", "b"]
    assert to_json_safe({"c", "a", "b"}) == ["a", "b", "c"]      # sorted for stability


def test_bool_is_not_coerced_to_int():
    out = to_json_safe({"flag": True, "count": 1})
    assert out["flag"] is True and out["count"] == 1


def test_unknown_object_stringifies_rather_than_raising():
    class Exotic:
        def __repr__(self):
            return "<exotic>"
    assert to_json_safe(Exotic()) == "<exotic>"


def test_deeply_nested_structure_terminates():
    node = {"leaf": 1}
    for _ in range(80):
        node = {"child": node}
    json.dumps(to_json_safe(node))        # must not recurse to death


# ── drop_keys: the chart arrays ──────────────────────────────────────────────

def test_drop_keys_removes_arrays_at_any_depth():
    payload = {"entries": [{"slug": "m13", "samples": [1, 2, 3], "alt": 80}],
               "moon": {"track": [(1, 2)], "illum": 0.5}}
    out = to_json_safe(payload, drop_keys=frozenset({"samples", "track"}))
    assert "samples" not in out["entries"][0]
    assert "track" not in out["moon"]
    assert out["entries"][0]["alt"] == 80 and out["moon"]["illum"] == 0.5


def test_tool_result_carries_tz_and_drop_keys():
    res = ToolResult({"t": datetime(2026, 7, 13, 22, 14), "samples": [1]},
                     tz=_TZ, drop_keys=frozenset({"samples"}))
    out = serialize.serialize_result(res)
    assert out["t"] == "2026-07-13T22:14:00-06:00"
    assert "samples" not in out


# ── the real thing ───────────────────────────────────────────────────────────

def test_real_plan_night_is_fully_json_safe():
    """A genuine astropy-computed plan, serialized. Guards the shape this layer
    exists for: `window` (tuple of naive datetimes), `moon.set_time`/`rise_time`/
    `track`, and per-entry transit/start/up datetimes."""
    plan = planning.plan_night(_SITE, _DAY, ["m13", "m81", "m31"])
    assert plan["entries"], "fixture night produced no targets — check the date"

    out = to_json_safe(plan, tz=_TZ, drop_keys=frozenset({"samples", "track"}))
    text = json.dumps(out, allow_nan=False)       # the actual contract

    # Every datetime came out as an offset-carrying ISO string.
    assert len(out["window"]) == 2
    for stamp in out["window"]:
        assert stamp.endswith(("-06:00", "-07:00")), stamp
        datetime.fromisoformat(stamp)             # parses back

    entry = out["entries"][0]
    for key in ("transit_time", "up_start", "up_end"):
        assert isinstance(entry[key], str)
        assert datetime.fromisoformat(entry[key]).tzinfo is not None

    # The chart arrays are gone, and nothing datetime-shaped survived.
    assert "samples" not in entry and "track" not in out["moon"]
    assert not any(isinstance(v, (datetime, date, Path)) for v in _walk(out))
    assert "NaN" not in text and "Infinity" not in text


def test_real_plan_night_without_tz_leaves_no_bogus_utc():
    """If a caller forgets the tz, output must not claim +00:00."""
    plan = planning.plan_night(_SITE, _DAY, ["m13"])
    out = to_json_safe(plan, drop_keys=frozenset({"samples", "track"}))
    assert "+00:00" not in json.dumps(out) and "Z\"" not in json.dumps(out)


# ── registry integration ─────────────────────────────────────────────────────

def test_registry_call_serializes_results(tmp_path, monkeypatch):
    """registry.call must serialize — not just return whatever the tool built.

    `saved_plans` is the probe: fieldguide.list_guides puts a real `Path` in
    every row, so if the wiring were missing this would come back unserializable
    and leaking an absolute path. (Per-tool JSON safety is covered exhaustively
    by the parametrized test in test_assistant_registry.py.)
    """
    from tests._helpers import seed_root
    from m110.assistant import registry, tools  # noqa: F401

    seed_root(tmp_path, monkeypatch)
    config.PLANS_DIR.mkdir(parents=True, exist_ok=True)
    (config.PLANS_DIR / "2026-07-13_summer.md").write_text("# Summer\n", encoding="utf-8")

    out = registry.call("saved_plans", {})
    text = json.dumps(out, allow_nan=False)          # would raise on a raw Path
    assert out["guides"][0]["name"] == "2026-07-13_summer.md"
    assert str(tmp_path) not in text

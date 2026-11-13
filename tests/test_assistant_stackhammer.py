"""The assistant's Stackhammer surface: `plan_stackhammer`, the preset proposal
and its app-side apply. Against the stand-in binary (`tests/fake_stackhammer.py`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from m110 import config, roundtrip, stackhammer as sh
from m110.assistant import apply as apply_mod, outbox, proposals
from m110.assistant import registry, tools  # noqa: F401
from tests._helpers import install_fake_stackhammer, seed_root, stackhammer_job

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"),
                                reason="the stand-in binary is a shebang script")


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "ASSISTANT_DIR",
                        root / config.INTERNAL_DIRNAME / "assistant")
    monkeypatch.setattr(config, "ASSISTANT_OUTBOX",
                        root / config.INTERNAL_DIRNAME / "assistant" / "outbox")
    _binary, calls = install_fake_stackhammer(tmp_path, monkeypatch)
    job = stackhammer_job("M51")
    return root, job, calls


def call(_tool, **args):
    return registry.call(_tool, args)


# ── plan_stackhammer ─────────────────────────────────────────────────────────

def test_plan_reports_every_setting_and_leaks_no_absolute_path(store):
    """Stackhammer's reports name files by absolute path — its Siril commands
    have to. None of that may reach a model, so the whole blob is checked."""
    _root, job, _calls = store
    (job / "darks").mkdir()
    (job / "darks" / "master_dark.fit").write_text("fit")
    out = call("plan_stackhammer", target="M51")

    assert out["lights"]["frames"] == 4
    assert out["working_dir"] == "Images/M51/siril"
    options = {r["option"]: r for r in out["settings"]}
    assert options["weight"]["choices"] and options["weight"]["why"]
    assert {"calibration", "background", "local-norm", "filter-fwhm"} <= set(options)
    assert out["calibration"]["subsets"][0]["dark"]["why"]
    assert out["solved"] is None and "not known" in out["solved_note"]
    assert out["binary"]["found"] == sh.SOURCES["path"]

    blob = json.dumps(out)
    assert str(config.DATA_ROOT) not in blob and str(Path.home()) not in blob
    assert 'cd \\"Images/M51/siril/lights\\"' in blob          # relative, still readable
    assert "sets" not in out["calibration"]["folders"][0]      # per-file lists dropped


def test_plan_ran_only_the_read_only_subcommands_and_wrote_nothing(store):
    _root, job, calls = store
    before = sorted(p.relative_to(job).as_posix() for p in job.rglob("*"))
    call("plan_stackhammer", target="M51", settings={"background": True})
    assert {c[0] for c in calls()} <= {"settings", "prepare", "plan"}
    assert sorted(p.relative_to(job).as_posix() for p in job.rglob("*")) == before


def test_overrides_ride_in_how_to_run_until_the_preset_holds_them(store):
    _root, job, _calls = store
    out = call("plan_stackhammer", target="M51",
               settings={"weight": "noise", "drizzle": True}, verbosity=2)
    assert out["overrides_applied"] == {"weight": "noise", "drizzle": True}
    assert out["preset"]["pending"] == {"weight": "noise", "drizzle": True}
    run = out["how_to_run"]
    assert "--engine stackhammer --run" in run and "M51" in run
    assert "--set weight=noise" in run and "--set drizzle=true" in run and "-vv" in run
    assert "Scripts → Stackhammer" in out["how_to_run_in_siril"]

    sh.write_preset(job, {"weight": "noise", "drizzle": True})
    again = call("plan_stackhammer", target="M51",
                 settings={"weight": "noise", "drizzle": True})
    assert again["preset"]["pending"] == {} and "--set" not in again["how_to_run"]
    assert {r["option"]: r["source"] for r in again["settings"]}["weight"] == "override"

    plain = call("plan_stackhammer", target="M51")
    assert {r["option"]: r["source"] for r in plain["settings"]}["weight"] == "preset"
    assert call("plan_stackhammer", target="M51",
                use_preset=False)["how_to_run"].count("--no-preset") == 1


def test_a_bad_setting_comes_back_with_the_valid_ones(store):
    with pytest.raises(registry.ToolError) as e:
        call("plan_stackhammer", target="M51", settings={"weight": "wfwhm"})
    assert "weight is one of" in str(e.value) and "noise-fwhm" in str(e.value)


def test_without_stackhammer_the_tool_says_where_it_looked(store, monkeypatch):
    monkeypatch.setattr(sh, "_on_path", lambda: None)
    with pytest.raises(registry.ToolError) as e:
        call("plan_stackhammer", target="M51")
    assert "Preferences → Processing tools" in str(e.value)
    assert "stackhammer-stacking" in str(e.value)
    assert str(Path.home()) not in str(e.value)


def test_a_per_filter_split_asks_which_filter(store):
    stackhammer_job("M81 M82", filt="LP")
    stackhammer_job("M81 M82", filt="IRCUT")
    with pytest.raises(registry.ToolError, match="split per filter"):
        call("plan_stackhammer", target="M81 M82")
    out = call("plan_stackhammer", target="M81 M82", filter="LP")
    assert out["working_dir"] == "Images/M81 M82/siril/LP"
    assert "'M81 M82/LP'" in out["how_to_run"]


# ── propose_stackhammer_preset → apply ───────────────────────────────────────

def _propose(**kw):
    args = {"target": "M51", "settings": {"weight": "noise", "feather": 0},
            "rationale": "faint target, depth over star shape", **kw}
    return call("propose_stackhammer_preset", **args)


def test_a_proposal_writes_nothing_until_applied(store):
    _root, job, _calls = store
    env = _propose()
    assert env["action"] == "set_stackhammer_preset"
    assert env["apply"]["safe_write"] is True
    assert env["apply"]["handler"] == proposals.SAFE_WRITE_ACTIONS[env["action"]]
    assert env["payload"] == {"target": "M51", "filter": None,
                              "settings": {"weight": "noise", "feather": 0}}
    assert "not applied" in env["summary"] and "| weight | noise-fwhm | noise |" in env["summary"]
    assert env["staged_as"] and not sh.preset_path(job).exists()

    said = apply_mod.apply_proposal(env["staged_as"])
    assert "Stackhammer preset saved for M51" in said
    assert sh.read_preset(job) == {"weight": "noise", "feather": 0}
    assert outbox.count() == 0


def test_the_preset_is_typed_and_checked_before_it_is_proposed(store):
    env = _propose(settings={"feather": "12", "local-norm": "off"})
    assert env["payload"]["settings"] == {"feather": 12, "local-norm": False}
    with pytest.raises(registry.ToolError, match="unknown option"):
        _propose(settings={"sharpen": True})
    with pytest.raises(registry.ToolError, match="at least one setting"):
        _propose(settings={})
    assert outbox.count() == 1


def test_a_preset_changed_since_the_proposal_is_drift(store):
    """The user opened the window in Siril and saved their own preset in between:
    applying would replace their choice with a stale suggestion."""
    _root, job, _calls = store
    env = _propose()
    assert not apply_mod.check_drift(env).drifted
    sh.write_preset(job, {"weight": "fwhm"})

    drift = apply_mod.check_drift(env)
    assert drift.drifted and "preset was changed" in drift.describe()
    with pytest.raises(apply_mod.ApplyError, match="changed"):
        apply_mod.apply_proposal(env["staged_as"])
    assert "presets/archive" in apply_mod.apply_proposal(env["staged_as"], force=True)
    assert sh.read_preset(job) == {"weight": "noise", "feather": 0}
    assert len(list((job / "presets" / "archive").iterdir())) == 1     # theirs is kept


def test_a_rerank_or_an_import_is_not_drift_for_a_preset(store):
    """The ranking and capture fingerprints belong to other proposal kinds."""
    env = _propose()
    env["basis"]["store_state"]["totals_mtime"] = "1999-01-01T00:00:00"
    env["basis"]["store_state"]["contexts_mtime"] = "1999-01-01T00:00:00"
    assert not apply_mod.check_drift(env).drifted


def test_apply_refuses_while_a_stack_runs_in_the_folder(store):
    _root, job, _calls = store
    env = _propose()
    roundtrip.write_run_marker(job, "stack")
    try:
        with pytest.raises(apply_mod.ApplyError, match="nothing was changed"):
            apply_mod.apply_proposal(env["staged_as"])
    finally:
        roundtrip.clear_run_marker(job)
    assert not sh.preset_path(job).exists()


@pytest.mark.parametrize("payload", [
    {"target": "../../etc", "settings": {"weight": "noise"}},
    {"target": "M51", "filter": "../..", "settings": {"weight": "noise"}},
    {"target": "M51", "settings": {}},
    {"target": "M51", "settings": {"weight": ["noise"]}},
    {"target": "No Such Target", "settings": {"weight": "noise"}},
])
def test_apply_does_not_trust_the_envelope(store, payload):
    """A proposal is a file an assistant wrote: it names a capture folder and a
    filter, never a path, and its settings are plain values."""
    root, _job, _calls = store
    env = _propose()
    path = config.ASSISTANT_OUTBOX / env["staged_as"]
    data = json.loads(path.read_text())
    data["payload"] = payload
    path.write_text(json.dumps(data))
    with pytest.raises(apply_mod.ApplyError):
        apply_mod.apply_proposal(env["staged_as"], force=True)
    assert not list(root.rglob(sh.PRESET_NAME))


def test_each_filter_job_gets_its_own_preset(store):
    lp = stackhammer_job("M81 M82", filt="LP")
    stackhammer_job("M81 M82", filt="IRCUT")
    env = _propose(target="M81 M82", filter="LP")
    assert env["title"] == "Stackhammer preset for M81 M82/LP"
    apply_mod.apply_proposal(env["staged_as"])
    assert sh.read_preset(lp) and not sh.preset_path(
        config.siril_job_dir("M81 M82", "IRCUT")).exists()


def test_a_target_with_no_sandbox_cannot_take_a_preset(store):
    (config.target_dir("M13") / "lights").mkdir(parents=True)
    (config.target_dir("M13") / "lights" / "a.fit").write_text("fit")
    with pytest.raises(registry.ToolError, match="no Siril working folder"):
        _propose(target="M13")

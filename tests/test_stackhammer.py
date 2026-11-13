"""m110.stackhammer — the second stacking engine.

Everything runs against `tests/fake_stackhammer.py`, a stand-in that speaks the
binary's JSON contract, and a monkeypatched `stacking.run_siril`: no real
Stackhammer, no real Siril, no live data.
"""
from __future__ import annotations

import json
import sys

import pytest

from m110 import config, launch, roundtrip, stackhammer as sh, stacking
from tests._helpers import install_fake_stackhammer, seed_root, stackhammer_job

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"),
                                reason="the stand-in binary is a shebang script")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    binary, calls = install_fake_stackhammer(tmp_path, monkeypatch)
    return binary, calls


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


# ── finding the binary ───────────────────────────────────────────────────────

def test_nothing_installed_means_not_found(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    assert sh.find_binary() is None
    with pytest.raises(sh.StackhammerError, match="Preferences"):
        sh.require_binary()


def test_the_script_installed_in_siril_names_the_binary(tmp_path, monkeypatch):
    """Mike's install: no PATH entry, no Preferences path, but the script Siril
    runs carries `STACKHAMMER_BINARY`. Read as text — the file imports sirilpy
    and would fail (or worse, run) if imported."""
    seed_root(tmp_path, monkeypatch)
    binary = _exe(tmp_path / "bin-m3" / "stackhammer")
    support = tmp_path / "org.siril.Siril"
    (support / "scripts").mkdir(parents=True)
    (support / "scripts" / "Stackhammer.py").write_text(
        'import sirilpy\nraise SystemExit("never executed")\n'
        f'VERSION = "0.1.0"\nSTACKHAMMER_BINARY = "{binary}"\n')
    monkeypatch.setattr(sh, "siril_support_dirs", lambda: [support])
    assert sh.find_binary() == (str(binary), "siril-script")


def test_an_empty_or_dead_script_path_falls_through(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    support = tmp_path / "org.siril.Siril"
    (support / "scripts").mkdir(parents=True)
    script = support / "scripts" / "Stackhammer.py"
    monkeypatch.setattr(sh, "siril_support_dirs", lambda: [support])
    on_path = _exe(tmp_path / "p" / "stackhammer")
    monkeypatch.setattr(sh, "_on_path", lambda: str(on_path))

    script.write_text('STACKHAMMER_BINARY = ""\n')                 # as shipped
    assert sh.find_binary() == (str(on_path), "path")
    script.write_text('STACKHAMMER_BINARY = "/nowhere/stackhammer"\n')
    assert sh.find_binary() == (str(on_path), "path")


def test_the_scripts_saved_choice_is_read_too(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    binary = _exe(tmp_path / "located" / "stackhammer")
    support = tmp_path / "org.siril.Siril"
    (support / "siril").mkdir(parents=True)
    (support / "siril" / sh.SIRIL_SCRIPT_CONFIG).write_text(
        json.dumps({"binary": str(binary)}))
    monkeypatch.setattr(sh, "siril_support_dirs", lambda: [support])
    assert sh.find_binary() == (str(binary), "script-config")


def test_preferences_wins_over_everything(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    chosen = _exe(tmp_path / "chosen" / "stackhammer")
    monkeypatch.setattr(sh, "_on_path", lambda: str(_exe(tmp_path / "p" / "stackhammer")))
    config.save_setting(launch.APP_PATHS_SETTING, {sh.TOOL_ID: str(chosen)})
    assert sh.find_binary() == (str(chosen), "preferences")


def test_stackhammer_is_a_registered_cli_tool():
    """Registered so Preferences grows a path row, flagged so nothing tries to
    open it like an app."""
    assert sh.TOOL_ID in launch.tool_ids()
    assert launch.is_cli(sh.TOOL_ID) and not launch.is_cli("siril")
    assert not launch.sets_working_dir(sh.TOOL_ID) and not launch.opens_file(sh.TOOL_ID)


# ── settings ─────────────────────────────────────────────────────────────────

def test_validate_types_values_from_the_command_line(fake):
    defaults = sh.settings(str(fake[0]))
    got = sh.validate({"weight": "noise", "drizzle": "true", "feather": "0",
                       "drizzle-scale": "2", "local-norm": "off",
                       "max-frame-residual": "0", "darks": "../cal/darks"}, defaults)
    assert got == {"weight": "noise", "drizzle": True, "feather": 0,
                   "drizzle-scale": 2, "local-norm": False,
                   "max-frame-residual": 0, "darks": "../cal/darks"}


@pytest.mark.parametrize("bad, says", [
    ({"weight": "wfwhm"}, "weight is one of"),            # the Siril stacker's word
    ({"wieght": "noise"}, "unknown option 'wieght'"),
    ({"feather": "wide"}, "feather takes a number"),
    ({"drizzle": "maybe"}, "drizzle is on or off"),
    ({"prepare": True}, "prepare is not a setting"),
])
def test_validate_refuses_and_lists_what_is_valid(fake, bad, says):
    defaults = sh.settings(str(fake[0]))
    with pytest.raises(sh.StackhammerError) as e:
        sh.validate(bad, defaults)
    assert says in str(e.value)
    assert "filter-fwhm" in str(e.value)          # the valid names, for the caller


def test_run_spells_out_every_setting(fake):
    """The run never leans on a default M110 and the binary might not share."""
    defaults = sh.settings(str(fake[0]))
    args = sh.run_args(defaults["settings"], {"weight": "noise", "drizzle": True,
                                              "max-frame-residual": 0})
    assert len([a for a in args if a.startswith("--")]) == len(defaults["settings"]) + 1
    assert args[args.index("--weight") + 1] == "noise"
    assert "--drizzle" in args and "--no-drizzle" not in args
    assert "--local-norm" in args and "--neutral-background" in args
    assert args[-2:] == ["--max-frame-residual", "0"]


def test_prepare_gets_only_what_was_chosen():
    """Unset, background extraction follows process/ — the binary's call."""
    assert sh.prepare_args({}) == []
    assert sh.prepare_args({"background": False}) == ["--no-background"]
    assert sh.prepare_args({"drizzle": True, "compress": True, "calibration": False,
                            "bias-level": 480, "darks": "../d"}) == [
        "--drizzle", "--compress", "--no-calibration", "--bias-level", "480",
        "--darks", "../d"]
    assert sh.prepare_args({"calibration": True, "cosmetic": True}) == []


def test_an_old_binary_is_refused(fake, monkeypatch):
    monkeypatch.setenv("FAKE_STACKHAMMER_SCHEMA", "4")
    with pytest.raises(sh.StackhammerError, match="too old"):
        sh.settings(str(fake[0]))


def test_every_spawn_sanitizes_the_child_environment():
    """Same reason as the Siril stacker's twin: a frozen M110's Qt and Python
    variables must not ride into a child."""
    import ast
    import inspect

    spawns = [n for n in ast.walk(ast.parse(inspect.getsource(sh)))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
              and n.func.attr in ("run", "Popen")]
    assert len(spawns) == 2
    for call in spawns:
        assert any(k.arg == "env" for k in call.keywords)


# ── presets ──────────────────────────────────────────────────────────────────

def test_preset_round_trips_in_the_scripts_format(fake):
    job = stackhammer_job()
    done = sh.write_preset(job, {"weight": "noise", "feather": 0})
    data = json.loads(sh.preset_path(job).read_text())
    assert data["stackhammer_preset"] == 1 and data["settings"]["weight"] == "noise"
    assert done["changed"] and done["archived"] is None
    assert sh.read_preset(job) == {"weight": "noise", "feather": 0}


def test_a_different_preset_is_archived_and_the_same_one_left_alone(fake):
    job = stackhammer_job()
    sh.write_preset(job, {"weight": "noise"})
    again = sh.write_preset(job, {"weight": "noise"})
    assert not again["changed"] and not (job / "presets" / "archive").exists()

    replaced = sh.write_preset(job, {"weight": "fwhm"})
    assert replaced["archived"].parent == job / "presets" / "archive"
    assert json.loads(replaced["archived"].read_text())["settings"] == {"weight": "noise"}
    assert sh.read_preset(job) == {"weight": "fwhm"}


def test_a_foreign_file_is_not_a_preset(fake):
    """Naztronomy's preset sits in the same folder; a file without the format
    marker is refused rather than half-read (the script's own rule)."""
    job = stackhammer_job()
    sh.preset_path(job).parent.mkdir()
    sh.preset_path(job).write_text(json.dumps({"drizzle": True}))
    assert sh.read_preset(job) is None


# ── the plan ─────────────────────────────────────────────────────────────────

def test_plan_before_the_plate_solve_says_what_is_not_known(fake):
    stackhammer_job()
    p = sh.build_plan("M51")
    out = p.as_json()
    assert p.needs_preprocessing() and out["solved"] is None
    assert "not known" in out["solved_note"]
    assert [s["name"] for s in out["siril_steps"]] == ["link", "calibrate", "plate solve"]
    assert out["lights"]["frames"] == 4 and out["sequence"] == "pp_lights_"
    assert {"default", "state"} == {r["source"] for r in out["settings"]}


def test_settings_come_from_defaults_then_the_preset_then_overrides(fake):
    job = stackhammer_job()
    sh.write_preset(job, {"weight": "noise", "feather": 0, "someday-option": 1})
    p = sh.build_plan("M51", {"feather": "12"})
    rows = {r["option"]: r for r in p.settings()}
    assert (rows["weight"]["value"], rows["weight"]["source"]) == ("noise", "preset")
    assert (rows["feather"]["value"], rows["feather"]["source"]) == (12, "override")
    assert rows["feather"]["proposed"] == 30
    assert rows["rejection"]["source"] == "default"
    assert p.ignored == ["someday-option"]          # a newer build's key: kept out, said

    plain = sh.build_plan("M51", use_preset=False)
    assert {r["source"] for r in plain.settings()} == {"default", "state"}


def test_a_chosen_setting_reaches_prepare_and_changes_the_recipe(fake):
    stackhammer_job()
    p = sh.build_plan("M51", {"background": True, "drizzle": True})
    assert p.sequence == "bkg_pp_lights_"
    steps = {s["name"]: s["commands"] for s in p.prepare["steps"]}
    assert "background" in steps and "-debayer" not in steps["calibrate"][0]
    prepare_call = next(c for c in fake[1]() if c[0] == "prepare")
    assert "--background" in prepare_call and "--drizzle" in prepare_call


def test_a_solved_sequence_is_planned_with_the_filters(fake):
    job = stackhammer_job()
    (job / "process").mkdir()
    (job / "process" / "pp_lights_.seq").write_text("seq")
    p = sh.build_plan("M51", {"filter-fwhm": 90})
    out = p.as_json()
    assert not p.needs_preprocessing()
    assert out["solved"]["selection"] == {**out["solved"]["selection"], "total": 4, "kept": 3}
    assert out["solved"]["framing"]["medianDepth"] == 3
    assert isinstance(out["solved"]["kept_frames"]["withoutDistortion"], int)
    plan_call = next(c for c in fake[1]() if c[0] == "plan")
    assert plan_call[plan_call.index("--seq") + 1] == "pp_lights_"    # never the default
    assert plan_call[plan_call.index("--filter-fwhm") + 1] == "90"


def test_a_per_filter_job_is_resolved_like_m110_stack(fake):
    stackhammer_job("M81 M82", filt="LP")
    p = sh.build_plan("M81 M82/LP")
    assert p.working == config.siril_job_dir("M81 M82", "LP")
    with pytest.raises(sh.StackhammerError):
        sh.build_plan("No Such Target")


# ── the run ──────────────────────────────────────────────────────────────────

class FakeSiril:
    """`stacking.run_siril`, recording each script and doing what Siril would
    to the folder: `link` writes its conversion list, the plate solve leaves a
    solved sequence."""

    def __init__(self, job, fail=None, order=None):
        self.job, self.fail, self.order = job, fail or {}, order
        self.scripts: list[str] = []

    def __call__(self, siril, working, ssf, log_path, heartbeat, on_line=None,
                 on_raw=None):
        self.scripts.append(ssf)
        process = self.job / "process"
        process.mkdir(exist_ok=True)
        if "link lights" in ssf:
            names = self.order or sorted(p.name for p in (self.job / "lights").iterdir())
            (process / "lights_conversion.txt").write_text("".join(
                f"'{self.job}/lights/{n}' -> '{process}/lights_{i:05d}.fit'\n"
                for i, n in enumerate(names, 1)))
            (process / "lights_.seq").write_text("seq")
        if "seqplatesolve" in ssf:
            seq = ssf.split("seqplatesolve ")[1].split()[0]
            (process / f"{seq}.seq").write_text("seq")
        step = next((k for k in self.fail if k in ssf), None)
        return (self.fail[step] if step else 0), []


def _run(job, monkeypatch, capsys, siril=None, **kw):
    siril = siril or FakeSiril(job)
    monkeypatch.setattr(stacking, "run_siril", siril)
    phases = []
    p = sh.build_plan(job, kw.pop("settings", None))
    rc = sh.execute(p, "siril-cli", heartbeat=1, mark=phases.append, **kw)
    return rc, siril, phases, capsys.readouterr().out


def test_a_run_preprocesses_stacks_and_cleans_up(fake, monkeypatch, capsys):
    job = stackhammer_job()
    rc, siril, phases, out = _run(job, monkeypatch, capsys, settings={"weight": "noise"})

    assert rc == 0 and phases == ["solve", "stack"]
    assert len(siril.scripts) == 3
    first, second, third = siril.scripts
    assert first.startswith("requires 1.4.0\nsetcompress 0\ncd ")   # see step_script
    assert f'cd "{job / "process"}"' in second and "calibrate lights_" in second
    assert "seqplatesolve pp_lights_" in third

    run = next(c for c in fake[1]() if c[0] == "run")
    assert run[1] == str(job / "process")
    assert run[run.index("--seq") + 1] == "pp_lights_"
    assert run[run.index("--output") + 1] == str(job)
    assert run[run.index("--weight") + 1] == "noise" and "--no-drizzle" in run
    stacks = list(job.glob("*_og.fit"))
    assert len(stacks) == 1 and f"Stacked: {stacks[0]}" in out
    assert "1 frame(s) left out by local normalization" in out
    # clean ran last and the scratch is gone; the lights are not
    assert fake[1]()[-1][0] == "clean" and not (job / "process" / "pp_lights_.seq").exists()
    assert len(list((job / "lights").iterdir())) == 4
    assert (job / sh.RUN_LOG).read_text().count('"event"') >= 4


def test_the_stack_can_be_handed_on_and_its_maps_are_left_alone(fake, monkeypatch, capsys):
    """The result lands at the top of the job folder, where the hand-off looks.
    The folder of maps beside it is Stackhammer's record of the run, not output:
    nothing in it is offered to send on or to import."""
    from m110 import siril

    job = stackhammer_job()
    _run(job, monkeypatch, capsys)
    stack = next(job.glob("*_og.fit"))
    maps = job / sh.MAPS_DIR / stack.stem
    (maps / "depth.fits").write_text("map")
    (maps / "rej.fits").write_text("map")
    (maps / "depth_final.png").write_text("a raster would read as a finished render")

    assert [p for _tier, p in stacking._candidate_paths("M51")] == [stack]
    assert sh.MAPS_DIR in siril._SKIP_DIRS
    assert list(siril._sandbox_outputs("M51")) == []


def test_an_earlier_runs_scratch_is_cleared_first(fake, monkeypatch, capsys):
    job = stackhammer_job()
    (job / "process").mkdir()
    (job / "process" / "bkg_pp_lights_.seq").write_text("stale")
    rc, siril, _, out = _run(job, monkeypatch, capsys)
    assert rc == 0 and "Cleared" in out
    order = [c[0] for c in fake[1]()]
    assert order.index("clean") < order.index("run")
    # with process/ empty again, background extraction is off again: the recipe
    # was asked for afresh rather than reused from before the clean
    assert "seqplatesolve pp_lights_" in siril.scripts[-1]


def test_restack_reuses_the_solved_sequence_and_needs_one(fake, monkeypatch, capsys):
    job = stackhammer_job()
    rc, siril, _, _ = _run(job, monkeypatch, capsys, restack=True)
    assert rc == 2 and siril.scripts == []

    (job / "process").mkdir(exist_ok=True)
    (job / "process" / "pp_lights_.seq").write_text("seq")
    rc, siril, phases, _ = _run(job, monkeypatch, capsys, restack=True, keep_process=True)
    assert rc == 0 and siril.scripts == [] and phases == ["stack"]
    assert (job / "process" / "pp_lights_.seq").exists()        # --keep-process


def test_a_plate_solve_error_is_not_the_end(fake, monkeypatch, capsys):
    job = stackhammer_job()
    rc, _, _, out = _run(job, monkeypatch, capsys,
                         siril=FakeSiril(job, fail={"seqplatesolve": 1}))
    assert rc == 0 and "carrying on with the frames that solved" in out


def test_any_other_siril_failure_stops_before_stacking(fake, monkeypatch, capsys):
    job = stackhammer_job()
    rc, siril, _, out = _run(job, monkeypatch, capsys,
                             siril=FakeSiril(job, fail={"calibrate lights_": 1}))
    assert rc == 1 and "calibrate step failed" in out and len(siril.scripts) == 2
    assert not any(c[0] == "run" for c in fake[1]())


def test_a_link_order_siril_disagrees_with_stops_the_run(fake, monkeypatch, capsys):
    """Frames are selected by number, so a different numbering would calibrate
    the wrong ones silently."""
    job = stackhammer_job()
    (job / ".fake_check").write_text("")
    names = sorted(p.name for p in (job / "lights").iterdir())
    rc, siril, _, out = _run(job, monkeypatch, capsys,
                             siril=FakeSiril(job, order=names[::-1]))
    assert rc == 1 and "numbered the files in another order" in out
    assert len(siril.scripts) == 1 and not any(c[0] == "run" for c in fake[1]())

    rc, _, _, _ = _run(job, monkeypatch, capsys, siril=FakeSiril(job))
    assert rc == 0                                   # the order it expected: fine


@pytest.mark.parametrize("mode, status, says", [
    ("error", 1, "the GPU ran out of memory"),
    ("cancelled", 130, "wrote nothing"),
])
def test_a_failed_or_cancelled_stack_keeps_the_scratch(fake, monkeypatch, capsys,
                                                      mode, status, says):
    job = stackhammer_job()
    monkeypatch.setenv("FAKE_STACKHAMMER_RUN", mode)
    rc, _, _, out = _run(job, monkeypatch, capsys)
    assert rc == status and says in out
    assert (job / "process" / "pp_lights_.seq").exists()
    assert fake[1]()[-1][0] == "run"                 # no clean after it


def test_handoff_goes_through_the_one_handoff_writer(fake, monkeypatch, capsys):
    job = stackhammer_job()
    seen = []
    monkeypatch.setattr(stacking, "apply_handoff",
                        lambda f, tool: seen.append((f.name, tool)) or f)
    rc, _, _, out = _run(job, monkeypatch, capsys, handoff="astrowizard")
    assert rc == 0 and seen and seen[0][1] == "astrowizard"
    assert "Handed to astrowizard" in out


# ── the CLI ──────────────────────────────────────────────────────────────────

def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["m110-stack", *argv])
    return stacking.main()


def test_cli_proposes_without_running_anything(fake, monkeypatch, capsys):
    job = stackhammer_job()
    monkeypatch.setattr(stacking, "run_siril", lambda *a, **k: pytest.fail("ran Siril"))
    assert _main(monkeypatch, "M51", "--engine", "stackhammer",
                 "--set", "weight=noise") == 0
    out = capsys.readouterr().out
    assert "Proposal only" in out and "* weight" in out and "noise" in out
    assert {c[0] for c in fake[1]()} == {"settings", "prepare"}
    assert not (job / "process").exists()


def test_cli_json_is_the_plan(fake, monkeypatch, capsys):
    stackhammer_job()
    assert _main(monkeypatch, "M51", "--engine", "stackhammer", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["engine"] == "stackhammer" and out["lights"]["frames"] == 4


def test_cli_runs_under_the_run_marker(fake, monkeypatch, capsys):
    job = stackhammer_job()
    seen = []

    class Watching(FakeSiril):
        def __call__(self, *a, **k):
            seen.append(roundtrip.stack_in_progress(job)["phase"])
            return super().__call__(*a, **k)

    monkeypatch.setattr(stacking, "run_siril", Watching(job))
    monkeypatch.setattr(stacking, "require_siril", lambda: "siril-cli")
    monkeypatch.delenv("SIRIL_CLI", raising=False)
    assert _main(monkeypatch, "M51", "--engine", "stackhammer", "--run") == 0
    assert seen == ["solve"] * 3 and roundtrip.stack_in_progress(job) is None


def test_cli_refuses_the_siril_engines_overrides(fake, monkeypatch, capsys):
    """`--weight` means something else to each engine; ignoring it would stack
    with settings nobody chose."""
    stackhammer_job()
    assert _main(monkeypatch, "M51", "--engine", "stackhammer", "--weight", "noise") == 2
    assert "--set KEY=VALUE" in capsys.readouterr().err
    assert _main(monkeypatch, "M51", "--set", "weight=noise") == 2
    assert "--engine stackhammer" in capsys.readouterr().err
    assert _main(monkeypatch, "M51", "--engine", "stackhammer", "--set", "weight") == 2
    assert "KEY=VALUE" in capsys.readouterr().err


def test_cli_says_where_it_looked_when_stackhammer_is_missing(tmp_path, monkeypatch, capsys):
    seed_root(tmp_path, monkeypatch)
    stackhammer_job()
    assert _main(monkeypatch, "M51", "--engine", "stackhammer") == 2
    assert "Preferences → Processing tools" in capsys.readouterr().err

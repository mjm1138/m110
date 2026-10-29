"""Tests for m110/running_app.py — naming the `m110-stack` of the app the user runs.

#192: `plan_stack` handed over a bare `m110-stack`, which is on nobody's PATH, and
the obvious fix (the server's own sibling) names the wrong build whenever the
assistant's server and the GUI are different installs — the bundle serving Claude
while the user drives the app from a dev venv. The conftest seal points
`config.APP_CONFIG_DIR` at a throwaway dir, so the record here never touches
`~/.m110`.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from m110 import config, running_app


@pytest.fixture
def record_file():
    path = config.APP_CONFIG_DIR / running_app.RECORD_NAME
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


def _write(path, **over):
    data = {"pid": os.getpid(), "data_root": str(config.DATA_ROOT),
            "stack_command": ["/Applications/M110.app/Contents/MacOS/m110-stack"],
            "install": "installed app", "version": "0.3.0b9"}
    data.update(over)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── this process's own m110-stack ────────────────────────────────────────────

def test_source_install_prefers_the_venv_sibling_over_path(tmp_path, monkeypatch):
    """PATH may hold a different install entirely; the interpreter's own bin/ is
    the one whose code this process is running."""
    bindir = tmp_path / "venv" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "m110-stack").write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "executable", str(bindir / "python"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(running_app.shutil, "which", lambda _n: "/elsewhere/m110-stack")
    assert running_app.stack_command() == [str(bindir / "m110-stack")]


def test_source_install_falls_back_to_path_then_the_module(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(running_app.shutil, "which", lambda _n: "/opt/bin/m110-stack")
    assert running_app.stack_command() == ["/opt/bin/m110-stack"]
    monkeypatch.setattr(running_app.shutil, "which", lambda _n: None)
    assert running_app.stack_command() == [str(tmp_path / "python"), "-m", "m110.stacking"]


def test_frozen_build_names_the_helper_beside_its_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", "/Applications/M110.app/Contents/MacOS/M110")
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert running_app.stack_command() == ["/Applications/M110.app/Contents/MacOS/m110-stack"]
    assert running_app.install_kind() == "installed app"


def test_appimage_dispatches_through_the_image_itself(monkeypatch):
    """The helper's path inside the mount exists only while it runs."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", "/opt/M110.AppImage")
    assert running_app.stack_command() == ["/opt/M110.AppImage", "--stack"]


# ── the record ───────────────────────────────────────────────────────────────

def test_record_round_trips_and_clear_removes_only_our_own(record_file):
    running_app.record()
    data = json.loads(record_file.read_text())
    assert data["pid"] == os.getpid()
    assert data["stack_command"] == running_app.stack_command()
    assert running_app.running_app()["stack_command"] == data["stack_command"]

    running_app.clear()
    assert not record_file.exists()

    _write(record_file, pid=os.getpid() + 1)       # a later window owns it now
    running_app.clear()
    assert record_file.exists()


def test_a_dead_pid_is_no_running_app(record_file):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    _write(record_file, pid=proc.pid)
    assert running_app.running_app() is None


def test_another_data_root_is_not_the_app_this_request_is_about(record_file, tmp_path):
    _write(record_file, data_root=str(tmp_path / "some other library"))
    assert running_app.running_app() is None


@pytest.mark.parametrize("text", ["", "{", "[]", '{"pid": "x"}',
                                  '{"pid": 1, "stack_command": []}'])
def test_a_malformed_record_is_ignored(record_file, text):
    record_file.parent.mkdir(parents=True, exist_ok=True)
    record_file.write_text(text)
    assert running_app.running_app() is None


def test_stacker_prefers_the_running_app_over_this_install(record_file):
    """The #192 trap: the server is the bundle, the GUI runs from a venv."""
    _write(record_file, stack_command=["/home/u/m110/.venv/bin/m110-stack"],
           install="development environment", version="0.3.0b9+dev")
    stk = running_app.stacker()
    assert stk["argv"] == ["/home/u/m110/.venv/bin/m110-stack"]
    assert stk["install"] == "development environment"
    assert stk["matches_running_app"] is True


def test_stacker_falls_back_to_this_install_and_says_so(record_file):
    stk = running_app.stacker()
    assert stk["argv"] == running_app.stack_command()
    assert stk["matches_running_app"] is False
    assert stk["install"] and stk["version"]


# ── shell quoting ────────────────────────────────────────────────────────────

def test_the_home_directory_becomes_an_unquoted_tilde(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/someone"))
    cmd = running_app.shell_command(
        ["/Users/someone/Documents/Code/m110/.venv/bin/m110-stack"], "M 31_mosaic", "--run")
    assert cmd == "~/Documents/Code/m110/.venv/bin/m110-stack 'M 31_mosaic' --run"
    assert "/Users/someone" not in cmd


def test_a_home_path_with_spaces_keeps_the_tilde_outside_the_quotes(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/someone"))
    cmd = running_app.shell_command(["/Users/someone/My Apps/m110-stack"])
    assert cmd == "~/'My Apps/m110-stack'"


def test_a_lookalike_prefix_is_not_the_home_directory(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/some"))
    assert running_app.shell_command(["/Users/someone/x"]) == "/Users/someone/x"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell quoting")
@pytest.mark.parametrize("name", ["M 31_mosaic", "it's", 'say "hi"', "both ' and \"",
                                  "$HOME", "back\\slash", "M81 M82/LP"])
def test_every_word_survives_a_real_shell(name):
    """Python's repr was the old quoting: it breaks on `$`, backslashes and a name
    holding both quote characters. Round-trip through /bin/sh to prove it."""
    cmd = running_app.shell_command(["printf", "%s\\n"], name)
    out = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True,
                         check=True).stdout
    assert out == name + "\n"

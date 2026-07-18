"""Tests for the external-app launcher (launch.py) — the guide side of #19.
No app is actually started: _spawn is monkeypatched to capture argv."""
import os
import sys

import pytest

from m110 import config, launch


@pytest.fixture
def captured_spawn(monkeypatch):
    calls = []
    monkeypatch.setattr(launch, "_spawn", lambda argv: calls.append(argv))
    return calls


# ── discovery: override wins, resolves .app, missing path ignored ────────────

def test_override_wins_over_autodetect(tmp_path, monkeypatch):
    binary = tmp_path / "mysiril"
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(config, "get_setting",
                        lambda k, d=None: {"siril": str(binary)} if k == launch.APP_PATHS_SETTING else d)
    assert launch.find_app("siril") == str(binary)


def test_override_missing_path_is_ignored(monkeypatch):
    monkeypatch.setattr(config, "get_setting",
                        lambda k, d=None: {"siril": "/nope/does-not-exist"} if k == launch.APP_PATHS_SETTING else d)
    # No override → falls through to auto-detect; force a platform with no match.
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(launch.shutil, "which", lambda name: None)
    assert launch.find_app("siril") is None


def test_override_resolves_macos_app_bundle(tmp_path, monkeypatch):
    app = tmp_path / "Siril.app"
    binary = app / "Contents" / "MacOS" / "siril"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(config, "get_setting",
                        lambda k, d=None: {"siril": str(app)} if k == launch.APP_PATHS_SETTING else d)
    assert launch.find_app("siril") == str(binary)


def test_autodetect_linux_uses_which(monkeypatch):
    monkeypatch.setattr(config, "get_setting", lambda k, d=None: d)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(launch.shutil, "which",
                        lambda name: "/usr/bin/siril" if name == "siril" else None)
    assert launch.find_app("siril") == "/usr/bin/siril"


def test_unknown_tool_is_none(monkeypatch):
    monkeypatch.setattr(config, "get_setting", lambda k, d=None: d)
    assert launch.find_app("pixinsight") is None


# ── launch: builds `-d <dir>` argv, errors when not found ────────────────────

def test_launch_builds_workdir_argv(tmp_path, monkeypatch, captured_spawn):
    binary = tmp_path / "siril"
    binary.write_text("x")
    monkeypatch.setattr(launch, "find_app", lambda tid: str(binary))
    wd = tmp_path / "Images" / "M10" / "siril"
    ret = launch.launch_processing("siril", wd)
    assert ret == str(binary)
    assert captured_spawn == [[str(binary), "-d", str(wd)]]


def test_macos_launch_uses_open_with_bundle_and_clean_env(tmp_path, monkeypatch):
    """On macOS we must launch via `open` (LaunchServices) so Siril is its own
    responsible process and its hardened-runtime Python can spawn — a direct
    child launch gets it SIGKILLed."""
    monkeypatch.setattr(sys, "platform", "darwin")
    binary = tmp_path / "Siril.app" / "Contents" / "MacOS" / "siril"
    binary.parent.mkdir(parents=True)
    binary.write_text("x")
    monkeypatch.setattr(launch, "find_app", lambda tid: str(binary))
    monkeypatch.setenv("VIRTUAL_ENV", "/proj/.venv")

    seen = {}

    class _Res:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env")
        return _Res()
    monkeypatch.setattr(launch.subprocess, "run", fake_run)

    wd = tmp_path / "Images" / "M10" / "siril"
    launch.launch_processing("siril", wd)
    assert seen["argv"] == ["/usr/bin/open", "-a", str(tmp_path / "Siril.app"),
                            "--args", "-d", str(wd)]
    assert "VIRTUAL_ENV" not in seen["env"]          # sanitized env handed to open


def test_macos_open_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    binary = tmp_path / "Siril.app" / "Contents" / "MacOS" / "siril"
    binary.parent.mkdir(parents=True)
    binary.write_text("x")
    monkeypatch.setattr(launch, "find_app", lambda tid: str(binary))

    class _Res:
        returncode = 1
        stderr = "Unable to find application named 'Siril'"
    monkeypatch.setattr(launch.subprocess, "run", lambda argv, **kw: _Res())
    with pytest.raises(launch.LaunchError, match="Unable to find application"):
        launch.launch_processing("siril", "/dir")


def test_launch_raises_when_not_found(monkeypatch, captured_spawn):
    monkeypatch.setattr(launch, "find_app", lambda tid: None)
    with pytest.raises(launch.LaunchError, match="Set its location"):
        launch.launch_processing("siril", "/some/dir")
    assert captured_spawn == []


def test_launch_wraps_os_error(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "find_app", lambda tid: "/bin/siril")

    def boom(argv):
        raise OSError("no exec")
    monkeypatch.setattr(launch, "_spawn", boom)
    with pytest.raises(launch.LaunchError, match="Couldn't start"):
        launch.launch_processing("siril", "/dir")


# ── child environment: don't leak our Python/venv into the tool (Siril venv) ──

def test_child_env_strips_our_python_and_venv(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/proj/.venv")
    monkeypatch.setenv("PYTHONHOME", "/proj/.venv")
    monkeypatch.setenv("PYTHONPATH", "/proj/src")
    monkeypatch.setenv("PATH", os.pathsep.join(["/proj/.venv/bin", "/usr/bin", "/bin"]))
    env = launch._child_env()
    assert "VIRTUAL_ENV" not in env
    assert "PYTHONHOME" not in env and "PYTHONPATH" not in env
    parts = env["PATH"].split(os.pathsep)
    assert "/proj/.venv/bin" not in parts        # our venv bin dropped
    assert "/usr/bin" in parts and "/bin" in parts  # system dirs kept


def test_child_env_restores_bundle_libpath(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/lib")
    env = launch._child_env()
    assert env["LD_LIBRARY_PATH"] == "/system/lib"   # restored from _ORIG
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_child_env_drops_bundle_libpath_without_orig(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/bundle/lib")
    monkeypatch.delenv("DYLD_LIBRARY_PATH_ORIG", raising=False)
    env = launch._child_env()
    assert "DYLD_LIBRARY_PATH" not in env


def test_child_env_strips_qt_plugin_paths(monkeypatch):
    """Frozen M110 exports QT_PLUGIN_PATH / QML2_IMPORT_PATH into its own bundled Qt
    (the PyInstaller PySide6 runtime hook). A launched tool that ships its own Qt —
    Siril's PyQt6 scripts — must NOT inherit them, or two Qt sets load into one
    process and it SIGABRTs (the 2026-07-18 Siril script crash)."""
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    frameworks = "/Applications/M110.app/Contents/Frameworks/PySide6/Qt"
    monkeypatch.setenv("QT_PLUGIN_PATH", f"{frameworks}/plugins")
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", f"{frameworks}/plugins/platforms")
    monkeypatch.setenv("QML2_IMPORT_PATH", f"{frameworks}/qml")
    env = launch._child_env()
    assert "QT_PLUGIN_PATH" not in env
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in env
    assert "QML2_IMPORT_PATH" not in env


def test_child_env_keeps_system_bin_when_not_venv(monkeypatch):
    """Outside a venv/frozen build we must NOT strip the interpreter's dir — it's
    a shared system bin the tool may need."""
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)   # look like system python
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))
    env = launch._child_env()
    assert "/usr/bin" in env["PATH"].split(os.pathsep)

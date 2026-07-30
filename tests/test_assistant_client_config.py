"""Connecting an external client — path resolution and safe JSON merging.

These edit a file belonging to *another application*, so the tests care most
about what must never happen: losing someone else's server, overwriting a config
we couldn't parse, or advertising a data root that isn't the one in use.
"""
import json
import sys
from pathlib import Path

import pytest

from m110 import config
from m110.assistant import client_config as cc


@pytest.fixture
def cfg(tmp_path):
    return tmp_path / "claude_desktop_config.json"


def _write(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── platform paths ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("platform, expected", [
    ("darwin", "Library/Application Support/Claude/claude_desktop_config.json"),
    ("linux", ".config/Claude/claude_desktop_config.json"),
])
def test_desktop_config_path_per_platform(platform, expected, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    assert cc.desktop_config_path().as_posix().endswith(expected)


def test_desktop_config_path_windows_uses_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(Path("/tmp/roaming")))
    p = cc.desktop_config_path()
    assert p.name == "claude_desktop_config.json" and "roaming" in p.as_posix()


# ── the server command this install advertises ───────────────────────────────

def test_source_install_command_is_runnable():
    cmd = cc.server_command()
    assert cmd
    # Either the console-script, or this very interpreter running the module —
    # both of which are guaranteed to have m110 importable.
    assert cmd[0].endswith("m110-mcp") or cmd[:1] == [sys.executable]


def test_frozen_build_points_beside_the_gui_binary(tmp_path, monkeypatch):
    fake = tmp_path / "M110.app" / "Contents" / "MacOS" / "M110"
    fake.parent.mkdir(parents=True)
    fake.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert cc.server_command() == [str(fake.with_name("m110-mcp"))]


def test_entry_always_pins_the_data_root():
    """config resolves the root at import time, and a client-spawned server
    inherits none of the app's state — so this is not optional."""
    entry = cc.server_entry()
    assert entry["env"]["M110_DATA_ROOT"] == str(config.DATA_ROOT)


def test_entry_honours_an_explicit_root(tmp_path):
    assert cc.server_entry(tmp_path)["env"]["M110_DATA_ROOT"] == str(tmp_path)


# ── merging ──────────────────────────────────────────────────────────────────

def test_writes_into_a_missing_config(cfg):
    path, backup = cc.write_desktop_config(cfg)
    assert backup is None
    written = json.loads(path.read_text(encoding="utf-8"))
    assert cc.SERVER_KEY in written["mcpServers"]


def test_preserves_other_servers(cfg):
    _write(cfg, {"mcpServers": {"github": {"command": "gh-mcp"}},
                 "someOtherSetting": {"keep": True}})
    cc.write_desktop_config(cfg)
    written = json.loads(cfg.read_text(encoding="utf-8"))
    assert written["mcpServers"]["github"] == {"command": "gh-mcp"}
    assert written["someOtherSetting"] == {"keep": True}
    assert cc.SERVER_KEY in written["mcpServers"]


def test_reconnecting_updates_in_place(cfg, tmp_path):
    cc.write_desktop_config(cfg, data_root=tmp_path / "old")
    cc.write_desktop_config(cfg, data_root=tmp_path / "new")
    written = json.loads(cfg.read_text(encoding="utf-8"))
    assert written["mcpServers"][cc.SERVER_KEY]["env"]["M110_DATA_ROOT"] == \
        str(tmp_path / "new")
    assert len(written["mcpServers"]) == 1          # not duplicated


def test_backs_up_before_overwriting(cfg):
    _write(cfg, {"mcpServers": {"github": {"command": "gh-mcp"}}})
    original = cfg.read_text(encoding="utf-8")
    _, backup = cc.write_desktop_config(cfg)
    assert backup and backup.read_text(encoding="utf-8") == original


def test_refuses_to_clobber_unparseable_json(cfg):
    cfg.write_text("{ this is not json ,,,", encoding="utf-8")
    with pytest.raises(cc.ClientConfigError) as e:
        cc.write_desktop_config(cfg)
    assert "won't overwrite" in str(e.value)
    # And it really didn't touch it.
    assert cfg.read_text(encoding="utf-8") == "{ this is not json ,,,"


def test_empty_file_is_treated_as_no_config(cfg):
    cfg.write_text("   \n", encoding="utf-8")
    cc.write_desktop_config(cfg)
    assert cc.SERVER_KEY in json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]


def test_rejects_a_json_document_that_is_not_an_object(cfg):
    cfg.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(cc.ClientConfigError):
        cc.read_desktop_config(cfg)


# ── connect / disconnect round trip ──────────────────────────────────────────

def test_is_connected_tracks_state(cfg):
    assert cc.is_connected(cfg) is False
    cc.write_desktop_config(cfg)
    assert cc.is_connected(cfg) is True


def test_disconnect_removes_only_our_entry(cfg):
    _write(cfg, {"mcpServers": {"github": {"command": "gh-mcp"}}})
    cc.write_desktop_config(cfg)
    assert cc.remove_from_desktop_config(cfg) is True
    written = json.loads(cfg.read_text(encoding="utf-8"))
    assert cc.SERVER_KEY not in written["mcpServers"]
    assert "github" in written["mcpServers"]


def test_disconnect_when_absent_is_a_no_op(cfg):
    _write(cfg, {"mcpServers": {}})
    assert cc.remove_from_desktop_config(cfg) is False


def test_is_connected_survives_a_broken_config(cfg):
    cfg.write_text("nonsense", encoding="utf-8")
    assert cc.is_connected(cfg) is False        # reports, doesn't raise


# ── what we show the user ────────────────────────────────────────────────────

def test_preview_shows_only_our_entry():
    """Showing the user's whole config back at them buries the one line changing."""
    preview = json.loads(cc.preview_desktop_json())
    assert list(preview["mcpServers"]) == [cc.SERVER_KEY]


def test_disclosure_names_what_leaves_the_machine_and_what_cannot_change():
    """Since M0.5 the assistant CAN create files (in its outbox), so the
    disclosure must not claim "read-only" — it must state the narrower, true
    guarantee: it cannot change or delete your library, and nothing lands
    without you accepting it."""
    low = cc.DISCLOSURE.lower()
    assert "read-only" not in low, "overstates the guarantee since M0.5"
    assert any(w in low for w in ("notes", "image", "capture"))
    assert "cannot change or delete" in low
    assert "accept" in low


def test_cli_command_pins_the_root_and_quotes_a_spacey_path(tmp_path):
    root = tmp_path / "My Astro Data"
    cmd = cc.cli_add_command(root)
    assert cmd.startswith("claude mcp add m110")
    assert f'M110_DATA_ROOT="{root}"' in cmd


def test_server_available_reports_a_missing_dependency(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name == "mcp":
            raise ModuleNotFoundError("no mcp")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    ok, why = cc.server_available()
    assert ok is False and "m110[assistant]" in why


def test_appimage_config_points_at_the_appimage_not_inside_it(tmp_path, monkeypatch):
    """An AppImage is a self-mounting archive — the internal path exists only
    while it runs, so a client config must target the .AppImage and let AppRun
    dispatch on --mcp."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    appimage = tmp_path / "M110-0.2.0-x86_64.AppImage"
    monkeypatch.setenv("APPIMAGE", str(appimage))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "mnt/usr/bin/M110"))
    assert cc.server_command() == [str(appimage), "--mcp"]


def test_plain_linux_frozen_build_uses_the_sibling_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "M110"))
    assert cc.server_command() == [str(tmp_path / "m110-mcp")]


def test_windows_frozen_build_gets_an_exe_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "M110.exe"))
    assert cc.server_command() == [str(tmp_path / "m110-mcp.exe")]

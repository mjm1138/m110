"""Connecting an external MCP client to this M110 install.

Qt-free on purpose: locating another application's config file, resolving which
server binary *this* install should advertise, and merging JSON without
destroying what's already there are all things that want unit tests. The
Preferences dialog stays a thin widget layer over this.

Editing a config that belongs to another application deserves care, so the
callers are expected to: show the exact JSON first, take an explicit
confirmation, back the file up, read-merge rather than overwrite, and refuse
outright when the existing file doesn't parse.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_KEY = "m110"
BACKUP_SUFFIX = ".m110-backup"

# What connecting actually means, in the user's terms. Surfaced verbatim in the
# confirmation dialog: M110 no longer holds an API key, but the data still
# leaves the machine, and that obligation doesn't go away.
DISCLOSURE = (
    "Connecting a client lets it read your M110 library — object notes, capture "
    "history, and image data — and send that to whatever AI model the client uses. "
    "M110's server is read-only: a client can look, and propose changes, but "
    "cannot alter your library, your files, or your settings."
)


class ClientConfigError(Exception):
    """The client's configuration could not be read or written safely."""


# ── which server command this install should advertise ───────────────────────

def server_command() -> list[str]:
    """The argv an MCP client should spawn to reach *this* install."""
    if getattr(sys, "frozen", False):
        # An AppImage is a self-mounting archive: the path inside it
        # ($APPDIR/usr/bin/m110-mcp) exists only while it's running, so a client
        # config must point at the .AppImage file itself and let AppRun dispatch
        # (see packaging/linux/build_appimage.sh).
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return [appimage, "--mcp"]

        # Elsewhere a frozen build ships m110-mcp beside the GUI binary, from
        # the same PyInstaller COLLECT (see packaging/*/M110.spec).
        exe = Path(sys.executable).with_name("m110-mcp")
        if sys.platform == "win32":
            exe = exe.with_suffix(".exe")
        return [str(exe)]

    # Source install: prefer the console-script if it's on PATH, else run the
    # module with this interpreter (which is guaranteed to have m110 importable).
    found = shutil.which("m110-mcp")
    return [found] if found else [sys.executable, "-m", "m110.assistant.mcp_server"]


def server_available() -> tuple[bool, str]:
    """Whether the server can actually start, and why not if it can't."""
    try:
        import mcp  # noqa: F401
    except ModuleNotFoundError:
        return False, ("The 'mcp' package isn't installed, so the assistant server "
                       "can't run. Install it with:  pip install 'm110[assistant]'")
    cmd = server_command()
    if getattr(sys, "frozen", False) and not Path(cmd[0]).exists():
        return False, (f"The assistant server was not found at {cmd[0]}. This build "
                       "may predate it — check for an M110 update.")
    return True, ""


def server_entry(data_root: Path | None = None) -> dict:
    """The `mcpServers` entry for this install."""
    from m110 import config

    cmd = server_command()
    # Pinning the data root is NOT optional: config resolves it at import time
    # from env -> saved preference -> default, and a client-spawned server
    # inherits none of the running app's state.
    return {"command": cmd[0], "args": cmd[1:],
            "env": {"M110_DATA_ROOT": str(data_root or config.DATA_ROOT)}}


# ── Claude Desktop ───────────────────────────────────────────────────────────

def desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def read_desktop_config(path: Path | None = None) -> dict:
    """Existing config, or {} when absent. Raises rather than clobber a file we
    can't parse — a hand-edited config with a stray comma is not ours to reset."""
    path = path or desktop_config_path()
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ClientConfigError(f"Couldn't read {path}: {exc}") from exc
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ClientConfigError(
            f"{path} isn't valid JSON ({exc}). Fix or remove it first — M110 won't "
            "overwrite a config it can't read."
        ) from exc
    if not isinstance(data, dict):
        raise ClientConfigError(f"{path} doesn't contain a JSON object.")
    return data


def is_connected(path: Path | None = None) -> bool:
    try:
        return SERVER_KEY in (read_desktop_config(path).get("mcpServers") or {})
    except ClientConfigError:
        return False


def merged_desktop_config(existing: dict, data_root: Path | None = None) -> dict:
    """`existing` with our server added or updated — every other server kept."""
    out = dict(existing)
    servers = dict(out.get("mcpServers") or {})
    servers[SERVER_KEY] = server_entry(data_root)
    out["mcpServers"] = servers
    return out


def preview_desktop_json(data_root: Path | None = None) -> str:
    """Just our entry, for the confirmation dialog — showing the user's whole
    config back at them buries the one line that's changing."""
    return json.dumps({"mcpServers": {SERVER_KEY: server_entry(data_root)}}, indent=2)


def write_desktop_config(path: Path | None = None,
                         data_root: Path | None = None) -> tuple[Path, Path | None]:
    """Merge our entry in. Returns (config_path, backup_path_or_None)."""
    path = path or desktop_config_path()
    existing = read_desktop_config(path)          # raises on unparseable

    backup = None
    if path.is_file():
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        try:
            shutil.copy2(path, backup)
        except OSError as exc:
            raise ClientConfigError(f"Couldn't back up {path}: {exc}") from exc

    merged = merged_desktop_config(existing, data_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)                     # atomic; no half-written config
    except OSError as exc:
        raise ClientConfigError(f"Couldn't write {path}: {exc}") from exc
    return path, backup


def remove_from_desktop_config(path: Path | None = None) -> bool:
    """Take our entry back out, leaving every other server alone."""
    path = path or desktop_config_path()
    existing = read_desktop_config(path)
    servers = dict(existing.get("mcpServers") or {})
    if SERVER_KEY not in servers:
        return False
    servers.pop(SERVER_KEY)
    existing["mcpServers"] = servers
    try:
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise ClientConfigError(f"Couldn't write {path}: {exc}") from exc
    return True


# ── Claude Code ──────────────────────────────────────────────────────────────

def cli_add_command(data_root: Path | None = None) -> str:
    """The `claude mcp add` line for Claude Code, which has no config file we
    should be editing — it owns its own scopes and merge rules."""
    from m110 import config

    root = str(data_root or config.DATA_ROOT)
    cmd = " ".join(subprocess.list2cmdline([c]) if " " in c else c
                   for c in server_command())
    return f'claude mcp add m110 --env M110_DATA_ROOT="{root}" -- {cmd}'

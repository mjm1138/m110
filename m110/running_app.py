"""Which M110 install the user is running, so a command can name the matching one.

Two installs often run side by side: an assistant client spawns the bundled MCP
server while the user drives the app from a dev venv, or the other way round. A
command the assistant hands over (`m110-stack … --run`) has to run the build of
the app the user is looking at, not merely the build that happened to answer, and
a bare `m110-stack` is on nobody's PATH (#192).

So the GUI records itself in `~/.m110/running.json` at launch — its pid, its data
root, and the argv of its own `m110-stack` — and removes the record on exit. A
reader trusts the record only while that pid is alive and serves the same data
root, and otherwise falls back to its own install, saying which it chose.

Lives beside `settings.json`, outside the data root: it describes this machine's
processes, not the library, and must never be backed up or published.
"""
from __future__ import annotations

import atexit
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from m110 import config

RECORD_NAME = "running.json"


def _record_path() -> Path:
    # Read at call time: the test seal repoints `config.APP_CONFIG_DIR`.
    return config.APP_CONFIG_DIR / RECORD_NAME


def install_kind() -> str:
    """"installed app" for a frozen build, else "development environment"."""
    return "installed app" if getattr(sys, "frozen", False) else "development environment"


def _version() -> str:
    from m110 import updates
    return updates.current_version()


def stack_command() -> list[str]:
    """The argv that runs *this* install's `m110-stack`.

    Mirrors `client_config.server_command`: a frozen build ships the helper beside
    its own executable (an AppImage dispatches it via `--stack`, since the path
    inside the mount exists only while it runs). From source, the console script
    sits beside the interpreter in the venv's `bin/` — preferred over PATH, which
    may well be a different install. `sys.executable` is deliberately not
    resolved: a venv's `python` is a symlink to the base interpreter, whose
    directory holds no `m110-stack`.
    """
    exe_name = "m110-stack.exe" if sys.platform == "win32" else "m110-stack"
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return [appimage, "--stack"]
        return [str(Path(sys.executable).with_name(exe_name))]

    sibling = Path(sys.executable).with_name(exe_name)
    if sibling.is_file():
        return [str(sibling)]
    found = shutil.which("m110-stack")
    return [found] if found else [sys.executable, "-m", "m110.stacking"]


# ── the record ──────────────────────────────────────────────────────────────

def record() -> None:
    """Note this process as the running app; removed again at interpreter exit.

    Best-effort: a read-only home directory must not stop the app launching, and
    without a record a reader simply falls back to its own install.
    """
    data = {
        "pid": os.getpid(),
        "data_root": str(config.DATA_ROOT),
        "stack_command": stack_command(),
        "install": install_kind(),
        "version": _version(),
    }
    path = _record_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return
    atexit.register(clear)


def clear() -> None:
    """Remove the record — only if it is still this process's (a second window
    launched later owns it now)."""
    path = _record_path()
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
            path.unlink()
    except (OSError, ValueError, AttributeError):
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # Never os.kill here: on Windows any signal but the CTRL events is
        # TerminateProcess.
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) \
                and code.value == 259                  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # exists, owned by someone else
    except OSError:
        return False
    return True


def running_app() -> dict | None:
    """The live app's record, or None if there is none we should trust.

    Stale (the app crashed, so `clear` never ran), malformed, or serving a
    different data root (then it is not the app this request is about) all read
    as no record.
    """
    try:
        data = json.loads(_record_path().read_text(encoding="utf-8"))
        pid = int(data["pid"])
        argv = [str(a) for a in data["stack_command"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not argv or not _pid_alive(pid):
        return None
    if os.path.realpath(data.get("data_root") or "/") != os.path.realpath(config.DATA_ROOT):
        return None
    return {**data, "pid": pid, "stack_command": argv}


# ── what a caller hands to the user ─────────────────────────────────────────

def stacker() -> dict:
    """The `m110-stack` to name, and which install it belongs to.

    `matches_running_app` is False when no app is running for this store (or it
    predates the record) — the command is then this process's own install, and a
    reader should say so, since it may not be the build the user will look at.
    """
    app = running_app()
    if app:
        return {"argv": app["stack_command"], "install": app.get("install", ""),
                "version": app.get("version", ""), "matches_running_app": True}
    return {"argv": stack_command(), "install": install_kind(),
            "version": _version(), "matches_running_app": False}


def shell_command(argv: list[str], *args: str) -> str:
    """`argv + args` as one line a POSIX shell runs as pasted.

    The home directory is written as a leading, unquoted `~` — bash and zsh expand
    it — so a path under it never puts the user's home into a model's context.
    Everything else is `shlex.quote`d (Python's repr is not shell quoting: it
    breaks on `$`, backslashes, and a name holding both quote characters).
    """
    home = str(Path.home())
    words = []
    for word in (*argv, *args):
        if home not in ("", "/") and (word == home or word.startswith(home + os.sep)):
            rest = word[len(home) + 1:]
            words.append("~/" + shlex.quote(rest) if rest else "~")
        else:
            words.append(shlex.quote(word))
    return " ".join(words)

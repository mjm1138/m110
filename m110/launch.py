"""Launch external processing/viewer apps — the guide side of #19 ("Process
in…" / "Open In…"). Qt-free so the engine stays headless/testable; the UI calls
`launch_processing` and catches `LaunchError`.

M110 never *controls* the tool: it starts it (optionally pointed at a working
directory) and gets out of the way. Discovery is settings-override →
OS-standard locations → give up (the UI then falls back to revealing the
folder). Nothing here writes into the content tree.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

# Per-tool `{tool_id: {path}}` overrides the user set in Preferences — a full
# path to the executable, or (macOS) the `.app` bundle, which we resolve to its
# binary. Wins over auto-detection.
APP_PATHS_SETTING = "external_app_paths"


class LaunchError(Exception):
    """Couldn't find or start the tool (surfaced to the user)."""


# Discovery + launch spec per tool id. `workdir_args` is the argv template that
# sets the working directory ({dir} substituted); Siril uses `-d <dir>`.
_TOOLS: dict[str, dict] = {
    "siril": {
        "label": "Siril",
        "macos_app": "Siril.app",
        "macos_bin": "Contents/MacOS/siril",          # inside the .app bundle
        "linux_bins": ["siril", "siril-cli"],          # in PATH
        "windows_names": ["siril.exe"],
        "windows_subpaths": [r"Siril\bin\siril.exe", r"Siril\siril.exe"],
        "workdir_args": ["-d", "{dir}"],
    },
}


def tool_label(tool_id: str) -> str:
    return _TOOLS.get(tool_id, {}).get("label", tool_id)


# ── discovery ────────────────────────────────────────────────────────────────

def _override(tool_id: str) -> str | None:
    """The user-configured path for a tool, resolved to a runnable binary, or
    None if unset/missing."""
    paths = config.get_setting(APP_PATHS_SETTING, {}) or {}
    raw = paths.get(tool_id)
    if not raw:
        return None
    p = Path(raw)
    if not p.exists():
        return None
    return _resolve_bundle(p, tool_id)


def _resolve_bundle(p: Path, tool_id: str) -> str:
    """On macOS a user may point at `Siril.app` (a directory) — resolve it to the
    binary inside. Elsewhere (or a plain file) use the path as given."""
    spec = _TOOLS.get(tool_id, {})
    if sys.platform == "darwin" and p.suffix == ".app" and spec.get("macos_bin"):
        binary = p / spec["macos_bin"]
        if binary.exists():
            return str(binary)
    return str(p)


def _macos_candidates() -> list[Path]:
    home = Path.home()
    return [Path("/Applications"), home / "Applications"]


def _find_macos(spec: dict) -> str | None:
    app = spec.get("macos_app")
    binrel = spec.get("macos_bin")
    if not (app and binrel):
        return None
    for base in _macos_candidates():
        binary = base / app / binrel
        if binary.exists():
            return str(binary)
    return None


def _find_linux(spec: dict) -> str | None:
    for name in spec.get("linux_bins", []):
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_windows(spec: dict) -> str | None:
    for name in spec.get("windows_names", []):
        found = shutil.which(name)
        if found:
            return found
    roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    for root in filter(None, roots):
        for sub in spec.get("windows_subpaths", []):
            cand = Path(root) / sub
            if cand.exists():
                return str(cand)
    return None


def find_app(tool_id: str) -> str | None:
    """Locate a tool's executable: user override → OS-standard locations → None."""
    override = _override(tool_id)
    if override:
        return override
    spec = _TOOLS.get(tool_id)
    if not spec:
        return None
    if sys.platform == "darwin":
        return _find_macos(spec)
    if sys.platform.startswith("win"):
        return _find_windows(spec)
    return _find_linux(spec)


# ── launch ───────────────────────────────────────────────────────────────────

def _spawn(argv: list[str]) -> None:
    """Start the app detached so it outlives M110 and never blocks the UI.
    Isolated for tests to monkeypatch."""
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "posix":
        kwargs["start_new_session"] = True                     # own process group
    else:
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(argv, **kwargs)


def launch_processing(tool_id: str, working_dir) -> str:
    """Open `tool_id` with its working directory set to `working_dir`. Returns
    the launched executable path; raises LaunchError if the tool can't be found
    or fails to start."""
    app = find_app(tool_id)
    if not app:
        raise LaunchError(
            f"Couldn't find {tool_label(tool_id)}. Set its location in "
            f"Preferences → Processing tools.")
    spec = _TOOLS[tool_id]
    args = [a.format(dir=str(working_dir)) for a in spec.get("workdir_args", [])]
    try:
        _spawn([app, *args])
    except OSError as exc:
        raise LaunchError(f"Couldn't start {tool_label(tool_id)}: {exc}") from exc
    return app

"""Stackhammer — a second stacking engine beside the Siril recipe in `stacking.py`.

Stackhammer (https://github.com/mjm1138/stackhammer) is a separate program: a
native macOS binary that takes over the expensive half of stacking from Siril
(applying the registration, drizzle, normalization, rejection, integration) and
adds local normalization. Siril still calibrates and plate-solves. This module
is M110's whole knowledge of it, and that knowledge is deliberately thin:

**M110 mirrors nothing it can read.** The binary describes itself —
`settings --json` gives every option with its value, its choices and *why*;
`prepare --json` gives the Siril commands that turn `lights/` into a
plate-solved sequence, with the calibration it matched; `plan --json` gives the
frames, canvas and depth of a solved sequence. So settings travel through M110
in Stackhammer's own vocabulary (`weight`, `local-norm`, `filter-fwhm`, …) and
are validated against the binary that will run them. A new Stackhammer option
needs no M110 release. The one list kept here is `ADVANCED`: four `run` flags
the binary accepts but does not report.

Read-only: `find_binary`, `settings`, `prepare`, `plan`, `build_plan`,
`read_preset`, `validate`. Writers: `write_preset` (one JSON file, the Siril
script's own preset format, so a window opened in Siril starts on the agreed
settings), `clean` and `execute` (the headless run behind
`m110-stack --engine stackhammer --run`).

Every JSON reader uses `.get`: the contract (schema 5) may grow fields, and two
calibration designs are still converging upstream.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from m110 import launch, roundtrip

TOOL_ID = "stackhammer"
MIN_SCHEMA = 5

PRESET_NAME = "stackhammer_presets.json"
PRESET_FORMAT = 1
RUN_LOG = "stackhammer_run.log"
MAPS_DIR = "stackhammer"            # <job dir>/stackhammer/<name>/: depth, rejection, frames.json

# The Siril script that drives Stackhammer from Siril's Scripts menu. Once
# installed it names the binary it was installed with, which is the best
# evidence of where the user's Stackhammer lives short of asking them.
SIRIL_SCRIPT_NAME = "Stackhammer.py"
SIRIL_SCRIPT_CONFIG = "stackhammer_script.json"
_BINARY_LINE = re.compile(r'^STACKHAMMER_BINARY\s*=\s*(["\'])(.*)\1\s*$', re.M)
CANDIDATES = ("/opt/homebrew/bin/stackhammer", "/usr/local/bin/stackhammer",
              "~/.local/bin/stackhammer")

# The four quality filters decide which frames are kept, so they go to `plan`
# as well as `run`.
FILTERS = ("filter-round", "filter-fwhm", "filter-bkg", "filter-nbstars")
# Where the calibration frames are. Values are paths, relative to the working
# directory when the folder is inside or beside it (the script's convention).
FOLDERS = ("darks", "flats", "biases", "dark-flats")
# `run` flags the binary accepts but `settings --json` does not list. Numbers,
# passed through only when someone set them. The Siril script ignores them in
# a preset (and says so), so they take effect on the headless path only.
ADVANCED = {
    "local-norm-degree": ("Local normalization's polynomial degree. Default 4.", int),
    "local-norm-reference-noise": (
        "Frames noisier than this many times the median frame stay out of local "
        "normalization's reference. Default 1.2.", float),
    "max-frame-residual": (
        "Leave out of the stack a frame whose sky keeps more than this after "
        "local normalization, in its own noise. 0 keeps every frame. Default 1.0.",
        float),
    "rejection-signal-share": (
        "Under frame noise, the share of a pixel's signal above the sky added to "
        "its noise. Default 1.0.", float),
}
# Reported by the binary, but a fact about `process/`, not a choice.
NOT_SETTABLE = {"prepare"}


class StackhammerError(Exception):
    """Stackhammer is missing, too old, or refused — worded for the user."""


# ── finding the binary ──────────────────────────────────────────────────────

def _executable(path) -> str | None:
    if not path:
        return None
    p = Path(os.path.expanduser(str(path)))
    return str(p) if p.is_file() and os.access(p, os.X_OK) else None


def siril_support_dirs() -> list[Path]:
    """Where Siril keeps its scripts and config on this platform."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "org.siril.Siril"]
    return [home / ".local" / "share" / "siril", home / ".config" / "siril"]


def _from_siril_script() -> str | None:
    """The binary named by the Stackhammer script installed in Siril.

    The file is read as text and one assignment is matched — never imported or
    executed: it is another program's source, and it imports `sirilpy`."""
    for base in siril_support_dirs():
        script = base / "scripts" / SIRIL_SCRIPT_NAME
        try:
            m = _BINARY_LINE.search(script.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        found = _executable(m.group(2)) if m else None
        if found:
            return found
    return None


def _from_script_config() -> str | None:
    """The binary the user last located from inside the script's window."""
    for base in siril_support_dirs():
        for cfg in (base / SIRIL_SCRIPT_CONFIG, base / "siril" / SIRIL_SCRIPT_CONFIG):
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            found = _executable(data.get("binary")) if isinstance(data, dict) else None
            if found:
                return found
    return None


# How `find_binary` found it, in words a user reads.
SOURCES = {
    "preferences": "set in M110 → Preferences → Processing tools",
    "siril-script": "named by the Stackhammer script installed in Siril",
    "script-config": "last located from the Stackhammer script's window",
    "standard": "found in a standard install location",
    "path": "found on PATH",
}


def find_binary() -> tuple[str, str] | None:
    """`(path, source)` for the Stackhammer binary, or None.

    Order: the Preferences override; the script installed in Siril (which
    records the binary it was installed with); the path saved from the script's
    window; the usual install places; PATH. The script comes before the usual
    places on purpose: whatever Siril would run is what the user's stacks were
    made with, and a preset written for one build should meet the same build."""
    override = launch.find_app(TOOL_ID)
    if override and _executable(override):
        return override, "preferences"
    for source, look in (("siril-script", _from_siril_script),
                         ("script-config", _from_script_config)):
        found = look()
        if found:
            return found, source
    for cand in CANDIDATES:
        found = _executable(cand)
        if found:
            return found, "standard"
    found = _on_path()
    return (found, "path") if found else None


def _on_path() -> str | None:
    return shutil.which("stackhammer")


NOT_FOUND = (
    "Stackhammer was not found. M110 looked at Preferences → Processing tools, "
    "the Stackhammer script installed in Siril, /opt/homebrew/bin, /usr/local/bin, "
    "~/.local/bin and PATH. Stackhammer is a separate program for Macs with Apple "
    "silicon (https://github.com/mjm1138/stackhammer); once it is built or "
    "installed, set its location in M110 → Preferences → Processing tools.")


def require_binary() -> tuple[str, str]:
    found = find_binary()
    if not found:
        raise StackhammerError(NOT_FOUND)
    return found


# ── talking to the binary (read-only subcommands) ───────────────────────────

def _json_call(binary: str, *args: str, timeout: int = 600) -> dict:
    """Run a read-only subcommand with `--json` and return its object.

    A failure is `Error: <message>` on stderr with nothing on stdout (exit 1), or
    an argument error (exit 64); either way the message is the binary's own."""
    try:
        done = subprocess.run([binary, *args, "--json"], capture_output=True,
                              text=True, timeout=timeout, env=launch._child_env(),
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        raise StackhammerError(f"Couldn't run Stackhammer: {e}") from e
    if done.returncode != 0:
        msg = (done.stderr or done.stdout or "").strip().splitlines()
        text = next((ln for ln in msg if ln.startswith("Error:")), msg[0] if msg else "")
        raise StackhammerError(text.removeprefix("Error:").strip()
                               or f"Stackhammer {args[0]} failed (exit {done.returncode}).")
    try:
        data = json.loads(done.stdout)
    except ValueError as e:
        raise StackhammerError(f"Stackhammer {args[0]} didn't answer in JSON.") from e
    if not isinstance(data, dict):
        raise StackhammerError(f"Stackhammer {args[0]} didn't answer with an object.")
    schema = data.get("schemaVersion")
    if isinstance(schema, int) and schema < MIN_SCHEMA:
        raise StackhammerError(
            f"This Stackhammer is too old for M110 (it speaks schema {schema}; "
            f"M110 needs {MIN_SCHEMA} or later). Build or install a newer one.")
    return data


def settings(binary: str) -> dict:
    """`settings --json`: `run`'s defaults and the preparation's, each with its
    reason. Reads no frames."""
    return _json_call(binary, "settings", timeout=60)


def prepare(binary: str, working: Path, args: list[str] | None = None) -> dict:
    """`prepare --json`: the lights, the calibration matched for them, and the
    Siril commands that make them a plate-solved sequence. Reads headers only."""
    return _json_call(binary, "prepare", str(working), *(args or []))


def plan(binary: str, process: Path, seq: str, args: list[str] | None = None) -> dict:
    """`plan --json` for a plate-solved sequence: which frames the filters keep,
    the canvas, the coverage depth, and the settings `run` would use."""
    return _json_call(binary, "plan", str(process), "--seq", seq, *(args or []))


# ── settings: Stackhammer's vocabulary, checked against the binary ──────────

def entries(data: dict) -> dict[str, dict]:
    """option → its `settings --json` entry, run settings and preparation both."""
    out: dict[str, dict] = {}
    for group in ("settings", "preparation"):
        for entry in data.get(group) or []:
            if isinstance(entry, dict) and entry.get("option"):
                out[entry["option"]] = {**entry, "group": group}
    return out


_TRUE, _FALSE = {"true", "on", "yes", "1"}, {"false", "off", "no", "0"}


def _coerce(option: str, value, like):
    """`value` as the type of `like` (the binary's default), or a ValueError."""
    if isinstance(like, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        raise ValueError(f"{option} is on or off (true/false), not {value!r}")
    if isinstance(like, (int, float)):
        if isinstance(value, bool):
            raise ValueError(f"{option} takes a number, not {value!r}")
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{option} takes a number, not {value!r}") from None
        return int(num) if num.is_integer() else num
    return str(value)


def validate(values: dict, defaults: dict) -> dict:
    """`values` checked and typed against what the binary reports.

    Names must be an option the binary lists, an `ADVANCED` run flag, or a
    calibration folder; a value must have the default's type and, where the
    option has a fixed set of `choices`, be one of them. Raises
    `StackhammerError` naming everything wrong at once."""
    known = entries(defaults)
    out, problems = {}, []
    for option, value in (values or {}).items():
        if option in NOT_SETTABLE:
            problems.append(f"{option} is not a setting: it reports whether process/ "
                            "already holds the plate-solved sequence")
        elif option in FOLDERS:
            out[option] = str(value)
        elif option in ADVANCED:
            try:
                out[option] = _coerce(option, value, ADVANCED[option][1]())
            except ValueError as e:
                problems.append(str(e))
        elif option in known:
            entry = known[option]
            try:
                typed = _coerce(option, value, entry.get("value"))
            except ValueError as e:
                problems.append(str(e))
                continue
            choices = entry.get("choices")
            if choices and typed not in choices:
                problems.append(f"{option} is one of {', '.join(choices)}, not {typed!r}")
                continue
            out[option] = typed
        else:
            problems.append(f"unknown option {option!r}")
    if problems:
        names = sorted(set(known) - NOT_SETTABLE | set(ADVANCED) | set(FOLDERS))
        raise StackhammerError("; ".join(problems) + ". Options this Stackhammer "
                               "knows: " + ", ".join(names) + ".")
    return out


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _flag(option: str, value) -> list[str]:
    """One option as CLI words: a bool is `--opt` / `--no-opt`."""
    if isinstance(value, bool):
        return [f"--{option}" if value else f"--no-{option}"]
    return [f"--{option}", _fmt(value)]


def prepare_args(chosen: dict) -> list[str]:
    """`prepare`'s flags for the settings someone chose (a preset or an override).

    Only what was chosen is passed, as the Siril script does: unset, background
    extraction follows what `process/` already holds, and that default is the
    binary's to make."""
    args: list[str] = []
    if chosen.get("drizzle") is True:
        args.append("--drizzle")
    if isinstance(chosen.get("background"), bool):
        args.append("--background" if chosen["background"] else "--no-background")
    if chosen.get("compress") is True:
        args.append("--compress")
    for option in ("calibration", "cosmetic", "equalize-cfa"):
        if chosen.get(option) is False:
            args.append(f"--no-{option}")
    if chosen.get("bias-level"):
        args += ["--bias-level", _fmt(chosen["bias-level"])]
    for option in FOLDERS:
        if chosen.get(option):
            args += [f"--{option}", str(chosen[option])]
    return args


def filter_args(chosen: dict) -> list[str]:
    return [a for f in FILTERS if f in chosen for a in _flag(f, chosen[f])]


def run_args(proposed: list[dict], chosen: dict) -> list[str]:
    """`run`'s flags: **every** setting the plan lists, spelled out, with the
    chosen values over the proposed ones — so the run never depends on a default
    this build of M110 and that build of Stackhammer might not share."""
    args: list[str] = []
    for entry in proposed or []:
        option = entry.get("option")
        if not option:
            continue
        args += _flag(option, chosen.get(option, entry.get("value")))
    for option in ADVANCED:
        if option in chosen:
            args += _flag(option, chosen[option])
    return args


# ── presets: the Siril script's own file ────────────────────────────────────

def preset_path(job_dir: Path) -> Path:
    return Path(job_dir) / "presets" / PRESET_NAME


def read_preset(job_dir: Path) -> dict | None:
    """The settings in `<job dir>/presets/stackhammer_presets.json`, or None when
    there is no preset or it is not one (wrong format marker, no settings)."""
    try:
        data = json.loads(preset_path(job_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("stackhammer_preset") != PRESET_FORMAT:
        return None
    found = data.get("settings")
    return dict(found) if isinstance(found, dict) else None


def preset_text(values: dict) -> str:
    """The file's bytes for `values`, as the script itself would write them."""
    data = {"stackhammer_preset": PRESET_FORMAT, "script": "m110",
            "settings": {k: v for k, v in values.items() if k not in NOT_SETTABLE}}
    return json.dumps(data, indent=4, sort_keys=True) + "\n"


def write_preset(job_dir: Path, values: dict) -> dict:
    """THE WRITER for a Stackhammer preset. Writes `values` to the job folder's
    preset, moving a different existing one into `presets/archive/` first (the
    same keep-both rule as the Naztronomy preset). Returns
    `{path, archived, changed}`. The caller has confirmed with the user, and has
    passed `roundtrip.require_idle` where a stack might be running."""
    from m110 import siril as siril_mod

    path = preset_path(job_dir)
    text = preset_text(values)
    try:
        if path.read_text(encoding="utf-8") == text:
            return {"path": path, "archived": None, "changed": False}
    except OSError:
        pass
    archived = siril_mod.archive_preset(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)
    return {"path": path, "archived": archived, "changed": True}


# ── the plan: read-only ─────────────────────────────────────────────────────

@dataclass
class StackhammerPlan:
    binary: str
    source: str                         # a key of SOURCES
    working: Path
    defaults: dict                      # settings --json
    preset: dict | None                 # what the job folder's preset holds
    overrides: dict                     # validated, this call's
    chosen: dict                        # preset ← overrides: what was decided
    ignored: list[str]                  # preset keys this binary doesn't know
    prepare: dict
    solved: dict | None = None          # plan --json, when a solved sequence exists
    solved_note: str = ""
    used_preset: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def process(self) -> Path:
        return Path(self.prepare.get("processDirectory") or self.working / "process")

    @property
    def sequence(self) -> str:
        return self.prepare.get("sequence") or "pp_lights_"

    def needs_preprocessing(self) -> bool:
        """True unless `process/` already holds the plate-solved sequence."""
        entry = next((s for s in self.prepare.get("settings") or []
                      if s.get("option") == "prepare"), {})
        return entry.get("value") is not False

    def settings(self) -> list[dict]:
        """Every option, in the binary's order: its value here, the binary's
        proposal, its choices, why, and who decided — `default` (the binary),
        `preset` (the job folder's file) or `override` (this call)."""
        rows: dict[str, dict] = {}
        for option, entry in entries(self.defaults).items():
            rows[option] = dict(entry)
        # A plan of real frames knows more than the frameless defaults (drizzle
        # is required for CFA frames), and `prepare` knows the preparation.
        for source in ((self.solved or {}).get("settings") or [],
                       self.prepare.get("settings") or []):
            for entry in source:
                if isinstance(entry, dict) and entry.get("option") in rows:
                    rows[entry["option"]].update(entry)
        out = []
        for option, entry in rows.items():
            proposed = entry.get("value")
            row = {"option": option, "value": proposed, "proposed": proposed,
                   "why": entry.get("why", ""), "group": entry.get("group"),
                   "source": "default"}
            if entry.get("choices"):
                row["choices"] = entry["choices"]
            if option in NOT_SETTABLE:
                row["source"] = "state"
            elif option in self.chosen:
                row["value"] = self.chosen[option]
                row["source"] = "override" if option in self.overrides else "preset"
            out.append(row)
        for option in (*ADVANCED, *FOLDERS):
            if option in self.chosen:
                why = (ADVANCED[option][0] if option in ADVANCED else
                       "where these calibration frames are, instead of the folder "
                       "beside the lights")
                out.append({"option": option, "value": self.chosen[option],
                            "proposed": None, "why": why,
                            "group": "advanced" if option in ADVANCED else "folders",
                            "source": "override" if option in self.overrides else "preset"})
        return out

    def warnings(self) -> list[str]:
        return [*(self.prepare.get("warnings") or []),
                *((self.solved or {}).get("warnings") or [])]

    def as_json(self) -> dict:
        prep, cal = self.prepare, self.prepare.get("calibration") or {}
        return {
            "engine": "stackhammer",
            "binary": {"source": self.source, "found": SOURCES.get(self.source, self.source),
                       "schema": self.defaults.get("schemaVersion")},
            "working_dir": self.working,
            "lights": prep.get("lights") or {},
            "calibration": {"applied": cal.get("applied"),
                            "applicable": cal.get("applicable"),
                            "summary": cal.get("summary") or [],
                            "subsets": cal.get("subsets") or [],
                            "folders": [{k: v for k, v in f.items() if k != "sets"}
                                        for f in cal.get("folders") or []]},
            "needs_preprocessing": self.needs_preprocessing(),
            "sequence": self.sequence,
            "existing_sequences": prep.get("existing") or [],
            "siril_steps": [{"name": s.get("name"), "why": s.get("why"),
                             "commands": s.get("commands") or []}
                            for s in prep.get("steps") or []],
            "solved": _solved_summary(self.solved),
            "solved_note": self.solved_note,
            "settings": self.settings(),
            "preset": {"exists": self.preset is not None, "used": self.used_preset,
                       "settings": self.preset or {}, "ignored": self.ignored},
            "overrides_applied": dict(self.overrides),
            "warnings": self.warnings(),
            "notes": [*self.notes, *((self.solved or {}).get("notes") or [])],
        }


def _solved_summary(solved: dict | None) -> dict | None:
    """`plan --json` without its per-frame lists: counts instead of the frame
    numbers, which on a mosaic are hundreds of integers nobody reads."""
    if not solved:
        return None
    sel = dict(solved.get("selection") or {})
    kept = sel.pop("kept", None) or []
    sel["kept"] = len(kept)
    frames = dict(solved.get("keptFrames") or {})
    for key in ("withoutWCS", "withoutDistortion", "unreadable"):
        frames[key] = len(frames.get(key) or [])
    return {"sequence": (solved.get("sequence") or {}).get("name"),
            "selection": sel, "kept_frames": frames,
            "framing": solved.get("framing")}


def _split_preset(preset: dict | None, defaults: dict) -> tuple[dict, list[str]]:
    """A preset's settings this binary knows, typed, and the names it doesn't —
    ignored and reported, never fatal: a preset outlives the build that wrote it."""
    known, ignored = {}, []
    for option, value in (preset or {}).items():
        try:
            known.update(validate({option: value}, defaults))
        except StackhammerError:
            ignored.append(option)
    return known, sorted(ignored)


def build_plan(directory, overrides: dict | None = None, *,
               use_preset: bool = True) -> StackhammerPlan:
    """Measure and propose; write nothing.

    `directory` is what `m110-stack` takes: a working directory, a capture
    folder's name, or `<target>/<FILTER>`. The settings are the binary's
    defaults, then the job folder's preset, then `overrides` — so the Siril
    script and the headless run stack the same folder the same way."""
    from m110 import stacking

    binary, source = require_binary()
    try:
        working, _lights = stacking.resolve_layout(stacking.resolve_input(directory))
    except stacking.StackingError as e:
        raise StackhammerError(str(e)) from e

    defaults = settings(binary)
    preset = read_preset(working) if use_preset else None
    from_preset, ignored = _split_preset(preset, defaults)
    typed = validate(overrides or {}, defaults)
    chosen = {**from_preset, **typed}

    prep = prepare(binary, working, prepare_args(chosen))
    out = StackhammerPlan(binary=binary, source=source, working=working,
                          defaults=defaults, preset=preset, overrides=typed,
                          chosen=chosen, ignored=ignored, prepare=prep,
                          used_preset=use_preset)

    from m110 import siril as siril_mod
    group = siril_mod.job_group(working)
    if group:
        out.notes.append(
            "M110 split this filter into several job folders because its lights "
            f"need different calibration ({', '.join(group)}). Stackhammer is "
            "planned and run one folder at a time here; m110-stack's Siril engine "
            "stacks the group together.")

    seq_file = out.process / f"{out.sequence}.seq"
    if out.needs_preprocessing() or not seq_file.exists():
        out.solved_note = (
            "No plate-solved sequence yet, so which frames the filters keep, the "
            "canvas and the coverage depth are not known: Stackhammer measures "
            "them from Siril's plate solve. A run preprocesses first, then plans.")
    else:
        try:
            out.solved = plan(binary, out.process, out.sequence, filter_args(chosen))
        except StackhammerError as e:
            out.solved_note = f"The sequence in process/ could not be planned: {e}"
    return out


def format_report(p: StackhammerPlan) -> str:
    """The proposal as text, for `m110-stack --engine stackhammer`."""
    lights = p.prepare.get("lights") or {}
    lines = [f"Stackhammer ({SOURCES.get(p.source, p.source)})", f"  {p.binary}",
             f"Working directory: {p.working}", ""]
    exposures = ", ".join(f"{e.get('frames')} × {e.get('seconds'):g} s"
                          for e in lights.get("exposures") or [])
    lines.append(f"Lights: {lights.get('frames', 0)} ({exposures}); "
                 f"{(lights.get('liveTimeSeconds') or 0) / 3600:.1f} h")
    if lights.get("instruments"):
        lines.append(f"Camera: {', '.join(lights['instruments'])}")
    for line in (p.prepare.get("calibration") or {}).get("summary") or []:
        lines.append(f"Calibration: {line}")
    if p.solved:
        s = _solved_summary(p.solved)
        sel, fr = s["selection"], s.get("framing") or {}
        lines.append(f"Sequence {s['sequence']}: {sel.get('total')} frames, "
                     f"{sel.get('kept')} kept by the filters")
        if fr:
            lines.append(f"Canvas {fr.get('width')}×{fr.get('height')}, "
                         f"{100 * (fr.get('coveredFraction') or 0):.0f}% covered; depth "
                         f"median {fr.get('medianDepth')}, maximum {fr.get('maximumDepth')}")
    else:
        lines.append(p.solved_note)
    for w in p.warnings():
        lines.append(f"Warning: {w}")
    for n in p.as_json()["notes"]:
        lines.append(f"Note: {n}")
    if p.preset is not None and p.used_preset:
        lines.append(f"Preset: presets/{PRESET_NAME} applied"
                     + (f" (ignored: {', '.join(p.ignored)})" if p.ignored else ""))
    lines += ["", "Settings:"]
    for row in p.settings():
        mark = {"override": "*", "preset": "+"}.get(row["source"], " ")
        # A reason describes the value Stackhammer proposed, so beside a changed
        # value it would read as an argument for the change.
        why = (row["why"] if row["value"] == row["proposed"] or row["proposed"] is None
               else f"(Stackhammer proposes {_fmt(row['proposed'])}: {row['why']})")
        lines.append(f" {mark} {row['option']:<22} {_fmt(row['value']):<12} {why}")
    lines.append("   (* set on the command line, + from the preset)")
    lines += ["", "Siril steps:"]
    for step in p.prepare.get("steps") or []:
        lines.append(f"  {step.get('name')}: {step.get('why')}")
        lines += [f"      {c}" for c in step.get("commands") or []]
    return "\n".join(lines)


# ── running: the writers ────────────────────────────────────────────────────

def clean(binary: str, working: Path) -> dict:
    """`stackhammer clean`: delete the recipe's own intermediates in `process/`
    (links and files named for its sequences; a link goes, never its target)."""
    return _json_call(binary, "clean", str(working))


def link_order(text: str) -> list[str]:
    """The source files' names in the order Siril's `link` numbered them, from
    its conversion list: one `'<source>' -> '<frame>'` per line."""
    names = []
    for line in text.splitlines():
        source, arrow, _ = line.partition("' -> '")
        if arrow and source.startswith("'"):
            names.append(os.path.basename(source[1:]))
    return names


def link_mismatch(check: dict, process: Path) -> str | None:
    """Why a step's `check` fails, or None. `prepare` selects frames by number
    (a mixed set of lights, one dark set of several), so Siril must have
    numbered the linked files the way the binary assumed."""
    name = check.get("file") or ""
    try:
        found = link_order((Path(process) / name).read_text(encoding="utf-8",
                                                            errors="replace"))
    except OSError as e:
        return f"Siril's list of linked files, {name}, can't be read ({e.strerror or e})"
    expected = list(check.get("names") or [])
    if found == expected:
        return None
    if len(found) != len(expected):
        return f"Siril linked {len(found)} files where {len(expected)} were expected"
    first = next(i for i, (a, b) in enumerate(zip(found, expected)) if a != b)
    return (f"Siril numbered the files in another order: frame {first + 1} is "
            f"{found[first]}, not {expected[first]}")


def step_script(step: dict, process: Path, first: bool, compress: bool) -> str:
    """One `prepare` step as a Siril script for its own `siril-cli` run.

    Each step is a separate run so a `check` can be verified before the next
    command, and so a plate solve that ends in an error doesn't take the steps
    before it down. Every step after the first assumes Siril is in `process/`
    (the Siril script keeps one session; we don't), hence the `cd`.

    `setcompress` persists across Siril runs, and `prepare` only ever turns it
    on, so a compressed earlier session would leak `.fz` intermediates into this
    one: with compression off, the first step says so."""
    lines = ["requires 1.4.0"]
    if first and not compress:
        lines.append("setcompress 0")
    if not first:
        lines.append(f'cd "{process}"')
    return "\n".join([*lines, *(step.get("commands") or [])]) + "\n"


def _printer(line: str) -> None:
    print(line, flush=True)


def run_stack(binary: str, process: Path, seq: str, output: Path, args: list[str],
              log_path: Path, heartbeat: int, on_line=None, on_raw=None) -> dict:
    """`stackhammer run --json`: returns its last event — `result`, `error` or
    `cancelled` (plus `returncode`). Every event line goes to `log_path`; a
    heartbeat reports the stage and the share of the run done. Ctrl-C is passed
    on as SIGINT, which the binary honours by writing nothing."""
    import threading

    cmd = [binary, "run", str(process), "--seq", seq, "--output", str(output),
           "--json", *args]
    t0 = time.monotonic()
    state = {"stage": "starting", "fraction": 0.0, "last": {}}
    beat = {"stage": None, "at": 0.0}
    lock = threading.Lock()

    def stamp(t):
        return f"{int(t) // 60:3d}:{int(t) % 60:02d}"

    def announce(now):                          # caller holds `lock`
        if on_line:
            on_line(f"  [{stamp(now - t0)}] {state['stage']}  "
                    f"({100 * state['fraction']:.0f}% of the stack)")
        beat["stage"], beat["at"] = state["stage"], now

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env=launch._child_env(),
                            encoding="utf-8", errors="replace")

    def reader():
        with open(log_path, "w", buffering=1, encoding="utf-8") as log:
            log.write(launch_line(cmd) + "\n")
            for line in proc.stdout:
                log.write(line)
                try:
                    event = json.loads(line)
                except ValueError:
                    event = None
                if on_raw:
                    on_raw(line.rstrip())
                if not isinstance(event, dict) or "event" not in event:
                    continue
                with lock:
                    kind = event["event"]
                    if kind in ("stage", "progress"):
                        state["stage"] = event.get("stage") or state["stage"]
                        state["fraction"] = event.get("fraction") or state["fraction"]
                    elif kind in ("result", "error", "cancelled"):
                        state["last"] = event

    reading = threading.Thread(target=reader, daemon=True)
    reading.start()
    try:
        while proc.poll() is None:
            time.sleep(1)
            now = time.monotonic()
            with lock:
                if state["stage"] != beat["stage"] or now - beat["at"] >= heartbeat:
                    announce(now)
    except KeyboardInterrupt:
        # The binary checks between chunks and bands; give it the same 15 s the
        # Siril script does before insisting.
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    reading.join(timeout=5)
    last = dict(state["last"]) or {"event": "error",
                                   "message": "Stackhammer ended without a result."}
    last["returncode"] = proc.returncode
    return last


def launch_line(cmd: list[str]) -> str:
    import shlex
    return " ".join(shlex.quote(c) for c in cmd)


def execute(p: StackhammerPlan, siril: str, *, verbose: int = 0,
            heartbeat: int | None = None, restack: bool = False,
            keep_process: bool = False, handoff: str | None = None,
            mark=lambda phase: None) -> int:
    """The `--run` half: Siril's preprocessing from `prepare`'s commands, then
    `stackhammer run`, then cleanup and the optional hand-off. Returns an exit
    status. `mark(phase)` updates the run marker (`roundtrip.write_run_marker`).

    Mirrors `stacking._execute` in what it promises: scratch from an earlier run
    is cleared first unless `restack`, nothing is cleaned after a failure, and
    the lights are never written."""
    from m110 import stacking

    working = p.working
    beat, stream = stacking.resolve_verbosity(verbose, heartbeat)
    on_raw = _printer if stream else None
    print(f"\nRunning Stackhammer in {working}")
    print(f"Reporting the current stage every {beat}s"
          + (", with full output" if stream else " (-v, -vv, -vvv for more)")
          + ".\n", flush=True)

    if restack:
        if p.needs_preprocessing():
            print("--restack reuses the plate-solved sequence in process/, and "
                  f"there is no {p.sequence} there. Run without --restack.",
                  file=sys.stderr)
            return 2
        print(f"  --restack: reusing {p.sequence} in process/\n", flush=True)
    else:
        if p.prepare.get("existing"):
            # Siril won't overwrite a sequence, so an earlier run's would be
            # reused, carrying that run's frame selection.
            removed = clean(p.binary, working)
            freed = (removed.get("bytes") or 0) / 1024**2
            print(f"  Cleared {freed:.0f} MB of an earlier run's intermediates from "
                  "process/ (--restack reuses them on purpose).\n", flush=True)
            # `prepare` reads process/ (background extraction follows what is
            # there), so the recipe is asked for again now that it is empty.
            p.prepare = prepare(p.binary, working, prepare_args(p.chosen))

        mark("solve")
        compress = bool(next((s.get("value") for s in p.prepare.get("settings") or []
                              if s.get("option") == "compress"), False))
        steps = p.prepare.get("steps") or []
        for i, step in enumerate(steps):
            name = step.get("name") or f"step {i + 1}"
            log = working / f"stackhammer_siril_{i + 1}_{name.replace(' ', '_')}.log"
            print(f"  Siril: {name}", flush=True)
            rc, _errors = stacking.run_siril(
                siril, working, step_script(step, p.process, i == 0, compress),
                log, beat, on_line=_printer, on_raw=on_raw)
            if rc != 0:
                if name == "plate solve":
                    # Siril ends a plate solve in an error when some frames don't
                    # solve, with the registration already written. The plan
                    # decides: unsolved frames are left out, and a plan with
                    # nothing to stack ends the run.
                    print("  Plate solving ended with an error; carrying on with "
                          f"the frames that solved. Log: {log}\n", flush=True)
                else:
                    print(f"\nSiril's {name} step failed (exit {rc}). Log: {log}\n")
                    return 1
            if step.get("check"):
                why = link_mismatch(step["check"], p.process)
                if why:
                    print(f"\nStopped before calibrating: {why}. The frames are "
                          "selected by number, so stacking on would calibrate the "
                          "wrong ones. Nothing was stacked.\n")
                    return 1

    mark("stack")
    try:
        p.solved = plan(p.binary, p.process, p.sequence, filter_args(p.chosen))
    except StackhammerError as e:
        print(f"\nNothing to stack: {e}\n")
        return 1
    s = _solved_summary(p.solved)
    fr = s.get("framing") or {}
    print(f"  Stacking {s['selection'].get('kept')} of {s['selection'].get('total')} "
          f"frames onto {fr.get('width')}×{fr.get('height')}, median depth "
          f"{fr.get('medianDepth')}.", flush=True)
    for w in p.solved.get("warnings") or []:
        print(f"  ! {w}", flush=True)

    log_path = working / RUN_LOG
    print(f"  Live log: {log_path}\n", flush=True)
    last = run_stack(p.binary, p.process, p.sequence, working,
                     run_args(p.solved.get("settings"), p.chosen),
                     log_path, beat, on_line=_printer, on_raw=on_raw)
    if last.get("event") == "cancelled":
        print("\nCancelled. Stackhammer wrote nothing; process/ is kept, so "
              "--restack picks up from the plate-solved sequence.\n")
        return 130
    if last.get("event") != "result" or not last.get("path"):
        print(f"\nFAILED: {last.get('message') or 'see the log'}. Log: {log_path}\n")
        return 1

    result = Path(last["path"])
    print()
    for line in last.get("summary") or []:
        print(f"  {line}")
    print(f"Stacked: {result}")
    left = last.get("leftOut") or []
    if left:
        print(f"         {len(left)} frame(s) left out by local normalization "
              "(--set max-frame-residual=0 keeps every frame)")

    if handoff:
        try:
            dest = stacking.apply_handoff(result, handoff)
            print(f"Handed to {handoff}: {dest}")
        except stacking.StackingError as e:
            print(f"  ! handoff skipped: {e}")

    wants_clean = next((r["value"] for r in p.settings() if r["option"] == "clean"), True)
    if keep_process or not wants_clean:
        print(f"Kept:    {p.process}")
    else:
        removed = clean(p.binary, working)
        print(f"Cleaned: {p.process}  "
              f"({(removed.get('bytes') or 0) / 1024**3:.1f} GB freed)")
    print()
    return 0


# ── the CLI: `m110-stack <target> --engine stackhammer` ─────────────────────

def parse_sets(pairs: list[str] | None) -> dict:
    """`--set key=value` words as a dict of strings (typed later, by `validate`)."""
    out = {}
    for pair in pairs or []:
        key, eq, value = pair.partition("=")
        if not eq or not key.strip():
            raise StackhammerError(f"--set takes KEY=VALUE, not {pair!r} "
                                   "(e.g. --set weight=noise --set drizzle=true)")
        out[key.strip().removeprefix("--")] = value.strip()
    return out


def cli(a) -> int:
    """Entry from `stacking.main` once `--engine stackhammer` is chosen. `a` is
    its parsed arguments."""
    from m110 import stacking

    try:
        p = build_plan(a.directory, parse_sets(a.set), use_preset=not a.no_preset)
    except StackhammerError as e:
        print(f"{e}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(p.as_json(), indent=2, default=str))
        return 0
    print(format_report(p))
    if not a.run:
        print("\nProposal only — nothing written. Re-run with --run to execute.\n")
        return 0

    try:
        siril = os.environ.get("SIRIL_CLI") or stacking.require_siril()
    except stacking.StackingError as e:
        print(f"{e}", file=sys.stderr)
        return 2
    other = roundtrip.stack_in_progress(p.working)
    if other:
        print(roundtrip.describe_runs([other]) + " Not starting a second run in "
              "the same folder: it would clear that run's scratch.", file=sys.stderr)
        return 2
    started = time.time()
    try:
        roundtrip.write_run_marker(p.working, "starting", started)
        return execute(p, siril, verbose=a.verbose, heartbeat=a.heartbeat,
                       restack=a.restack, keep_process=a.keep_process,
                       handoff=a.handoff,
                       mark=lambda ph: roundtrip.write_run_marker(p.working, ph, started))
    except StackhammerError as e:
        print(f"\nFAILED: {e}\n", file=sys.stderr)
        return 1
    finally:
        roundtrip.clear_run_marker(p.working)

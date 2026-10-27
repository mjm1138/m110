"""Integration goals — how many minutes an object needs, per telescope model (#184).

The **default** goal is the object type's deep-stack threshold
(`build_derived.deep_threshold`, calibrated on an S50) scaled by the telescope's
speed: ``(f_model / f_S50)²``, so a faster f-ratio needs proportionally less time.
The user can **override** it for one object on one model ("M77 on the S50 needs
420 min"), with an optional one-line reason so the number keeps its justification.

Goals are keyed by **telescope model** — `devices.effective_preset` (``seestar_s50``,
``dwarf_3``, …) — so several units of one model pool their minutes. A telescope no
preset describes is its own model under its device key, and its optics (if the user
entered them on the Devices page) come from ``devices.toml``.

Stored in `.m110_internal_data/integration_goals.toml`:

    [goals."m77"]
    seestar_s50 = { min = 420, reason = "outer disk SNR ~5–7 per 12″" }

Stable per-store prefs like `pins.toml`: survives derived-data regeneration, lazily
created (absence = no overrides), a malformed file reads as empty. Qt-free.
"""
from __future__ import annotations

import tomllib

from . import config

REFERENCE_MODEL = "seestar_s50"     # the telescope DEEP_MIN_BY_TYPE was calibrated on
INITIAL_SHARE = 0.25                # below this share of the goal an object reads "Initial"
DEFAULT_ROUND_MIN = 5               # default goals round to this many minutes

INITIAL, IN_PROGRESS, DEEP = "initial", "in_progress", "deep_stack"
STATE_RANK = {INITIAL: 0, IN_PROGRESS: 1, DEEP: 2}
SOURCE_USER, SOURCE_DEFAULT = "user", "default"


# ── storage ──────────────────────────────────────────────────────────────────

def load() -> dict[str, dict[str, dict]]:
    """``{slug: {model: {"min": float, "reason"?: str}}}`` for the current store,
    tolerant of absence / a malformed file (→ empty). Non-positive minutes are
    dropped."""
    path = config.INTEGRATION_GOALS_TOML
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, dict[str, dict]] = {}
    table = data.get("goals", {})
    if not isinstance(table, dict):
        return {}
    for slug, per_model in table.items():
        if not isinstance(per_model, dict):
            continue
        clean = {}
        for model, entry in per_model.items():
            if not isinstance(entry, dict):
                continue
            minutes = entry.get("min")
            if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) \
                    or minutes <= 0:
                continue
            item = {"min": float(minutes)}
            reason = entry.get("reason")
            if isinstance(reason, str) and reason.strip():
                item["reason"] = reason.strip()
            clean[str(model)] = item
        if clean:
            out[str(slug)] = clean
    return out


def set_goal(slug: str, model: str, minutes: float, reason: str | None = None) -> None:
    """Set `slug`'s goal on `model` to `minutes` (with an optional reason).
    Non-positive minutes clear it. Rewrites the file, keeping every other goal."""
    if not minutes or minutes <= 0:
        clear_goal(slug, model)
        return
    goals = load()
    item = {"min": float(minutes)}
    if reason and reason.strip():
        item["reason"] = reason.strip()
    goals.setdefault(slug, {})[model] = item
    _write(goals)


def clear_goal(slug: str, model: str) -> None:
    """Drop `slug`'s goal on `model`, so the default applies again. Idempotent."""
    goals = load()
    if model in goals.get(slug, {}):
        del goals[slug][model]
        if not goals[slug]:
            del goals[slug]
        _write(goals)


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _write(goals: dict[str, dict[str, dict]]) -> None:
    lines = ["# Integration goals per object and telescope model (object detail pane).",
             "# min = minutes of captured integration; the type default applies when unset.",
             ""]
    for slug in sorted(goals):
        if not goals[slug]:
            continue
        lines.append(f"[goals.{_q(slug)}]")
        for model in sorted(goals[slug]):
            item = goals[slug][model]
            fields = [f"min = {_num(item['min'])}"]
            if item.get("reason"):
                fields.append(f"reason = {_q(item['reason'])}")
            lines.append(f"{_q(model)} = {{ {', '.join(fields)} }}")
        lines.append("")
    path = config.INTEGRATION_GOALS_TOML
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ── models and their speed ───────────────────────────────────────────────────

def model_key(device_key: str | None, registry: dict | None = None) -> str:
    """The telescope model a device belongs to: its preset, else the device key
    itself (so an unrecognised telescope is a model of one). ``"unknown"`` for a
    session with no TELESCOP."""
    from . import devices
    return devices.effective_preset(device_key, registry) or devices.folder_name(device_key)


def model_label(model: str, registry: dict | None = None) -> str:
    """What the UI calls a model: the preset's name, else the device's label."""
    from . import devices
    from .planning_config import DEVICE_PRESETS
    if model in DEVICE_PRESETS:
        return DEVICE_PRESETS[model].name
    return devices.label(model, registry)


def f_ratio(model: str, registry: dict | None = None) -> float | None:
    """The model's focal ratio: the preset's optics, else the optics the user entered
    for that telescope on the Devices page. None when not known."""
    from . import devices
    from .planning_config import DEVICE_PRESETS
    if model in DEVICE_PRESETS:
        return DEVICE_PRESETS[model].f_ratio
    reg = devices.load_registry() if registry is None else registry
    optics = reg.get(model, {}).get("optics", {})
    ap, fl = optics.get("aperture_mm"), optics.get("focal_length_mm")
    return fl / ap if ap and fl else None


def speed_factor(model: str, registry: dict | None = None) -> tuple[float, bool]:
    """``(factor, calibrated)``: how much integration this model needs relative to
    the reference S50 for the same depth, ``(f_model / f_S50)²``. A model whose
    f-ratio is unknown gets 1.0 and ``calibrated=False``."""
    from .planning_config import DEVICE_PRESETS
    ref = DEVICE_PRESETS[REFERENCE_MODEL].f_ratio
    f = f_ratio(model, registry)
    if not f or not ref:
        return 1.0, False
    return (f / ref) ** 2, True


def default_goal(obj_type: str | None, model: str, registry: dict | None = None) -> float:
    """The type threshold scaled by the model's speed, rounded to
    :data:`DEFAULT_ROUND_MIN` minutes (never below it)."""
    from .build_derived import deep_threshold
    factor, _ = speed_factor(model, registry)
    raw = deep_threshold(obj_type) * factor
    return float(max(DEFAULT_ROUND_MIN, DEFAULT_ROUND_MIN * round(raw / DEFAULT_ROUND_MIN)))


def resolve(slug: str, obj_type: str | None, model: str, goals: dict | None = None,
            registry: dict | None = None) -> tuple[float, str]:
    """``(minutes, source)`` for `slug` on `model`: the user's goal when set
    (``"user"``), else the model's default for the type (``"default"``)."""
    goals = load() if goals is None else goals
    item = goals.get(slug, {}).get(model)
    if item:
        return item["min"], SOURCE_USER
    return default_goal(obj_type, model, registry), SOURCE_DEFAULT


# ── progress ─────────────────────────────────────────────────────────────────

def fraction(integration_min: float, goal_min: float) -> float:
    """Share of the goal reached, 0..1."""
    if not goal_min or goal_min <= 0:
        return 1.0
    return max(0.0, min(1.0, (integration_min or 0.0) / goal_min))


def state(integration_min: float, goal_min: float) -> str:
    """``deep_stack`` at the goal, ``in_progress`` from :data:`INITIAL_SHARE` of it,
    else ``initial``."""
    if (integration_min or 0.0) >= goal_min:
        return DEEP
    return IN_PROGRESS if fraction(integration_min, goal_min) >= INITIAL_SHARE else INITIAL


def rollup(by_model: dict[str, dict]) -> tuple[str, dict] | None:
    """The most advanced ``(model, entry)`` of a ``by_model`` map — highest state,
    then highest fraction, then model key for a stable tie-break. None when empty."""
    if not by_model:
        return None
    model = min(by_model, key=lambda m: (-STATE_RANK.get(by_model[m].get("status"), -1),
                                         -by_model[m].get("fraction", 0.0), m))
    return model, by_model[model]


def progress_lines(by_model: dict[str, dict], registry: dict | None = None) -> list[str]:
    """One human line per model of a ``by_model`` map, most advanced first —
    "ZWO Seestar S50: 208 of 420 min (50%, your goal)". For tooltips and summaries."""
    from . import devices
    reg = devices.load_registry() if registry is None else registry
    order = sorted(by_model, key=lambda m: (-STATE_RANK.get(by_model[m].get("status"), -1),
                                            -by_model[m].get("fraction", 0.0), m))
    lines = []
    for m in order:
        e = by_model[m]
        whose = "your goal" if e.get("goal_source") == SOURCE_USER else "default goal"
        lines.append(f"{model_label(m, reg)}: {e.get('integration_min', 0):.0f} of "
                     f"{e.get('goal_min', 0):.0f} min "
                     f"({int(e.get('fraction', 0.0) * 100)}%, {whose})")
    return lines


def active_model(registry: dict | None = None) -> str:
    """The model of the telescope Planning is set to; the reference S50 when the
    store has no telescope yet."""
    from .planning_config import active_device_key
    key = active_device_key()
    return model_key(key, registry) if key else REFERENCE_MODEL


def capture_report(slug: str, obj_type: str | None, totals: dict,
                   registry: dict | None = None, goals: dict | None = None) -> dict:
    """The goal half of an object's capture summary (assistant tools): the active
    telescope's goal and progress, plus every model that captured it.

    ``deep_threshold_min`` / ``fraction_of_deep`` keep their names but are the
    *active telescope's* integration goal — what "deep" means for the next night."""
    from . import devices
    reg = devices.load_registry() if registry is None else registry
    goals = load() if goals is None else goals
    by_model = totals.get("by_model") or {}
    active = active_model(reg)
    goal, source = resolve(slug, obj_type, active, goals, reg)
    have = (by_model.get(active) or {}).get("integration_min", 0.0)
    return {
        "active_model": active,
        "deep_threshold_min": goal,
        "goal_source": source,
        "fraction_of_deep": round(fraction(have, goal), 3),
        "goals": [{"model": m, "label": model_label(m, reg),
                   "integration_min": e.get("integration_min", 0.0),
                   "goal_min": e.get("goal_min"), "goal_source": e.get("goal_source"),
                   "fraction": e.get("fraction"), "status": e.get("status")}
                  for m, e in sorted(by_model.items())],
    }

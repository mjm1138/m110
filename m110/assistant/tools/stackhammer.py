"""Stackhammer proposal — what Stackhammer would do with a target, and why.

Read-only, like `plan_stack`, and for the same reason: a stack costs hours. This
runs only Stackhammer's own read-only subcommands (`settings`, `prepare`,
`plan`), which read FITS headers and write nothing; the executor
(`m110.stackhammer.execute`) is the CLI's job, after a human agrees.

Unlike `plan_stack`, nothing here decides a setting. Stackhammer reports every
option with its value, its choices and its reason, so this tool relays them and
lets the caller change any of them by Stackhammer's own names. That is also why
`settings` is one free-form object rather than a parameter per option: the list
belongs to the binary the user has, not to this build of M110.
"""
from __future__ import annotations

from pathlib import Path

from m110 import config, running_app
from m110.assistant.registry import ToolError, register
from m110.assistant.serialize import ToolResult
from m110.assistant.store import require_store
from m110.assistant.tools.stacking import (_resolve_dir, _scrub, siril_block,
                                           stacker_block)

SKILL_HINT = ("The stackhammer-stacking skill (get_skill) still explains every "
              "option without it.")


def scrub(value):
    """Absolute store paths out of every string, at any depth. Stackhammer's
    reports name files by absolute path (its Siril commands must), and
    `serialize` only relativizes `Path` objects."""
    if isinstance(value, str):
        return _scrub(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def set_words(values: dict) -> list[str]:
    """`--set KEY=VALUE` words that reproduce `values` on the command line."""
    words = []
    for key, value in values.items():
        text = ("true" if value else "false") if isinstance(value, bool) else f"{value}"
        words += ["--set", f"{key}={text}"]
    return words


def job_dir(target: str, filt: str | None) -> Path:
    """The Siril job folder for a target (and filter), or a ToolError. A preset
    lives in a job folder, so loose lights with no sandbox don't qualify."""
    directory = _resolve_dir(target, filt)
    base = config.siril_dir(target)
    if directory != base and base not in directory.parents:
        raise ToolError(
            f"{target!r} has no Siril working folder yet, and a Stackhammer preset "
            "lives in one. M110 creates it on the next sync.")
    return directory


@register(
    name="plan_stackhammer",
    title="Plan a Stackhammer stack",
    description=(
        "Ask Stackhammer — a separate, faster stacking engine for Siril on Apple "
        "silicon, with local normalization — what it would do with a capture "
        "folder's lights. Returns the lights, the calibration it matched for them "
        "and why (a Seestar app's own subs get none), the Siril steps that "
        "preprocess them, and EVERY Stackhammer setting with its value, its choices, "
        "its reason and who decided it (the binary's default, the folder's preset, "
        "or an override passed here). When the folder already holds a plate-solved "
        "sequence it also returns which frames the quality filters keep, the canvas "
        "and the coverage depth; before that those are not known, and the result "
        "says so. Pass `settings` to see a what-if: the whole report is asked for "
        "again with them. "
        "STRICTLY READ-ONLY: it runs only Stackhammer's read-only commands, which "
        "read FITS headers; it does NOT stack and writes nothing. Present the "
        "proposal, get agreement, then either give `how_to_run` VERBATIM for the "
        "user to run, or stage the agreed settings with propose_stackhammer_preset "
        "so the Stackhammer window in Siril opens on them. Seconds on a large set."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target": {"type": "string",
                       "description": ("Capture-folder name, e.g. 'M51' or 'M81 M82'. "
                                       "The capture target (a folder), not an object "
                                       "slug. Mosaics keep their '_mosaic' suffix.")},
            "filter": {"type": "string",
                       "description": ("Which filter's job to plan, e.g. 'LP'. Required "
                                       "when the sandbox is split per filter; the error "
                                       "lists what is available.")},
            "settings": {"type": "object",
                         "description": ("Stackhammer settings to change, by "
                                         "Stackhammer's own option names, e.g. "
                                         "{\"weight\": \"noise\", \"drizzle\": true, "
                                         "\"filter-fwhm\": 95, \"background\": true}. "
                                         "Call once without it to see every option, "
                                         "its choices and its reason. Checked against "
                                         "the installed Stackhammer; an unknown name "
                                         "or value is refused with the valid ones.")},
            "use_preset": {"type": "boolean",
                           "description": ("Apply the folder's saved Stackhammer "
                                           "preset (default true), as a run does. "
                                           "False shows Stackhammer's own defaults.")},
            "verbosity": {"type": "integer", "minimum": 0, "maximum": 3,
                          "description": ("How much the run says in the terminal; "
                                          "changes only `how_to_run`. 0 (default): "
                                          "the stage every 60s. 1: every 30s. 2: "
                                          "every 10s. 3: every line, live.")},
        },
        "required": ["target"],
    },
    cost="seconds",
    engine=("m110.stackhammer.build_plan", "m110.stackhammer.find_binary",
            "m110.stackhammer.validate", "m110.siril.working_dirs"),
)
def plan_stackhammer(target: str, filter: str | None = None,
                     settings: dict | None = None, use_preset: bool = True,
                     verbosity: int = 0) -> ToolResult:
    require_store()
    from m110 import stackhammer          # lazy: pulls the stacker (numpy) with it

    directory = _resolve_dir(target, filter)
    if not stackhammer.find_binary():
        raise ToolError(f"{stackhammer.NOT_FOUND} {SKILL_HINT}")
    try:
        plan = stackhammer.build_plan(directory, settings or {}, use_preset=use_preset)
    except stackhammer.StackhammerError as e:
        raise ToolError(_scrub(str(e))) from e

    payload = scrub(plan.as_json())
    # A Path, so `serialize` writes it store-relative.
    payload["working_dir"] = Path(plan.working)
    payload["target"] = target
    payload["filter"] = filter
    payload["siril"] = siril_block()

    # What a run would use that the preset on disk doesn't already say — the
    # words `how_to_run` must carry, and what a preset proposal would change.
    on_disk = plan.preset or {}
    pending = {k: v for k, v in plan.overrides.items() if on_disk.get(k) != v}
    payload["preset"]["pending"] = pending
    payload["preset"]["note"] = (
        "These overrides are not in the folder's preset. Stage them with "
        "propose_stackhammer_preset (settings = the preset's plus these) and the "
        "Stackhammer window in Siril opens on them; `how_to_run` carries them "
        "either way." if pending else
        "The folder's preset already says everything this proposal uses."
        if plan.preset is not None else
        "No preset in this folder: a run uses Stackhammer's defaults.")

    args = set_words(pending)
    if not use_preset:
        args.append("--no-preset")
    level = max(0, min(3, int(verbosity or 0)))
    if level:
        args.append(f"-{'v' * level}")
    name = f"{target}/{filter}" if filter else target
    stk = running_app.stacker()
    payload["how_to_run"] = (
        running_app.shell_command(stk["argv"], name, "--engine", "stackhammer",
                                  "--run", *args)
        + "   # add --handoff to send the finished stack to AstroWizard")
    payload["how_to_measure"] = running_app.shell_command(
        stk["argv"], name, "--engine", "stackhammer")
    payload["how_to_run_in_siril"] = (
        "Or from Siril: open this target with Process in Siril in M110, then run "
        "Scripts → Stackhammer. Its window loads the folder's preset "
        f"(presets/{stackhammer.PRESET_NAME}) when it opens, shows the same plan, "
        "and one Run preprocesses, stacks and loads the result.")
    payload["stacker"] = stacker_block(stk)
    return ToolResult(payload)


@register(
    name="propose_stackhammer_preset",
    title="Propose a Stackhammer preset",
    description=(
        "Propose the Stackhammer settings a capture folder should be stacked with, "
        "as that folder's preset file. Once the user applies it in M110, the "
        "Stackhammer window in Siril opens on those settings and a headless run "
        "(`how_to_run` from plan_stackhammer) uses them without any --set. Pass the "
        "COMPLETE set of settings the preset should hold — it replaces the file, it "
        "does not merge — taking the current ones from plan_stackhammer's `preset` "
        "and changing what was agreed. Only settings that differ from Stackhammer's "
        "defaults need to be in it. Checked against the installed Stackhammer. "
        "Does NOT apply anything and does NOT stack: the proposal waits in M110 for "
        "the user to review. Seconds. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target": {"type": "string",
                       "description": "Capture-folder name, as for plan_stackhammer."},
            "filter": {"type": "string",
                       "description": ("Which filter's job folder, when the sandbox is "
                                       "split per filter. Each has its own preset.")},
            "settings": {"type": "object",
                         "description": ("The preset's settings, by Stackhammer's "
                                         "option names, e.g. {\"weight\": \"noise\", "
                                         "\"filter-fwhm\": 95}. The whole preset, "
                                         "not a change to it.")},
            "rationale": {"type": "string",
                          "description": ("Why these settings, in a sentence or two "
                                          "the user will read when reviewing.")},
        },
        "required": ["target", "settings", "rationale"],
    },
    cost="seconds",
    engine=("m110.stackhammer.validate", "m110.stackhammer.read_preset",
            "m110.stackhammer.settings"),
)
def propose_stackhammer_preset(target: str, settings: dict, rationale: str,
                               filter: str | None = None) -> dict:
    require_store()
    from m110 import stackhammer
    from m110.assistant import proposals

    directory = job_dir(target, filter)
    if not settings:
        raise ToolError("Give at least one setting. To go back to Stackhammer's "
                        "defaults the user can delete the preset file.")
    found = stackhammer.find_binary()
    if not found:
        raise ToolError(f"{stackhammer.NOT_FOUND} A preset can't be checked without "
                        "it, so none was proposed.")
    try:
        defaults = stackhammer.settings(found[0])
        values = stackhammer.validate(settings, defaults)
    except stackhammer.StackhammerError as e:
        raise ToolError(_scrub(str(e))) from e

    proposed = {o: e.get("value") for o, e in stackhammer.entries(defaults).items()}
    current = stackhammer.read_preset(directory) or {}
    rows = []
    for option in sorted(set(values) | set(current)):
        was = current.get(option, proposed.get(option))
        now = values.get(option, proposed.get(option))
        if was != now:
            rows.append({"option": option, "was": was, "now": now,
                         "default": proposed.get(option)})
    name = f"{target}/{filter}" if filter else target
    unread = sorted(set(values) & set(stackhammer.ADVANCED))
    summary = "\n".join([
        f"**Proposed Stackhammer preset for {name} — not applied.**", "",
        rationale.strip(), "",
        *(["| Setting | Now | Proposed | Stackhammer's default |", "|---|---|---|---|",
           *(f"| {r['option']} | {r['was']} | {r['now']} | {r['default']} |"
             for r in rows)] if rows else
          ["No setting changes: the folder's preset already says this."]),
        "",
        f"The preset holds {len(values)} setting(s): "
        + ", ".join(f"{k} = {v}" for k, v in sorted(values.items())) + ".",
        *([f"The Stackhammer window in Siril does not read {', '.join(unread)} from "
           "a preset; a headless run does."] if unread else []),
        "",
        f"Applying writes `presets/{stackhammer.PRESET_NAME}` in the folder's Siril "
        "working directory; a different preset already there is kept in "
        "`presets/archive/`. Nothing is stacked.",
    ])
    return proposals.emit(
        action="set_stackhammer_preset", title=f"Stackhammer preset for {name}",
        rationale=rationale,
        payload={"target": target, "filter": filter, "settings": values},
        preview={"changes": rows}, summary=summary,
        target={"slug": name},
        tools=("plan_stackhammer",), functions=("m110.stackhammer.validate",),
        extra_state={"stackhammer_preset_sha256": proposals.file_sha256(
            stackhammer.preset_path(directory))})

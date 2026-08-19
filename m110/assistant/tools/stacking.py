"""Stacking proposal — measure a target's subs and say what settings they support.

Read-only, and deliberately narrow. `m110.stacking` also contains the executor,
but nothing here can reach it: this module calls `build_plan` with
`deep_measure=False`, which is pure FITS-header reads and skips even the two
enrichments that would shell out to Siril. Running a stack is the CLI's job
(`m110-stack --run`), where a human has agreed to the settings first.
"""
from __future__ import annotations

from pathlib import Path

from m110 import config, launch
from m110.assistant.registry import ToolError, register
from m110.assistant.serialize import ToolResult
from m110.assistant.store import require_store


def _resolve_dir(target: str) -> Path:
    """The Siril sandbox for a capture folder, with a message the model can act on."""
    base = config.siril_dir(target)
    if base.is_dir():
        return base
    if config.lights_dir(target).is_dir():
        return config.target_dir(target)
    known = sorted(p.name for p in config.IMAGES_DIR.iterdir() if p.is_dir()) \
        if config.IMAGES_DIR.is_dir() else []
    raise ToolError(
        f"No subs found for {target!r}. Known capture folders: "
        f"{', '.join(known) or '(none)'}"
    )


@register(
    name="plan_stack",
    title="Plan a stack",
    description=(
        "Measure a capture folder's light frames and propose Siril stacking settings: "
        "frame count and integration, mixed exposures or gain, mosaic geometry, "
        "coverage depth, and the drizzle / rejection / weighting / feathering choices "
        "those support — each with the reason it was chosen — plus the projected disk "
        "cost and the exact Siril script the settings produce. Reads every frame's "
        "FITS header, so seconds on a large set. "
        "STRICTLY READ-ONLY: this measures and proposes, it does NOT stack. Present "
        "the proposal, get the user's agreement, and then tell them to run "
        "`m110-stack <dir> --run` themselves — a large mosaic costs hours and over "
        "100 GB, so starting one unasked is the failure to avoid."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target": {"type": "string",
                       "description": ("Capture-folder name, e.g. 'M51' or 'M81 M82'. "
                                       "This is the capture target (a folder), not an "
                                       "object slug — one folder can feed several "
                                       "objects. Mosaics keep their '_mosaic' suffix.")},
            "only_exposure": {"type": "number",
                              "description": ("Consider only frames at this exposure in "
                                              "seconds. Use when a set mixes exposures "
                                              "and they should be stacked separately.")},
            "exclude_night": {"type": "string",
                              "description": ("Drop one night, YYYY-MM-DD. Use sparingly: "
                                              "the quality filters already drop poor "
                                              "frames individually, across every night.")},
        },
        "required": ["target"],
    },
    cost="seconds",
    engine=("m110.stacking.build_plan", "m110.stacking.resolve_layout",
            "m110.launch.find_app"),
)
def plan_stack(target: str, only_exposure: float | None = None,
               exclude_night: str | None = None) -> ToolResult:
    require_store()
    from m110 import stacking            # lazy: pulls astropy on first header read

    directory = _resolve_dir(target)
    ov = stacking.Overrides(
        only_exposure=[only_exposure] if only_exposure is not None else None,
        exclude_night=[exclude_night] if exclude_night else None,
    )
    try:
        plan = stacking.build_plan(directory, ov, deep_measure=False)
    except stacking.StackingError as e:
        raise ToolError(str(e)) from e

    payload = plan.as_json()
    # `serialize` relativizes Path objects but passes strings through verbatim, so
    # hand it a Path — otherwise the user's home directory rides into the model's
    # context in every response.
    payload["working_dir"] = Path(plan.working)
    payload["frames_total"] = plan.frames_total

    siril = launch.find_app("siril")
    payload["siril"] = {
        "found": bool(siril),
        # Never the absolute path: whether Siril exists is the useful fact, where
        # it lives is the user's filesystem.
        "note": ("Siril is installed, so `m110-stack <dir> --run` will work."
                 if siril else
                 "Siril was not found on this machine. Stacking needs it — "
                 "https://siril.org — or its location can be set in M110 → "
                 "Preferences → Processing tools."),
    }
    # By capture-folder name, never by path: an absolute path here would put the
    # user's home directory into the model's context, and `serialize` can only
    # relativize a Path — a path baked into a command string sails straight
    # through. `m110-stack` resolves the name against the store itself.
    payload["how_to_run"] = (
        f"m110-stack {target!r} --run"
        + (f" --only-exposure {only_exposure:g}" if only_exposure is not None else "")
        + (f" --exclude-night {exclude_night}" if exclude_night else "")
        + "   # add --handoff to send the finished stack to AstroWizard"
    )
    return ToolResult(payload)

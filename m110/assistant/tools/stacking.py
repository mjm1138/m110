"""Stacking proposal — measure a target's subs and say what settings they support.

Read-only, and deliberately narrow. `m110.stacking` also contains the executor,
but nothing here can reach it: this module calls `build_plan` with
`deep_measure=False`, which is pure FITS-header reads and skips even the two
enrichments that would shell out to Siril. Running a stack is the CLI's job
(`m110-stack --run`), where a human has agreed to the settings first.

The override surface is wide on purpose. The engine decides settings
deterministically — `build_proposal` is the stacking analogue of
`prioritize.rank` — so the assistant's job is not to re-derive them but to
*manipulate* them and see what the engine then says. Every override recomputes
the whole proposal, canvas and disk included, so "what if we dropped drizzle?"
is answered with real numbers rather than a recital of the flag.
"""
from __future__ import annotations

from pathlib import Path

from m110 import config, launch
from m110.assistant.registry import ToolError, register
from m110.assistant.serialize import ToolResult
from m110.assistant.store import require_store

# Per-frame arrays the surveyor keeps for its own arithmetic and a model has no
# use for. `temps` is the offender: one float per frame, so ~900 numbers on a
# mosaic — far and away the largest thing in the payload, and every one of them
# is noise next to the range, which is summarised below. Same reasoning as
# `planning._CHART_KEYS`.
_BULK_KEYS = frozenset({"temps"})


def _scrub(message: str) -> str:
    """Absolute store paths out of an engine message.

    The success payload is protected by handing `serialize` a `Path`, but an
    **error** message is a plain string built by the engine and passed through
    verbatim — a second, easily-missed way for the user's home directory to reach
    a model. Anything reporting a location reports it store-relative.
    """
    for root in (str(config.DATA_ROOT), str(Path.home())):
        if root and root != "/":
            message = message.replace(root + "/", "").replace(root, "<data root>")
    return message


def _filter_jobs(target: str) -> list[tuple[str, Path]]:
    """`(filter, job_dir)` for a sandbox split per filter, else `[]`.

    `siril.working_dirs` is the authority on the split — the same list "Process
    in Siril" offers — so the two can't disagree about what a job is.
    """
    from m110 import siril

    base = config.siril_dir(target)
    if not base.is_dir():
        return []
    return [(d.name, d) for d in siril.working_dirs(target) if d != base]


def _count_lights(job_dir: Path) -> int:
    lights = job_dir / "lights"
    if not lights.is_dir():
        return 0
    return sum(1 for p in lights.iterdir()
               if p.is_file() and config.is_fits_file(p.name))


def _resolve_dir(target: str, filt: str | None) -> Path:
    """The directory to measure, or a ToolError a model can act on."""
    jobs = _filter_jobs(target)
    if jobs:
        by_name = {name.upper(): d for name, d in jobs}
        if filt is None:
            listing = ", ".join(f"{n} ({_count_lights(d)} frames)" for n, d in jobs)
            raise ToolError(
                f"{target!r} is split per filter and each filter stacks separately: "
                f"{listing}. Call again with `filter` set to the one you want. "
                "Broadband and narrowband are combined AFTER stacking, never in one "
                "stack — see the siril-stacking skill."
            )
        if filt.upper() not in by_name:
            raise ToolError(
                f"No filter {filt!r} for {target!r}. Available: "
                f"{', '.join(n for n, _ in jobs)}."
            )
        return by_name[filt.upper()]

    if filt:
        raise ToolError(
            f"{target!r} is not split per filter, so there is no {filt!r} job to "
            "plan. Call again without `filter`."
        )
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


# Tool argument -> the CLI flag that reproduces it, so `how_to_run` stays a true
# statement of what was proposed. An override with no entry here would be
# silently dropped from the command, which is how a user ends up running
# something other than what they agreed to.
_CLI_FLAGS = {
    "only_exposure": lambda v: f" --only-exposure {v:g}",
    "exclude_night": lambda v: f" --exclude-night {v}",
    "drizzle": lambda v: " --no-drizzle" if not v else f" --drizzle {v:g}",
    "pixfrac": lambda v: f" --pixfrac {v:g}",
    "rejection": lambda v: f' --rejection "{v}"',
    "weight": lambda v: f" --weight {v}",
    "overlap_norm": lambda v: " --overlap-norm" if v else " --no-overlap-norm",
    "feather": lambda v: f" --feather {int(v)}",
    "no_bg_extract": lambda v: " --no-bg-extract",
    "no_filters": lambda v: " --no-filters",
    "filter_pct": lambda v: f" --filter-pct {v:g}",
}


@register(
    name="plan_stack",
    title="Plan a stack",
    description=(
        "Measure a capture folder's light frames and propose Siril stacking settings: "
        "frame count and integration, mixed exposures or gain, mosaic geometry, "
        "coverage depth, and the drizzle / rejection / weighting / feathering choices "
        "those support — each with the reason it was chosen — plus the projected disk "
        "cost and the three Siril scripts the settings produce. Reads every frame's FITS "
        "header, so seconds on a large set. "
        "Pass any override to see what the engine proposes INSTEAD: the whole proposal "
        "is recomputed, canvas and disk included, so a what-if is answered with real "
        "numbers rather than a guess. "
        "STRICTLY READ-ONLY: this measures and proposes, it does NOT stack. Present "
        "the proposal, get the user's agreement, then give them the `how_to_run` "
        "command to run themselves — a large mosaic costs hours and over 100 GB, so "
        "starting one unasked is the failure to avoid."
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
            "filter": {"type": "string",
                       "description": ("Which filter's job to plan, e.g. 'LP' or "
                                       "'IRCUT'. Required when the sandbox is split per "
                                       "filter — each filter stacks separately and they "
                                       "are combined afterwards. The error lists what "
                                       "is available.")},
            "only_exposure": {"type": "number",
                              "description": ("Consider only frames at this exposure in "
                                              "seconds. Use when a set mixes exposures "
                                              "and they should be stacked separately.")},
            "exclude_night": {"type": "string",
                              "description": ("Drop one night, YYYY-MM-DD. Use sparingly: "
                                              "the quality filters already drop poor "
                                              "frames individually, across every night.")},
            "drizzle": {"type": "number",
                        "description": ("Force the drizzle scale, e.g. 2 for 2x, or 0 to "
                                        "turn drizzle off. Omit to let coverage depth "
                                        "decide, which is usually right.")},
            "pixfrac": {"type": "number",
                        "description": ("Force the drizzle pixel fraction (0-1). Only "
                                        "meaningful with drizzle on.")},
            "rejection": {"type": "string",
                          "description": ("Force the rejection algorithm, e.g. 'w 3 3' "
                                          "(Winsorized), 'l 5 5' (linear fit), "
                                          "'p 0.2 0.1' (percentile), or 'none'.")},
            "weight": {"type": "string",
                       "enum": ["noise", "wfwhm", "nbstars", "nbstack", "none"],
                       "description": ("Force frame weighting. Siril silently drops "
                                       "noise weighting when overlap normalisation is "
                                       "on; the engine reconciles that and says so.")},
            "overlap_norm": {"type": "boolean",
                             "description": ("Force overlap normalisation on or off. On "
                                             "protects large-scale structure across a "
                                             "mosaic but is poorly constrained at the "
                                             "edges, and is the first suspect for a very "
                                             "slow stack.")},
            "feather": {"type": "integer",
                        "description": ("Feather width in pixels at each frame's border; "
                                        "0 turns it off. Mosaics need it.")},
            "no_bg_extract": {"type": "boolean",
                              "description": ("Skip per-frame background extraction. Do "
                                              "NOT do this on a mosaic — every pointing "
                                              "carries a different gradient, and "
                                              "normalisation cannot correct a gradient "
                                              "within a frame.")},
            "no_filters": {"type": "boolean",
                           "description": ("Drop the four quality filters. Only for a set "
                                           "already too thin to lose frames.")},
            "filter_pct": {"type": "number",
                           "description": ("Set all four quality-filter thresholds at "
                                           "once, e.g. 95. The default is 98.")},
        },
        "required": ["target"],
    },
    cost="seconds",
    engine=("m110.stacking.build_plan", "m110.stacking.resolve_layout",
            "m110.siril.working_dirs", "m110.launch.find_app"),
)
def plan_stack(target: str, filter: str | None = None,
               only_exposure: float | None = None, exclude_night: str | None = None,
               drizzle: float | None = None, pixfrac: float | None = None,
               rejection: str | None = None, weight: str | None = None,
               overlap_norm: bool | None = None, feather: int | None = None,
               no_bg_extract: bool = False, no_filters: bool = False,
               filter_pct: float | None = None) -> ToolResult:
    require_store()
    from m110 import stacking            # lazy: pulls astropy on first header read

    directory = _resolve_dir(target, filter)
    ov = stacking.Overrides(
        only_exposure=[only_exposure] if only_exposure is not None else None,
        exclude_night=[exclude_night] if exclude_night else None,
        # A JSON schema has no tri-state number, so 0 is how the caller says
        # "off" — and the CLI spells that as its own `--no-drizzle` flag.
        drizzle=drizzle if drizzle else None,
        no_drizzle=drizzle == 0,
        pixfrac=pixfrac,
        rejection=rejection,
        weight=weight,
        ov=overlap_norm,
        feather=feather,
        no_bg_extract=no_bg_extract,
        no_filters=no_filters,
        filter_pct=filter_pct,
    )
    try:
        plan = stacking.build_plan(directory, ov, deep_measure=False)
    except stacking.StackingError as e:
        raise ToolError(_scrub(str(e))) from e

    payload = plan.as_json()
    # Summarise before dropping: the spread across a session is the part worth
    # knowing (it drives dark current), not the per-frame series.
    temps = plan.survey.temps
    if temps:
        payload["survey"]["sensor_temp_c"] = {
            "min": round(min(temps), 1), "max": round(max(temps), 1)}
    # `serialize` relativizes Path objects but passes strings through verbatim, so
    # hand it a Path — otherwise the user's home directory rides into the model's
    # context in every response.
    payload["working_dir"] = Path(plan.working)
    payload["frames_total"] = plan.frames_total
    payload["filter"] = filter

    applied = {k: v for k, v in (
        ("only_exposure", only_exposure), ("exclude_night", exclude_night),
        ("drizzle", drizzle), ("pixfrac", pixfrac), ("rejection", rejection),
        ("weight", weight), ("overlap_norm", overlap_norm), ("feather", feather),
        ("no_bg_extract", no_bg_extract or None),
        ("no_filters", no_filters or None), ("filter_pct", filter_pct),
    ) if v is not None}
    # Echoed so a reader can tell an engine proposal from a hand-forced setting.
    # Without it an overridden run reads identically to one the engine chose.
    payload["overrides_applied"] = applied

    siril = launch.find_app("siril")
    payload["siril"] = {
        "found": bool(siril),
        # Never the absolute path: whether Siril exists is the useful fact, where
        # it lives is the user's filesystem.
        "note": ("Siril is installed, so the command below will work."
                 if siril else
                 "Siril was not found on this machine. Stacking needs it — "
                 "https://siril.org — or its location can be set in M110 → "
                 "Preferences → Processing tools."),
    }

    # By capture-folder name, never by path: an absolute path here would put the
    # user's home directory into the model's context, and `serialize` can only
    # relativize a Path — a path baked into a command string sails straight
    # through. `m110-stack` resolves the name against the store itself.
    flags = "".join(_CLI_FLAGS[k](v) for k, v in applied.items())
    name = f"{target}/{filter}" if filter else target
    payload["how_to_run"] = (
        f"m110-stack {name!r} --run{flags}"
        "   # add --handoff to send the finished stack to AstroWizard"
    )
    return ToolResult(payload, drop_keys=_BULK_KEYS)

"""The single place engine values are coerced into JSON-safe shapes.

`registry.call` runs every tool result through `to_json_safe` exactly once, so
no tool hand-formats a datetime — get it wrong in one place and every tool is
wrong the same way, which is the point.

Three hazards, all real in this engine:

1. **Naive-local datetimes.** `planning.plan_night` returns them in `window`,
   `moon.set_time`/`rise_time`/`track`, and every `night_track` entry
   (`transit_time`, `start_time`, `up_start`, `up_end`). Emitting those bare
   invites the reader to assume UTC — and "is 04:30 before or after dawn" is
   exactly the kind of question that then gets answered wrongly. Tools that
   return datetimes pass `tz=` (from the `Site` the plan was computed for) so
   the output carries a real offset.

2. **`Path`.** Returned by `fieldguide.list_guides`, `objects.hero_path`,
   `build_images.hero_source_path`, `Site.profiles_dir`, and the siril plan
   dataclasses. Absolute paths leak the user's home directory into model
   context and are useless as identifiers. Paths inside the data root become
   store-relative POSIX strings — stable ids a caller can hand back to
   `saved_plans(name=)` — and anything outside collapses to its basename.

3. **Dataclasses.** `Weights`, `TargetContext`, `Site`, `Device`, `PrepPlan`.
   `asdict()` then recurse, which catches `Site.profiles_dir` via rule 2 for
   free. Note `Site.tz` is a *property*, so `asdict` won't emit it; the
   `timezone` field it derives from is a real field and survives.

Plus the boring cases that break `json.dumps`: `date`, `set`, `tuple`, `nan`,
`inf`, `Decimal`.
"""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any

_MAX_DEPTH = 24     # engine data is shallow; this only stops pathological nesting


@dataclasses.dataclass(frozen=True)
class ToolResult:
    """Optional wrapper letting a tool supply serialization hints.

    Tools usually return a plain dict. A tool whose payload carries datetimes
    (the planning ones) returns this instead, so the offset comes from the site
    the plan was actually computed for rather than a guess made downstream.

    `drop_keys` removes chart-shaped arrays anywhere in the payload —
    `night_track`'s `samples` (~40 tuples per target, times up to 30 targets)
    and the moon `track`. They exist to draw the timeline widget; to a model
    they are pure payload bloat, and dropping them at the tool boundary is
    easier to get right than remembering at each call site.
    """
    data: Any
    tz: Any = None                          # tzinfo, e.g. Site.tz
    drop_keys: frozenset[str] = frozenset()


def _num(x: float) -> float | None:
    # JSON has no NaN/Infinity; json.dumps emits them bare by default, which is
    # invalid JSON and rejected by strict parsers.
    return None if (math.isnan(x) or math.isinf(x)) else x


def _path(p: PurePath, root: Path | None) -> str:
    if root is not None:
        try:
            return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):
            pass
    # Outside the store (or unresolvable): the basename is all a caller can use,
    # and it keeps the user's directory layout out of model context.
    return Path(p).name


def _dt(v: datetime, tz) -> str:
    if v.tzinfo is not None:
        return v.isoformat()
    if tz is not None:
        return v.replace(tzinfo=tz).isoformat()
    # No offset known — say so by omitting one rather than implying UTC.
    return v.isoformat()


def to_json_safe(obj: Any, *, tz=None, root: Path | None = None,
                 drop_keys: frozenset[str] | set[str] | tuple = (),
                 _depth: int = 0) -> Any:
    """Return `obj` rebuilt from JSON-representable parts.

    `tz` supplies the offset for naive datetimes; `root` is the data root that
    Paths are made relative to (defaults to `config.DATA_ROOT`); `drop_keys`
    names mapping keys to omit at any depth.
    """
    if root is None:
        from m110 import config
        root = config.DATA_ROOT

    if _depth > _MAX_DEPTH:
        return str(obj)

    kw = {"tz": tz, "root": root, "drop_keys": drop_keys, "_depth": _depth + 1}

    # Order matters: bool before int, datetime before date (datetime subclasses
    # date), str/bytes before the generic Sequence branch.
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return _num(obj)
    if isinstance(obj, Decimal):
        return _num(float(obj))
    if isinstance(obj, datetime):
        return _dt(obj, tz)
    if isinstance(obj, (date, time)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, PurePath):
        return _path(obj, root)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_json_safe(dataclasses.asdict(obj), **kw)

    if isinstance(obj, Mapping):
        return {str(k): to_json_safe(v, **kw)
                for k, v in obj.items() if k not in drop_keys}

    if isinstance(obj, (set, frozenset)):
        # Sort where possible so output is stable across runs.
        try:
            items = sorted(obj)
        except TypeError:
            items = list(obj)
        return [to_json_safe(v, **kw) for v in items]

    if isinstance(obj, Sequence):
        return [to_json_safe(v, **kw) for v in obj]

    # Unknown object: stringify rather than raise. A tool returning something
    # exotic is a bug, but a live conversation shouldn't die over it.
    return str(obj)


def serialize_result(result: Any, *, root: Path | None = None) -> Any:
    """Normalize whatever a tool returned — plain value or `ToolResult`."""
    if isinstance(result, ToolResult):
        return to_json_safe(result.data, tz=result.tz, root=root,
                            drop_keys=frozenset(result.drop_keys))
    return to_json_safe(result, root=root)

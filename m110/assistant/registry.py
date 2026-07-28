"""The tool registry — provider-neutral descriptors over engine functions.

This module imports neither MCP nor any LLM SDK. That is the point: the stdio
MCP server, a future in-app transport, and any provider adapter all consume the
same `Tool` objects, and `params` is already provider-neutral JSON Schema.

Every registered tool is READ-ONLY or PLAN-ONLY. Nothing here may write to the
data store or the content tree — see tests/test_assistant_readonly.py, which
proves it three ways and is parametrized over the registry so a newly added
tool cannot skip the check.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

COSTS = ("instant", "seconds", "slow")


class ToolError(Exception):
    """A tool failed in a way the model can reasonably recover from."""


class ToolInputError(ToolError):
    """The arguments were invalid — a protocol-level bad request."""


class StoreUnavailable(ToolError):
    """The configured data root isn't a usable M110 store.

    An external client spawns this server with M110_DATA_ROOT pinned in its
    config; if that path is wrong, moved, or never bootstrapped, engine readers
    raise bare FileNotFoundError. The server is read-only and must NOT call
    `config.ensure_data_root()` to fix it (that writes), so tools surface this
    instead — the model can then tell the user what's actually wrong.
    """


@dataclass(frozen=True)
class Tool:
    name: str                        # snake_case, unique
    title: str                       # short human label
    description: str                 # model-facing; states cost + read-only contract
    params: dict                     # JSON Schema (object, additionalProperties: false)
    fn: Callable[..., Any]
    cost: str = "instant"            # one of COSTS
    returns: str = "json"            # "json" | "json+images"
    engine: tuple[str, ...] = ()     # provenance, e.g. ("m110.prioritize.rank",)


_TOOLS: dict[str, Tool] = {}


def register(*, name: str, title: str, description: str, params: dict,
             cost: str = "instant", returns: str = "json",
             engine: tuple[str, ...] = ()) -> Callable:
    """Decorator declaring a function as a tool."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in _TOOLS:
            raise ValueError(f"duplicate tool name: {name}")
        if cost not in COSTS:
            raise ValueError(f"bad cost {cost!r} for {name}; expected one of {COSTS}")
        _TOOLS[name] = Tool(name=name, title=title, description=description,
                            params=params, fn=fn, cost=cost, returns=returns,
                            engine=engine)
        return fn
    return deco


def all_tools() -> list[Tool]:
    return [_TOOLS[k] for k in sorted(_TOOLS)]


def get(name: str) -> Tool:
    try:
        return _TOOLS[name]
    except KeyError:
        raise ToolInputError(f"unknown tool: {name}") from None


def _validate(tool: Tool, args: dict) -> dict:
    """Minimal JSON-Schema-shaped validation — enough for the shapes we author.

    Hand-rolled rather than pulling `jsonschema` into the runtime; the dev extra
    has it so tests can assert the schemas are themselves legal.
    """
    schema = tool.params or {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(args, dict):
        raise ToolInputError(f"{tool.name}: arguments must be an object")
    if schema.get("additionalProperties") is False:
        for k in args:
            if k not in props:
                raise ToolInputError(f"{tool.name}: unexpected argument {k!r}")
    for k in required:
        if k not in args:
            raise ToolInputError(f"{tool.name}: missing required argument {k!r}")

    types = {"string": str, "integer": int, "number": (int, float),
             "boolean": bool, "array": list, "object": dict}
    clean = {}
    for k, v in args.items():
        if v is None:
            continue
        spec = props.get(k, {})
        want = spec.get("type")
        py = types.get(want)
        # bool is an int subclass — don't let True satisfy an integer field.
        if py and (not isinstance(v, py) or (want != "boolean" and isinstance(v, bool))):
            raise ToolInputError(f"{tool.name}: {k!r} must be {want}")
        if "enum" in spec and v not in spec["enum"]:
            raise ToolInputError(f"{tool.name}: {k!r} must be one of {spec['enum']}")
        if want == "integer":
            lo, hi = spec.get("minimum"), spec.get("maximum")
            if lo is not None and v < lo:
                raise ToolInputError(f"{tool.name}: {k!r} must be >= {lo}")
            if hi is not None and v > hi:
                raise ToolInputError(f"{tool.name}: {k!r} must be <= {hi}")
        clean[k] = v
    return clean


def call(name: str, args: dict | None = None) -> Any:
    """Look up, validate, invoke, serialize.

    Serialization happens here and only here, so no tool hand-formats a
    datetime or leaks an absolute path. A tool needing control (an offset for
    naive datetimes, chart arrays to drop) returns a `serialize.ToolResult`.
    """
    from m110.assistant import serialize

    tool = get(name)
    result = tool.fn(**_validate(tool, args or {}))
    return serialize.serialize_result(result)

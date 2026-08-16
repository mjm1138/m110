"""stdio MCP server exposing the assistant tool registry.

The ONLY module that imports `mcp`. Everything it serves comes from
`m110.assistant.registry`, so an in-app transport can serve the same tools with
no MCP involvement.

Two hard requirements, both load-bearing:

1. **stdout purity.** The engine contains bare `print()` calls (build_images,
   build_derived, catalog, refresh, scan_sessions). Under stdio MCP a single
   stray line corrupts the JSON-RPC stream and the client dies with an opaque
   parse error. `main()` therefore points `sys.stdout` at stderr before anything
   else runs, and hands the real stdout only to the transport.

2. **No astropy at import.** The `initialize`/`tools/list` handshake must return
   well under a second; a client that times out never reaches a tool at all. The
   planning tools import astropy inside their function bodies.
"""
from __future__ import annotations

import sys

# ── (1) stdout purity — before any engine import can print ───────────────────
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import asyncio  # noqa: E402
import json  # noqa: E402
from io import TextIOWrapper  # noqa: E402

from m110.assistant import registry  # noqa: E402
from m110.assistant.registry import ToolError, ToolInputError  # noqa: E402

SERVER_NAME = "m110"


def _require_mcp():
    try:
        import mcp.types  # noqa: F401
        from mcp.server.lowlevel import Server  # noqa: F401
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by hand
        raise SystemExit(
            "M110's assistant server needs the 'mcp' package (v2 or newer).\n"
            "Install it with:  pip install 'm110[assistant]'"
        ) from exc
    except ImportError as exc:  # pragma: no cover - exercised by hand
        # `mcp` is present but the low-level Server moved or vanished — i.e. an
        # SDK major we haven't ported to. Say so, rather than letting the
        # AttributeError surface from inside build_server() where it reads like
        # our bug. (v1→v2 removed the decorator API this module used to use.)
        raise SystemExit(
            f"M110's assistant server can't use the installed 'mcp' package: {exc}\n"
            "It needs mcp v2.x.  Reinstall with:  pip install 'm110[assistant]'"
        ) from exc


def build_server():
    """Wire the registry into an MCP Server. Imported lazily by `main`.

    **SDK v2 shape.** v2 removed the low-level `Server` decorator API this was
    originally built on (`@server.list_tools()` and friends) in favour of handler
    callables passed to the constructor. Three mechanical consequences, and they
    are the whole of the difference:

    * a handler takes ``(context, params)`` rather than the unpacked domain
      arguments, so ``name``/``arguments``/``uri`` now arrive on ``params``;
    * a handler returns a **Result** model rather than a bare list or string —
      ``ListToolsResult(tools=…)`` where v1 returned the list, and
      ``ReadResourceResult(contents=[TextResourceContents(…)])`` where v1 could
      return the markdown as a plain ``str``;
    * the models are snake_case with camelCase aliases and ``populate_by_name``,
      so ``inputSchema=`` / ``mimeType=`` still bind — kept as the wire spells
      them.

    Everything the tools and skills actually serve is unchanged, which is the
    point of `registry` owning the content: this module is transport, and only
    the transport moved.
    """
    import anyio
    import mcp.types as types
    from mcp.server.lowlevel import Server

    # Populate the registry (import for side effect).
    from m110.assistant import skills as skills_mod, tools  # noqa: F401

    # ── skills, served three ways from one loader so they can't drift ────────

    async def on_list_prompts(_ctx, _params) -> types.ListPromptsResult:
        return types.ListPromptsResult(prompts=[
            types.Prompt(
                name=s.id, description=s.description,
                arguments=[types.PromptArgument(name=a, required=False)
                           for a in s.arguments],
            )
            for s in skills_mod.all_skills()
        ])

    async def on_get_prompt(_ctx, params) -> types.GetPromptResult:
        skill = skills_mod.get(params.name)
        if skill is None:
            raise ValueError(f"unknown prompt: {params.name}")
        return types.GetPromptResult(
            description=skill.description,
            messages=[types.PromptMessage(
                role="user",
                content=types.TextContent(type="text",
                                          text=skill.render(params.arguments)),
            )],
        )

    async def on_list_resources(_ctx, _params) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=[
            types.Resource(uri=s.uri, name=s.name, description=s.description,
                           mimeType="text/markdown")
            for s in skills_mod.all_skills()
        ])

    async def on_read_resource(_ctx, params) -> types.ReadResourceResult:
        skill_id = skills_mod.id_from_uri(params.uri)
        skill = skills_mod.get(skill_id) if skill_id else None
        if skill is None:
            raise ValueError(f"unknown resource: {params.uri}")
        return types.ReadResourceResult(contents=[
            types.TextResourceContents(uri=params.uri, mimeType="text/markdown",
                                       text=skill.body)
        ])

    async def on_list_tools(_ctx, _params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(name=t.name, description=t.description, inputSchema=t.params)
            for t in registry.all_tools()
        ])

    async def on_call_tool(_ctx, params) -> types.CallToolResult:
        name, arguments = params.name, params.arguments or {}
        try:
            # The engine is synchronous and blocking; off-thread it so a slow
            # call can't starve protocol keepalives.
            result, images = await anyio.to_thread.run_sync(
                lambda: registry.call_with_media(name, arguments)
            )
        except ToolInputError as exc:
            # An input error (bad/missing argument, unknown tool) stays a
            # **successful response carrying `is_error`**, not a JSON-RPC error.
            # v1 arrived here by accident — its decorator wrapper turned any
            # exception the handler raised into `CallToolResult(isError=True)`, so
            # the `raise ValueError` this replaces never actually reached the wire
            # as a protocol error. v2 propagates a raise, so preserving the old
            # behaviour now takes saying it explicitly.
            #
            # Keeping it is the deliberate choice: a model recovers from an
            # is_error result (it can read the message and retry with the right
            # argument) far better than from a transport-level failure, and
            # changing it is a client-visible protocol change that has no business
            # riding along in a transport port.
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True)
        except ToolError as exc:
            # Deliberately NOT `is_error=True`, which v2 makes expressible for the
            # first time: under v1 this path returned a plain content list, i.e. a
            # successful response carrying an error message, and a decline (a wrong
            # data root, the likeliest real failure) is what it reports. Changing
            # that is a client-visible protocol change and belongs in its own
            # change, not smuggled into a transport port.
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {exc}")])
        except Exception:
            # Never let a traceback with absolute paths reach the model.
            import traceback
            traceback.print_exc(file=sys.stderr)
            return types.CallToolResult(content=[types.TextContent(
                type="text",
                text=f"Error: {name} failed unexpectedly. See the M110 server log.",
            )])
        # Text first, then any images: the grounding metadata should be read
        # before the picture is looked at.
        blocks: list[types.ContentBlock] = [
            types.TextContent(type="text", text=json.dumps(result, default=str))
        ]
        blocks += [types.ImageContent(type="image", data=img.base64,
                                      mimeType=img.mime_type) for img in images]
        return types.CallToolResult(content=blocks)

    return Server(
        SERVER_NAME,
        on_list_prompts=on_list_prompts,
        on_get_prompt=on_get_prompt,
        on_list_resources=on_list_resources,
        on_read_resource=on_read_resource,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _run() -> None:
    import anyio
    from mcp.server.stdio import stdio_server

    server = build_server()
    # The SDK's default path would grab sys.stdout — which now points at stderr.
    out = anyio.wrap_file(TextIOWrapper(_REAL_STDOUT.buffer, encoding="utf-8"))
    async with stdio_server(stdout=out) as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    _require_mcp()
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, BrokenPipeError):
        pass


if __name__ == "__main__":
    main()

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
            "M110's assistant server needs the 'mcp' package.\n"
            "Install it with:  pip install 'm110[assistant]'"
        ) from exc


def build_server():
    """Wire the registry into an MCP Server. Imported lazily by `main`."""
    import anyio
    import mcp.types as types
    from mcp.server.lowlevel import Server

    # Populate the registry (import for side effect).
    from m110.assistant import tools  # noqa: F401

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=t.name, description=t.description, inputSchema=t.params)
            for t in registry.all_tools()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        try:
            # The engine is synchronous and blocking; off-thread it so a slow
            # call can't starve protocol keepalives.
            result, images = await anyio.to_thread.run_sync(
                lambda: registry.call_with_media(name, arguments)
            )
        except ToolInputError as exc:
            raise ValueError(str(exc)) from None
        except ToolError as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]
        except Exception:
            # Never let a traceback with absolute paths reach the model.
            import traceback
            traceback.print_exc(file=sys.stderr)
            return [types.TextContent(
                type="text",
                text=f"Error: {name} failed unexpectedly. See the M110 server log.",
            )]
        # Text first, then any images: the grounding metadata should be read
        # before the picture is looked at.
        blocks: list[types.ContentBlock] = [
            types.TextContent(type="text", text=json.dumps(result, default=str))
        ]
        blocks += [types.ImageContent(type="image", data=img.base64,
                                      mimeType=img.mime_type) for img in images]
        return blocks

    return server


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

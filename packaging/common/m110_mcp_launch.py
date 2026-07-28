"""PyInstaller entry point for the bundled `m110-mcp` stdio server.

Mirrors m110_launch.py: PyInstaller needs a concrete script to analyze, and the
installed `m110-mcp` console-script isn't a file on disk.

This is a SECOND executable built from the same Analysis/PYZ as the GUI and
collected into the same folder, so it shares the Python runtime, Qt, astropy and
all package data — it costs a few hundred KB, not another bundle. It must be
built with console=True: the GUI executable has no usable stdio (on Windows,
console=False links against the GUI subsystem, where the standard handles don't
exist at all), and a stdio MCP server without stdout is a non-starter.
"""
from m110.assistant.mcp_server import main

if __name__ == "__main__":
    main()

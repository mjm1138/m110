"""PyInstaller entry point for the bundled `m110-stack` CLI.

Mirrors m110_mcp_launch.py: PyInstaller needs a concrete script to analyze, and
the installed `m110-stack` console-script isn't a file on disk.

A THIRD executable from the same Analysis/PYZ as the GUI and the MCP server,
collected into the same folder, so it shares the Python runtime, astropy, numpy
and all package data — a few hundred KB, not another bundle.

console=True, and for a real reason rather than symmetry: this is a long-running
job whose whole progress story is stdout. A windowed build on Windows links
against the GUI subsystem, where the standard handles do not exist at all, so a
progress heartbeat would go nowhere and a multi-hour stack would be
indistinguishable from a hang.

⚠️ Adding this third console EXE re-arms the LSBackgroundOnly trap: PyInstaller's
BUNDLE inherits `console` last-one-wins across the COLLECT's EXEs and stamps
LSBackgroundOnly=True when it reads "console app", which makes M110 register with
no menu bar, no Dock icon and no Force Quit entry. The explicit
`LSBackgroundOnly: False` in the macOS spec's info_plist is what holds that off —
do not remove it. Verify with `lsappinfo list | grep -A6 space.m110.M110`.
"""
from m110.stacking import main

if __name__ == "__main__":
    raise SystemExit(main())

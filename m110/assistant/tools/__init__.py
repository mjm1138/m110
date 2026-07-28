"""Tool modules. Importing this package populates the registry.

Must stay astropy-free: the MCP handshake budget depends on it, so the planning
tools import `m110.planning` inside their function bodies, never at module
scope (mirroring `prioritize.build_contexts`).
"""
from . import library, overview  # noqa: F401  (import for side effect: registration)

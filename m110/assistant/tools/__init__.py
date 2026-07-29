"""Tool modules. Importing this package populates the registry.

Must stay astropy-free: the MCP handshake budget depends on it, so the planning
tools import `m110.planning` inside their function bodies, never at module
scope (mirroring `prioritize.build_contexts`).
"""
from . import (  # noqa: F401  (imported for side effect: tool registration)
    docs,
    library,
    objects,
    overview,
    processing,
    ranking,
)

"""Assistant layer — a provider-neutral tool registry over the M110 engine.

Deliberately kept free of both Qt and any LLM/MCP SDK: `registry` describes
engine operations as JSON-Schema'd tools, and separate transports (the stdio
MCP server today, an in-app client later) consume the same descriptors.

Importing this package must stay cheap — no astropy, no Qt. See `mcp_server`
for the handshake budget that depends on it.
"""

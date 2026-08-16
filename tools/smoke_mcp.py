#!/usr/bin/env python3
"""Smoke-test M110's assistant MCP server without any AI client.

    python tools/smoke_mcp.py                        # the store the app would use
    python tools/smoke_mcp.py --root ~/Documents/M110

Spawns the server exactly as an MCP client does — the command, args and env that
`client_config.server_entry()` writes into the client's config — and speaks
JSON-RPC to it over real pipes. Stdlib only; no client, no API key, no network.

Why this exists: when "the assistant isn't working", the useful first question is
whether the *server* is broken or the *client* simply isn't finding it. This
answers that in a couple of seconds, and it exercises the things that actually
break in practice:

  * the handshake completes (a client that times out here never reaches a tool,
    and the failure reads as "the server is broken")
  * stdout carries **only** JSON-RPC. The engine has bare `print()` calls, and
    one of them reaching stdout corrupts the stream — this fails loudly on it
    rather than leaving an opaque parse error in a client log
  * tools, prompts (skills) and a couple of real calls against the actual store

Reads only. See `tests/test_assistant_registry.py` for the three-layer proof.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Protocol version to negotiate. Bump only alongside the pinned `mcp` dependency.
# Reviewed at the SDK v2 port and deliberately LEFT: the server agrees to this
# exact version under v2, so it still proves the handshake, and it is the more
# useful thing to assert — a version real clients actually send, i.e. that we
# haven't broken backward compatibility. (Asking for the SDK's own newest,
# 2026-07-28, is not the same test: the server negotiates that down to 2025-11-25,
# so pinning it here would assert a version we never actually speak.)
PROTO = "2025-06-18"
HANDSHAKE_BUDGET_S = 1.0


class Client:
    """The smallest MCP client that can answer "is the server alive?"."""

    def __init__(self, argv: list[str], env: dict):
        self.proc = subprocess.Popen(
            argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id,
                                          "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SystemExit("server closed stdout before replying "
                                 "— see its stderr below")
            if not line.strip():
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                raise SystemExit(
                    f"NON-JSON on stdout — the JSON-RPC stream is corrupted, "
                    f"almost certainly a stray print(): {line!r}") from None

    def call_tool(self, name: str, arguments: dict | None = None):
        """Return a tool's parsed JSON, or None with the message it declined with.

        A tool may legitimately refuse — a wrong data root is the likeliest real
        failure a user hits — and that arrives as a text block, not JSON.
        """
        resp = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if "error" in resp:
            return None, resp["error"].get("message", str(resp["error"]))
        blocks = resp.get("result", {}).get("content", [])
        text = next((b["text"] for b in blocks if b.get("type") == "text"), "")
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            return None, text.strip() or "(empty response)"

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def close(self) -> str:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        return self.proc.stderr.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="data root to point the server at "
                                   "(default: whatever this install resolves to)")
    args = ap.parse_args()

    try:
        from m110.assistant import client_config as cc
    except ModuleNotFoundError:
        print("Can't import m110 — run from the repo root, or `pip install -e .`",
              file=sys.stderr)
        return 2

    ok, why = cc.server_available()
    if not ok:
        print(f"✗ {why}", file=sys.stderr)
        return 2

    entry = cc.server_entry(Path(args.root).expanduser() if args.root else None)
    argv = [entry["command"], *entry["args"]]
    env = {**os.environ, **entry["env"]}
    # Running from a git worktree whose tree isn't what the editable install
    # points at: make sure this checkout wins.
    env.setdefault("PYTHONPATH", str(Path.cwd()))

    print(f"spawning: {' '.join(argv)}")
    print(f"store:    {entry['env']['M110_DATA_ROOT']}\n")

    client = Client(argv, env)
    warnings = []
    try:
        t0 = time.monotonic()
        init = client.rpc("initialize", {
            "protocolVersion": PROTO, "capabilities": {},
            "clientInfo": {"name": "m110-smoke", "version": "0"}})
        elapsed = time.monotonic() - t0
        if "error" in init:
            print(f"✗ handshake failed: {init['error']}", file=sys.stderr)
            return 1
        caps = sorted(init["result"]["capabilities"])
        print(f"✓ handshake      {elapsed:.2f}s   capabilities: {', '.join(caps)}")
        if elapsed > HANDSHAKE_BUDGET_S:
            warnings.append(
                f"handshake took {elapsed:.2f}s (budget {HANDSHAKE_BUDGET_S}s). "
                "On a first run that's usually the OS verifying a new binary; if it "
                "persists, something heavy (astropy?) is being imported at module "
                "scope and clients may time out.")
        client.notify("notifications/initialized")

        tools = [t["name"] for t in client.rpc("tools/list")["result"]["tools"]]
        print(f"✓ tools          {len(tools)}")
        for name in tools:
            print(f"                   {name}")

        prompts = [p["name"] for p in client.rpc("prompts/list")["result"]["prompts"]]
        print(f"✓ skills         {', '.join(prompts) or '(none)'}")

        overview, refused = client.call_tool("get_store_overview")
        if refused:
            # Almost always a data root that doesn't exist or was never opened by
            # the app. The server says so precisely; pass that straight through.
            print(f"✗ store          {refused}")
            print("\nThe server runs, but it can't read that library. Fix the path "
                  "(or open M110 once pointed at it) and re-run.")
            return 1
        if not overview.get("derived_available"):
            print(f"! store          {overview.get('note', 'no derived data yet')}")
            warnings.append("No derived data — open M110 and Refresh, or the "
                            "assistant can't answer questions about captures.")
        else:
            grand = overview["summary"]["grand"]
            print(f"✓ library        {overview['object_count']} objects · "
                  f"{grand['captured']} captured")
            if overview["ranking"]["context_stale"]:
                warnings.append("The cached ranking is stale — Recompute on the "
                                "Planning page for current priorities. (The "
                                "assistant discloses this rather than hiding it.)")

        rank, refused = client.call_tool("rank_targets", {"limit": 3})
        if refused:
            print(f"! ranking        {refused}")
        elif rank["rows"]:
            # Mark pins: they float above higher-scoring targets by design, which
            # otherwise reads as a sorting bug.
            print("✓ top targets    " + ", ".join(
                f"{r['slug']} ({r['score']}{'▲pinned' if r.get('pinned') else ''})"
                for r in rank["rows"]))
        else:
            print(f"! ranking        {rank['note']}")
    finally:
        stderr = client.close()

    print("\nServer is healthy — a client pointed at this config will work.")
    for w in warnings:
        print(f"\n  note: {w}")
    if stderr.strip():
        print("\n--- server stderr (diagnostics belong here, never on stdout) ---")
        for line in stderr.strip().splitlines()[:20]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

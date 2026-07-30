"""The outbox — the one place an assistant tool may create a file.

M0 shipped a strictly read-only server. That made saving a field guide
impossible, and copy-pasting markdown out of a chat is not a workflow. So the
invariant is relaxed, precisely:

    Before:  no tool writes.
    Now:     no tool MODIFIES or DELETES anything. A tool may CREATE a new file,
             only inside this outbox, subject to a quota.

The property with actual value was never "zero bytes written" — it was "the
assistant cannot damage or silently alter what you made". A brand-new file in a
staging directory does neither. In one line: *it can hand you things; it can't
change your library.*

What makes that safe rather than merely narrower:

* **Nothing here is authoritative.** The store reads none of it. Deleting the
  whole directory loses nothing the user authored, which is why `backup.py`
  excludes it.
* **Create-only.** `write()` refuses to overwrite; a colliding name gets a
  suffix, exactly as `fieldguide.save` already does.
* **One directory, provably.** Every path is resolved and re-checked against
  the outbox root *after* resolution, so traversal, absolute paths and symlinks
  pointing outward all fail closed.
* **Quotas.** A model in a loop can waste disk; it can't fill it.

Tier-1 artifacts (field guides, device plan files) and Tier-2 proposal
envelopes both land here, so the app has one queue to review rather than two.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from m110 import config

README = """\
# Assistant outbox — safe to delete

Things the AI assistant has handed to M110 but that you haven't accepted yet:
saved plans it drafted, and changes it proposed.

Nothing in here affects your library. M110 reads none of it until you accept an
item in the app (look for the "from the assistant" banner). Deleting this folder
throws away pending suggestions and nothing else.

This is the only folder the assistant can write to. It cannot change, move, or
delete anything else in your library.
"""

# Quotas. Generous for real use, small enough that a runaway model wastes little.
MAX_FILES = 200
MAX_BYTES_PER_FILE = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024

ARTIFACT_SUFFIXES = {".md", ".json", ".txt", ".csv"}
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


class OutboxError(Exception):
    """A write was refused. The message is shown to the model, so it explains."""


@dataclass(frozen=True)
class OutboxItem:
    """One pending item, as the app sees it."""
    name: str
    path: Path
    kind: str                 # "artifact" | "proposal"
    created: datetime
    size_bytes: int
    title: str = ""
    summary: str = ""
    action: str = ""          # proposals only: the envelope's action
    target: str = ""          # proposals only: e.g. the slug it applies to


# ── paths ────────────────────────────────────────────────────────────────────

def outbox_dir() -> Path:
    return Path(config.ASSISTANT_OUTBOX)


def ensure_outbox() -> Path:
    """Create the outbox on first use. Idempotent, and never touches anything else."""
    d = outbox_dir()
    d.mkdir(parents=True, exist_ok=True)
    readme = d.parent / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    return d


def safe_name(name: str, *, default: str = "item") -> str:
    """A filename that cannot escape the outbox or surprise a file manager.

    Strips directory separators outright rather than resolving them — a name is
    a name here, never a path — then normalizes and whitelists characters.
    """
    name = unicodedata.normalize("NFKD", str(name or ""))
    name = name.replace("\\", "/").split("/")[-1]        # any dir part is discarded
    name = name.strip().strip(".")                       # no leading dot, no trailing dots
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    stem = _SAFE_STEM.sub("-", stem).strip("-")[:80] or default
    suffix = _SAFE_STEM.sub("", suffix).lower()[:8]
    return f"{stem}.{suffix}" if suffix else stem


def _resolved_within(path: Path) -> Path:
    """Resolve, then verify containment. Order matters: checking before resolving
    is how symlink escapes get through."""
    root = outbox_dir().resolve()
    full = (root / path).resolve()
    if full != root and root not in full.parents:
        raise OutboxError("refused: that path is outside the assistant outbox")
    return full


# ── quotas ───────────────────────────────────────────────────────────────────

def _existing() -> list[Path]:
    d = outbox_dir()
    return sorted(p for p in d.glob("*") if p.is_file()) if d.is_dir() else []


def usage() -> dict:
    files = _existing()
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files),
            "max_files": MAX_FILES, "max_total_bytes": MAX_TOTAL_BYTES}


def _check_quota(incoming: int) -> None:
    used = usage()
    if incoming > MAX_BYTES_PER_FILE:
        raise OutboxError(
            f"refused: {incoming:,} bytes exceeds the {MAX_BYTES_PER_FILE:,}-byte "
            "limit for a single item")
    if used["files"] >= MAX_FILES:
        raise OutboxError(
            f"refused: the outbox already holds {used['files']} items (limit "
            f"{MAX_FILES}). The user needs to review them in M110 first.")
    if used["bytes"] + incoming > MAX_TOTAL_BYTES:
        raise OutboxError(
            f"refused: the outbox is full ({used['bytes']:,} of "
            f"{MAX_TOTAL_BYTES:,} bytes). The user needs to review it in M110.")


# ── the writer ───────────────────────────────────────────────────────────────

def write(name: str, text: str, *, kind: str = "artifact") -> Path:
    """Create a new file in the outbox. Never overwrites; returns the real path."""
    if kind not in ("artifact", "proposal"):
        raise OutboxError(f"unknown outbox kind: {kind!r}")
    data = text.encode("utf-8")
    _check_quota(len(data))

    clean = safe_name(name)
    if Path(clean).suffix.lower() not in ARTIFACT_SUFFIXES:
        raise OutboxError(
            f"refused: {clean!r} — the outbox holds "
            f"{', '.join(sorted(ARTIFACT_SUFFIXES))} files only")

    ensure_outbox()
    dest = _resolved_within(Path(clean))
    # Create-only: a collision gets a suffix rather than replacing anything.
    stem, suffix = Path(clean).stem, Path(clean).suffix
    i = 1
    while dest.exists():
        dest = _resolved_within(Path(f"{stem}-{i}{suffix}"))
        i += 1

    # Exclusive create: if something appeared between the check and the write,
    # fail rather than clobber it.
    with open(dest, "x", encoding="utf-8") as f:
        f.write(text)
    return dest


def write_proposal(envelope: dict) -> Path:
    """Stage a proposal envelope so the app can offer to apply it."""
    action = envelope.get("action", "proposal")
    stamp = (envelope.get("created") or "")[:19].replace(":", "").replace("-", "")
    return write(f"{stamp or 'proposal'}-{action}.json",
                 json.dumps(envelope, indent=2), kind="proposal")


# ── reading (the app side) ───────────────────────────────────────────────────

def _describe(path: Path) -> OutboxItem:
    st = path.stat()
    created = datetime.fromtimestamp(st.st_mtime)
    if path.suffix.lower() == ".json":
        try:
            env = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            env = {}
        if env.get("schema", "").startswith("m110.proposal/"):
            return OutboxItem(
                name=path.name, path=path, kind="proposal", created=created,
                size_bytes=st.st_size, title=env.get("title", path.stem),
                summary=env.get("summary", ""), action=env.get("action", ""),
                target=(env.get("target") or {}).get("slug", ""))
    title = ""
    if path.suffix.lower() == ".md":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                title = line.lstrip("# ").strip()
                break
    return OutboxItem(name=path.name, path=path, kind="artifact", created=created,
                      size_bytes=st.st_size, title=title or path.stem)


def items() -> list[OutboxItem]:
    """Everything pending, newest first."""
    return sorted((_describe(p) for p in _existing()),
                  key=lambda i: i.created, reverse=True)


def count() -> int:
    return len(_existing())


def read(name: str) -> str:
    return _resolved_within(Path(safe_name(name))).read_text(encoding="utf-8")


def discard(name: str) -> bool:
    """Delete one pending item. App-side only — no tool calls this."""
    path = _resolved_within(Path(safe_name(name)))
    if not path.is_file():
        return False
    path.unlink()
    return True

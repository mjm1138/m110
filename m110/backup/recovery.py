"""Make a pooled backup recoverable without M110.

The honest cost of content-addressed storage is that `objects/` on its own is a
bag of hash-named blobs: every byte of your library is there, but not the names
or the layout. A mirrored snapshot needs no software at all to restore — it *is*
your files, in the right folders. Losing that outright would be a bad trade for a
data-safety feature, so a pooled backup carries its own way back:

* `INDEX.tsv` — plain text, one line per file: path, hash, size. Greppable with
  no tools at all.
* `latest-manifest.json.gz` — a full-fidelity copy of the newest snapshot's
  manifest at the top level, so losing `snapshots/` isn't fatal.
* `restore.py` — stdlib-only, no install, rebuilds a tree from any manifest. The
  recovery instructions travel *with* the data instead of living in
  documentation the user won't have at the moment they need it.
* `README.txt` — what the folders are, in a paragraph.

(On a destination that supports hardlinks there is also `latest/`, a real
browsable tree costing no extra bytes. That's the nicest answer — but it's absent
exactly where the pooled format is chosen automatically, i.e. where the
filesystem can't link, which is why these four exist.)
"""
from __future__ import annotations

import gzip
import json

INDEX_KEY = "INDEX.tsv"
LATEST_MANIFEST_KEY = "latest-manifest.json.gz"
RESTORE_SCRIPT_KEY = "restore.py"
README_KEY = "README.txt"

RESTORE_SCRIPT = '''#!/usr/bin/env python3
"""Rebuild files from an M110 backup, without M110.

This backup stores every file once under objects/, named by the SHA-256 of its
contents, and records what a backup contained in a manifest under snapshots/.
This script reads a manifest and writes the files back out with their real names.

It uses nothing but the Python standard library. Run it from this folder:

    python3 restore.py                          # newest backup -> ./restored
    python3 restore.py snapshots/<name>.json.gz  ~/somewhere
    python3 restore.py latest-manifest.json.gz   ~/somewhere  Images/M51

The third argument, if given, restores only paths starting with that prefix.

Doing it by hand is fine too: INDEX.tsv lists every file with its hash, and the
object for hash abcdef... lives at objects/ab/cd/abcdef...
"""
import gzip
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_manifest(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def object_path(sha):
    return os.path.join(HERE, "objects", sha[:2], sha[2:4], sha)


def main(argv):
    manifest_path = argv[0] if argv else os.path.join(HERE, "latest-manifest.json.gz")
    out_dir = argv[1] if len(argv) > 1 else os.path.join(os.getcwd(), "restored")
    prefix = argv[2] if len(argv) > 2 else ""

    if not os.path.exists(manifest_path):
        sys.exit("No manifest at %s — pass one from snapshots/" % manifest_path)
    files = load_manifest(manifest_path).get("files", {})

    written = missing = 0
    for rel in sorted(files):
        if prefix and not rel.startswith(prefix):
            continue
        src = object_path(files[rel]["sha256"])
        if not os.path.isfile(src):
            print("MISSING %s" % rel)
            missing += 1
            continue
        dst = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o644)
        written += 1

    print("Restored %d file(s) to %s" % (written, out_dir))
    if missing:
        sys.exit("%d file(s) had no stored object — this backup is incomplete." % missing)


if __name__ == "__main__":
    main(sys.argv[1:])
'''

README = """M110 backup — what's in this folder
===================================

objects/     Every file from your library, stored once, named by the SHA-256 of
             its contents. Read-only on purpose: several backups share the same
             file, so editing one here would change all of them.
snapshots/   One file per backup, listing what that backup contained: the real
             path of every file and which object holds its contents. Gzipped
             JSON — "gunzip -c <file>" reads it anywhere.
latest/      A browsable copy of the most recent backup, with real filenames and
             folders. It costs no extra space (the files are shared with
             objects/). Only present when this destination supports it.
INDEX.tsv    The newest backup as plain text: path, hash, size.
restore.py   Rebuilds files from a manifest using only Python's standard
             library — no M110 needed. Run "python3 restore.py" here.
state.json   A summary M110 keeps for speed. Nothing depends on it.

Every backup is complete on its own. There is no chain to replay: you can
restore the oldest one exactly as easily as the newest.
"""


def gzip_json(payload: dict) -> bytes:
    raw = json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")
    # mtime=0 keeps the bytes deterministic for a given manifest.
    return gzip.compress(raw, mtime=0)


def read_gzip_json(blob: bytes) -> dict:
    if blob[:2] == b"\x1f\x8b":
        blob = gzip.decompress(blob)
    return json.loads(blob.decode("utf-8"))


def index_text(manifest: dict) -> str:
    lines = ["# path\tsha256\tsize",
             f"# backup {manifest.get('timestamp', '')} "
             f"({manifest.get('file_count', 0)} files)"]
    for rel, meta in sorted(manifest.get("files", {}).items()):
        lines.append(f"{rel}\t{meta.get('sha256', '')}\t{meta.get('size', 0)}")
    return "\n".join(lines) + "\n"


def write_recovery(backend, manifest: dict, manifest_blob: bytes) -> None:
    """Refresh the four top-level recovery artifacts after a successful backup."""
    backend.put_bytes(LATEST_MANIFEST_KEY, manifest_blob)
    backend.put_bytes(INDEX_KEY, index_text(manifest).encode("utf-8"))
    backend.put_bytes(RESTORE_SCRIPT_KEY, RESTORE_SCRIPT.encode("utf-8"))
    backend.put_bytes(README_KEY, README.encode("utf-8"))

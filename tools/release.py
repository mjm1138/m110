#!/usr/bin/env python3
"""Cut an M110 release — one command, one version number.

    python tools/release.py 0.2.0b2              # full release
    python tools/release.py 0.2.0b2 --dry-run    # print every step, change nothing
    python tools/release.py 0.2.0b2 --resume-from tag
    python tools/release.py 0.2.0b2 --skip-macos # non-Mac host (no cert)

Automates the mechanical half of RELEASING.md and, more importantly, the parts
that have actually bitten:

* **Three version spellings from one input.** PEP 440 `0.2.0b2` (pyproject +
  `__init__`), SemVer `v0.2.0-beta.2` (the git tag — what `release.yml` triggers
  on), and numeric `0.2.0` (the DMG filename / `CFBundleShortVersionString`).
  Deriving all three from one argument removes the class of typo where the tag and
  the package disagree.
* **The 0.0.1 trap** — reinstall + assert `importlib.metadata` reports the new
  version *before* anything is built, so a stale editable install can't stamp the
  wrong number into the DMG and the About box.
* **The changelog drift** — `[Unreleased]` is moved into a dated, versioned
  section. Both 0.1.0-beta.3 and 0.2.0-beta.1 shipped with the changelog trailing
  because this was a manual step.
* **The untested pipeline** — dispatches `release.yml` on `main` and waits for
  green *before* tagging, so a broken build surfaces while it's still cheap
  (RELEASING.md step 0).

What it deliberately does NOT do — these need a human:
* decide the version number (that's the argument) or write the changelog prose
  (it must already be under `[Unreleased]`);
* the manual test pass (TESTING.md) — the script asks you to confirm you've done it;
* verify the DMG is Gatekeeper-clean on a *fresh* Mac (your dev cert masks this);
* write the announce post.

Every phase is idempotent-ish and re-runnable via `--resume-from`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTE = os.environ.get("M110_REMOTE", "github")
WORKFLOW = "release.yml"

PHASES = ["preflight", "bump", "changelog", "docs", "commit", "smoke", "tag",
          "wait", "macos", "upload", "verify"]


class Fail(SystemExit):
    def __init__(self, msg: str):
        super().__init__(f"\n\033[31m✗ {msg}\033[0m\n")


def say(msg: str) -> None:
    print(f"\033[36m==>\033[0m {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}", flush=True)


def run(cmd: list[str], *, dry: bool = False, capture: bool = False,
        check: bool = True, cwd: Path = ROOT) -> str:
    """Run a command. `dry` prints instead of executing (read-only commands should
    pass dry=False so a --dry-run still *inspects* the real repo)."""
    if dry:
        print(f"  \033[33m[dry-run]\033[0m {' '.join(cmd)}")
        return ""
    r = subprocess.run(cmd, cwd=cwd, text=True,
                       capture_output=capture or not check)
    if check and r.returncode != 0:
        out = (r.stdout or "") + (r.stderr or "")
        raise Fail(f"command failed: {' '.join(cmd)}\n{out.strip()}")
    return (r.stdout or "").strip()


# ── the three version spellings ───────────────────────────────────────────────

def versions(arg: str) -> dict:
    """One input → every spelling the release needs.

    Accepts either PEP 440 (`0.2.0b2`) or the tag form (`v0.2.0-beta.2`); they
    normalize to the same `packaging` Version, so both are safe to type.
    """
    from packaging.version import InvalidVersion, Version
    raw = arg.strip()
    try:
        v = Version(raw[1:] if raw[:1].lower() == "v" else raw)
    except InvalidVersion:
        raise Fail(f"not a valid version: {arg!r} (try 0.2.0b2 or v0.2.0-beta.2)")

    pep440 = str(v)                       # canonical: 0.2.0b2
    numeric = v.base_version              # 0.2.0 — the DMG / CFBundleShortVersionString
    if v.pre:                             # ('b', 2) → v0.2.0-beta.2 (SemVer, for the tag)
        kind = {"a": "alpha", "b": "beta", "rc": "rc"}[v.pre[0]]
        tag = f"v{numeric}-{kind}.{v.pre[1]}"
    else:
        tag = f"v{numeric}"
    return {"pep440": pep440, "numeric": numeric, "tag": tag,
            "prerelease": bool(v.pre or v.dev)}


# ── phases ────────────────────────────────────────────────────────────────────

def preflight(V: dict, args) -> None:
    say("Preflight")
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    if branch != "main" and not args.force:
        raise Fail(f"on branch {branch!r}, expected 'main' (--force to override)")
    ok(f"on {branch}")

    if run(["git", "status", "--porcelain"], capture=True):
        raise Fail("working tree is dirty — commit or stash first")
    ok("working tree clean")

    run(["git", "fetch", REMOTE, "--quiet"])
    local = run(["git", "rev-parse", "HEAD"], capture=True)
    remote = run(["git", "rev-parse", f"{REMOTE}/main"], capture=True)
    if local != remote and not args.force:
        raise Fail(f"local main != {REMOTE}/main — pull/push first (--force to override)")
    ok(f"in sync with {REMOTE}/main")

    existing = run(["git", "tag", "-l", V["tag"]], capture=True)
    if existing:
        raise Fail(f"tag {V['tag']} already exists locally — bump the version or delete it")
    if run(["gh", "release", "view", V["tag"], "--json", "tagName"],
           capture=True, check=False):
        raise Fail(f"a GitHub Release for {V['tag']} already exists")
    ok(f"{V['tag']} is free")

    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"^## \[Unreleased\]\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m or not m.group(1).strip():
        raise Fail("CHANGELOG.md has no content under [Unreleased] — write the "
                   "user-facing notes first (the script moves them, it can't author them)")
    ok(f"changelog [Unreleased] has {len(m.group(1).strip().splitlines())} lines")

    say("Running the test suite (the gate)")
    run([sys.executable, "-m", "pytest", "-q"])
    ok("tests green")

    if not args.skip_macos:
        if sys.platform != "darwin":
            raise Fail("not on macOS — pass --skip-macos to cut a release without the DMG")
        ident = os.environ.get("SIGN_IDENTITY", "")
        if not ident:
            raise Fail("SIGN_IDENTITY unset — export your Developer ID, or --skip-macos")
        found = run(["security", "find-identity", "-v", "-p", "codesigning"],
                    capture=True, check=False)
        if ident.split("(")[0].strip() not in found:
            raise Fail(f"signing identity not in the keychain: {ident!r}")
        ok("signing identity present")

    if not args.yes:
        print("\n  Manual test pass done (TESTING.md)? Release notes read right?")
        if input("  Type the version to confirm: ").strip() != V["pep440"]:
            raise Fail("confirmation did not match — aborting")


def bump(V: dict, args) -> None:
    say(f"Bumping to {V['pep440']}  (tag {V['tag']}, DMG M110-{V['numeric']}.dmg)")
    for path, pattern, repl in (
        (ROOT / "pyproject.toml", r'^version = ".*"',
         f'version = "{V["pep440"]}"'),
        (ROOT / "m110" / "__init__.py", r'^__version__ = ".*"',
         f'__version__ = "{V["pep440"]}"'),
    ):
        text = path.read_text()
        new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
        if n != 1:
            raise Fail(f"could not find the version line in {path.name}")
        if args.dry_run:
            print(f"  \033[33m[dry-run]\033[0m {path.name} → {repl}")
        else:
            path.write_text(new)
            ok(f"{path.name} → {V['pep440']}")

    # The 0.0.1 trap: the packaged Info.plist reads importlib.metadata, so a stale
    # editable install silently stamps the wrong version into the DMG + About box.
    say("Reinstalling so the installed metadata matches")
    run([sys.executable, "-m", "pip", "install", "-e", ".[build]", "-q"], dry=args.dry_run)
    if not args.dry_run:
        got = run([sys.executable, "-c",
                   "import importlib.metadata as m; print(m.version('m110'))"],
                  capture=True)
        if got != V["pep440"]:
            raise Fail(f"installed metadata says {got!r}, expected {V['pep440']!r} "
                       "— the 0.0.1 trap; the build would stamp the wrong version")
        ok(f"importlib.metadata reports {got}")


def changelog(V: dict, args) -> None:
    say("Moving [Unreleased] → a dated section")
    path = ROOT / "CHANGELOG.md"
    text = path.read_text()
    heading = f"## [{V['tag'].lstrip('v')}] - {date.today().isoformat()}"
    new, n = re.subn(r"^## \[Unreleased\]\s*\n", f"## [Unreleased]\n\n{heading}\n\n",
                     text, count=1, flags=re.M)
    if n != 1:
        raise Fail("no [Unreleased] heading in CHANGELOG.md")
    if args.dry_run:
        print(f"  \033[33m[dry-run]\033[0m CHANGELOG.md → insert {heading!r}")
    else:
        path.write_text(new)
        ok(heading)


def docs(V: dict, args) -> None:
    """Render the versioned docs site.

    After `changelog` so the release's own entries are on the published page, and
    before `commit` because Cloudflare Pages deploys `site/` straight from the
    repo — unrendered docs are unpublished docs. `latest/` moves to this release.

    Reads the **working tree**, not `--from-tag`: the tag does not exist yet at
    this point in the pipeline (`tag` runs three phases later), and the tree is
    exactly what is about to become it. `--from-tag` is for backfilling a release
    that already happened, where the tree is no longer that version.
    """
    say("Rendering the docs site")
    if args.dry_run:
        print(f"  \033[33m[dry-run]\033[0m site/docs/{V['tag']}/ (+ latest/)")
        return
    sys.path.insert(0, str(ROOT / "tools"))
    import build_docs
    build_docs.build(V["tag"], quiet=True)
    ok(f"site/docs/{V['tag']}/ + latest/")


def commit(V: dict, args) -> None:
    say("Committing the bump")
    run(["git", "add", "pyproject.toml", "m110/__init__.py", "CHANGELOG.md",
         "site/docs"], dry=args.dry_run)
    run(["git", "commit", "-m", f"release {V['pep440']}"], dry=args.dry_run)
    run(["git", "push", REMOTE, "main"], dry=args.dry_run)
    ok(f"pushed to {REMOTE}/main")


def smoke(V: dict, args) -> None:
    # RELEASING.md step 0: release.yml only triggers on a tag, so nothing else ever
    # exercises it. Prove it builds BEFORE the tag exists — a failure here costs a
    # re-run; a failure after tagging costs a half-published Release.
    say("Smoke-testing the release pipeline on main (no Release is created)")
    if args.dry_run:
        print(f"  \033[33m[dry-run]\033[0m gh workflow run {WORKFLOW} --ref main; gh run watch")
        return
    run(["gh", "workflow", "run", WORKFLOW, "--ref", "main"])
    time.sleep(12)
    rid = _latest_run("workflow_dispatch")
    ok(f"dispatched run {rid}")
    _watch(rid, "smoke build")


def tag(V: dict, args) -> None:
    say(f"Tagging {V['tag']}")
    run(["git", "tag", "-a", V["tag"], "-m", f"M110 {V['tag']}"], dry=args.dry_run)
    run(["git", "push", REMOTE, V["tag"]], dry=args.dry_run)
    ok(f"pushed {V['tag']} → release.yml is building")


def wait(V: dict, args) -> None:
    say("Waiting for CI to build Linux + Windows and publish the Release")
    if args.dry_run:
        print("  \033[33m[dry-run]\033[0m gh run watch; gh release view")
        return
    time.sleep(15)
    rid = _latest_run("push")
    _watch(rid, "release build")
    assets = _assets(V["tag"])
    ok(f"Release {V['tag']} has {len(assets)} asset(s): {', '.join(assets)}")


def macos(V: dict, args) -> None:
    if args.skip_macos:
        say("Skipping the macOS DMG (--skip-macos)")
        return
    say("Building + signing + notarizing the macOS DMG (several minutes)")
    dmg = ROOT / "dist" / f"M110-{V['numeric']}.dmg"
    run(["./packaging/macos/build_release.sh"], dry=args.dry_run)
    if not args.dry_run and not dmg.is_file():
        raise Fail(f"expected {dmg} — build_release.sh did not produce it")
    # Notarize + staple the DMG itself, so the *download* is Gatekeeper-clean and
    # not just the .app inside it.
    say("Notarizing + stapling the DMG")
    run(["xcrun", "notarytool", "submit", str(dmg),
         "--keychain-profile", "M110-notary", "--wait"], dry=args.dry_run)
    run(["xcrun", "stapler", "staple", str(dmg)], dry=args.dry_run)
    if not args.dry_run:
        run(["spctl", "-a", "-t", "open", "--context", "context:primary-signature",
             "-v", str(dmg)], check=False)
        ok(f"{dmg.name} signed, notarized, stapled")


def upload(V: dict, args) -> None:
    if args.skip_macos:
        say("Skipping the DMG upload (--skip-macos)")
        return
    dmg = ROOT / "dist" / f"M110-{V['numeric']}.dmg"
    say(f"Uploading {dmg.name} to the {V['tag']} Release")
    run(["gh", "release", "upload", V["tag"], str(dmg), "--clobber"], dry=args.dry_run)
    ok("uploaded")


def verify(V: dict, args) -> None:
    say("Verifying the Release")
    if args.dry_run:
        print("  \033[33m[dry-run]\033[0m gh release view")
        return
    assets = _assets(V["tag"])
    want = [".dmg", ".AppImage", "setup.exe"]
    if args.skip_macos:
        want.remove(".dmg")
    missing = [w for w in want if not any(a.endswith(w) or w in a for a in assets)]
    for a in assets:
        ok(a)
    if missing:
        raise Fail(f"Release {V['tag']} is missing: {', '.join(missing)}")
    print(f"\n\033[32m✓ {V['tag']} is published\033[0m — "
          f"https://github.com/mjm1138/m110/releases/tag/{V['tag']}\n"
          "  Remaining (human): check the DMG on a Mac WITHOUT your dev cert, "
          "then announce.\n")


# ── gh helpers ────────────────────────────────────────────────────────────────

def _latest_run(event: str) -> str:
    out = run(["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "5",
               "--json", "databaseId,event,status"], capture=True)
    for r in json.loads(out):
        if r["event"] == event and r["status"] != "completed":
            return str(r["databaseId"])
    for r in json.loads(out):          # fall back to the newest of that event
        if r["event"] == event:
            return str(r["databaseId"])
    raise Fail(f"no {WORKFLOW} run found for event {event!r}")


def _watch(run_id: str, what: str) -> None:
    print(f"  watching {what} (run {run_id})…")
    subprocess.run(["gh", "run", "watch", run_id, "--exit-status"], cwd=ROOT)
    out = run(["gh", "run", "view", run_id, "--json", "conclusion"], capture=True)
    concl = json.loads(out)["conclusion"]
    if concl != "success":
        raise Fail(f"{what} finished {concl!r} — "
                   f"https://github.com/mjm1138/m110/actions/runs/{run_id}")
    ok(f"{what} green")


def _assets(tag: str) -> list[str]:
    out = run(["gh", "release", "view", tag, "--json", "assets"],
              capture=True, check=False)
    if not out:
        raise Fail(f"no GitHub Release for {tag}")
    return [a["name"] for a in json.loads(out).get("assets", [])]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Cut an M110 release from one version number.",
        epilog="e.g. python tools/release.py 0.2.0b2")
    p.add_argument("version", help="PEP 440 (0.2.0b2) or tag form (v0.2.0-beta.2)")
    p.add_argument("--dry-run", action="store_true",
                   help="inspect + print every step, change nothing")
    p.add_argument("--skip-macos", action="store_true",
                   help="no DMG (not on a Mac / no cert)")
    p.add_argument("--resume-from", choices=PHASES, metavar="PHASE",
                   help=f"restart mid-release: {', '.join(PHASES)}")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--force", action="store_true",
                   help="allow a dirty/unsynced/non-main tree (dangerous)")
    args = p.parse_args()

    V = versions(args.version)
    start = PHASES.index(args.resume_from) if args.resume_from else 0
    fns = {"preflight": preflight, "bump": bump, "changelog": changelog,
           "docs": docs, "commit": commit, "smoke": smoke, "tag": tag,
           "wait": wait, "macos": macos, "upload": upload, "verify": verify}

    print(f"\n\033[1mM110 release {V['pep440']}\033[0m — tag {V['tag']}, "
          f"DMG M110-{V['numeric']}.dmg"
          f"{'  [DRY RUN]' if args.dry_run else ''}\n")
    for name in PHASES[start:]:
        fns[name](V, args)


if __name__ == "__main__":
    main()

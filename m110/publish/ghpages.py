"""GitHub Pages publisher — deploy the rendered static site to a `gh-pages`
branch (BUGS #27a; the port of the Astronomy `deploy.sh` / ghp-import workflow).

Shells out to the user's installed **git**, so auth rides on their existing
setup (SSH key / credential helper) — no new dependency, no tokens handled
here. Qt-free.

Two deploy modes trade repo size against upload time:

* **replace** (default) — each deploy is a fresh single-commit orphan branch,
  force-pushed (ghp-import `-f` semantics). The remote stays lean forever no
  matter how often renders churn, but every publish re-uploads the whole site.
* **incremental** — the deployed tip is fetched first and the new commit
  descends from it, so the push sends only objects the remote lacks. Uploads
  are a fraction of the site once it's up (web derivatives are content-hashed,
  so an unchanged image is literally the same blob), at the cost of a history
  that accumulates every superseded image forever.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from . import site
from .errors import PublishError

DEFAULT_BRANCH = "gh-pages"
DEPLOY_MODES = ("replace", "incremental")
DEFAULT_DEPLOY_MODE = "replace"

_GIT_TIMEOUT = 600     # seconds — local plumbing only (init/add/commit); the
                       # network transfers have NO wall-clock cap (a first
                       # full-site upload can legitimately take arbitrarily long
                       # on a slow uplink) — Cancel is the escape hatch, and it
                       # kills the git process for real.
_STREAM_POLL_S = 0.2
# git --progress writes "Writing objects:  42% (123/291), 88.10 MiB | 1.2 MiB/s"
# (and "Receiving objects: …" when fetching).
_PROGRESS_RE = re.compile(rb"(?:Writing|Receiving) objects:\s+\d+%\s+\((\d+)/(\d+)\)")
# The site folder is generated content that must publish verbatim, so the deploy
# repo neutralises the user's global excludes — a global "*.jpg"/"*.png" rule
# would otherwise silently strip the whole gallery (the hazard ghp-import
# sidesteps by force-adding). Only OS junk is excluded instead.
_JUNK_EXCLUDES = (".DS_Store", "Thumbs.db", "._*")

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$")
_GH_URL_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$")


def normalize_repo(text: str) -> str:
    """Turn user input into a git push URL.

    Bare ``owner/repo`` becomes the SSH form (``git@github.com:owner/repo.git``
    — the auth most likely already configured for a GitHub user); anything that
    already looks like a URL/remote path passes through verbatim.
    """
    text = (text or "").strip()
    if _OWNER_REPO_RE.match(text):
        return f"git@github.com:{text}.git"
    return text


def pages_url(repo: str) -> str | None:
    """The https://<owner>.github.io/<repo>/ URL a github.com repo serves at
    (root URL for an ``<owner>.github.io`` repo); None if not github.com."""
    m = _GH_URL_RE.match(normalize_repo(repo))
    if not m:
        return None
    owner, name = m.group("owner"), m.group("repo")
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{name}/"


def _run_git(args, *, cwd=None, action="run git"):
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                             text=True, timeout=_GIT_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise PublishError(f"git timed out trying to {action}.") from exc
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        raise PublishError(f"git failed to {action}:\n{detail}")
    return res


def _git_stream(args, *, should_cancel=None, progress=None) -> tuple[int, str]:
    """Run a network git command with its `--progress` stderr streamed.

    Object counts are parsed into `progress(done, total)`; cancellation **kills
    the process** (no orphaned transfer racing a later deploy); there is no
    wall-clock timeout. Returns (returncode, stderr tail) — the caller decides
    whether a failure is fatal.
    """
    cancelled = should_cancel or (lambda: False)
    proc = subprocess.Popen(["git", *args], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    tail: deque[bytes] = deque(maxlen=30)   # last stderr lines, for the error
    counts = [0, 0]

    def _read_stderr():
        buf = b""
        while True:
            chunk = proc.stderr.read(256)
            if not chunk:
                break
            buf += chunk
            while True:
                m = re.search(rb"[\r\n]", buf)
                if m is None:
                    break
                line, buf = buf[:m.start()], buf[m.end():]
                if line:
                    tail.append(line)
                    pm = _PROGRESS_RE.search(line)
                    if pm:
                        counts[0], counts[1] = int(pm.group(1)), int(pm.group(2))
        if buf:
            tail.append(buf)

    reader = threading.Thread(target=_read_stderr, daemon=True)
    reader.start()
    reported = (0, 0)
    while proc.poll() is None:
        if cancelled():
            proc.kill()
            proc.wait()
            raise PublishError("Cancelled.")
        if progress and counts[1] and tuple(counts) != reported:
            reported = tuple(counts)
            progress(*reported)
        time.sleep(_STREAM_POLL_S)
    reader.join(timeout=5)
    if progress and counts[1] and proc.returncode == 0:
        progress(counts[1], counts[1])
    return proc.returncode, b"\n".join(tail).decode("utf-8", "replace").strip()


def _fetch_tip(git_dir_args: list, url: str, branch: str, *,
               should_cancel=None, progress=None) -> bool:
    """Fetch the deployed branch's tip so the next commit can descend from it.

    Tries a **blob-less** shallow fetch first: the commit's trees alone are
    enough for the push to work out what the remote already has, so this costs
    a few KB instead of re-downloading the whole deployed site. Falls back to a
    plain shallow fetch where the server doesn't support partial clone.
    Returns False when the branch doesn't exist yet (first deploy) or the
    remote can't be read — the deploy then proceeds parentless, and a genuine
    auth/URL problem surfaces on the push, where the message is actionable.
    """
    for extra in (["--filter=blob:none"], []):
        rc, err = _git_stream([*git_dir_args, "fetch", "--depth", "1",
                               "--progress", *extra, url, branch],
                              should_cancel=should_cancel, progress=progress)
        if rc == 0:
            return True
        if "couldn't find remote ref" in err.lower():
            return False          # no deployed branch yet
    return False


def deploy(site_dir: Path, repo: str, branch: str = DEFAULT_BRANCH, *,
           mode: str = DEFAULT_DEPLOY_MODE, should_cancel=None, progress=None,
           status=None) -> dict:
    """Publish `site_dir` to `branch` on `repo` (see the module docstring for
    the two modes).

    Returns {"repo", "branch", "mode", "url", "incremental"}. Raises
    PublishError on any failure (git missing, nothing rendered, push rejected)
    with git's own stderr so an auth/repo problem is actionable.
    `progress`/`status` surface the transfer (objects done / total; a stage
    label) in the UI.
    """
    cancelled = should_cancel or (lambda: False)
    site_dir = Path(site_dir)
    url = normalize_repo(repo)
    mode = mode if mode in DEPLOY_MODES else DEFAULT_DEPLOY_MODE
    if not url:
        raise PublishError("Enter a GitHub repository (owner/repo or a git URL).")
    if shutil.which("git") is None:
        raise PublishError(
            "git was not found. Deploying to GitHub Pages needs the git "
            "command-line tool installed and on PATH.")
    if not (site_dir / "index.html").exists():
        raise PublishError(
            f"No rendered site found at {site_dir} (missing index.html).")

    # GitHub Pages runs Jekyll unless told not to; .nojekyll keeps it serving
    # the files exactly as rendered (ghp-import -n).
    nojekyll = site_dir / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="m110-ghpages-") as tmp:
        gd = Path(tmp) / ".git"
        git_dir = ["--git-dir", str(gd), "--work-tree", str(site_dir)]
        if status:
            status("Preparing deploy…")
        _run_git(["init", "-q", str(tmp)], action="initialise the deploy repo")
        # Commit identity local to the throwaway repo — works on machines with
        # no global git identity configured.
        _run_git([*git_dir, "config", "user.name", "M110"], action="configure")
        _run_git([*git_dir, "config", "user.email", "m110@localhost"],
                 action="configure")
        _run_git([*git_dir, "config", "core.excludesFile", ""], action="configure")
        (gd / "info").mkdir(parents=True, exist_ok=True)
        (gd / "info" / "exclude").write_text("\n".join(_JUNK_EXCLUDES) + "\n",
                                             encoding="utf-8")
        # Deterministic branch name regardless of the user's init.defaultBranch.
        _run_git([*git_dir, "symbolic-ref", "HEAD", "refs/heads/deploy"],
                 action="configure")

        incremental = False
        if mode == "incremental":
            if status:
                status("Checking the deployed site…")
            if _fetch_tip(git_dir, url, branch, should_cancel=should_cancel,
                          progress=progress):
                # Point the branch at the deployed tip **without touching the
                # work tree** — it *is* the rendered site, so `checkout` /
                # `reset --hard` must never be used here. The index stays
                # empty, so the commit below records exactly what's on disk,
                # with the deployed tip as its parent → the push sends only
                # objects the remote lacks, and files swept from the render are
                # simply absent from the new tree (deleted on the branch).
                _run_git([*git_dir, "update-ref", "refs/heads/deploy",
                          "FETCH_HEAD"], action="read the deployed site")
                incremental = True

        if cancelled():
            raise PublishError("Cancelled.")
        if status:
            status("Preparing deploy…")
        _run_git([*git_dir, "add", "-A"], action="stage the site")
        # --allow-empty: an unchanged incremental re-publish is a no-op commit,
        # not an error.
        _run_git([*git_dir, "commit", "-q", "--allow-empty", "-m",
                  f"Publish {datetime.now().strftime('%Y-%m-%d %H:%M')} (M110)"],
                 action="commit the site")
        if cancelled():
            raise PublishError("Cancelled.")
        if status:
            status("Uploading to GitHub…")
        rc, err = _git_stream(
            [*git_dir, "push", "--force", "--progress", url,
             f"HEAD:refs/heads/{branch}"],
            should_cancel=should_cancel, progress=progress)
        if rc != 0:
            raise PublishError(f"git failed to push to {url}:\n{err}")

    return {"repo": url, "branch": branch, "mode": mode,
            "incremental": incremental, "url": pages_url(repo)}


def render(options, *, should_cancel=None, progress=None, status=None,
           prior=None) -> dict:
    """Publisher entry point: render the static site (or reuse `prior`, the
    static-site result from the same run) and deploy it to GitHub Pages."""
    if not (options.github_repo or "").strip():
        raise PublishError(
            "Enter a GitHub repository (owner/repo or a git URL) to deploy "
            "to GitHub Pages.")
    result = prior or site.render(options, should_cancel=should_cancel,
                                  progress=progress, status=status)
    if should_cancel and should_cancel():
        raise PublishError("Cancelled.")
    dep = deploy(options.output_dir, options.github_repo,
                 options.github_branch, mode=options.github_deploy_mode,
                 should_cancel=should_cancel, progress=progress, status=status)
    return {**result, **dep}

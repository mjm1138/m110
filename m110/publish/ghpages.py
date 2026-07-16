"""GitHub Pages publisher — deploy the rendered static site to a `gh-pages`
branch (BUGS #27a; the port of the Astronomy `deploy.sh` / ghp-import workflow).

Shells out to the user's installed **git**, so auth rides on their existing
setup (SSH key / credential helper) — no new dependency, no tokens handled
here. Each deploy is a fresh single-commit orphan branch, **force-pushed**
(ghp-import `-f` semantics): the remote repo stays lean regardless of how many
times heroes/thumbnails are re-rendered. Qt-free.
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
_GIT_TIMEOUT = 600     # seconds — local plumbing only (init/add/commit); the
                       # network push has NO wall-clock cap (a first full-site
                       # upload can legitimately take arbitrarily long on a slow
                       # uplink) — Cancel is the escape hatch, and it kills the
                       # push process for real.
_PUSH_POLL_S = 0.2
# git push --progress writes "Writing objects:  42% (123/291), 88.10 MiB | 1.2 MiB/s"
_WRITING_RE = re.compile(rb"Writing objects:\s+\d+%\s+\((\d+)/(\d+)\)")

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


def _push(git_dir_args: list, url: str, branch: str, *,
          should_cancel=None, progress=None):
    """`git push --force --progress`, streamed: object-upload progress is parsed
    from stderr into `progress(sent, total)`, cancellation **kills the push
    process** (no orphaned uploads racing a later deploy), and there is no
    wall-clock timeout — big first pushes on slow uplinks are legitimate."""
    cancelled = should_cancel or (lambda: False)
    proc = subprocess.Popen(
        ["git", *git_dir_args, "push", "--force", "--progress", url,
         f"HEAD:refs/heads/{branch}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    tail: deque[bytes] = deque(maxlen=30)   # last stderr lines, for the error
    counts = [0, 0]                          # (sent, total) from Writing objects

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
                    pm = _WRITING_RE.search(line)
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
        time.sleep(_PUSH_POLL_S)
    reader.join(timeout=5)
    if proc.returncode != 0:
        detail = b"\n".join(tail).decode("utf-8", "replace").strip()
        raise PublishError(f"git failed to push to {url}:\n{detail}")
    if progress and counts[1]:
        progress(counts[1], counts[1])


def deploy(site_dir: Path, repo: str, branch: str = DEFAULT_BRANCH, *,
           should_cancel=None, progress=None, status=None) -> dict:
    """Force-push `site_dir` as a single-commit `branch` to `repo`.

    Returns {"repo", "branch", "url"}. Raises PublishError on any failure
    (git missing, nothing rendered, push rejected) with git's own stderr so
    an auth/repo problem is actionable. `progress`/`status` surface the
    upload (objects sent / total; a stage label) in the UI.
    """
    cancelled = should_cancel or (lambda: False)
    site_dir = Path(site_dir)
    url = normalize_repo(repo)
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
        git_dir = ["--git-dir", str(Path(tmp) / ".git"),
                   "--work-tree", str(site_dir)]
        if status:
            status("Preparing deploy…")
        _run_git(["init", "-q", str(tmp)], action="initialise the deploy repo")
        # Commit identity local to the throwaway repo — works on machines with
        # no global git identity configured.
        _run_git([*git_dir, "config", "user.name", "M110"], action="configure")
        _run_git([*git_dir, "config", "user.email", "m110@localhost"],
                 action="configure")
        if cancelled():
            raise PublishError("Cancelled.")
        _run_git([*git_dir, "add", "-A"], action="stage the site")
        _run_git([*git_dir, "commit", "-q", "-m",
                  f"Publish {datetime.now().strftime('%Y-%m-%d %H:%M')} (M110)"],
                 action="commit the site")
        if cancelled():
            raise PublishError("Cancelled.")
        if status:
            status("Uploading to GitHub…")
        _push(git_dir, url, branch, should_cancel=should_cancel,
              progress=progress)

    return {"repo": url, "branch": branch, "url": pages_url(repo)}


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
                 options.github_branch, should_cancel=should_cancel,
                 progress=progress, status=status)
    return {**result, **dep}

"""GitHub Pages publisher — URL normalization + the git deploy against a local
bare repo (file:// URL; no network, no GitHub)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from m110 import publish
from m110.publish import ghpages
from m110.publish.errors import PublishError
from m110.publish.options import PublishOptions
from tests._helpers import seed_root

needs_git = pytest.mark.skipif(shutil.which("git") is None,
                               reason="git not installed")


# ── normalize_repo / pages_url ────────────────────────────────────────────────

def test_normalize_repo_forms():
    assert ghpages.normalize_repo("mjm1138/astro") == "git@github.com:mjm1138/astro.git"
    assert (ghpages.normalize_repo("https://github.com/mjm1138/astro.git")
            == "https://github.com/mjm1138/astro.git")
    assert (ghpages.normalize_repo("git@github.com:mjm1138/astro.git")
            == "git@github.com:mjm1138/astro.git")
    assert ghpages.normalize_repo("  mjm1138/astro  ") == "git@github.com:mjm1138/astro.git"
    assert ghpages.normalize_repo("") == ""
    # non-GitHub URLs pass through untouched
    assert ghpages.normalize_repo("file:///tmp/bare.git") == "file:///tmp/bare.git"


def test_pages_url():
    assert ghpages.pages_url("mjm1138/astro") == "https://mjm1138.github.io/astro/"
    assert (ghpages.pages_url("https://github.com/mjm1138/astro.git")
            == "https://mjm1138.github.io/astro/")
    assert (ghpages.pages_url("git@github.com:mjm1138/astro.git")
            == "https://mjm1138.github.io/astro/")
    # an <owner>.github.io repo serves at the root
    assert (ghpages.pages_url("mjm1138/mjm1138.github.io")
            == "https://mjm1138.github.io/")
    assert ghpages.pages_url("file:///tmp/bare.git") is None
    assert ghpages.pages_url("") is None


# ── deploy against a local bare repo ─────────────────────────────────────────

def _bare_repo(tmp_path: Path) -> str:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    return bare.as_uri()


def _site(tmp_path: Path, marker: str = "v1") -> Path:
    site = tmp_path / "site"
    (site / "img").mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(f"<html>{marker}</html>")
    (site / "img" / "hero.jpg").write_bytes(b"\xff\xd8jpg")
    return site


def _branch_file(remote: str, branch: str, path: str) -> bytes | None:
    res = subprocess.run(
        ["git", "--git-dir", remote.removeprefix("file://"),
         "show", f"{branch}:{path}"],
        capture_output=True)
    return res.stdout if res.returncode == 0 else None


def _commit_count(remote: str, branch: str) -> int:
    res = subprocess.run(
        ["git", "--git-dir", remote.removeprefix("file://"),
         "rev-list", "--count", branch],
        capture_output=True, text=True, check=True)
    return int(res.stdout.strip())


@needs_git
def test_deploy_pushes_site_with_nojekyll(tmp_path):
    remote = _bare_repo(tmp_path)
    site = _site(tmp_path)
    res = ghpages.deploy(site, remote)
    assert res["branch"] == "gh-pages"
    assert res["url"] is None            # file:// remote has no pages URL
    assert _branch_file(remote, "gh-pages", "index.html") == b"<html>v1</html>"
    assert _branch_file(remote, "gh-pages", "img/hero.jpg") is not None
    assert _branch_file(remote, "gh-pages", ".nojekyll") is not None


@needs_git
def test_redeploy_force_replaces_single_commit(tmp_path):
    remote = _bare_repo(tmp_path)
    ghpages.deploy(_site(tmp_path, "v1"), remote)
    assert _commit_count(remote, "gh-pages") == 1
    ghpages.deploy(_site(tmp_path, "v2"), remote)
    assert _branch_file(remote, "gh-pages", "index.html") == b"<html>v2</html>"
    assert _commit_count(remote, "gh-pages") == 1   # replaced, not appended


@needs_git
def test_deploy_refuses_unrendered_dir(tmp_path):
    remote = _bare_repo(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PublishError, match="index.html"):
        ghpages.deploy(empty, remote)


@needs_git
def test_deploy_surfaces_git_error(tmp_path):
    with pytest.raises(PublishError, match="git failed"):
        ghpages.deploy(_site(tmp_path), (tmp_path / "nonexistent.git").as_uri())


def test_deploy_requires_git(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(PublishError, match="git was not found"):
        ghpages.deploy(_site(tmp_path), "mjm1138/astro")


def test_deploy_requires_repo(tmp_path):
    with pytest.raises(PublishError, match="repository"):
        ghpages.deploy(_site(tmp_path), "   ")


# ── render entry point / registry chaining ───────────────────────────────────

def test_render_requires_repo_config(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    with pytest.raises(PublishError, match="repository"):
        ghpages.render(PublishOptions(output_dir=tmp_path / "site"))


@needs_git
def test_render_reuses_prior_static_site_result(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    remote = _bare_repo(tmp_path)
    site_dir = _site(tmp_path)
    monkeypatch.setattr(ghpages.site, "render",
                        lambda *a, **k: pytest.fail("re-rendered despite prior"))
    opts = PublishOptions(output_dir=site_dir, github_repo=remote)
    res = ghpages.render(opts, prior={"pages": 7, "output_dir": str(site_dir)})
    assert res["pages"] == 7
    assert res["branch"] == "gh-pages"
    assert _branch_file(remote, "gh-pages", "index.html") is not None


@needs_git
def test_run_publish_chains_static_site_into_ghpages(tmp_path, monkeypatch):
    """With both targets enabled, static-site renders once and github-pages
    deploys that result instead of re-rendering."""
    root = seed_root(tmp_path, monkeypatch)
    pytest.importorskip("jinja2")
    pytest.importorskip("markdown")
    from m110 import config
    from tests._helpers import seed_capture
    seed_capture(root)   # the index template needs a real summary/capture
    remote = _bare_repo(tmp_path)
    out = tmp_path / "site"
    config.save_setting(publish.SETTING_KEY, ["static-site", "github-pages"])

    # The registry holds a direct reference to the real site.render (which runs
    # for the static-site target); ghpages looks it up on the module at call
    # time — so this patch trips only if ghpages *re-renders* despite `prior`.
    monkeypatch.setattr(ghpages.site, "render",
                        lambda *a, **k: pytest.fail("ghpages re-rendered despite prior"))
    res = publish.run_publish(PublishOptions(output_dir=out, github_repo=remote))
    assert res["static-site"]["pages"] >= 1
    assert res["github-pages"]["branch"] == "gh-pages"
    assert res["github-pages"]["pages"] == res["static-site"]["pages"]
    assert _branch_file(remote, "gh-pages", "index.html") is not None


# ── push progress + cancellation ─────────────────────────────────────────────

@needs_git
def test_deploy_reports_push_progress(tmp_path):
    remote = _bare_repo(tmp_path)
    seen = []
    ghpages.deploy(_site(tmp_path), remote,
                   progress=lambda i, t: seen.append((i, t)))
    assert seen, "no progress reported from git push --progress"
    i, t = seen[-1]
    assert i == t > 0          # ends complete (all objects sent)


@needs_git
def test_cancel_mid_push_kills_the_push(tmp_path):
    """Cancel during the network phase must kill the git process (no orphaned
    upload racing a later deploy) and surface as a cancelled PublishError."""
    import time as _time
    remote = _bare_repo(tmp_path)
    # A pre-receive hook that stalls the push long enough to cancel mid-flight.
    hook = Path(remote.removeprefix("file://")) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    hook.chmod(0o755)

    t0 = _time.monotonic()
    with pytest.raises(PublishError, match="Cancelled"):
        ghpages.deploy(_site(tmp_path), remote,
                       should_cancel=lambda: _time.monotonic() - t0 > 0.5)
    assert _time.monotonic() - t0 < 10          # did not wait out the hook
    # The push never landed.
    res = subprocess.run(
        ["git", "--git-dir", remote.removeprefix("file://"),
         "rev-parse", "--verify", "gh-pages"], capture_output=True)
    assert res.returncode != 0


# ── finished-only galleries ──────────────────────────────────────────────────

def test_image_state_rule():
    from m110 import objects
    assert objects.image_state("a.png", "Finished render", {}) == "finished"
    assert objects.image_state("s.fit", "Siril stack", {}) == "working"
    assert objects.image_state("s.fit", "Siril stack", {"s.fit": "finished"}) == "finished"
    assert objects.image_state("a.png", "Finished render", {"a.png": "working"}) == "working"


@needs_git
def test_finished_only_excludes_working_files(tmp_path, monkeypatch):
    """finished_only=True publishes finished/ images but not stacks/device
    stacks; finished_only=False publishes both (the 8a behaviour)."""
    pytest.importorskip("jinja2")
    pytest.importorskip("markdown")
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from m110 import config, refresh
    from m110.publish import site as pub_site
    from tests._helpers import seed_root as _seed, seed_capture

    root = _seed(tmp_path, monkeypatch)
    _, tid = seed_capture(root)
    fin = config.finished_dir(tid) / f"{tid}_final.png"
    fin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), (40, 80, 160)).save(fin)
    wrk = config.seestar_stacks_dir(tid) / f"{tid}_device.jpg"
    wrk.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), (160, 80, 40)).save(wrk)
    refresh.run_refresh(render=False)

    def names(finished_only):
        out = tmp_path / ("site-fin" if finished_only else "site-all")
        res = pub_site.render(PublishOptions(output_dir=out,
                                             finished_only=finished_only))
        assert res["pages"] >= 1
        return res["images"]

    assert names(finished_only=False) == 2
    assert names(finished_only=True) == 1

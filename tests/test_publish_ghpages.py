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


# ── incremental deploy mode ──────────────────────────────────────────────────

def _site_n(tmp_path: Path, n: int, marker: str = "v1") -> Path:
    """A site dir with `n` distinct binary "images" + an index."""
    site = tmp_path / "site"
    (site / "img").mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(f"<html>{marker}</html>", encoding="utf-8")
    for i in range(n):
        (site / "img" / f"{i}.jpg").write_bytes(b"\xff\xd8" + bytes([i]) * 4096)
    return site


@needs_git
def test_incremental_keeps_history_and_sends_only_changes(tmp_path):
    """Incremental descends from the deployed tip: history accumulates, and the
    second push transfers far fewer objects than the first (the whole point —
    an unchanged image is the same content-hashed blob the remote already has)."""
    remote = _bare_repo(tmp_path)
    first, second = [], []
    site = _site_n(tmp_path, 12, "v1")
    ghpages.deploy(site, remote, mode="incremental",
                   progress=lambda i, t: first.append(t))
    assert _commit_count(remote, "gh-pages") == 1

    # One image changes; the other 11 stay byte-identical.
    site = _site_n(tmp_path, 12, "v2")
    (site / "img" / "0.jpg").write_bytes(b"\xff\xd8changed")
    ghpages.deploy(site, remote, mode="incremental",
                   progress=lambda i, t: second.append(t))

    assert _commit_count(remote, "gh-pages") == 2          # history kept
    assert _branch_file(remote, "gh-pages", "index.html") == b"<html>v2</html>"
    # The push is the last phase, so the final progress report is its object
    # count: the whole site went up first, only the changed objects second.
    assert second[-1] < first[-1]
    assert first[-1] >= 12          # every image + index + .nojekyll + tree/commit


@needs_git
def test_incremental_tip_fetch_is_blobless_when_server_allows_filters(tmp_path):
    """GitHub supports partial clone, so reading the deployed tip costs a few
    objects (commit + trees) rather than re-downloading the whole site. The
    plain-shallow fallback (servers without filter support) is what the other
    incremental tests exercise, since a bare repo disallows filters by default."""
    remote = _bare_repo(tmp_path)
    subprocess.run(["git", "--git-dir", remote.removeprefix("file://"),
                    "config", "uploadpack.allowFilter", "true"], check=True)
    site = _site_n(tmp_path, 12)
    ghpages.deploy(site, remote, mode="incremental")

    stage = [""]
    phases = []          # (stage label, objects) — the split the UI shows
    ghpages.deploy(site, remote, mode="incremental",
                   status=lambda s: stage.__setitem__(0, s),
                   progress=lambda i, t: phases.append((stage[0], t)))
    fetched = [t for s, t in phases if "deployed site" in s]
    assert fetched, "the tip fetch reported no progress"
    assert max(fetched) < 12          # trees only — no blobs came back down


@needs_git
def test_incremental_first_deploy_without_branch(tmp_path):
    """No gh-pages yet → nothing to descend from; deploy proceeds parentless."""
    remote = _bare_repo(tmp_path)
    res = ghpages.deploy(_site(tmp_path), remote, mode="incremental")
    assert res["incremental"] is False        # no tip existed
    assert res["mode"] == "incremental"
    assert _commit_count(remote, "gh-pages") == 1
    assert _branch_file(remote, "gh-pages", "index.html") == b"<html>v1</html>"


@needs_git
def test_incremental_propagates_deletions(tmp_path):
    """A file swept from the render is gone from the branch — incremental still
    mirrors the folder exactly, it just uploads less."""
    remote = _bare_repo(tmp_path)
    site = _site_n(tmp_path, 3)
    ghpages.deploy(site, remote, mode="incremental")
    assert _branch_file(remote, "gh-pages", "img/2.jpg") is not None
    (site / "img" / "2.jpg").unlink()
    ghpages.deploy(site, remote, mode="incremental")
    assert _branch_file(remote, "gh-pages", "img/2.jpg") is None
    assert _branch_file(remote, "gh-pages", "img/1.jpg") is not None


@needs_git
def test_replace_mode_still_force_replaces_after_incremental(tmp_path):
    """The modes interoperate: switching back to replace collapses history."""
    remote = _bare_repo(tmp_path)
    site = _site_n(tmp_path, 2)
    ghpages.deploy(site, remote, mode="incremental")
    ghpages.deploy(site, remote, mode="incremental")
    assert _commit_count(remote, "gh-pages") == 2
    ghpages.deploy(site, remote, mode="replace")
    assert _commit_count(remote, "gh-pages") == 1


def test_deploy_mode_normalizes(tmp_path):
    opts = PublishOptions(output_dir=tmp_path / "x", github_deploy_mode="bogus")
    assert opts.github_deploy_mode == "replace"
    assert PublishOptions(output_dir=tmp_path / "x",
                          github_deploy_mode="incremental"
                          ).github_deploy_mode == "incremental"


@needs_git
def test_global_excludes_cannot_strip_site_images(tmp_path, monkeypatch):
    """A user's global gitignore must not silently drop the gallery (the
    ghp-import force-add lesson: a global "*.jpg" is a real-world config)."""
    excludes = tmp_path / "global_ignore"
    excludes.write_text("*.jpg\n.DS_Store\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    subprocess.run(["git", "config", "--global", "core.excludesFile",
                    str(excludes)], check=True)
    remote = _bare_repo(tmp_path)
    site = _site(tmp_path)
    (site / ".DS_Store").write_bytes(b"junk")
    ghpages.deploy(site, remote)
    assert _branch_file(remote, "gh-pages", "img/hero.jpg") is not None  # kept
    assert _branch_file(remote, "gh-pages", ".DS_Store") is None         # junk


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


def _seeded_three_tier_store(tmp_path, monkeypatch):
    """A capture with one image per tier: finished render, device stack,
    Siril (working) stack. Returns the store root."""
    from PIL import Image
    from m110 import config, refresh
    from tests._helpers import seed_root as _seed, seed_capture

    root = _seed(tmp_path, monkeypatch)
    _, tid = seed_capture(root)
    for d, name, color in [
            (config.finished_dir(tid), f"{tid}_final.png", (40, 80, 160)),
            (config.seestar_stacks_dir(tid), f"{tid}_device.jpg", (160, 80, 40)),
            (config.stacks_dir(tid), f"{tid}_stack.png", (80, 160, 40))]:
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), color).save(d / name)
    refresh.run_refresh(render=False)
    return root


def test_gallery_levels_pick_tiers(tmp_path, monkeypatch):
    pytest.importorskip("jinja2")
    pytest.importorskip("markdown")
    pytest.importorskip("PIL")
    from m110.publish import site as pub_site
    _seeded_three_tier_store(tmp_path, monkeypatch)

    def n_images(level):
        res = pub_site.render(PublishOptions(output_dir=tmp_path / f"site-{level}",
                                             gallery_level=level))
        return res["images"]

    assert n_images("finished") == 1
    assert n_images("device-stacks") == 2
    assert n_images("all") == 3
    # unknown level normalizes to the default
    assert PublishOptions(output_dir=tmp_path / "x",
                          gallery_level="bogus").gallery_level == "finished"


def test_rerender_sweeps_stale_output(tmp_path, monkeypatch):
    """Re-rendering with narrower options genuinely shrinks the output folder:
    stale gallery derivatives and section pages from the previous render are
    deleted, so a deploy never uploads what the options exclude."""
    pytest.importorskip("jinja2")
    pytest.importorskip("markdown")
    pytest.importorskip("PIL")
    from m110.publish import site as pub_site
    _seeded_three_tier_store(tmp_path, monkeypatch)
    out = tmp_path / "site"

    pub_site.render(PublishOptions(output_dir=out, gallery_level="all"))
    all_imgs = {p.name for p in (out / "img").rglob("*") if p.is_file()}
    assert (out / "processing.html").exists()

    pub_site.render(PublishOptions(output_dir=out, gallery_level="finished",
                                   sections={"library", "galleries"}))
    fin_imgs = {p.name for p in (out / "img").rglob("*") if p.is_file()}
    assert fin_imgs < all_imgs                     # stale derivatives removed
    assert not (out / "processing.html").exists()  # unchecked page removed
    assert not (out / "sessions.html").exists()
    assert (out / "index.html").exists()

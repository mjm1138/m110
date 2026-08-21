"""Tests for `tools/build_docs.py` — the versioned docs site.

Runs the **real** builder into a temp dir, for the reason `test_make_test_corpus`
exists: `tools/` lives outside the package, so nothing fails when it breaks — a
human just gets a traceback the next time they cut a release. Checking that the
symbols still exist would not have caught the dead links this found.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
pytest.importorskip("markdown")
import build_docs  # noqa: E402

TAG = "v9.9.9-beta.1"


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr(build_docs, "SITE_DOCS", tmp_path / "docs")
    build_docs.build(TAG, quiet=True)
    return tmp_path / "docs"


def test_every_doc_page_and_the_changelog_are_published(built):
    names = {p.stem for p in (built / TAG).glob("*.html")}
    for md in (ROOT / "docs").glob("*.md"):
        slug = "index" if md.name == "README.md" else md.stem
        assert slug in names, f"{md.name} was not published"
    assert "changelog" in names


def test_no_markdown_links_survive_and_none_of_them_dangle(built):
    """The bug this caught in review: CHANGELOG.md links DONE.md, SECURITY.md and
    docs-archive/SECURITY_ASSESSMENT.md — none of which are docs pages, so the
    obvious rewrite produced three 404s."""
    for page in built.rglob("*.html"):
        html = page.read_text()
        # Relative only: a GitHub link to a repo file correctly ends in .md.
        assert not re.search(r'href="(?!https?://)[^":]+\.md"', html), (
            f"unrewritten .md link in {page.name}")
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if href.startswith("/") and not href.startswith("/docs/"):
                continue          # the site root/assets, outside this build
            if href.startswith("/docs/"):
                target = built / href[len("/docs/"):]
            else:
                target = page.parent / href.split("#")[0]
            if href.endswith("/"):
                target = target / "index.html"
            if "assets" in href:
                continue          # docs.css, written once beside the versions
            assert target.exists(), f"{page.name} -> {href} does not exist"


def test_a_repo_file_that_is_not_a_docs_page_links_to_github_at_this_tag(built):
    html = (built / TAG / "changelog.html").read_text()
    assert f"https://github.com/{build_docs.REPO}/blob/{TAG}/DONE.md" in html
    assert "DONE.html" not in html


def test_nav_follows_the_order_the_readme_links_them_in(built):
    """The site nav is the table of contents the author already maintains, so a
    page added to docs/README.md appears without touching the builder."""
    html = (built / TAG / "index.html").read_text()
    block = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
    nav = re.findall(r'<a href="([a-z]+)\.html"', block)
    assert nav[:4] == ["index", "ingest", "library", "processing"]
    assert nav[-1] == "changelog"


def test_latest_is_a_full_copy_so_deep_links_resolve(built):
    """A redirect at the directory root would cover the index and 404 everything
    under it."""
    versioned = {p.name for p in (built / TAG).glob("*.html")}
    assert {p.name for p in (built / "latest").glob("*.html")} == versioned
    assert (built / "latest" / "processing.html").is_file()


def test_an_older_version_is_marked_stale_and_not_canonical(tmp_path, monkeypatch):
    monkeypatch.setattr(build_docs, "SITE_DOCS", tmp_path / "docs")
    build_docs.build("v9.9.9-beta.1", quiet=True)
    build_docs.build("v0.0.1", latest=False, quiet=True)
    old = (tmp_path / "docs" / "v0.0.1" / "index.html").read_text()
    assert "older release" in old and "/docs/latest/" in old
    assert "rel=\"canonical\"" not in old
    # …and it did not steal latest/
    assert "v9.9.9" in (tmp_path / "docs" / "latest" / "index.html").read_text()


def test_the_version_index_lists_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(build_docs, "SITE_DOCS", tmp_path / "docs")
    for t in ("v0.1.0", "v0.3.0-beta.5", "v0.2.0"):
        build_docs.build(t, latest=False, quiet=True)
    listed = re.findall(r'<li><a href="([^"/]+)/"', 
                        (tmp_path / "docs" / "index.html").read_text())
    assert listed == ["v0.3.0-beta.5", "v0.2.0", "v0.1.0"]


def test_the_release_script_runs_this_builder():
    """A docs site nobody rebuilds is worse than none — it goes quietly stale."""
    src = (ROOT / "tools" / "release.py").read_text()
    assert '"docs"' in src and "build_docs.build" in src
    phases = re.search(r"PHASES = \[(.*?)\]", src, re.S).group(1)
    order = [p.strip().strip('"') for p in phases.replace("\n", "").split(",")]
    # after `changelog` (so the release's entries are in) and before `commit`
    # (Cloudflare deploys site/ from the repo).
    assert order.index("changelog") < order.index("docs") < order.index("commit")


def test_from_tag_publishes_what_that_release_shipped(tmp_path, monkeypatch):
    """A version's directory built from the working tree would publish unreleased
    prose under a released version number — the exact mismatch the site exists to
    fix. Backfilling reads the docs out of git instead."""
    import subprocess
    tag = "v0.3.0-beta.5"
    if subprocess.run(["git", "rev-parse", "--verify", tag], cwd=ROOT,
                      capture_output=True).returncode:
        pytest.skip(f"{tag} not present in this checkout")
    monkeypatch.setattr(build_docs, "SITE_DOCS", tmp_path / "docs")
    build_docs.build(tag, quiet=True, from_tag=True)
    shipped = (tmp_path / "docs" / tag / "processing.html").read_text()
    current = (ROOT / "docs" / "processing.md").read_text()
    # a heading added after that release must NOT appear in its directory
    assert "Keeping working files under control" in current
    assert "Keeping working files under control" not in shipped


def test_the_release_phase_uses_the_working_tree_not_the_tag():
    """At `docs` time the tag does not exist yet — `tag` runs three phases later —
    and the tree is exactly what is about to become it."""
    src = (ROOT / "tools" / "release.py").read_text()
    body = src[src.index("def docs("):src.index("def commit(")]
    assert "from_tag" not in body

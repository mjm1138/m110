#!/usr/bin/env python3
"""Render `docs/*.md` + `CHANGELOG.md` into the versioned docs site under `site/`.

**Why this exists.** `Help → User guide` used to open `docs/README.md` on `main`,
and main is always ahead of every shipped release — so a user on the current build
read about features they did not have. Pinning the link to the release *tag* fixed
the correctness half (`updates.user_guide_url`); this fixes the rest: the guide is
now a real page on m110.space, one directory per release, with `latest/` tracking
the newest.

    site/docs/assets/docs.css        shared, NOT versioned — restyling improves
                                     every past version at once, which is what you
                                     want from a stylesheet and not from prose
    site/docs/<tag>/index.html       docs/README.md
    site/docs/<tag>/<page>.html      one per docs/*.md
    site/docs/<tag>/changelog.html   CHANGELOG.md
    site/docs/latest/                a full copy of the newest release's directory
    site/docs/index.html             every version, newest first

`latest/` is a **copy, not a redirect**, so that a deep link
(`/docs/latest/planning.html`) resolves. A redirect at the directory root would
only cover the index and would 404 everything under it.

Run by `tools/release.py`'s `docs` phase, after `changelog` (so the release's own
entries are in) and before `commit` (Cloudflare Pages deploys `site/` from the
repo, so the output has to be committed). Also runnable by hand:

    python tools/build_docs.py v0.3.0-beta.5
    python tools/build_docs.py v0.3.0-beta.5 --no-latest   # an old version, after the fact
"""
from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_DOCS = ROOT / "site" / "docs"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "mjm1138/m110"

#: `changelog.html` is generated from CHANGELOG.md, which does not live in docs/.
CHANGELOG_SLUG = "changelog"

CSS = """\
/* M110 docs — shared across every version on purpose: restyling should improve
   the whole archive at once. Tokens mirror the landing page. */
:root {
  --parchment-1:#f4ecd8; --parchment-2:#e7d9bb; --ink:#2b2118; --ink-soft:#5c4f3f;
  --accent:#3b6ea5; --accent-ink:#fff; --card:#fffaf0; --card-border:#d8c8a6;
  --code-bg:#f0e6cf; --grid:rgba(43,33,24,.10);
  --shadow:0 1px 3px rgba(43,33,24,.12), 0 8px 24px rgba(43,33,24,.08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --parchment-1:#14171c; --parchment-2:#0d0f13; --ink:#ece3d0; --ink-soft:#a99f8c;
    --accent:#7aa7d6; --accent-ink:#10151b; --card:#1a1e25; --card-border:#2c333d;
    --code-bg:#11151a; --grid:rgba(236,227,208,.06);
    --shadow:0 1px 3px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
}
* { box-sizing:border-box; }
body {
  margin:0; min-height:100vh; color:var(--ink); line-height:1.65;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:
    linear-gradient(135deg,var(--grid) 1px,transparent 1px) 0 0/44px 44px,
    linear-gradient(45deg,var(--grid) 1px,transparent 1px) 0 0/44px 44px,
    linear-gradient(180deg,var(--parchment-1),var(--parchment-2));
  -webkit-font-smoothing:antialiased;
}
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
h1,h2,h3,h4 { font-family:Georgia,"Times New Roman",serif; line-height:1.25; }
h1 { font-size:2.1rem; margin:.2em 0 .6em; }
h2 { margin-top:2em; border-bottom:1px solid var(--card-border); padding-bottom:.25em; }
code, pre { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.92em; }
code { background:var(--code-bg); padding:.12em .38em; border-radius:4px; }
pre { background:var(--code-bg); padding:14px 16px; border-radius:10px; overflow-x:auto; }
pre code { background:none; padding:0; }
blockquote { margin:1.2em 0; padding:.4em 1.1em; border-left:3px solid var(--card-border); color:var(--ink-soft); }
table { border-collapse:collapse; width:100%; margin:1.2em 0; display:block; overflow-x:auto; }
th,td { border:1px solid var(--card-border); padding:8px 11px; text-align:left; vertical-align:top; }
th { background:var(--code-bg); }
img { max-width:100%; height:auto; }
hr { border:0; border-top:1px solid var(--card-border); margin:2.4em 0; }

.shell { display:flex; gap:36px; max-width:1180px; margin:0 auto; padding:0 24px 72px; }
.side { flex:0 0 232px; padding-top:28px; position:sticky; top:0; align-self:flex-start;
        max-height:100vh; overflow-y:auto; }
.side .brand { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.side .brand img { width:34px; height:34px; border-radius:8px; }
.side .brand b { font-family:Georgia,serif; font-size:1.15rem; }
.side nav { margin-top:18px; }
.side nav a { display:block; padding:5px 10px; border-radius:7px; color:var(--ink); font-size:.95rem; }
.side nav a:hover { background:var(--card); text-decoration:none; }
.side nav a.on { background:var(--accent); color:var(--accent-ink); font-weight:600; }
.main { flex:1 1 auto; min-width:0; padding-top:28px; }
.card { background:var(--card); border:1px solid var(--card-border); border-radius:14px;
        padding:26px 32px; box-shadow:var(--shadow); }

.vbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:16px; font-size:.9rem; }
.vtag { font-weight:700; letter-spacing:.05em; text-transform:uppercase; font-size:.74rem;
        color:var(--accent); border:1.5px solid var(--accent); border-radius:999px; padding:2px 11px; }
.stale { background:#8a5a00; color:#fff; border-radius:8px; padding:10px 14px; margin-bottom:18px; font-size:.94rem; }
@media (prefers-color-scheme: dark) { .stale { background:#7a5200; } }
.foot { margin-top:28px; color:var(--ink-soft); font-size:.86rem; }
@media (max-width:860px) {
  .shell { flex-direction:column; gap:0; }
  .side { position:static; flex:1 1 auto; max-height:none; }
  .card { padding:20px; }
}
"""

PAGE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — M110 docs</title>
<meta name="description" content="{description}">
<link rel="icon" type="image/png" href="/assets/app-icon.png">
<link rel="stylesheet" href="/docs/assets/docs.css">
{canonical}</head>
<body>
<div class="shell">
  <aside class="side">
    <a class="brand" href="/"><img src="/assets/app-icon.png" alt=""><b>M110</b></a>
    {vbar}
    <nav>{nav}</nav>
  </aside>
  <main class="main">
    {stale}
    <article class="card">{body}</article>
    <p class="foot">{foot}</p>
  </main>
</div>
</body>
</html>
"""


def _md():
    try:
        import markdown
    except ImportError:                                    # pragma: no cover
        raise SystemExit(
            "build_docs needs the `publish` extra:  pip install -e '.[publish]'")
    return markdown.Markdown(extensions=[
        "extra", "tables", "fenced_code", "toc", "sane_lists", "attr_list"])


def _slug(path: Path) -> str:
    return "index" if path.name.lower() == "readme.md" else path.stem


def _title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def _summary(text: str) -> str:
    """First non-heading, non-blank line, flattened — the meta description."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ">", "-", "|", "!", "*")):
            line = re.sub(r"[*`\[\]]|\(.*?\)", "", line)
            return (line[:180] + "…") if len(line) > 180 else line
    return "M110 user documentation."


def _git_show(tag: str, path: str) -> str | None:
    try:
        return subprocess.run(["git", "show", f"{tag}:{path}"], cwd=ROOT,
                              capture_output=True, text=True,
                              check=True).stdout
    except subprocess.CalledProcessError:
        return None


def sources_at_tag(tag: str) -> list[tuple[str, Path, str]]:
    """The docs **as that release actually shipped them**, read out of git.

    Building a version's directory from the working tree would publish unreleased
    prose under a released version number — precisely the mismatch this whole site
    exists to fix. `--from-tag` is therefore how any past release is backfilled,
    and the release pipeline builds the tag it has just written.
    """
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", tag, "docs/"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    names = [n for n in listing if n.endswith(".md")]
    readme = "docs/README.md"
    order = [readme] if readme in names else []
    if order:
        for m in re.findall(r"\]\(([A-Za-z0-9_-]+\.md)\)",
                            _git_show(tag, readme) or ""):
            if f"docs/{m}" in names and f"docs/{m}" not in order:
                order.append(f"docs/{m}")
    order += [n for n in sorted(names) if n not in order]

    entries = []
    for n in order:
        text = _git_show(tag, n)
        if text is not None:
            entries.append((_slug(Path(n)), Path(n), text))
    cl = _git_show(tag, "CHANGELOG.md")
    if cl is not None:
        entries.append((CHANGELOG_SLUG, CHANGELOG, cl))
    return entries


def ordered_pages() -> list[Path]:
    """docs/README.md first, then the order README links them in, then anything
    it forgot (alphabetically).

    Taking the order from the README rather than a list in here means the site nav
    is the table of contents the author already maintains — a new page linked there
    simply appears, and one that is *not* linked still gets published rather than
    silently vanishing."""
    readme = DOCS / "README.md"
    order: list[Path] = [readme]
    if readme.is_file():
        for name in re.findall(r"\]\(([A-Za-z0-9_-]+\.md)\)", readme.read_text()):
            p = DOCS / name
            if p.is_file() and p not in order:
                order.append(p)
    for p in sorted(DOCS.glob("*.md")):
        if p not in order:
            order.append(p)
    return order


def _rewrite_links(html: str, slugs: set, tag: str, base: str) -> str:
    """Point every relative `.md` link somewhere that exists.

    A link to a page we publish becomes `<slug>.html`. A link to a **repo file we
    do not publish** — `CHANGELOG.md` cites `DONE.md`, `SECURITY.md` and
    `docs-archive/SECURITY_ASSESSMENT.md` — becomes a GitHub link **at this tag**,
    which is both correct for the version and immutable. Rewriting those to
    `DONE.html` (the obvious first cut) published three dead links.

    `base` is the source file's directory relative to the repo root, since a link
    is relative to the file that wrote it: `docs/` for the guide pages, `""` for
    CHANGELOG.md at the root.

    Anchors, absolute paths and external URLs are left alone."""
    def sub(m):
        target = m.group(1)
        if target.lower().startswith(("http://", "https://", "#", "/", "mailto:")):
            return m.group(0)
        page, _, frag = target.partition("#")
        if not page.lower().endswith(".md"):
            return m.group(0)
        slug = "index" if Path(page).name.lower() == "readme.md" else Path(page).stem
        anchor = f"#{frag}" if frag else ""
        if slug in slugs and "/" not in page:
            return f'href="{slug}.html{anchor}"'
        repo_path = posixpath.normpath(posixpath.join(base, page)).lstrip("./")
        return f'href="https://github.com/{REPO}/blob/{tag}/{repo_path}{anchor}"'
    return re.sub(r'href="([^"]+)"', sub, html)


def build(tag: str, *, latest: bool = True, quiet: bool = False,
          from_tag: bool = False) -> Path:
    out = SITE_DOCS / tag
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (SITE_DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (SITE_DOCS / "assets" / "docs.css").write_text(CSS, encoding="utf-8")

    if from_tag:
        entries = sources_at_tag(tag)
    else:
        entries = [(_slug(p), p, p.read_text(encoding="utf-8"))
                   for p in ordered_pages()]
        if CHANGELOG.is_file():
            entries.append((CHANGELOG_SLUG, CHANGELOG,
                            CHANGELOG.read_text(encoding="utf-8")))

    titles = {slug: _title(text, path.stem.title())
              for slug, path, text in entries}

    def nav_for(current: str) -> str:
        out_html = []
        for slug, _p, _t in entries:
            cls = ' class="on"' if slug == current else ""
            href = "index.html" if slug == "index" else f"{slug}.html"
            out_html.append(f'<a href="{href}"{cls}>{titles[slug]}</a>')
        return "\n      ".join(out_html)

    md = _md()
    slugs = {slug for slug, _p, _t in entries}
    for slug, path, text in entries:
        md.reset()
        base = "" if path == CHANGELOG else "docs"
        body = _rewrite_links(md.convert(text), slugs, tag, base)
        stale = "" if latest else (
            '<div class="stale">These are the docs for an older release. '
            '<a href="/docs/latest/">Go to the current version →</a></div>')
        canonical = ("" if not latest else
                     f'<link rel="canonical" href="https://m110.space/docs/latest/'
                     f'{"" if slug == "index" else slug + ".html"}">\n')
        html = PAGE.format(
            title=titles[slug], description=_summary(text).replace('"', "&quot;"),
            version=tag, nav=nav_for(slug), body=body, stale=stale,
            canonical=canonical,
            vbar=f'<div class="vbar"><span class="vtag">{tag}</span>'
                 f'<a href="/docs/">all versions</a></div>',
            foot=f'M110 {tag} · <a href="https://github.com/{REPO}">source</a>'
                 f' · <a href="/docs/">other versions</a>')
        (out / f"{slug}.html").write_text(html, encoding="utf-8")

    if latest:
        live = SITE_DOCS / "latest"
        if live.exists():
            shutil.rmtree(live)
        shutil.copytree(out, live)

    write_index()
    if not quiet:
        print(f"docs: {len(entries)} pages → site/docs/{tag}/"
              f"{' (+ latest/)' if latest else ''}")
    return out


def _version_key(name: str):
    """Newest first. Falls back to the raw name for anything unparseable rather
    than dropping it — an unlisted version is worse than an oddly sorted one."""
    try:
        from packaging.version import Version
        return (1, Version(name.lstrip("v").replace("-beta.", "b")
                           .replace("-alpha.", "a").replace("-rc.", "rc")))
    except Exception:
        return (0, name)


def write_index() -> None:
    versions = sorted(
        (d.name for d in SITE_DOCS.iterdir()
         if d.is_dir() and d.name not in {"assets", "latest"}),
        key=_version_key, reverse=True)
    items = "\n".join(
        f'<li><a href="{v}/">{v}</a></li>' for v in versions) or "<li>none yet</li>"
    body = (f"<h1>M110 documentation</h1>"
            f'<p>The current guide is at <a href="latest/">/docs/latest/</a>. '
            f"Every released version keeps its own copy, so a link stays true to "
            f"the build it described.</p><ul>{items}</ul>")
    html = PAGE.format(
        title="Documentation", description="M110 user documentation, by release.",
        version="all versions", nav="", body=body, stale="", canonical="",
        vbar="", foot=f'<a href="https://github.com/{REPO}">source</a>')
    (SITE_DOCS / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tag", help="release tag, e.g. v0.3.0-beta.5")
    ap.add_argument("--no-latest", action="store_true",
                    help="don't update latest/ (rebuilding an older version)")
    ap.add_argument("--from-tag", action="store_true",
                    help="read docs out of git at TAG instead of the working "
                         "tree — how a past release is backfilled truthfully")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.tag, latest=not a.no_latest, quiet=a.quiet,
          from_tag=a.from_tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())

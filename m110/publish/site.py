"""Static-site renderer — the generalized successor to the Astronomy
`scripts/build_site.py`. Reads the live derived rollups + Library + journals,
applies the publish selection/privacy filters, and writes a self-contained
static website (no server needed) to `options.output_dir`.

Qt-free. Jinja2 + markdown are lazy-imported (the optional `publish` extra); a
clear `PublishDepsMissing` is raised when they're absent.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .. import build_images, catalog, derived, objects
from . import images as pub_images
from . import select
from .errors import PublishDepsMissing

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_PROC_STATUS_RANK = {"out_of_date": 0, "not_processed": 1, "up_to_date": 2,
                     "dismissed": 3}


def _require_deps():
    try:
        import jinja2
        import markdown as md_lib
    except ImportError as exc:
        raise PublishDepsMissing(
            "Publishing needs the optional 'publish' extra. Install it with:\n"
            "    pip install 'm110[publish]'") from exc
    return jinja2, md_lib


def _env(jinja2):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["status_label"] = lambda s: {
        "deep_stack": "Deep Stack", "initial": "Initial",
    }.get(s, s or "—")
    env.filters["bar_pct"] = lambda v: max(0, min(100, v or 0))
    return env


def render(options, *, should_cancel=None, progress=None, status=None,
           prior=None) -> dict:
    """Render the static site. Returns {pages, objects, images, output_dir}.
    (`prior` is part of the publisher contract; the renderer ignores it.)"""
    jinja2, md_lib = _require_deps()
    cancelled = should_cancel or (lambda: False)
    if status:
        status("Rendering site…")

    library = catalog.load_library()
    totals = derived.load_totals()
    by_slug = totals.get("by_slug", {})
    by_folder = totals.get("by_folder", {})
    sessions = derived.load_sessions()
    processing = derived.load_processing()

    pub = select.publishable_slugs(library)
    # Summary recomputed over the published subset so excluded objects don't leak
    # into category counts/ids. Reuses the exact build_derived logic.
    from .. import build_derived
    pub_library = {s: e for s, e in library.items() if s in pub}
    summary = build_derived.build_summary(pub_library, totals) if totals else {}
    sessions = select.filter_sessions(sessions, pub)
    processing = select.filter_processing(processing, pub)
    proc_folders = processing.get("folders", {})

    out = options.output_dir
    img_dir = out / "img"
    (out / "objects").mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    for asset in ("style.css", "sortable.js"):
        src = TEMPLATES_DIR / asset
        if src.exists():
            shutil.copyfile(src, out / asset)

    env = _env(jinja2)

    # ── per-object contexts (captured publishable objects get full treatment) ──
    captured = sorted(
        (s for s in pub if s in by_slug),
        key=lambda s: catalog.catalog_sort_key(library[s].get("id") or s),
    )
    objs: dict[str, dict] = {}
    n_images = 0
    for i, slug in enumerate(captured, 1):
        if cancelled():
            break
        entry = library[slug]
        folders = build_images.folders_for_slug(slug, by_folder)
        fm, body = objects.read_journal(slug)
        visible = select.journal_visible(slug, options, fm)
        html = (md_lib.markdown(objects.journal_to_markdown(body),
                                extensions=["fenced_code", "tables"])
                if (visible and body.strip()) else "")
        imgs = pub_images.emit_gallery(slug, folders, by_folder, img_dir,
                                       galleries=options.has("galleries"),
                                       finished_only=options.finished_only)
        n_images += len(imgs)
        hero = pub_images.emit_hero(slug, img_dir)
        if hero is None and imgs:
            hero = next((im["thumb"] for im in imgs if im.get("thumb")), None)
        proc = sorted((proc_folders[f] for f in folders if f in proc_folders),
                      key=lambda p: _PROC_STATUS_RANK.get(p.get("status"), 9))
        objs[slug] = {
            "slug": slug, "entry": entry, "totals": by_slug.get(slug),
            "is_captured": True, "folders": folders,
            "sessions": [s for s in sessions if slug in s.get("slugs", [])],
            "journal_html": html, "journal_visible": visible,
            "images": imgs, "hero": hero, "processing": proc,
        }
        if progress:
            progress(i, len(captured))

    # Index rows: full Library when "library" is on, else only captured objects.
    if options.has("library"):
        row_slugs = sorted(pub, key=lambda s: catalog.catalog_sort_key(
            library[s].get("id") or s))
    else:
        row_slugs = captured
    rows = [objs.get(s) or {
        "slug": s, "entry": library[s], "totals": by_slug.get(s),
        "is_captured": s in by_slug,
    } for s in row_slugs]

    base = {
        "site_title": options.site_title,
        "build_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sections": options.sections,
        "year": datetime.now().year,
    }

    def write(name, ctx, dest, root=""):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(name).render(root=root, **base, **ctx), encoding="utf-8")

    pages = ["index.html"]
    write("index.html", {"rows": rows, "summary": summary}, out / "index.html")
    if options.has("summary"):
        write("summary.html",
              {"summary": summary, "by_folder": by_folder,
               "processing": processing},
              out / "summary.html")
        pages.append("summary.html")
    if options.has("sessions"):
        write("sessions.html", {"sessions": sessions}, out / "sessions.html")
        pages.append("sessions.html")
    if options.has("processing"):
        write("processing.html", {"processing": processing}, out / "processing.html")
        pages.append("processing.html")
    if options.has("journal"):
        feed = sorted(
            (o for o in objs.values() if o.get("journal_visible") and o.get("journal_html")),
            key=lambda o: (o.get("totals") or {}).get("last_capture") or "",
            reverse=True)
        write("journal.html", {"objects": feed}, out / "journal.html")
        pages.append("journal.html")

    n_pages = len(pages)
    for o in objs.values():
        write("object.html", {"obj": o},
              out / "objects" / f"{o['slug']}.html", root="../")
        n_pages += 1

    return {"pages": n_pages, "objects": len(objs), "images": n_images,
            "output_dir": str(out)}

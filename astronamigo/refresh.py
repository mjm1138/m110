"""Refresh the live data store: rescan FITS sessions, rebuild derived rollups.

Faithful port of `rebuild.sh`'s scan + derive steps (it calls the same ported
`scan_sessions` and `build_derived` code, so output is byte-identical). Image
rendering (build_site) is NOT ported yet — hero/gallery thumbnails still come
from the live generated `site/` until that step lands, so a brand-new object's
images won't appear until the Astronomy `build_site` runs.
"""
from __future__ import annotations

from . import scan_sessions, build_derived


def run_refresh(render: bool = True) -> dict:
    """Rescan sessions, rebuild derived rollups, and (re)generate gallery/hero
    images for the data store. Returns a small summary dict for the UI.
    """
    rows = scan_sessions.scan()
    scan_sessions.write_jsonl(rows)
    build_derived.main()  # loads catalog/priorities/sessions/overrides → derived/*.json

    rendered = None
    if render:
        try:
            from . import build_images, catalog, derived
            rendered = build_images.render_images(catalog.load_catalog(),
                                                  derived.load_totals())
        except Exception as exc:  # never let rendering break a refresh
            print(f"  image render skipped: {exc}")
    return {"sessions": len(rows), "rendered": rendered}

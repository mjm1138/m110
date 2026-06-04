"""Refresh the live data store: rescan FITS sessions, rebuild derived rollups.

Faithful port of `rebuild.sh`'s scan + derive steps (it calls the same ported
`scan_sessions` and `build_derived` code, so output is byte-identical). Image
rendering (build_site) is NOT ported yet — hero/gallery thumbnails still come
from the live generated `site/` until that step lands, so a brand-new object's
images won't appear until the Astronomy `build_site` runs.
"""
from __future__ import annotations

from . import scan_sessions, build_derived


def run_refresh() -> dict:
    """Rescan sessions and rebuild derived rollups in the live data store.

    Returns a small summary dict for the UI.
    """
    rows = scan_sessions.scan()
    scan_sessions.write_jsonl(rows)
    build_derived.main()  # loads catalog/priorities/sessions/overrides → derived/*.json
    return {"sessions": len(rows)}

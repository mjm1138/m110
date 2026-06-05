"""Read and order the object catalog from the live data store.

Mirrors the shape of Astronomy's `catalog.toml` (a dict keyed by slug; each
value has id/name/type/magnitude/size/season/...).
"""
from __future__ import annotations

import re
import tomllib

from . import config

_M = re.compile(r"^M\s*(\d+)$")
_NGC = re.compile(r"^NGC\s*(\d+)$", re.IGNORECASE)


def load_catalog() -> dict[str, dict]:
    """Return the catalog as {slug: entry}."""
    with open(config.CATALOG_TOML, "rb") as f:
        return tomllib.load(f)["catalog"]


def object_count() -> int:
    return len(load_catalog())


def catalog_sort_key(obj_id: str):
    """Natural catalog order: Messier-numeric, then NGC-numeric, then
    alphabetical. Mirrors the site's `_catalog_sort_key` so the GUI Object
    column matches the web view (M1, M2, … M10, not M1, M10, M100).
    Care: "Markarian's Chain" starts with M but isn't a Messier number.
    """
    s = (obj_id or "").strip()
    m = _M.match(s)
    if m:
        return (0, int(m.group(1)), "")
    n = _NGC.match(s)
    if n:
        return (1, int(n.group(1)), "")
    return (2, 0, s.lower())

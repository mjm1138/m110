"""Read the object catalog from the live data store.

First engine read-path. Mirrors the shape of Astronomy's `catalog.toml`
(a dict keyed by slug; each value has id/name/type/magnitude/size/season/...).
"""
from __future__ import annotations

import tomllib

from .config import CATALOG_TOML


def load_catalog() -> dict[str, dict]:
    """Return the catalog as {slug: entry}."""
    with open(CATALOG_TOML, "rb") as f:
        return tomllib.load(f)["catalog"]


def object_count() -> int:
    return len(load_catalog())

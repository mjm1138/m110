"""Publishing engine — render/export a selected view of the collection.

A *publisher* turns the user's `PublishOptions` into an artifact (a static
website, a deploy, …). The registry mirrors `processing.WORKFLOWS`: each entry is
available (selectable) or a registered-disabled placeholder shown "(soon)". The
first slice ships the local `static-site` target; GitHub Pages / Netlify are
placeholders for follow-up targets that build on the same engine. Qt-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import config
from .errors import PublishError, PublishDepsMissing
from .options import PublishOptions, ALL_SECTIONS, DEFAULT_SECTIONS, DEFAULT_SITE_TITLE
from . import ghpages, site

SETTING_KEY = "publish_targets"
DEFAULT_TARGETS = ["static-site"]

__all__ = [
    "Publisher", "PUBLISHERS", "PUBLISHERS_BY_ID", "SETTING_KEY",
    "enabled_target_ids", "run_publish", "PublishOptions", "PublishError",
    "PublishDepsMissing", "ALL_SECTIONS", "DEFAULT_SECTIONS", "DEFAULT_SITE_TITLE",
]


@dataclass(frozen=True)
class Publisher:
    id: str
    label: str
    available: bool                       # False → shown disabled ("soon")
    # (options, *, should_cancel, progress, prior) -> dict; `prior` is the
    # static-site result from the same run, so a deploy target can reuse the
    # rendered folder instead of rendering twice.
    render: Callable | None = None


PUBLISHERS = [
    Publisher("static-site", "Static website", True, site.render),
    Publisher("github-pages", "GitHub Pages", True, ghpages.render),
    Publisher("netlify", "Netlify", False),
]
PUBLISHERS_BY_ID = {p.id: p for p in PUBLISHERS}


def enabled_target_ids() -> list[str]:
    """Publisher ids the user has enabled (default: the local static site)."""
    val = config.get_setting(SETTING_KEY, None)
    return list(val) if isinstance(val, list) else list(DEFAULT_TARGETS)


def run_publish(options: PublishOptions, should_cancel=None, progress=None) -> dict:
    """Run every enabled + available publisher, in registry order (static-site
    first, so deploy targets can reuse its render). Returns {publisher_id: result}."""
    enabled = set(enabled_target_ids())
    results = {}
    for p in PUBLISHERS:
        if p.id in enabled and p.available and p.render:
            results[p.id] = p.render(options, should_cancel=should_cancel,
                                     progress=progress,
                                     prior=results.get("static-site"))
    return results

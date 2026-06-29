"""Publishing exceptions (kept separate so `site.py` can raise them without
importing the package `__init__`, which builds the registry from `site`)."""
from __future__ import annotations


class PublishError(Exception):
    """Base for publishing failures."""


class PublishDepsMissing(PublishError):
    """The optional `publish` extra (jinja2 + markdown) isn't installed.

    Raised by the static-site renderer so the UI can show an actionable
    "pip install m110[publish]" message instead of a raw ImportError — the same
    degrade-gracefully pattern as `catalog.OnlineLookupError`.
    """

"""Finished / intermediate filename hints — the single, user-editable source of
truth for "does this filename look like a *finished* deliverable or an
*intermediate* by-product?"

Three consumers used to each carry their own hardcoded copy of the same
``(processed|final|finished)`` vocabulary — tuned to one person's filename
habits, which meant a stranger's finished export (e.g. an ``NGC 6992`` render
with none of those words) would silently misclassify. This module centralizes
the vocabulary and makes it editable in Preferences:

* :func:`is_finished_name` — the file's name marks it a finished render/stack.
* :func:`is_intermediate_name` — a star-layer / by-product that is never final.

Hints are **case-insensitive substring keywords** (not regexes) so a non-technical
user can type ``starnet, denoise`` without knowing regex. Persisted in
``settings.json`` under :data:`SETTING_KEY` (Qt-free; read at classify time — no
restart). Format facts (which file *extensions* are rasters/FITS) stay in the
consumers; only the habit-driven keyword vocabulary lives here.
"""
from __future__ import annotations

from . import config

# Setting key in ~/.m110/settings.json (a dict: {"finished": [...], "intermediate": [...]}).
SETTING_KEY = "finished_hints"

# Seed vocabulary — the patterns the three consumers hardcoded before this module.
DEFAULT_FINISHED = ["processed", "final", "finished"]
DEFAULT_INTERMEDIATE = ["starless", "starmask"]


def _clean(tokens) -> list[str]:
    """Normalize a keyword list: strip, drop blanks, lowercase, de-dup (ordered)."""
    seen: dict[str, None] = {}
    for t in tokens or ():
        t = str(t).strip().lower()
        if t:
            seen.setdefault(t, None)
    return list(seen)


def get_hints() -> dict:
    """The active hint set — the saved override, else the seeded defaults.

    Returns ``{"finished": [...], "intermediate": [...]}``. Replace (not merge)
    semantics once saved, so a user can *remove* a default keyword.
    """
    saved = config.get_setting(SETTING_KEY) or {}
    finished = _clean(saved.get("finished")) if "finished" in saved else list(DEFAULT_FINISHED)
    intermediate = (_clean(saved.get("intermediate"))
                    if "intermediate" in saved else list(DEFAULT_INTERMEDIATE))
    return {"finished": finished, "intermediate": intermediate}


def set_hints(finished, intermediate) -> None:
    """Persist the hint set (cleaned). Read live by the consumers — no restart."""
    config.save_setting(SETTING_KEY, {
        "finished": _clean(finished),
        "intermediate": _clean(intermediate),
    })


def _matches(name: str, keywords) -> bool:
    low = name.lower()
    return any(k in low for k in keywords)


def is_finished_name(name: str) -> bool:
    """True if `name` carries a finished-deliverable keyword."""
    return _matches(name, get_hints()["finished"])


def is_intermediate_name(name: str) -> bool:
    """True if `name` carries an intermediate / star-layer keyword (never final)."""
    return _matches(name, get_hints()["intermediate"])

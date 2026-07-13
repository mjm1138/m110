"""In-app update check against the GitHub Releases API (Qt-free, stdlib-only).

M110 ships as a notarized `.dmg` / AppImage / `.exe` with no auto-updater, so a
beta user has no in-app signal that a newer build exists. This module fetches the
repo's releases, compares the newest tag to the running version, and reports
whether an update is available. The UI (``m110/ui/main.py``) runs the check on a
background thread at launch (throttled to ~once/24h) and surfaces a quiet,
dismissible banner; a Help → "Check for updates…" action reuses the same check.

Networking is stdlib ``urllib`` with a short timeout and **degrades silently** —
any network/parse error returns ``None`` (mirroring the ``online`` extra's
``OnlineLookupError`` graceful-degradation pattern). No new dependency;
``packaging`` (a setuptools/pip transitive) does the PEP 440 comparison.

Preferences live in ``settings.json`` via ``config.get_setting``/``save_setting``:
``update_check_enabled`` (default on), ``last_update_check`` (epoch, for the
throttle), ``update_skip_version`` (a tag the user dismissed from the banner).
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass

from . import config

# The one knob to change when the public org/repo name is settled — mirrors
# ``about_dialog.SOURCE_URL`` / ``error_report.REPO_URL``.
REPO = "mjm1138/m110"
_API = f"https://api.github.com/repos/{REPO}/releases"
_RELEASES_URL = f"https://github.com/{REPO}/releases"
# Online home of the user guide (docs/README.md), for Help → User guide + the site.
USER_GUIDE_URL = f"https://github.com/{REPO}/blob/main/docs/README.md"
_TIMEOUT_S = 6
_CHECK_INTERVAL_S = 24 * 3600

SETTING_ENABLED = "update_check_enabled"
SETTING_LAST_CHECK = "last_update_check"
SETTING_SKIP = "update_skip_version"


def current_version() -> str:
    """Installed distribution version, or ``"dev"`` when running from source.

    The single source of the running version (``about_dialog.app_version``
    delegates here)."""
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version("m110")
        except PackageNotFoundError:
            return "dev"
    except Exception:
        return "dev"


@dataclass
class Release:
    tag: str
    name: str
    url: str
    prerelease: bool
    published_at: str


@dataclass
class UpdateInfo:
    current: str
    latest: str        # the newest release tag (as published, e.g. "v0.1.0-beta.1")
    url: str           # the release's html_url (download page)
    is_newer: bool     # latest > current under PEP 440


def _norm(tag: str) -> str:
    """Drop a leading ``v``/``V`` so ``v0.1.0`` compares against ``0.1.0``."""
    return tag[1:] if tag[:1] in ("v", "V") else tag


def _newer(latest_tag: str, current: str) -> bool:
    try:
        from packaging.version import parse as vparse
        return vparse(_norm(latest_tag)) > vparse(_norm(current))
    except Exception:
        # Unparseable version (e.g. a "dev" source build) → never nag.
        return False


def _parse_releases(payload) -> list[Release]:
    out: list[Release] = []
    if not isinstance(payload, list):
        return out
    for r in payload:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        tag = r.get("tag_name") or ""
        if not tag:
            continue
        out.append(Release(
            tag=tag,
            name=r.get("name") or tag,
            url=r.get("html_url") or _RELEASES_URL,
            prerelease=bool(r.get("prerelease")),
            published_at=r.get("published_at") or "",
        ))
    return out


def _fetch(url: str = _API, timeout: int = _TIMEOUT_S):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"M110/{current_version()}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed host)
        return json.loads(resp.read().decode("utf-8"))


def latest_release(include_prereleases: bool = True, *, fetch=_fetch) -> Release | None:
    """Newest release from the repo, or ``None`` on any failure.

    Uses ``/releases`` (not ``/releases/latest``) because the beta is flagged as a
    *pre-release*, which ``/releases/latest`` excludes. Prereleases are included by
    default while the app is itself in beta. Sorted by parsed version (GitHub
    already returns newest-first, but a version sort is robust to ordering)."""
    try:
        payload = fetch()
    except Exception:
        return None
    rels = _parse_releases(payload)
    if not include_prereleases:
        rels = [r for r in rels if not r.prerelease]
    if not rels:
        return None
    try:
        from packaging.version import parse as vparse

        def _key(r: Release):
            try:
                return vparse(_norm(r.tag))
            except Exception:
                return vparse("0")

        rels = sorted(rels, key=_key, reverse=True)
    except Exception:
        pass
    return rels[0]


def check(*, include_prereleases: bool = True, fetch=_fetch) -> UpdateInfo | None:
    """Fetch the newest release and compare to the running version.

    Returns an :class:`UpdateInfo` (``is_newer`` says whether to nudge), or
    ``None`` when the check couldn't complete (offline, rate-limited, parse
    error)."""
    rel = latest_release(include_prereleases, fetch=fetch)
    if rel is None:
        return None
    cur = current_version()
    return UpdateInfo(current=cur, latest=rel.tag, url=rel.url,
                      is_newer=_newer(rel.tag, cur))


# ── throttle / preferences ─────────────────────────────────────────────────────

def check_enabled() -> bool:
    return bool(config.get_setting(SETTING_ENABLED, True))


def set_check_enabled(enabled: bool) -> None:
    config.save_setting(SETTING_ENABLED, bool(enabled))


def should_check(now: float | None = None, interval_s: int = _CHECK_INTERVAL_S) -> bool:
    """Whether the launch check should run: enabled and not run within
    ``interval_s`` (default 24h). The manual Help action bypasses this."""
    if not check_enabled():
        return False
    now = time.time() if now is None else now
    raw = config.get_setting(SETTING_LAST_CHECK, 0) or 0
    try:
        last = float(raw)
    except (TypeError, ValueError):
        last = 0.0
    return (now - last) >= interval_s


def record_check(now: float | None = None) -> None:
    config.save_setting(SETTING_LAST_CHECK, time.time() if now is None else now)


def skipped_version() -> str:
    return config.get_setting(SETTING_SKIP, "") or ""


def skip_version(tag: str) -> None:
    """Remember a tag the user dismissed so the launch banner stays hidden for
    that version (a newer one still shows)."""
    config.save_setting(SETTING_SKIP, tag)


def is_skipped(tag: str) -> bool:
    s = skipped_version()
    return bool(s) and _norm(s) == _norm(tag)

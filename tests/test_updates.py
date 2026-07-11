"""Update-check engine (`m110.updates`) — all offline (the network fetch is
monkeypatched with a fixture payload; the throttle/skip prefs run against an
in-memory settings dict)."""
from __future__ import annotations

import pytest

from m110 import updates


# ── a representative GitHub /releases payload (newest first, includes a prerelease) ──
FIXTURE = [
    {"tag_name": "v0.2.0-beta.1", "name": "M110 0.2.0-beta.1",
     "html_url": "https://github.com/mjm1138/m110/releases/tag/v0.2.0-beta.1",
     "prerelease": True, "draft": False, "published_at": "2026-08-01T00:00:00Z"},
    {"tag_name": "v0.1.0-beta.1", "name": "M110 0.1.0-beta.1",
     "html_url": "https://github.com/mjm1138/m110/releases/tag/v0.1.0-beta.1",
     "prerelease": True, "draft": False, "published_at": "2026-07-11T00:00:00Z"},
    {"tag_name": "v0.0.9", "name": "old draft", "html_url": "x",
     "prerelease": False, "draft": True, "published_at": "2026-06-01T00:00:00Z"},
]


def _fetch_ok(*a, **k):
    return FIXTURE


def _fetch_boom(*a, **k):
    raise OSError("network down")


# ── version comparison ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("latest,current,expected", [
    ("v0.2.0", "0.1.0b1", True),
    ("0.2.0", "v0.1.0", True),          # mixed v-prefix
    ("v0.1.0-beta.1", "0.1.0b1", False),  # same version, different spelling
    ("v0.1.0", "0.2.0", False),         # older
    ("v0.1.0", "dev", False),           # dev source build → never nag
])
def test_newer(latest, current, expected):
    assert updates._newer(latest, current) is expected


# ── release parsing / selection ────────────────────────────────────────────────

def test_latest_release_skips_drafts_and_picks_newest():
    rel = updates.latest_release(fetch=_fetch_ok)
    assert rel is not None
    assert rel.tag == "v0.2.0-beta.1"
    assert rel.prerelease is True
    assert "0.2.0" in rel.url


def test_latest_release_can_exclude_prereleases():
    # Every non-draft entry here is a prerelease → excluding them yields nothing.
    assert updates.latest_release(include_prereleases=False, fetch=_fetch_ok) is None


def test_latest_release_degrades_on_network_error():
    assert updates.latest_release(fetch=_fetch_boom) is None


def test_check_reports_newer(monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "0.1.0b1")
    info = updates.check(fetch=_fetch_ok)
    assert info is not None
    assert info.is_newer is True
    assert info.latest == "v0.2.0-beta.1"
    assert info.current == "0.1.0b1"


def test_check_up_to_date(monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "0.2.0")
    info = updates.check(fetch=_fetch_ok)
    assert info is not None and info.is_newer is False


def test_check_none_on_failure():
    assert updates.check(fetch=_fetch_boom) is None


# ── throttle + skip prefs (in-memory settings) ─────────────────────────────────

@pytest.fixture
def mem_settings(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(updates.config, "get_setting",
                        lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(updates.config, "save_setting",
                        lambda k, v: store.__setitem__(k, v))
    return store


def test_should_check_respects_enabled_flag(mem_settings):
    mem_settings[updates.SETTING_ENABLED] = False
    assert updates.should_check(now=1_000_000.0) is False


def test_should_check_throttles_to_interval(mem_settings):
    now = 1_000_000.0
    # Never checked → yes.
    assert updates.should_check(now=now) is True
    updates.record_check(now=now)
    # Just checked → no.
    assert updates.should_check(now=now + 60) is False
    # A day later → yes.
    assert updates.should_check(now=now + 24 * 3600 + 1) is True


def test_should_check_tolerates_bad_last_check(mem_settings):
    mem_settings[updates.SETTING_LAST_CHECK] = "not-a-number"
    assert updates.should_check(now=1_000_000.0) is True


def test_skip_version_roundtrip(mem_settings):
    assert updates.is_skipped("v0.2.0") is False
    updates.skip_version("v0.2.0")
    assert updates.is_skipped("v0.2.0") is True
    assert updates.is_skipped("0.2.0") is True     # v-prefix insensitive
    assert updates.is_skipped("v0.3.0") is False   # a newer one still shows

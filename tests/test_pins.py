"""Manual Pin / Mute priority overrides (#3): the stable per-store prefs file."""
import pytest

from m110 import config, pins
from tests._helpers import seed_root


@pytest.fixture
def store(tmp_path, monkeypatch):
    return seed_root(tmp_path, monkeypatch)


def test_empty_when_absent(store):
    assert pins.load() == {}
    assert pins.get_state("m101") is None
    assert pins.pinned_slugs() == set()
    assert pins.muted_slugs() == set()
    assert not config.PINS_TOML.exists()          # lazily created — no write on read


def test_set_get_roundtrip_persists(store):
    pins.set_state("m101", pins.PIN)
    pins.set_state("ngc-7000", pins.MUTE)
    assert config.PINS_TOML.exists()
    # re-read from disk (fresh call, no in-memory cache)
    assert pins.get_state("m101") == "pin"
    assert pins.pinned_slugs() == {"m101"}
    assert pins.muted_slugs() == {"ngc-7000"}


def test_clear_removes_key(store):
    pins.set_state("m101", pins.PIN)
    pins.set_state("m101", None)
    assert pins.get_state("m101") is None
    assert pins.load() == {}


def test_state_transition_pin_to_mute(store):
    pins.set_state("m42", pins.PIN)
    pins.set_state("m42", pins.MUTE)
    assert pins.get_state("m42") == "mute"
    assert pins.pinned_slugs() == set()


def test_slug_with_apostrophe_and_space(store):
    """A slug carrying quoting-hostile characters round-trips (TOML key quoting)."""
    slug = "markarian's chain"
    pins.set_state(slug, pins.PIN)
    assert pins.get_state(slug) == "pin"


def test_unknown_state_value_ignored(store):
    pins.set_state("m1", "bogus")                 # not pin/mute → treated as clear
    assert pins.get_state("m1") is None


def test_malformed_file_tolerated(store):
    config.PINS_TOML.parent.mkdir(parents=True, exist_ok=True)
    config.PINS_TOML.write_text("this is not valid toml = = =")
    assert pins.load() == {}                       # degrades to empty, no raise

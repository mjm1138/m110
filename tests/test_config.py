"""Tests for data-root resolution, bootstrap/seed, and Seestar detection."""
import json

from m110 import config


def test_resolve_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("M110_DATA_ROOT", str(tmp_path / "x"))
    assert config._resolve_data_root() == (tmp_path / "x")


def test_resolve_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "absent.json")
    assert config._resolve_data_root() == config.DEFAULT_DATA_ROOT


def test_resolve_saved_setting(monkeypatch, tmp_path):
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    sf = tmp_path / "settings.json"
    sf.write_text(json.dumps({"data_root": str(tmp_path / "saved")}))
    monkeypatch.setattr(config, "SETTINGS_FILE", sf)
    assert config._resolve_data_root() == (tmp_path / "saved")


def test_ensure_data_root_creates_and_seeds(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    internal = root / config.INTERNAL_DIRNAME
    # seeded static files now live in the hidden internal store
    assert (internal / "catalog.toml").is_file()
    assert (internal / "priorities.toml").is_file()
    # a "don't touch" README accompanies the internals
    assert (internal / "README.txt").is_file()
    # directory skeleton: two visible axes + Media/Inbox + hidden internals
    for sub in ("Objects", "Images", "Media", "Inbox",
                config.INTERNAL_DIRNAME,
                f"{config.INTERNAL_DIRNAME}/derived",
                f"{config.INTERNAL_DIRNAME}/renders/hero"):
        assert (root / sub).is_dir(), sub


def test_ensure_is_idempotent_and_preserves_edits(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    cat = root / config.INTERNAL_DIRNAME / "catalog.toml"
    cat.write_text("# user-edited\n")
    config.ensure_data_root(root)  # must NOT overwrite an existing catalog
    assert cat.read_text() == "# user-edited\n"


def test_find_seestar_no_crash():
    res = config.find_seestar_myworks()
    assert res is None or res.name == "MyWorks"

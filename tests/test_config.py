"""Tests for data-root resolution, bootstrap/seed, and Seestar detection."""
import json

from astronamigo import config


def test_resolve_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRONAMIGO_DATA_ROOT", str(tmp_path / "x"))
    assert config._resolve_data_root() == (tmp_path / "x")


def test_resolve_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("ASTRONAMIGO_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "absent.json")
    assert config._resolve_data_root() == config.DEFAULT_DATA_ROOT


def test_resolve_saved_setting(monkeypatch, tmp_path):
    monkeypatch.delenv("ASTRONAMIGO_DATA_ROOT", raising=False)
    sf = tmp_path / "settings.json"
    sf.write_text(json.dumps({"data_root": str(tmp_path / "saved")}))
    monkeypatch.setattr(config, "SETTINGS_FILE", sf)
    assert config._resolve_data_root() == (tmp_path / "saved")


def test_ensure_data_root_creates_and_seeds(tmp_path):
    root = tmp_path / "Astronamigo"
    config.ensure_data_root(root)
    # seeded static files
    assert (root / "data" / "catalog.toml").is_file()
    assert (root / "data" / "priorities.toml").is_file()
    # directory skeleton
    for sub in ("Images/FITS", "Images/Seestar_stacks", "Images/From the scope",
                "Images/Finished Images", "data/objects", "data/derived",
                "site/img/hero"):
        assert (root / sub).is_dir(), sub


def test_ensure_is_idempotent_and_preserves_edits(tmp_path):
    root = tmp_path / "Astronamigo"
    config.ensure_data_root(root)
    (root / "data" / "catalog.toml").write_text("# user-edited\n")
    config.ensure_data_root(root)  # must NOT overwrite an existing catalog
    assert (root / "data" / "catalog.toml").read_text() == "# user-edited\n"


def test_find_seestar_no_crash():
    res = config.find_seestar_myworks()
    assert res is None or res.name == "MyWorks"

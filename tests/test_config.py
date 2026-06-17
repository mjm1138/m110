"""Tests for data-root resolution, bootstrap/seed, and Seestar detection."""
import json

from m110 import config, objects


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


def test_ensure_creates_journal_template_and_stubs(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    internal = root / config.INTERNAL_DIRNAME
    # reference template lives in the internals
    assert (internal / "journal_template.md").is_file()
    # every seeded catalog object gets an Objects/<id>/journal.md stub
    import tomllib
    with (internal / "catalog.toml").open("rb") as f:
        catalog = tomllib.load(f)["catalog"]
    assert len(catalog) > 100
    sample_slug, sample = next(iter(catalog.items()))
    obj_id = (sample.get("id") or sample_slug).replace("/", "-").strip()
    stub = root / "Objects" / obj_id / "journal.md"
    assert stub.is_file()
    text = stub.read_text()
    assert text.startswith("---") and "name:" in text  # has the template frontmatter
    # objects.read_journal parses it when OBJECTS_DIR/CATALOG_TOML point here
    monkey_cat = root / config.INTERNAL_DIRNAME / "catalog.toml"
    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "OBJECTS_DIR", root / "Objects")
        mp.setattr(config, "CATALOG_TOML", monkey_cat)
        fm, _ = objects.read_journal(sample_slug)
    assert fm.get("name")


def test_ensure_stub_never_overwrites_existing_journal(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    import tomllib
    with (root / config.INTERNAL_DIRNAME / "catalog.toml").open("rb") as f:
        slug, entry = next(iter(tomllib.load(f)["catalog"].items()))
    obj_id = (entry.get("id") or slug).replace("/", "-").strip()
    journal = root / "Objects" / obj_id / "journal.md"
    journal.write_text("# my own notes\n")
    config.ensure_data_root(root)  # must not clobber
    assert journal.read_text() == "# my own notes\n"


def test_setting_get_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    assert config.get_setting("missing", "fallback") == "fallback"
    config.save_setting("processing_workflows", ["siril"])
    assert config.get_setting("processing_workflows") == ["siril"]
    # saving one key preserves the others
    config.save_setting("data_root", "/tmp/x")
    assert config.get_setting("processing_workflows") == ["siril"]
    assert config.get_setting("data_root") == "/tmp/x"


def test_find_seestar_no_crash():
    res = config.find_seestar_myworks()
    assert res is None or res.name == "MyWorks"

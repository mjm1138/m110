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


def test_is_first_run_true_when_nothing_set(monkeypatch, tmp_path):
    """No env, no saved preference, no store at the default → a genuine first run."""
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "absent.json")
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", tmp_path / "default")
    assert config.is_first_run() is True


def test_is_first_run_false_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("M110_DATA_ROOT", str(tmp_path / "x"))
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "absent.json")
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", tmp_path / "default")
    assert config.is_first_run() is False


def test_is_first_run_false_with_saved_pref(monkeypatch, tmp_path):
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    sf = tmp_path / "settings.json"
    sf.write_text(json.dumps({"data_root": str(tmp_path / "saved")}))
    monkeypatch.setattr(config, "SETTINGS_FILE", sf)
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", tmp_path / "default")
    assert config.is_first_run() is False


def test_is_first_run_false_when_default_store_exists(monkeypatch, tmp_path):
    """A returning user (store at the default, no explicit saved pref) isn't prompted."""
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "absent.json")
    default = tmp_path / "default"
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", default)
    (default / config.INTERNAL_DIRNAME).mkdir(parents=True)
    (default / config.INTERNAL_DIRNAME / "library.toml").write_text("")
    assert config.is_first_run() is False


def test_ensure_data_root_creates_and_seeds(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    internal = root / config.INTERNAL_DIRNAME
    # seeded static files now live in the hidden internal store
    assert (internal / "library.toml").is_file()
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
    cat = root / config.INTERNAL_DIRNAME / "library.toml"
    cat.write_text("# user-edited\n")
    config.ensure_data_root(root)  # must NOT overwrite an existing catalog
    assert cat.read_text() == "# user-edited\n"


def test_ensure_creates_journal_template_and_stubs(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    internal = root / config.INTERNAL_DIRNAME
    # reference template lives in the internals
    assert (internal / "journal_template.md").is_file()
    # 5d: the Library starts empty; a stub is generated for each Library object on
    # ensure_data_root. Add one, re-ensure, and confirm it gets a stub.
    with (internal / "library.toml").open("a") as f:
        f.write('\n[catalog.m31]\nid = "M31"\nname = "Andromeda"\ntype = "galaxy"\n')
    config.ensure_data_root(root)
    stub = root / "Objects" / "M31" / "journal.md"
    assert stub.is_file()
    text = stub.read_text()
    assert text.startswith("---") and "name:" in text  # has the template frontmatter
    # objects.read_journal parses it when OBJECTS_DIR/CATALOG_TOML point here
    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "OBJECTS_DIR", root / "Objects")
        mp.setattr(config, "LIBRARY_TOML", internal / "library.toml")
        fm, _ = objects.read_journal("m31")
    assert fm.get("name")


def test_ensure_stub_never_overwrites_existing_journal(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    internal = root / config.INTERNAL_DIRNAME
    with (internal / "library.toml").open("a") as f:
        f.write('\n[catalog.m31]\nid = "M31"\nname = "Andromeda"\ntype = "galaxy"\n')
    journal = root / "Objects" / "M31" / "journal.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
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


# The probe below runs for real against a scratch "volumes" root — a mounted
# telescope is just a filesystem, so a directory is a faithful stand-in and the
# preference ordering can be tested instead of assumed.

def test_find_seestar_finds_a_mounted_volume(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VOLUMES_DIR", tmp_path)
    mw = tmp_path / "Seestar S50" / "MyWorks"
    mw.mkdir(parents=True)
    assert config.find_seestar_myworks() == mw


def test_find_seestar_prefers_an_obviously_named_volume(tmp_path, monkeypatch):
    """Both a backup drive and the scope are mounted, and both happen to hold a
    MyWorks — the Seestar/EMMC name wins (SMB mounts show up as 'EMMC Images')."""
    monkeypatch.setattr(config, "VOLUMES_DIR", tmp_path)
    (tmp_path / "Archive Drive" / "MyWorks").mkdir(parents=True)
    scope = tmp_path / "EMMC Images" / "MyWorks"
    scope.mkdir(parents=True)
    assert config.find_seestar_myworks() == scope


def test_find_seestar_none_when_nothing_is_mounted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VOLUMES_DIR", tmp_path)
    (tmp_path / "Archive Drive").mkdir()
    assert config.find_seestar_myworks() is None

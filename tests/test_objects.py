"""Tests for the journal reader (Objects/<catalog id>/journal.md)."""
from m110 import config, objects


def _write_journal(objects_dir, folder_name, text):
    d = objects_dir / folder_name
    d.mkdir(parents=True)
    (d / "journal.md").write_text(text)


def test_read_journal_frontmatter_and_body(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    # No catalog → object_folder_name falls back to the slug.
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
    _write_journal(
        od, "m99",
        '---\nname: "Test Galaxy"\nhero_caption: "a caption"\n---\n\n'
        '# Heading\n\nSome body text.\n')
    fm, body = objects.read_journal("m99")
    assert fm["name"] == "Test Galaxy"
    assert fm["hero_caption"] == "a caption"
    assert "Heading" in body and "Some body text." in body


def test_journal_folder_uses_catalog_id(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    cat = tmp_path / "catalog.toml"
    cat.write_text('[catalog.m99]\nid = "M99"\nname = "Coma Pinwheel"\n')
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "CATALOG_TOML", cat)
    # Folder is named by the human-friendly catalog id, not the slug.
    assert objects.object_folder_name("m99") == "M99"
    _write_journal(od, "M99", "no frontmatter body\n")
    fm, body = objects.read_journal("m99")
    assert fm == {} and "no frontmatter body" in body


def test_missing_journal_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
    assert objects.read_journal("nope") == ({}, "")


def test_no_frontmatter_returns_whole_body(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
    _write_journal(od, "x", "# Just body\n\ntext\n")
    fm, body = objects.read_journal("x")
    assert fm == {}
    assert "Just body" in body

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


def test_write_journal_creates_folder_and_round_trips(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
    # no folder yet → read is empty
    assert objects.read_journal_text("m42") == ""

    text = '---\nname: "Orion"\nhero_caption: "the sword"\n---\n\n# Notes\n\nbody\n'
    path = objects.write_journal("m42", text)
    assert path == od / "m42" / "journal.md"      # slug fallback (no catalog)
    assert path.is_file()
    # raw round-trip + parsed view both reflect the edit
    assert objects.read_journal_text("m42") == text
    fm, body = objects.read_journal("m42")
    assert fm["name"] == "Orion" and fm["hero_caption"] == "the sword"
    assert "body" in body


def test_journal_to_markdown_strips_comments_and_keeps_breaks():
    body = "# Heading\n\n<!--\neditor guidance\n-->\nrough night.\nbetter night.\n"
    md = objects.journal_to_markdown(body)
    assert "editor guidance" not in md and "-->" not in md     # comment dropped
    assert "rough night.  \nbetter night." in md               # hard line break
    assert md.startswith("# Heading")


def test_journal_to_markdown_preserves_lists_and_code():
    body = "- a\n- b\n\n```\ncode one\ncode two\n```\n"
    md = objects.journal_to_markdown(body)
    assert "- a\n- b" in md                 # list items get no trailing hard break
    assert "code one\ncode two" in md       # fenced code left untouched


def test_write_journal_overwrites_existing(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
    objects.write_journal("m42", "first\n")
    objects.write_journal("m42", "second\n")   # edit replaces prior content
    assert objects.read_journal_text("m42") == "second\n"

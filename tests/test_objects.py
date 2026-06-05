"""Tests for the journal reader."""
from m110 import config, objects


def test_read_journal_frontmatter_and_body(tmp_path, monkeypatch):
    od = tmp_path / "objects"
    od.mkdir()
    (od / "m99.md").write_text(
        '---\nname: "Test Galaxy"\nhero_caption: "a caption"\n---\n\n'
        '# Heading\n\nSome body text.\n')
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    fm, body = objects.read_journal("m99")
    assert fm["name"] == "Test Galaxy"
    assert fm["hero_caption"] == "a caption"
    assert "Heading" in body and "Some body text." in body


def test_missing_journal_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path)
    assert objects.read_journal("nope") == ({}, "")


def test_no_frontmatter_returns_whole_body(tmp_path, monkeypatch):
    od = tmp_path / "objects"
    od.mkdir()
    (od / "x.md").write_text("# Just body\n\ntext\n")
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    fm, body = objects.read_journal("x")
    assert fm == {}
    assert "Just body" in body

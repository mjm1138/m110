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
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
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
    monkeypatch.setattr(config, "LIBRARY_TOML", cat)
    # Folder is named by the human-friendly catalog id, not the slug.
    assert objects.object_folder_name("m99") == "M99"
    _write_journal(od, "M99", "no frontmatter body\n")
    fm, body = objects.read_journal("m99")
    assert fm == {} and "no frontmatter body" in body


def test_missing_journal_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    assert objects.read_journal("nope") == ({}, "")


def test_no_frontmatter_returns_whole_body(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    _write_journal(od, "x", "# Just body\n\ntext\n")
    fm, body = objects.read_journal("x")
    assert fm == {}
    assert "Just body" in body


def test_write_journal_creates_folder_and_round_trips(tmp_path, monkeypatch):
    od = tmp_path / "Objects"
    monkeypatch.setattr(config, "OBJECTS_DIR", od)
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
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
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    objects.write_journal("m42", "first\n")
    objects.write_journal("m42", "second\n")   # edit replaces prior content
    assert objects.read_journal_text("m42") == "second\n"


# ── list-valued frontmatter + per-image curation (#17) ────────────────────────

def _objects_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")


def test_frontmatter_list_roundtrip_and_clear(tmp_path, monkeypatch):
    _objects_root(tmp_path, monkeypatch)
    objects.set_frontmatter_list("m99", "finished_extra", ["a.png", "b.png"])
    assert objects.get_frontmatter_list("m99", "finished_extra") == ["a.png", "b.png"]
    # other frontmatter keys survive alongside the list
    objects.set_frontmatter_key("m99", "hero", "a.png")
    assert objects.read_journal("m99")[0]["hero"] == "a.png"
    assert objects.get_frontmatter_list("m99", "finished_extra") == ["a.png", "b.png"]
    # empty list deletes the key
    objects.set_frontmatter_list("m99", "finished_extra", [])
    assert objects.get_frontmatter_list("m99", "finished_extra") == []
    assert "finished_extra" not in objects.read_journal("m99")[0]


def test_curation_set_get_and_single_list_invariant(tmp_path, monkeypatch):
    _objects_root(tmp_path, monkeypatch)
    objects.set_curation("m99", "img.png", "finished")
    assert objects.get_curation("m99") == {"img.png": "finished"}
    # flipping to working moves it out of finished_extra (only in one list)
    objects.set_curation("m99", "img.png", "working")
    assert objects.get_curation("m99") == {"img.png": "working"}
    assert objects.get_frontmatter_list("m99", "finished_extra") == []
    # clearing removes it entirely
    objects.set_curation("m99", "img.png", None)
    assert objects.get_curation("m99") == {}


def test_curation_rejects_unknown_state(tmp_path, monkeypatch):
    _objects_root(tmp_path, monkeypatch)
    assert objects.set_curation("m99", "img.png", "bogus") is None
    assert objects.get_curation("m99") == {}

"""Tests for the media reader (m110/media.py)."""
from m110 import config, media


def test_scan_groups_by_category_and_kind(tmp_path, monkeypatch):
    root = tmp_path / "Media"
    (root / "Moon_photo").mkdir(parents=True)
    (root / "Moon_photo" / "a.jpg").write_text("x")
    (root / "Moon_photo" / "b.png").write_text("x")
    (root / "Moon_photo" / "notes.txt").write_text("x")        # wrong ext → skipped
    (root / "Lunar_video").mkdir(parents=True)
    (root / "Lunar_video" / "clip.mp4").write_text("x")
    (root / "Random").mkdir()                                   # not _photo/_video → skip
    (root / "Random" / "c.jpg").write_text("x")
    monkeypatch.setattr(config, "MEDIA_DIR", root)

    cats = media.scan()
    by = {(c["category"], c["kind"]): c for c in cats}
    assert set(by) == {("Lunar", "video"), ("Moon", "photo")}
    assert [i["name"] for i in by[("Moon", "photo")]["items"]] == ["a.jpg", "b.png"]
    assert by[("Lunar", "video")]["items"][0]["name"] == "clip.mp4"
    # sort: category A→Z (Lunar before Moon)
    assert [c["category"] for c in cats] == ["Lunar", "Moon"]


def test_scan_missing_or_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "nope")
    assert media.scan() == []
    empty = tmp_path / "Media"
    (empty / "Moon_photo").mkdir(parents=True)                  # folder, no media files
    monkeypatch.setattr(config, "MEDIA_DIR", empty)
    assert media.scan() == []

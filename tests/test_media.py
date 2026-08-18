"""Tests for the media reader (m110/media.py)."""
import pytest

from m110 import config, media


def _mk(root, rel, data=b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "Media"
    root.mkdir()
    monkeypatch.setattr(config, "MEDIA_DIR", root)
    return root


def test_lists_files_and_skips_sidecars_and_junk(store):
    """The Seestar writes a `_thn.jpg` beside every capture. Listing them made
    each photo appear twice — once full-size, once as a low-res duplicate."""
    _mk(store, "Moon_photo/a.jpg")
    _mk(store, "Moon_photo/a_thn.jpg")          # sidecar → not an item
    _mk(store, "Moon_photo/notes.txt")          # not media
    _mk(store, "Moon_photo/.DS_Store")          # dotfile
    _mk(store, "Lunar_video/clip.mp4")
    _mk(store, "Lunar_video/clip_thn.jpg")      # video poster → not an item
    _mk(store, "Lunar_video/clip.avi.txt")      # device junk
    _mk(store, "Lunar_video/clip.avi.idx")
    _mk(store, "Random/c.jpg")                  # not a _photo/_video folder

    names = sorted(i.name for i in media.list_media())
    assert names == ["a.jpg", "clip.mp4"]
    assert media.categories() == ["Lunar", "Moon"]


def test_kind_comes_from_the_file_not_the_folder(store):
    """A stacked result lands as a `.jpg` inside a `_video/` folder. The old
    folder-gated scan hid it entirely."""
    _mk(store, "Lunar_video/clip.mp4")
    _mk(store, "Lunar_video/Video_Stacked_Lunar_20260424-074221.jpg")
    by_name = {i.name: i for i in media.list_media()}
    assert by_name["Video_Stacked_Lunar_20260424-074221.jpg"].kind == "photo"
    assert by_name["clip.mp4"].kind == "video"
    # Both belong to the same category, taken from the folder prefix.
    assert {i.category for i in by_name.values()} == {"Lunar"}


def test_walk_is_recursive_and_records_the_subfolder(store):
    """Processed output nests (`ASIVideoStack_Output/`); a shallow scan misses it
    and gives no sign that it did."""
    _mk(store, "Lunar_video/ASIVideoStack_Output/sharp.jpg")
    items = media.list_media()
    assert [i.name for i in items] == ["sharp.jpg"]
    assert items[0].subfolder == "ASIVideoStack_Output"
    assert items[0].category == "Lunar"


def test_poster_for_video_is_the_sibling_sidecar(store):
    _mk(store, "Lunar_video/clip.mp4")
    poster = _mk(store, "Lunar_video/clip_thn.jpg")
    item = next(i for i in media.list_media() if i.kind == "video")
    assert media.poster_for(item) == poster


def test_poster_for_video_without_a_sidecar_is_none(store):
    """No sidecar → the grid paints its placeholder rather than guessing."""
    _mk(store, "Lunar_video/orphan.mp4")
    item = next(iter(media.list_media()))
    assert media.poster_for(item) is None


def test_poster_for_photo_is_the_file_itself(store):
    p = _mk(store, "Moon_photo/a.jpg")
    item = next(iter(media.list_media()))
    assert media.poster_for(item) == p


def test_astro_tiff_is_rendered_not_shown_raw(tmp_path, monkeypatch, store):
    """Qt decodes TIFF, but maps a 32-bit float linearly — a faint stack lands at
    max luminance ~14/255, i.e. black. It must go through the percentile stretch,
    so `poster_for` returns a *render*, never the source."""
    import numpy as np
    import tifffile

    monkeypatch.setattr(config, "MEDIA_RENDERS_DIR", tmp_path / "renders")
    faint = np.random.normal(0.02, 0.002, (64, 64)).astype("float32")
    src = store / "Moon_photo" / "stack.tif"
    src.parent.mkdir(parents=True)
    tifffile.imwrite(src, faint)

    item = next(iter(media.list_media()))
    assert media.needs_render(item)
    poster = media.poster_for(item)
    assert poster is not None and poster != src
    assert poster.parent == config.MEDIA_RENDERS_DIR


def test_poster_render_false_never_blocks(tmp_path, monkeypatch, store):
    """Bulk tile population must not pay ~0.1 s per file inline."""
    import numpy as np
    import tifffile

    monkeypatch.setattr(config, "MEDIA_RENDERS_DIR", tmp_path / "renders")
    src = store / "Moon_photo" / "stack.tif"
    src.parent.mkdir(parents=True)
    tifffile.imwrite(src, np.zeros((32, 32), dtype="float32"))
    item = next(iter(media.list_media()))

    assert media.poster_for(item, render=False) is None      # nothing cached yet
    assert media.pending_posters([item]) == [item]
    assert media.render_posters([item]) == 1
    assert media.poster_for(item, render=False) is not None  # now cached
    assert media.pending_posters([item]) == []               # …and not re-rendered


def test_jpeg_and_png_are_shown_directly(store):
    """No render tier for formats Qt shows faithfully — that would be pure cost."""
    _mk(store, "Moon_photo/a.jpg")
    _mk(store, "Moon_photo/b.png")
    for item in media.list_media():
        assert not media.needs_render(item)
        assert media.poster_for(item, render=False) == item.path


def test_captured_prefers_the_filename_stamp(store):
    """Filename timestamps order the wall; mtime is the fallback. (Display only —
    nothing computes with this.)"""
    _mk(store, "Moon_photo/2026-05-31-002114-Lunar.jpg")
    _mk(store, "Moon_photo/undated.jpg")
    by_name = {i.name: i for i in media.list_media()}
    from datetime import datetime
    stamped = by_name["2026-05-31-002114-Lunar.jpg"]
    assert datetime.fromtimestamp(stamped.captured) == datetime(2026, 5, 31, 0, 21, 14)
    assert by_name["undated.jpg"].captured == by_name["undated.jpg"].mtime


def test_missing_or_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "nope")
    assert media.list_media() == []
    empty = tmp_path / "Media"
    (empty / "Moon_photo").mkdir(parents=True)
    monkeypatch.setattr(config, "MEDIA_DIR", empty)
    assert media.list_media() == []


# ── cleanup ───────────────────────────────────────────────────────────────────

def test_cleanup_never_offers_a_live_video_poster(store):
    """The invariant that matters: a video's sidecar is the only still it has, so
    it is content, not cruft. A photo's sidecar is redundant and goes."""
    _mk(store, "Lunar_video/clip.mp4")
    _mk(store, "Lunar_video/clip_thn.jpg")
    _mk(store, "Moon_photo/a.jpg")
    _mk(store, "Moon_photo/a_thn.jpg")
    _mk(store, "Lunar_video/clip.avi.txt")

    names = sorted(p.name for p in media.cleanup_candidates())
    assert names == ["a_thn.jpg", "clip.avi.txt"]


def test_cleanup_offers_an_orphaned_sidecar(store):
    """Its source is gone, so it can't be a poster for anything."""
    _mk(store, "Lunar_video/gone_thn.jpg")
    assert [p.name for p in media.cleanup_candidates()] == ["gone_thn.jpg"]


def test_discard_deletes_only_candidates(store):
    _mk(store, "Moon_photo/a.jpg", b"x" * 10)
    _mk(store, "Moon_photo/a_thn.jpg", b"y" * 20)
    result = media.discard(media.cleanup_candidates())
    assert result == {"deleted": 1, "bytes": 20, "skipped": 0}
    assert (store / "Moon_photo" / "a.jpg").exists()
    assert not (store / "Moon_photo" / "a_thn.jpg").exists()


def test_discard_refuses_a_video_poster_handed_to_it_directly(store):
    """`discard` recomputes the candidate set rather than trusting its argument,
    so a stale UI selection can never delete a file that has become content."""
    _mk(store, "Lunar_video/clip.mp4")
    poster = _mk(store, "Lunar_video/clip_thn.jpg")
    assert media.discard([poster]) == {"deleted": 0, "bytes": 0, "skipped": 1}
    assert poster.exists()


def test_discard_refuses_paths_outside_the_media_dir(store, tmp_path):
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("keep me")
    assert media.discard([outside])["deleted"] == 0
    assert outside.exists()

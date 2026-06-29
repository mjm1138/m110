"""End-to-end static-site rendering on a temp store (never live data)."""
from m110 import catalog, config, objects, publish
from m110.publish.options import PublishOptions
from tests._helpers import add_library, seed_capture, seed_root


def _finished_png(tid):
    """Drop a tiny real PNG into the object's finished/ tier so a gallery exists."""
    from PIL import Image
    d = config.finished_dir(tid)
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(d / f"{tid}_processed.png")


def _render(tmp_path, **opts):
    out = tmp_path / "site"
    publish.run_publish(PublishOptions(output_dir=out, **opts))
    return out


def test_renders_index_and_object_page(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    out = _render(tmp_path)
    assert (out / "index.html").is_file()
    assert (out / "style.css").is_file()
    assert (out / "objects" / f"{slug}.html").is_file()
    assert f"objects/{slug}.html" in (out / "index.html").read_text()


def test_excluded_object_has_no_page_or_row(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    catalog.set_publish_flag(slug, False)
    out = _render(tmp_path)
    assert not (out / "objects" / f"{slug}.html").is_file()
    assert f"objects/{slug}.html" not in (out / "index.html").read_text()


def test_journal_notes_respect_exclude(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "---\nname: M\n---\n\nUNIQUE_NOTE_TOKEN here.\n")
    # default: journal section on → notes appear on the object page
    out = _render(tmp_path)
    assert "UNIQUE_NOTE_TOKEN" in (out / "objects" / f"{slug}.html").read_text()
    # globally excluded → notes gone
    out2 = tmp_path / "site2"
    publish.run_publish(PublishOptions(output_dir=out2, exclude_journals=True))
    assert "UNIQUE_NOTE_TOKEN" not in (out2 / "objects" / f"{slug}.html").read_text()


def test_private_journal_hidden(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "---\nprivate: true\n---\n\nSECRET_TOKEN body.\n")
    out = _render(tmp_path)
    assert "SECRET_TOKEN" not in (out / "objects" / f"{slug}.html").read_text()


def test_section_toggles_emit_only_selected_pages(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    out = _render(tmp_path, sections={"library", "sessions"})
    assert (out / "sessions.html").is_file()
    assert not (out / "summary.html").is_file()
    assert not (out / "journal.html").is_file()
    # nav reflects the selection
    idx = (out / "index.html").read_text()
    assert "sessions.html" in idx
    assert "summary.html" not in idx


def test_gallery_images_emitted_when_selected(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    _finished_png(tid)
    from m110 import refresh
    refresh.run_refresh()  # regenerate totals/images now that a finished png exists
    out = _render(tmp_path, sections={"library", "galleries"})
    img_dir = out / "img"
    assert img_dir.is_dir()
    jpgs = list(img_dir.glob("*.jpg"))
    assert jpgs, "expected at least one gallery thumbnail"
    # galleries off → no thumbnails generated
    out2 = tmp_path / "site2"
    publish.run_publish(PublishOptions(output_dir=out2, sections={"library"}))
    assert not list((out2 / "img").glob("*.jpg"))

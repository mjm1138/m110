"""Tests for the in-place store migration to the two-axis layout (v2).

Builds an old-layout temp root, migrates it, and asserts the new tree, the
slug→id journal mapping, the FITS-level collapse (incl. root stack files folded
into stacks/), idempotency, and the version stamp. Never touches live data.
"""
from m110 import migrate

INTERNAL = ".m110_internal_data"


def _build_old_layout(root):
    data = root / "data"
    (data / "objects").mkdir(parents=True)
    (data / "derived").mkdir(parents=True)
    (data / "catalog.toml").write_text(
        '[catalog.m101]\nid = "M101"\nname = "Pinwheel"\n'
        '[catalog.m81]\nid = "M81"\nname = "Bode"\n')
    (data / "priorities.toml").write_text("# priorities\n")
    (data / "sessions.jsonl").write_text('{"date": "2026-01-01"}\n')
    (data / "processing_overrides.toml").write_text("# overrides\n")
    (data / "derived" / "totals.json").write_text("{}")
    (data / "objects" / "m101.md").write_text("journal pinwheel\n")
    (data / "objects" / "m81.md").write_text("journal bode\n")
    (data / "objects" / "weird.md").write_text("no catalog entry\n")  # → fallback slug

    site = root / "site" / "img" / "hero"
    site.mkdir(parents=True)
    (root / "site" / "img" / "abc123.jpg").write_text("thumb")
    (site / "m101.jpg").write_text("hero")

    fits = root / "Images" / "FITS" / "M101"
    (fits / "lights").mkdir(parents=True)
    (fits / "lights" / "Light_x.fit").write_text("light")
    (fits / "stacks").mkdir()
    (fits / "stacks" / "Stacked_sub.fit").write_text("stacksub")
    (fits / "M101_root.fit").write_text("rootstack")          # root stack → stacks/
    (fits / "darks").mkdir()
    (fits / "darks" / "dark1.fit").write_text("dark")          # preserved subdir

    seestar = root / "Images" / "Seestar_stacks" / "M101"
    seestar.mkdir(parents=True)
    (seestar / "Stacked_10.fit").write_text("ss")

    finished = root / "Images" / "Finished Images" / "M101"
    finished.mkdir(parents=True)
    (finished / "final.png").write_text("png")

    media = root / "Images" / "Lunar_photo"
    media.mkdir(parents=True)
    (media / "moon.jpg").write_text("moon")

    staging = root / "Images" / "From the scope" / "M5_sub"
    staging.mkdir(parents=True)
    (staging / "Light_m5.fit").write_text("m5")


def test_migrate_reshapes_store(tmp_path):
    root = tmp_path / "M110"
    _build_old_layout(root)

    assert migrate.migrate_store(root) is True

    internal = root / INTERNAL
    # machine state → hidden internal store
    assert (internal / "catalog.toml").is_file()
    assert (internal / "priorities.toml").is_file()
    assert (internal / "sessions.jsonl").is_file()
    assert (internal / "processing_overrides.toml").is_file()
    assert (internal / "derived" / "totals.json").is_file()
    # renders (site/img → renders), carrying hero/
    assert (internal / "renders" / "abc123.jpg").is_file()
    assert (internal / "renders" / "hero" / "m101.jpg").is_file()

    # journals → Objects/<catalog id>/journal.md (slug→id; fallback to slug)
    assert (root / "Objects" / "M101" / "journal.md").read_text() == "journal pinwheel\n"
    assert (root / "Objects" / "M81" / "journal.md").read_text() == "journal bode\n"
    assert (root / "Objects" / "weird" / "journal.md").is_file()  # no catalog id → slug

    # capture content: FITS/<t> collapses to Images/<t>, root stack → stacks/
    t = root / "Images" / "M101"
    assert (t / "lights" / "Light_x.fit").is_file()
    assert (t / "stacks" / "Stacked_sub.fit").is_file()
    assert (t / "stacks" / "M101_root.fit").is_file()       # root-level stack folded in
    assert (t / "darks" / "dark1.fit").is_file()            # other subdirs preserved
    assert (t / "seestar-stacks" / "Stacked_10.fit").is_file()
    assert (t / "finished" / "final.png").is_file()

    # media + staging → top-level siblings
    assert (root / "Media" / "Lunar_photo" / "moon.jpg").is_file()
    assert (root / "Inbox" / "M5_sub" / "Light_m5.fit").is_file()

    # legacy containers gone
    assert not (root / "data").exists()
    assert not (root / "site").exists()
    assert not (root / "Images" / "FITS").exists()
    assert not (root / "Images" / "Seestar_stacks").exists()
    assert not (root / "Images" / "Finished Images").exists()

    # version stamp
    assert (internal / ".store_version").read_text().strip() == "2"


def test_migrate_is_idempotent(tmp_path):
    root = tmp_path / "M110"
    _build_old_layout(root)
    assert migrate.migrate_store(root) is True
    # second run is a no-op (version stamp), tree unchanged
    assert migrate.migrate_store(root) is False
    assert (root / "Objects" / "M101" / "journal.md").read_text() == "journal pinwheel\n"
    assert (root / "Images" / "M101" / "lights" / "Light_x.fit").is_file()


def test_migrate_skips_fresh_root(tmp_path):
    root = tmp_path / "M110"
    (root / "Objects").mkdir(parents=True)
    (root / "Images").mkdir()
    # no old-layout markers → nothing to do
    assert migrate.migrate_store(root) is False

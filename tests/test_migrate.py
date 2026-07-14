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

    # OS junk that must not keep legacy containers alive after migration
    (root / "Images" / "FITS").mkdir(parents=True)
    (root / "Images" / "FITS" / ".DS_Store").write_text("")
    (root / "data" / ".DS_Store").write_text("")

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
    # machine state → hidden internal store; the object set lands as the Library
    # (v0 → reshape → v3 catalog.toml→library.toml, all in one pass).
    assert (internal / "library.toml").is_file()
    assert not (internal / "catalog.toml").exists()
    assert (internal / ".store_version").read_text().strip() == str(migrate.STORE_VERSION)
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

    # version stamp (asserted above)


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


def test_migrate_v2_to_v3_renames_catalog_to_library(tmp_path):
    """A two-axis (v2) store with catalog.toml is brought to v3: the per-store
    object set is renamed to library.toml (content preserved), no old-layout
    reshape needed."""
    root = tmp_path / "M110"
    internal = root / INTERNAL
    internal.mkdir(parents=True)
    (internal / "catalog.toml").write_text('[catalog.m31]\nid = "M31"\n')
    (internal / ".store_version").write_text("2")

    assert migrate.migrate_store(root) is True
    assert (internal / "library.toml").read_text() == '[catalog.m31]\nid = "M31"\n'
    assert not (internal / "catalog.toml").exists()
    assert (internal / ".store_version").read_text().strip() == str(migrate.STORE_VERSION)
    # idempotent
    assert migrate.migrate_store(root) is False


def test_migrate_v3_to_v4_prunes_combined_target_objects(tmp_path):
    """v3 → v4: a capture target wrongly promoted into the object axis (`m81-m82`,
    type "unknown", id "M81 M82") is dropped from the Library; real catalog objects
    and genuinely off-catalog targets are kept (#40c)."""
    root = tmp_path / "M110"
    internal = root / INTERNAL
    internal.mkdir(parents=True)
    (internal / "library.toml").write_text(
        '[catalog.m81]\nid = "M81"\ntype = "galaxy"\n\n'
        '[catalog.m81-m82]\nid = "M81 M82"\nname = ""\ntype = "unknown"\n\n'
        '[catalog.ngc-1234]\nid = "NGC 1234"\nname = ""\ntype = "unknown"\n')
    (internal / ".store_version").write_text("3")

    assert migrate.migrate_store(root) is True
    text = (internal / "library.toml").read_text()
    assert "[catalog.m81-m82]" not in text        # the pseudo-object is gone
    assert "[catalog.m81]" in text                # a real object stays
    assert "[catalog.ngc-1234]" in text           # an off-catalog target stays
    assert (internal / ".store_version").read_text().strip() == str(migrate.STORE_VERSION)
    # idempotent
    assert migrate.migrate_store(root) is False

"""Tests for the staging ingest planner + apply (temp fixtures, never live data)."""
from astronamigo import config, ingest


def _make_staging(tmp_path, monkeypatch):
    images = tmp_path / "Images"
    staging = images / "From the scope"
    staging.mkdir(parents=True)
    monkeypatch.setattr(config, "IMAGES_DIR", images)
    return images, staging


def test_plan_classifies_subs_stacks_media(tmp_path, monkeypatch):
    images, staging = _make_staging(tmp_path, monkeypatch)

    # raw subframes for a NEW object "M 13" → FITS/M13/lights/
    sub = staging / "M 13_sub"
    sub.mkdir()
    (sub / "Light_M13_20s_IRCUT_20260101-000000.fit").touch()
    (sub / "Light_M13_20s_IRCUT_20260101-000020.fit").touch()
    # in-app stacks dir
    stk = staging / "M13"
    stk.mkdir()
    (stk / "Stacked_10_M13.fit").touch()
    (stk / "not_a_stack.fit").touch()          # not a stack prefix → ignored
    # media dir
    med = staging / "Lunar_photo"
    med.mkdir()
    (med / "2026-01-01-000000-Lunar.jpg").touch()

    ops = ingest.scan_staging_plan()
    by_kind = {}
    for op in ops:
        by_kind.setdefault(op.kind, []).append(op)

    assert len(by_kind["light"]) == 2
    assert all(op.new_object for op in by_kind["light"])  # M13 FITS dir doesn't exist
    assert "FITS/M13/lights/" in by_kind["light"][0].dest_rel
    assert len(by_kind["stack"]) == 1                     # only the Stacked_ one
    assert by_kind["stack"][0].dest_rel.startswith("Seestar_stacks/M13/")
    assert len(by_kind["media"]) == 1
    assert by_kind["media"][0].dest_rel.startswith("Lunar_photo/")


def test_existing_files_excluded(tmp_path, monkeypatch):
    images, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    (sub / "Light_b.fit").touch()
    # one already present in the destination → only the other is "new"
    dest = images / "FITS" / "M5" / "lights"
    dest.mkdir(parents=True)
    (dest / "Light_a.fit").touch()

    ops = ingest.scan_staging_plan()
    names = sorted(op.src.rsplit("/", 1)[-1] for op in ops)
    assert names == ["Light_b.fit"]
    assert ops[0].new_object is False  # FITS/M5 already exists


def test_apply_moves_and_creates_dirs(tmp_path, monkeypatch):
    images, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81 M82_sub"
    sub.mkdir()
    (sub / "Light_x.fit").write_text("data")

    ops = ingest.scan_staging_plan()
    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}

    moved_to = images / "FITS" / "M81 M82" / "lights" / "Light_x.fit"
    assert moved_to.is_file()
    assert moved_to.read_text() == "data"
    assert not (sub / "Light_x.fit").exists()   # moved, not copied
    # re-scan now shows nothing new
    assert ingest.scan_staging_plan() == []


def test_scan_cancellation_raises(tmp_path, monkeypatch):
    images, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    import pytest
    with pytest.raises(ingest.IngestCancelled):
        ingest.scan_staging_plan(should_cancel=lambda: True)


def test_apply_cancellation_stops_cleanly(tmp_path, monkeypatch):
    images, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "a.fit").write_text("1")
    (sub / "b.fit").write_text("2")
    ops = ingest.scan_staging_plan()
    # cancel before any op runs
    result = ingest.apply_ops(ops, should_cancel=lambda: True)
    assert result["cancelled"] is True
    assert result["moved"] == 0


def test_no_staging_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")  # no "From the scope"
    assert ingest.staging_available() is False
    assert ingest.scan_staging_plan() == []


def test_seestar_plan_uses_copy_and_leaves_device(tmp_path, monkeypatch):
    images = tmp_path / "Images"
    images.mkdir(parents=True)
    monkeypatch.setattr(config, "IMAGES_DIR", images)
    # fake mounted device MyWorks with the staging layout
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    sub = myworks / "M 13_sub"
    sub.mkdir(parents=True)
    (sub / "Light_M13_a.fit").write_text("data")
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    ops = ingest.scan_seestar_plan()
    assert len(ops) == 1
    assert ops[0].action == "copy"
    assert "FITS/M13/lights/" in ops[0].dest_rel

    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}
    # copied into collection AND still present on the "device"
    assert (images / "FITS" / "M13" / "lights" / "Light_M13_a.fit").is_file()
    assert (sub / "Light_M13_a.fit").is_file()

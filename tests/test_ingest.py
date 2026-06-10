"""Tests for the staging ingest planner + apply (temp fixtures, never live data).

dest_rel is relative to the data root, so destinations read as
``Images/<target>/lights``, ``Images/<target>/seestar-stacks``, ``Media/<cat>``.
"""
from m110 import config, ingest


def _make_staging(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "MEDIA_DIR", root / "Media")
    monkeypatch.setattr(config, "STAGING_DIR", root / "Inbox")
    staging = root / "Inbox"
    staging.mkdir(parents=True)
    return root, staging


def test_plan_classifies_subs_stacks_media(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)

    # raw subframes for a NEW object "M 13" → Images/M13/lights/
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
    assert all(op.new_object for op in by_kind["light"])  # M13 target doesn't exist
    assert "Images/M13/lights/" in by_kind["light"][0].dest_rel
    assert len(by_kind["stack"]) == 1                     # only the Stacked_ one
    assert by_kind["stack"][0].dest_rel.startswith("Images/M13/seestar-stacks/")
    assert len(by_kind["media"]) == 1
    assert by_kind["media"][0].dest_rel.startswith("Media/Lunar_photo/")


def test_existing_files_excluded(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    (sub / "Light_b.fit").touch()
    # one already present in the destination → only the other is "new"
    dest = config.lights_dir("M5")
    dest.mkdir(parents=True)
    (dest / "Light_a.fit").touch()

    ops = ingest.scan_staging_plan()
    names = sorted(op.src.rsplit("/", 1)[-1] for op in ops)
    assert names == ["Light_b.fit"]
    assert ops[0].new_object is False  # Images/M5 already exists


def test_apply_moves_and_creates_dirs(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81 M82_sub"
    sub.mkdir()
    (sub / "Light_x.fit").write_text("data")

    ops = ingest.scan_staging_plan()
    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}

    moved_to = config.lights_dir("M81 M82") / "Light_x.fit"
    assert moved_to.is_file()
    assert moved_to.read_text() == "data"
    assert not (sub / "Light_x.fit").exists()   # moved, not copied
    # re-scan now shows nothing new
    assert ingest.scan_staging_plan() == []


def test_scan_cancellation_raises(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    import pytest
    with pytest.raises(ingest.IngestCancelled):
        ingest.scan_staging_plan(should_cancel=lambda: True)


def test_apply_cancellation_stops_cleanly(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
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
    monkeypatch.setattr(config, "STAGING_DIR", tmp_path / "Inbox")  # not created
    assert ingest.staging_available() is False
    assert ingest.scan_staging_plan() == []


def test_seestar_plan_uses_copy_and_leaves_device(tmp_path, monkeypatch):
    root, _ = _make_staging(tmp_path, monkeypatch)
    # fake mounted device MyWorks with the staging layout
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    sub = myworks / "M 13_sub"
    sub.mkdir(parents=True)
    (sub / "Light_M13_a.fit").write_text("data")
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    ops = ingest.scan_seestar_plan()
    assert len(ops) == 1
    assert ops[0].action == "copy"
    assert "Images/M13/lights/" in ops[0].dest_rel

    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}
    # copied into collection AND still present on the "device"
    assert (config.lights_dir("M13") / "Light_M13_a.fit").is_file()
    assert (sub / "Light_M13_a.fit").is_file()


def test_seestar_copies_stack_previews(tmp_path, monkeypatch):
    """Stack folders' preview .jpg/.png are copied too (so the gallery has
    ready-made images); the device's *_thn.* sidecars are skipped."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    stk = myworks / "M13"
    stk.mkdir(parents=True)
    (stk / "Stacked_10_M13.fit").write_text("f")
    (stk / "M13.jpg").write_text("j")          # device preview render
    (stk / "M13_thn.jpg").write_text("t")      # device thumbnail sidecar (skip)
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    names = sorted(op.src.rsplit("/", 1)[-1] for op in ingest.scan_seestar_plan())
    assert "Stacked_10_M13.fit" in names
    assert "M13.jpg" in names
    assert "M13_thn.jpg" not in names

"""The `rejected/` sub tier (#110) — exclude subs from processing without deleting
them, and without the telescope re-syncing them on the next import.

Two halves, tested separately because they fail in different ways:
  * **prep** must not link a rejected sub into a Siril sandbox — and, since
    `apply_prep` is add-only, `prune_rejected` must drop the link of a sub rejected
    *after* a sandbox already existed;
  * **import** must treat `lights/` + `rejected/` as one population, so a rejected
    sub is never copied back in (which is the whole reason to move rather than delete).
"""
from m110 import config, ingest, processing, scan_sessions, siril


def _isolate(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "INTERNAL_DIR", root / ".m110_internal_data")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return root


def _sub(target: str, n: int) -> str:
    """A Seestar-shaped sub filename (the `scan_sessions` filename fast path reads
    date/exposure/filter straight from it, so no real FITS payload is needed)."""
    return f"Light_{target}_30.0s_LP_2026052{n}-01010{n}.fit"


def _capture(target: str, count: int = 3) -> list[str]:
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    names = [_sub(target, i) for i in range(1, count + 1)]
    for name in names:
        (d / name).write_text("x")
    return names


def _reject(target: str, name: str) -> None:
    """Move a sub out of `lights/` into `rejected/` — what the user does by hand."""
    dest = config.rejected_dir(target)
    dest.mkdir(parents=True, exist_ok=True)
    (config.lights_dir(target) / name).rename(dest / name)


def _sandbox_links(target: str) -> set[str]:
    out = set()
    base = config.siril_dir(target)
    for ldir in siril._sandbox_lights_dirs(base):
        out |= {f.name for f in ldir.iterdir() if f.is_file()}
    return out


# ── prep: a rejected sub is out of the population ───────────────────────────

def test_prep_does_not_link_a_rejected_sub(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    _reject("M101", names[0])

    plan = siril.plan_prep("M101")
    assert plan.total_lights == 2
    linked = {name for job in plan.jobs for (_src, dst) in job.links
              for name in [dst.rsplit("/", 1)[-1]]}
    assert linked == set(names[1:])


def test_prune_drops_the_link_of_a_sub_rejected_after_prep(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    assert _sandbox_links("M101") == set(names)

    _reject("M101", names[0])                     # …after the sandbox already exists
    res = siril.prune_rejected("M101")

    assert res == {"pruned": 1, "orphans": 0, "skipped": False}
    assert _sandbox_links("M101") == set(names[1:])
    # The frame itself is untouched — moved, never destroyed.
    assert (config.rejected_dir("M101") / names[0]).is_file()


def test_prune_leaves_a_sub_that_merely_vanished(tmp_path, monkeypatch):
    """No `rejected/` copy means the sandbox link may be the last one — never unlink."""
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    (config.lights_dir("M101") / names[0]).unlink()

    res = siril.prune_rejected("M101")

    assert res["pruned"] == 0 and res["orphans"] == 1
    assert _sandbox_links("M101") == set(names)


def test_prune_skips_a_target_with_unimported_output(tmp_path, monkeypatch):
    """Same guard as `autoprep` — never disturb an in-progress/finished run."""
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    (config.siril_dir("M101") / "M101_processed.png").write_text("render")
    _reject("M101", names[0])

    res = siril.prune_rejected("M101")

    assert res["skipped"] is True and res["pruned"] == 0
    assert _sandbox_links("M101") == set(names)


def test_prune_covers_a_stale_single_filter_lights_dir(tmp_path, monkeypatch):
    """A target that became multi-filter leaves its old `siril/lights/` behind
    (BUGS #28) — the stale dir is exactly where an excluded sub would go on being
    stacked, so the prune must reach it and not just the live job dirs."""
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    stale = config.siril_dir("M101") / "lights"
    live = config.siril_dir("M101") / "LP" / "lights"
    for d in (stale, live):
        d.mkdir(parents=True)
        for name in names:
            (d / name).write_text("x")

    _reject("M101", names[0])
    res = siril.prune_rejected("M101")

    assert res["pruned"] == 2
    assert names[0] not in {f.name for f in stale.iterdir()}
    assert names[0] not in {f.name for f in live.iterdir()}


def test_prune_never_touches_the_archive_or_presets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    archived = config.siril_dir("M101") / "archive" / "20260101-000000"
    archived.mkdir(parents=True)
    (archived / names[0]).write_text("x")
    preset = config.siril_dir("M101") / "presets" / siril.PRESET_NAME

    _reject("M101", names[0])
    siril.prune_rejected("M101")

    assert (archived / names[0]).is_file()
    assert preset.is_file()


def test_reconcile_rejected_runs_over_the_store(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    _reject("M101", names[0])

    res = processing.reconcile_rejected()

    assert res["siril"]["pruned"] == 1
    assert _sandbox_links("M101") == set(names[1:])


def test_reconcile_rejected_is_a_noop_without_the_tier(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _capture("M101")
    siril.apply_prep(siril.plan_prep("M101"))
    assert processing.reconcile_rejected() == {"siril": {"pruned": 0, "orphans": 0}}


# ── sessions: a rejected sub stops counting toward integration ──────────────

def test_sessions_ignore_rejected_subs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    rows = scan_sessions.scan()
    assert sum(r["frames"] for r in rows) == len(names)

    _reject("M101", names[0])
    rows = scan_sessions.scan()
    assert sum(r["frames"] for r in rows) == len(names) - 1


# ── import: the two tiers are one population ────────────────────────────────

def _source(root, target, tier, names):
    """A source directory shaped like an M110 store: <src>/<target>/<tier>/…"""
    d = root / "src" / target / tier
    d.mkdir(parents=True)
    for name in names:
        (d / name).write_text("x")
    return root / "src"


def test_import_does_not_resync_a_rejected_sub(tmp_path, monkeypatch):
    """The point of the whole feature: the telescope still holds the frame, and
    importing again must not bring it back into `lights/`.

    The source also carries one genuinely new sub, so a scan that silently
    recognized nothing would fail this rather than pass it."""
    root = _isolate(tmp_path, monkeypatch)
    names = _capture("M101")
    _reject("M101", names[0])
    fresh = _sub("M101", 9)
    src = _source(root, "M101", "lights", names + [fresh])

    ops = ingest.scan_directory_plan(src)

    assert [o.dest_rel for o in ops] == [f"Images/M101/lights/{fresh}"]


def test_import_preserves_the_rejected_tier(tmp_path, monkeypatch):
    """Importing from another store (a backup, the precursor library) keeps the
    exclusion — without the layout mapping these read as loose FITS and land in
    `lights/` via the OBJECT header."""
    root = _isolate(tmp_path, monkeypatch)
    names = [_sub("M101", 1)]
    src = _source(root, "M101", "rejected", names)

    ops = ingest.scan_directory_plan(src)

    assert len(ops) == 1
    assert ops[0].kind == "rejected"
    assert ops[0].dest_rel == f"Images/M101/rejected/{names[0]}"


def test_import_does_not_copy_a_live_sub_into_rejected(tmp_path, monkeypatch):
    """Symmetric to the resync guard: a sub already in `lights/` must not be
    duplicated into `rejected/` because some other store filed it there."""
    root = _isolate(tmp_path, monkeypatch)
    names = _capture("M101", count=1)
    src = _source(root, "M101", "rejected", names)

    assert ingest.scan_directory_plan(src) == []

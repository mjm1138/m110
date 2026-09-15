"""The round-trip's output discovery must never *enter* a sandbox's hardlinked
frame tree, only skip it.

`sandbox_outputs` / `root_outputs` used to ``rglob("*")`` the whole target and
drop the skipped directories' files afterwards. Semantically fine, but the
skipped directories are the huge ones — ``lights/`` and every sandbox's hardlink
copy of it — so each `has_unimported_output` listed and stat'ed the entire
capture three times over. Asked for every target on every sync, that grew
with the collection until the refresh took ~20 s on a 42k-sub store. The walk
now prunes those directories before descending; these tests pin that down by
watching which directories are actually opened.
"""
import os

from m110 import astrowizard, config, roundtrip, siril


def _target(tmp_path, monkeypatch, name="M42"):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    base = config.target_dir(name)
    # Raw subs, the Siril hardlink tree (with a per-filter job) and the
    # AstroWizard one — three copies of the capture, plus a sub-subdir inside
    # each so a non-pruning walk would have to recurse further still.
    for tree in ("lights", "siril/LP/lights", "siril/lights", "astrowizard/lights"):
        d = base / tree
        (d / "deeper").mkdir(parents=True)
        for i in range(5):
            (d / f"Light_M42_10.0s_LP_2026081{i}-220000.fit").write_text("sub")
        (d / "deeper" / "M42_final.png").write_text("would be claimed if walked")
    # …and the real output the walk exists to find.
    (base / "siril" / "LP" / "M42_processed.png").write_text("render")
    (base / "astrowizard" / "M42_final.png").write_text("finish")
    (base / "stray_processed.png").write_text("loose in the object dir")
    return name, base


def _opened_dirs(monkeypatch):
    seen = []
    real = os.scandir

    def spy(path=".", *a, **kw):
        seen.append(os.fspath(path))
        return real(path, *a, **kw)
    monkeypatch.setattr(os, "scandir", spy)
    return seen


def _touched(seen, base, *names):
    return [p for p in seen if any(os.sep + n in p.replace(str(base), "")
                                   for n in names)]


def test_siril_discovery_never_descends_into_frame_trees(tmp_path, monkeypatch):
    target, base = _target(tmp_path, monkeypatch)
    seen = _opened_dirs(monkeypatch)
    found = sorted(p.name for p, _k, _d in roundtrip.finished_outputs(target, siril.SANDBOX))
    # The outputs are found (sandbox job dir + loose in the object dir)…
    assert found == ["M42_processed.png", "stray_processed.png"]
    # …the other workflow's sandbox is not claimed…
    assert "M42_final.png" not in found
    # …and no ``lights/`` (or its subdirs) was ever opened, nor the other sandbox.
    assert _touched(seen, base, "lights", "astrowizard") == []
    assert siril.has_unimported_output(target) is True


def test_astrowizard_discovery_never_descends_into_frame_trees(tmp_path, monkeypatch):
    target, base = _target(tmp_path, monkeypatch)
    seen = _opened_dirs(monkeypatch)
    found = sorted(p.name for p, _k, _d in roundtrip.finished_outputs(target, astrowizard.SANDBOX))
    assert found == ["M42_final.png"]
    assert _touched(seen, base, "lights", "siril") == []
    assert astrowizard.has_unimported_output(target) is True


def test_walk_matches_the_ancestor_rule(tmp_path, monkeypatch):
    """A file is skipped iff *any* ancestor directory name is in the skip set —
    exactly what the old post-filter computed — and symlinked dirs aren't followed."""
    base = tmp_path / "t"
    (base / "keep" / "lights" / "x").mkdir(parents=True)
    (base / "keep" / "lights" / "x" / "a.png").write_text("skipped: under lights")
    (base / "keep" / "b.png").write_text("kept")
    (base / "lights" / "keep").mkdir(parents=True)
    (base / "lights" / "keep" / "c.png").write_text("skipped: lights is an ancestor")
    (base / "d.png").write_text("kept")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "e.png").write_text("only reachable via a symlink")
    os.symlink(tmp_path / "elsewhere", base / "keep" / "link")
    got = {p.name: parts for p, parts in roundtrip._walk_files(base, {"lights"})}
    assert got == {"b.png": ("keep",), "d.png": ()}


def test_only_missing_backfill_checks_existence_before_listing_lights(tmp_path, monkeypatch):
    """The refresh-time backfill must not list a prepped target's subs just to skip it."""
    target, base = _target(tmp_path, monkeypatch)
    seen = _opened_dirs(monkeypatch)
    siril.autoprep([target], only_missing=True)
    assert _touched(seen, base, "lights") == []

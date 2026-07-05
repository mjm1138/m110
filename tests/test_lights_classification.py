"""Lights vs. processing-by-products classification (the M27 phantom-filter bug).

One shared definition of "a raw light sub" — `config.is_light_frame` (the
capture-timestamp signature `scan_sessions` already uses) — is enforced in two
places that used to disagree:

  * import (bug A): a non-sub `.fit` in a lights source is routed to
    `working_files/`, never `lights/`;
  * Siril prep (bug B): `siril._lights` ignores non-subs, so a stray product
    can't spawn a phantom `OTHER` filter / bogus job.

Plus the one-time cleanup (bug C): `ingest.plan_lights_cleanup` relocates
already-mis-filed products out of `lights/`.
"""
from __future__ import annotations

from m110 import config, ingest, siril
from ._helpers import seed_root


# Real Seestar subs (trailing capture timestamp) vs. Siril/PixInsight products.
SUBS = [
    "Light_M 27_20.0s_LP_20260525-030150.fit",
    "mosaic_M27_10.0s_IRCUT_20260601-224501.fit",
]
PRODUCTS = [
    "M27_final.fit",
    "starless_M_27_888x20sec_2026-05-25_drizzle-1-5x_2026-06-28_1344_spcc.fit",
    "M_27_2026-06-28_processed.fit",
    "VeraLux_StarComposer_result.fit",
]


def test_is_light_frame_classification():
    for s in SUBS:
        assert config.is_light_frame(s), s
    for p in PRODUCTS:
        assert not config.is_light_frame(p), p
    # Fail-safe: an unknown-rig sub with no product markers is kept as a light
    # (we deny known products, we don't whitelist Seestar naming).
    assert config.is_light_frame("DWARF_something_0000.fit")
    assert not config.is_light_frame("anything.png")   # not a .fit


def _seed_lights(root, target, names):
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("x")
    return d


# ── bug B: prep ignores non-subs ─────────────────────────────────────────────

def test_prep_lights_excludes_products(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _seed_lights(root, "M27", SUBS + PRODUCTS)
    plan = siril.plan_prep("M27")
    # Only the two real subs are seen (across their genuine LP/IRCUT filters);
    # the products don't invent a phantom OTHER filter.
    assert plan.total_lights == len(SUBS)
    assert plan.filters == ["IRCUT", "LP"]
    assert "OTHER" not in plan.filters
    linked = {name for j in plan.jobs for _, dst in j.links
              for name in [dst.rsplit("/", 1)[-1]]}
    assert not (linked & set(PRODUCTS))


# ── bug A: import diverts non-subs to working_files/ ─────────────────────────

def test_emit_files_routes_products_to_working(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "src"
    src.mkdir()
    for n in SUBS + PRODUCTS:
        (src / n).write_text("x")
    ops = ingest._emit_files(src, SUBS + PRODUCTS, "light", "M27",
                             "M27", "copy", "raw-fits")
    by_kind: dict[str, set[str]] = {}
    for op in ops:
        by_kind.setdefault(op.kind, set()).add(op.dest.rsplit("/", 1)[-1])
    assert by_kind["light"] == set(SUBS)
    assert by_kind["working"] == set(PRODUCTS)
    # Destinations land in the right tiers.
    for op in ops:
        parent = op.dest.rsplit("/", 2)[-2]
        assert parent == ("lights" if op.kind == "light" else "working_files")


# ── bug C: cleanup relocates existing pollution ──────────────────────────────

def test_plan_lights_cleanup(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _seed_lights(root, "M27", SUBS + PRODUCTS)
    _seed_lights(root, "M13", SUBS)                 # clean target — untouched
    ops = ingest.plan_lights_cleanup()
    assert {op.dest.rsplit("/", 1)[-1] for op in ops} == set(PRODUCTS)
    assert all(op.action == "move" and op.kind == "working" for op in ops)
    assert all(op.object == "M27" for op in ops)    # M13 produced nothing

    ingest.apply_ops(ops)
    lights_left = {f.name for f in config.lights_dir("M27").iterdir()}
    working = {f.name for f in config.working_files_dir("M27").iterdir()}
    assert lights_left == set(SUBS)                 # subs stay
    assert working == set(PRODUCTS)                 # products relocated
    # Idempotent: a second plan finds nothing.
    assert ingest.plan_lights_cleanup() == []

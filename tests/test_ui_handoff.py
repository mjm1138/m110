"""Offscreen wiring test for the "Send to AstroWizard" handoff (ROADMAP 14a).

The engine half (`stacking.handoff_candidates` / `apply_handoff`) is tested in
test_stacking.py. What is only testable here is that the dialog **actually calls
it** — a preview that lists the right stacks but writes nothing, or writes the
wrong one, looks identical from the engine's side. Temp store via
`tests/_helpers.seed_root`; the `qapp` fixture comes from pytest-qt.
"""
import json

import pytest

pytest.importorskip("PySide6")

from m110 import config, stacking  # noqa: E402
from tests._helpers import seed_capture, seed_root  # noqa: E402


def _stack(path, when, *, frames=100, history=None):
    """A FITS stack carrying the header cards the handoff reads."""
    import numpy as np
    from astropy.io import fits
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["DATE"] = when
    h.header["STACKCNT"] = frames
    h.header["LIVETIME"] = frames * 20.0
    h.header["OBJECT"] = path.stem
    for line in history or []:
        h.header["HISTORY"] = line
    h.writeto(path)
    return path


def _dialog(slug, monkeypatch, parent=None):
    """The dialog with the post-send message box stubbed out — it is modal and
    would block the run; what it offers is tested by reading `_sent`."""
    from m110.ui.handoff_dialog import HandoffDialog
    monkeypatch.setattr(HandoffDialog, "_offer_to_open", lambda self: None)
    return HandoffDialog(slug, parent=parent)


def test_dialog_lists_stacks_newest_first_and_hands_the_chosen_one_over(
        tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    older = _stack(config.stacks_dir(target) / "older.fit", "2026-07-01T00:00:00")
    newer = _stack(config.siril_dir(target) / "newer.fit", "2026-08-19T00:00:00",
                   frames=900)

    d = _dialog(slug, monkeypatch)
    try:
        names = [d._table.item(r, 0).text() for r in range(d._table.rowCount())]
        assert names == ["newer.fit", "older.fit"]
        # Row 0 preselected: the stack someone wants to finish is the one they
        # just made, so the default answer should need no clicks.
        assert d._selected()[1].name == "newer.fit"
        assert d._send.isEnabled()

        d._do_send()

        dest = config.astrowizard_dir(target) / "newer.fit"
        assert d._sent == dest
        assert dest.stat().st_ino == newer.stat().st_ino    # hardlinked, no disk cost
        prov = json.loads((dest.parent / ("newer.fit" + stacking.SIDECAR_SUFFIX))
                          .read_text())
        assert prov["frames"] == 900 and prov["source"] == "newer.fit"
        # The one that was not chosen stays where it was.
        assert not (config.astrowizard_dir(target) / older.name).exists()
    finally:
        d.deleteLater(); qapp.processEvents()


def test_selecting_a_different_row_hands_over_that_one(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    _stack(config.stacks_dir(target) / "older.fit", "2026-07-01T00:00:00")
    _stack(config.siril_dir(target) / "newer.fit", "2026-08-19T00:00:00")

    d = _dialog(slug, monkeypatch)
    try:
        d._table.selectRow(1)
        assert d._selected()[1].name == "older.fit"
        d._do_send()
        assert d._sent.name == "older.fit"
    finally:
        d.deleteLater(); qapp.processEvents()


def test_re_sorting_the_table_still_hands_over_the_highlighted_stack(
        tmp_path, monkeypatch, qapp):
    """The sharp one: the table is sortable, so a visual row index is not a stable
    handle on a candidate. Reading the selection back by position sent a DIFFERENT
    file than the one highlighted — silently, and after a confirmation the user
    had already given."""
    from PySide6.QtCore import Qt

    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    _stack(config.stacks_dir(target) / "older.fit", "2026-07-01T00:00:00", frames=10)
    _stack(config.siril_dir(target) / "newer.fit", "2026-08-19T00:00:00", frames=900)

    d = _dialog(slug, monkeypatch)
    try:
        d._table.selectRow(0)
        chosen = d._selected()[1].name
        assert chosen == "newer.fit"

        # Sort ascending by name — "newer" and "older" swap places, the selection
        # follows the row it was on, and the answer must not change with it.
        d._table.sortByColumn(0, Qt.AscendingOrder)
        d._table.selectRow(1)                       # whatever is now second
        second = d._table.item(1, 0).text()
        assert d._selected()[1].name == second

        d._do_send()
        assert d._sent.name == second
    finally:
        d.deleteLater(); qapp.processEvents()


def test_an_object_with_no_stacks_explains_itself_and_cannot_send(
        tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, _target = seed_capture(root)          # lights only, nothing stacked

    d = _dialog(slug, monkeypatch)
    try:
        assert d._table.rowCount() == 0
        assert not d._send.isEnabled()
        assert "stack it first" in d._status.text().lower()
    finally:
        d.deleteLater(); qapp.processEvents()


def test_the_button_gate_matches_what_the_dialog_would_show(tmp_path, monkeypatch,
                                                            qapp):
    """`can_hand_off` is the cheap header-free check the detail pane calls on every
    render; it must agree with the expensive listing or the button lies."""
    from m110.ui.handoff_dialog import can_hand_off

    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    assert can_hand_off(slug) is False

    _stack(config.stacks_dir(target) / "s.fit", "2026-08-19T00:00:00")
    assert can_hand_off(slug) is True
    assert can_hand_off(slug, "pixinsight") is False     # unknown tool, not a crash


def test_it_preselects_the_linear_stack_not_merely_the_newest(
        tmp_path, monkeypatch, qapp):
    """On a real library `stacks/` holds the stacker's output next to the user's
    own saved steps, and the newest file is very often a stretched one — so
    defaulting to row 0 handed AstroWizard exactly the wrong thing. Judged from
    the header: `_denoise` sounds like a linear step and is not."""
    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    _stack(config.stacks_dir(target) / "og.fit", "2026-08-01T00:00:00",
           history=["mean stacking with winsorized sigma clipping rejection"])
    _stack(config.stacks_dir(target) / "denoise.fit", "2026-08-19T00:00:00",
           history=["Background extraction (Correction: Subtraction)",
                    "VeraLux v1.5.2 Stretch",
                    "GraXpert AI denoise: strength 0.76"])

    d = _dialog(slug, monkeypatch)
    try:
        # Newest first, so the stretched one is still at the top of the list…
        assert d._table.item(0, 0).text().endswith("denoise.fit")
        # …but the linear one is what's selected.
        assert d._selected()[1].name == "og.fit"

        state = {d._table.item(r, 0).text(): d._table.item(r, 6).text()
                 for r in range(d._table.rowCount())}
        assert set(state.values()) == {"linear", "stretched"}

        # And picking the stretched one anyway is allowed, but says so.
        d._table.selectRow(0)
        assert "already been stretched" in d._status.text()
        assert d._send.isEnabled()
    finally:
        d.deleteLater(); qapp.processEvents()


def test_an_intermediate_never_reaches_the_picker(tmp_path, monkeypatch, qapp):
    """A starless layer carries the same STACKCNT as its parent, so it would sort
    to the top and be exactly the wrong thing to finish."""
    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    _stack(config.siril_dir(target) / "s.fit", "2026-08-19T00:00:00")
    _stack(config.siril_dir(target) / "starless_s.fit", "2026-08-19T01:00:00")

    d = _dialog(slug, monkeypatch)
    try:
        names = [d._table.item(r, 0).text() for r in range(d._table.rowCount())]
        assert names == ["s.fit"]
    finally:
        d.deleteLater(); qapp.processEvents()

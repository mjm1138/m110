"""Offscreen wiring for the assistant queue surface.

The banner-not-modal decision is a behavioural claim, so it gets asserted:
nothing here may pop a dialog on its own.
"""
import pytest

pytest.importorskip("PySide6")

from m110 import config, pins, prioritize  # noqa: E402
from m110.assistant import outbox, registry, tools  # noqa: E402,F401
from tests._helpers import add_library, seed_root as _seed_root  # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = _seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "ASSISTANT_DIR",
                        root / config.INTERNAL_DIRNAME / "assistant")
    monkeypatch.setattr(config, "ASSISTANT_OUTBOX",
                        root / config.INTERNAL_DIRNAME / "assistant" / "outbox")
    add_library(root, {"m101": {"id": "M101", "name": "Pinwheel", "type": "galaxy"}})
    prioritize.write_contexts([
        prioritize.TargetContext("m101", "galaxy", 30.0, True,
                                 {"observable": True, "transit_alt": 70.0,
                                  "hours_clear": 4.0, "nights_to_close": 40}, None, None)])
    return root


def _banner(qapp):
    from m110.ui.assistant_review import AssistantBanner
    return AssistantBanner()


def test_banner_is_hidden_when_the_queue_is_empty(store, qapp):
    b = _banner(qapp)
    try:
        assert b.refresh() == 0
        assert not b.isVisible()
    finally:
        b.deleteLater()


def test_banner_appears_and_counts_both_kinds(store, qapp):
    registry.call("save_field_guide", {"title": "Tonight", "markdown": "# Tonight\n"})
    registry.call("propose_pins", {"rationale": "r", "pin": ["m101"]})
    b = _banner(qapp)
    try:
        assert b.refresh() == 2
        text = b._msg.text()
        assert "1 saved plan" in text and "1 suggested change" in text
    finally:
        b.deleteLater()


def test_banner_has_no_dismiss_control(store, qapp):
    """It's the queue indicator — it goes away by emptying the queue, not by
    being hidden. A dismissible one would defeat 'nothing gets missed'."""
    from PySide6.QtWidgets import QPushButton
    registry.call("save_field_guide", {"title": "x", "markdown": "# x\n"})
    b = _banner(qapp)
    try:
        b.refresh()
        labels = {btn.text() for btn in b.findChildren(QPushButton)}
        assert labels == {"Review…"}
    finally:
        b.deleteLater()


def test_review_dialog_lists_and_accepts_an_artifact(store, qapp):
    from m110.ui.assistant_review import AssistantReviewDialog
    registry.call("save_field_guide", {
        "title": "Summer", "date": "2026-07-13", "markdown": "# Summer\n\nBody.\n"})
    dlg = AssistantReviewDialog()
    try:
        assert dlg._list.count() == 1
        assert "Body." in dlg._detail.toMarkdown()
        dlg._accept()
        assert dlg._list.count() == 0
        assert outbox.count() == 0
        saved = list(config.PLANS_DIR.glob("*.md"))
        assert len(saved) == 1 and saved[0].name.startswith("2026-07-13_")
    finally:
        dlg.deleteLater()


def test_review_dialog_applies_a_proposal(store, qapp):
    from m110.ui.assistant_review import AssistantReviewDialog
    registry.call("propose_pins", {"rationale": "r", "pin": ["m101"]})
    dlg = AssistantReviewDialog()
    try:
        assert pins.load() == {}
        dlg._accept()
        assert pins.get_state("m101") == "pin"
        assert outbox.count() == 0
    finally:
        dlg.deleteLater()


def test_review_dialog_warns_when_the_store_has_drifted(store, qapp):
    from m110.ui.assistant_review import AssistantReviewDialog
    registry.call("propose_pins", {"rationale": "r", "pin": ["m101"]})
    # The real sequence: shoot, import, refresh.
    prioritize.write_contexts([
        prioritize.TargetContext("m101", "galaxy", 400.0, True,
                                 {"observable": True, "transit_alt": 70.0,
                                  "hours_clear": 4.0, "nights_to_close": 3}, None, None)])
    dlg = AssistantReviewDialog()
    try:
        dlg._show_current()
        assert "⚠" in dlg._status.text()
        assert "recomputed" in dlg._status.text()
    finally:
        dlg.deleteLater()


def test_constructing_the_surface_pops_no_dialog(store, qapp, monkeypatch):
    """The whole point of the banner: notification must never interrupt."""
    from PySide6.QtWidgets import QMessageBox
    from m110.ui.assistant_review import AssistantBanner
    registry.call("save_field_guide", {"title": "x", "markdown": "# x\n"})
    for name in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, **k: pytest.fail("a modal was shown"))
    b = AssistantBanner()
    try:
        b.refresh()
    finally:
        b.deleteLater()

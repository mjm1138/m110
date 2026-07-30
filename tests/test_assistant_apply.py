"""Accepting staged items — the app-side half.

The drift check is the point: a proposal drafted before a four-hour session and
a refresh is reasoning about a library that no longer exists.
"""
import json
from datetime import date

import pytest

from m110 import config, fieldguide, objects as journals, pins, prioritize
from m110.assistant import apply as apply_mod, outbox, proposals
from m110.assistant import registry, tools  # noqa: F401
from tests._helpers import add_library, seed_root as _seed_root


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
                                  "hours_clear": 4.0, "nights_to_close": 40}, None, None),
        prioritize.TargetContext("m13", "globular", 0.0, True,
                                 {"observable": True, "transit_alt": 80.0,
                                  "hours_clear": 5.0, "nights_to_close": 90}, None, None),
    ])
    return root


# ── artifacts ────────────────────────────────────────────────────────────────

def test_accepting_a_guide_files_it_under_the_night_it_plans_for(store):
    registry.call("save_field_guide", {
        "title": "Summer galaxies", "date": "2026-07-13",
        "markdown": "# Observing plan — 2026-07-13\n\nBody.\n"})
    name = outbox.items()[0].name

    path = apply_mod.accept_artifact(name)
    assert path.parent == config.PLANS_DIR
    # The plan's OWN night, not today — the staged name carries it.
    assert path.name.startswith("2026-07-13_")
    # ...and the title the user asked for, not the document's generic H1.
    assert "summer-galaxies" in path.name
    assert "Body." in path.read_text(encoding="utf-8")
    assert outbox.count() == 0, "accepted items leave the queue"
    assert any(g["name"] == path.name for g in fieldguide.list_guides())


def test_accepting_twice_is_impossible(store):
    registry.call("save_field_guide", {"title": "x", "markdown": "# x\n"})
    name = outbox.items()[0].name
    apply_mod.accept_artifact(name)
    with pytest.raises(apply_mod.ApplyError, match="no longer"):
        apply_mod.accept_artifact(name)


def test_discarding_leaves_the_store_alone(store):
    registry.call("save_field_guide", {"title": "x", "markdown": "# x\n"})
    apply_mod.discard(outbox.items()[0].name)
    assert outbox.count() == 0
    assert fieldguide.list_guides() == []


# ── proposals ────────────────────────────────────────────────────────────────

def _stage(kind):
    if kind == "pins":
        return registry.call("propose_pins", {"rationale": "r", "pin": ["m101"]})
    if kind == "weights":
        return registry.call("propose_weights",
                             {"rationale": "r", "type_groups": {"galaxy": 2.0}})
    return registry.call("propose_journal_entry",
                         {"slug": "m101", "markdown": "A note.", "rationale": "r"})


def test_applying_a_pin_proposal_actually_pins(store):
    _stage("pins")
    name = outbox.items()[0].name
    assert pins.load() == {}
    apply_mod.apply_proposal(name)
    assert pins.get_state("m101") == "pin"
    assert outbox.count() == 0


def test_applying_a_weights_proposal_persists_the_tuning(store):
    _stage("weights")
    name = outbox.items()[0].name
    apply_mod.apply_proposal(name)
    assert prioritize.load_weights().type_weights.get("galaxy") == 2.0


def test_applying_a_journal_proposal_appends_without_losing_existing_notes(store):
    journals.write_journal("m101", "---\nhero: x.jpg\n---\n\nExisting note.\n")
    _stage("journal")
    apply_mod.apply_proposal(outbox.items()[0].name)
    text = journals.read_journal_text("m101")
    assert "Existing note." in text and "A note." in text
    assert text.index("Existing note.") < text.index("A note.")


# ── drift: the reason basis.store_state exists ───────────────────────────────

def test_drift_is_detected_when_the_ranking_is_recomputed(store):
    _stage("pins")
    name = outbox.items()[0].name

    # Simulate the real sequence: shoot, import, refresh.
    prioritize.write_contexts([
        prioritize.TargetContext("m101", "galaxy", 400.0, True,
                                 {"observable": True, "transit_alt": 70.0,
                                  "hours_clear": 4.0, "nights_to_close": 3}, None, None)])

    report = apply_mod.check_drift(json.loads(outbox.read(name)))
    assert report.drifted
    assert "recomputed" in report.describe()

    with pytest.raises(apply_mod.ApplyError, match="changed since this was suggested"):
        apply_mod.apply_proposal(name)
    assert pins.load() == {}, "a drifted proposal must not be applied"

    # ...but the user can still choose to go ahead.
    apply_mod.apply_proposal(name, force=True)
    assert pins.get_state("m101") == "pin"


def test_journal_drift_is_detected_when_notes_are_edited(store):
    journals.write_journal("m101", "original\n")
    _stage("journal")
    name = outbox.items()[0].name
    journals.write_journal("m101", "edited by hand\n")
    report = apply_mod.check_drift(json.loads(outbox.read(name)))
    assert report.drifted and "notes were edited" in report.describe()


def test_no_drift_when_nothing_changed(store):
    _stage("pins")
    report = apply_mod.check_drift(json.loads(outbox.read(outbox.items()[0].name)))
    assert not report.drifted


def test_repreview_reflects_the_store_as_it_is_now(store):
    _stage("pins")
    envelope = json.loads(outbox.read(outbox.items()[0].name))
    fresh = apply_mod.repreview(envelope)
    assert fresh["after"][0]["slug"] == "m101"        # the pin floats it to the top


# ── the allowlist is the gate ────────────────────────────────────────────────

def test_an_action_outside_the_allowlist_is_refused(store):
    envelope = proposals.build(
        action="delete_everything", title="Nope", rationale="r",
        payload={}, summary="s")
    assert envelope["apply"]["safe_write"] is False
    outbox.write("evil.json", json.dumps(envelope), kind="proposal")
    with pytest.raises(apply_mod.ApplyError, match="not on the list"):
        apply_mod.apply_proposal("evil.json")


def test_a_non_proposal_file_is_refused(store):
    outbox.write("notes.json", json.dumps({"hello": "world"}), kind="proposal")
    with pytest.raises(apply_mod.ApplyError, match="not a proposal"):
        apply_mod.apply_proposal("notes.json")

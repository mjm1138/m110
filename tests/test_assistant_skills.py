"""The skills layer: loader, the `get_skill` tool, and the content itself.

The content tests are deliberately assertive. These files are instructions to a
model about a read-only server, and the failure mode of a wrong one is
confident, plausible fiction told to the user — which is exactly what the whole
design is built to prevent.
"""
import pytest

from m110.assistant import registry, skills, tools  # noqa: F401

ALL = skills.all_skills()
EXPECTED = {"plan-a-night", "explain-the-numbers", "critique-an-image"}


# ── loader ───────────────────────────────────────────────────────────────────

def test_the_three_v1_skills_are_present():
    assert {s.id for s in ALL} == EXPECTED


@pytest.mark.parametrize("skill", ALL, ids=lambda s: s.id)
def test_frontmatter_is_complete(skill):
    assert skill.name and skill.name != skill.id
    assert skill.description, "the description is what a client shows in a picker"
    assert len(skill.description) > 40, "too terse to help a model choose"
    assert skill.body.strip().startswith("#")
    assert "---" not in skill.body.split("\n")[0]      # frontmatter fully stripped


@pytest.mark.parametrize("skill", ALL, ids=lambda s: s.id)
def test_declared_arguments_appear_as_placeholders(skill):
    for arg in skill.arguments:
        assert "{{" + arg + "}}" in skill.body, (
            f"{skill.id} declares argument {arg!r} but never uses it")


def test_placeholders_are_all_declared():
    import re
    for skill in ALL:
        for found in set(re.findall(r"\{\{(\w+)\}\}", skill.body)):
            assert found in skill.arguments, (
                f"{skill.id} uses {{{{{found}}}}} but doesn't declare it")


def test_render_substitutes_and_never_leaves_raw_braces():
    skill = skills.get("plan-a-night")
    out = skill.render({"date": "2026-07-13", "site": "Backyard"})
    assert "2026-07-13" in out and "Backyard" in out
    assert "{{" not in out

    # A half-supplied prompt must not ship literal braces to the model either.
    partial = skill.render({"date": "2026-07-13"})
    assert "{{" not in partial and "not specified" in partial


def test_uri_round_trip():
    for skill in ALL:
        assert skills.id_from_uri(skill.uri) == skill.id


def test_id_from_uri_rejects_anything_not_ours():
    # Parses the shape only — resolving the id is skills.get's job — but it must
    # never accept a foreign scheme or a traversal-shaped id.
    assert skills.id_from_uri("m110-skill://unknown-but-well-formed") == \
        "unknown-but-well-formed"
    for hostile in ("http://evil/x", "m110-skill://../../etc/passwd",
                    "m110-skill://a/b", "file:///etc/passwd", ""):
        assert skills.id_from_uri(hostile) is None


def test_get_unknown_skill_is_none():
    assert skills.get("no-such-skill") is None


# ── the get_skill tool ───────────────────────────────────────────────────────

def test_get_skill_lists_then_fetches():
    listing = registry.call("get_skill", {})
    assert listing["count"] == len(EXPECTED)
    assert {s["id"] for s in listing["skills"]} == EXPECTED

    got = registry.call("get_skill", {"id": "critique-an-image"})
    assert got["instructions"].strip().startswith("#")
    assert "grounding" in got["instructions"].lower()


def test_get_skill_unknown_id_lists_the_real_ones():
    with pytest.raises(registry.ToolError) as e:
        registry.call("get_skill", {"id": "nope"})
    assert "plan-a-night" in str(e.value)


# ── content guarantees ───────────────────────────────────────────────────────

def test_no_skill_promises_a_write():
    """Every skill must be explicit that this server cannot change anything —
    a model that implies otherwise leaves the user believing a change landed."""
    for skill in ALL:
        low = skill.body.lower()
        assert "read-only" in low or "cannot" in low or "not applied" in low, (
            f"{skill.id} never states the read-only constraint")


def test_skills_reference_only_tools_that_exist():
    """A skill naming a tool that isn't registered sends the model hunting for
    something it can't call."""
    import re
    names = {t.name for t in registry.all_tools()}
    for skill in ALL:
        for cited in set(re.findall(r"`(\w+)`", skill.body)):
            # Only check things that look like tool names we own.
            if cited.startswith(("get_", "list_", "plan_", "rank_", "propose_",
                                 "object_", "saved_")):
                assert cited in names, f"{skill.id} cites unknown tool {cited!r}"


def test_skills_reference_only_engine_functions_that_exist():
    import importlib
    import re
    for skill in ALL:
        for dotted in set(re.findall(r"`(m110\.[\w.]+)`", skill.body)):
            mod_name, _, attr = dotted.rpartition(".")
            mod = importlib.import_module(mod_name)
            assert hasattr(mod, attr), f"{skill.id} cites missing {dotted}"


def test_explain_the_numbers_carries_the_rule_people_get_wrong():
    body = skills.get("explain-the-numbers").body
    assert "urgency" in body and "completion factor" in body
    # Type-aware thresholds, with the real values.
    assert "240" in body and "360" in body


def test_critique_skill_forbids_blaming_the_preview_stretch():
    """The single most likely wrong critique: judging M110's own auto-stretch."""
    body = skills.get("critique-an-image").body
    assert "was_linear_fits" in body
    assert "caveats" in body
    assert "get_object" in body.split("## Procedure")[1][:400], (
        "the critique procedure must call get_object before get_image")


def test_plan_skill_forbids_hand_assembling_a_schedule():
    body = skills.get("plan-a-night").body
    assert "plan_night" in body
    assert "not up" in body.lower()
    assert "Do not" in body


def test_skill_dir_layout_matches_the_claude_skill_convention():
    """Files live at skills/<id>/SKILL.md so the directory can be symlinked
    into ~/.claude/skills/ unchanged."""
    for skill in ALL:
        assert (skills.SKILLS_DIR / skill.id / "SKILL.md").is_file()


def test_skills_ship_as_package_data():
    import tomllib
    from pathlib import Path
    root = Path(skills.__file__).parents[2]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["m110"]
    assert any("assistant/skills" in g for g in globs), (
        "skills would be missing from an installed or frozen build")

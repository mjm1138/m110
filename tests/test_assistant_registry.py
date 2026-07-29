"""Registry hygiene + the guarantees the assistant layer rests on.

Three of these are parametrized over the registry, so a newly added tool is
covered by construction rather than by remembering to extend a test.
"""
import ast
import hashlib
import importlib
import json
import subprocess
import os
import sys
from pathlib import Path

import pytest

from m110 import config
from m110.assistant import registry, tools  # noqa: F401  (import populates registry)

from tests._helpers import add_library
from tests._helpers import seed_root as _seed_root


@pytest.fixture
def seed_root(tmp_path, monkeypatch):
    """A bootstrapped throwaway store holding one object.

    `_helpers.seed_root` is a plain function, so wrap it as a fixture once here —
    these tests are parametrized over the registry and would otherwise repeat it.
    An object is added (cheaply, without a refresh) so `get_object` has a real
    slug to resolve; the point of these tests is the registry contract, not
    capture data.
    """
    root = _seed_root(tmp_path, monkeypatch)
    add_library(root, {"m101": {"id": "M101", "name": "Pinwheel Galaxy",
                                "type": "galaxy", "season": "spring"}})
    return root


ALL = registry.all_tools()
ASSISTANT_DIR = Path(registry.__file__).parent

# Representative arguments per tool. A tool with no entry is called with {}.
ARGS = {
    "list_objects": {"query": "m", "limit": 5},
    "get_object": {"slug": "m101"},
    "object_observability": {"slugs": ["m101"]},
    "plan_night": {"count": 2},
    "get_image": {"slug": "m101"},
}


def _invoke(tool):
    """Call a tool, tolerating a legitimate refusal.

    Against a bare fixture store some tools correctly decline — `plan_night`
    has no cached ranking contexts to plan from, for instance. A refusal is a
    valid outcome and still proves the properties these tests care about (it
    wrote nothing, it touched no astropy). Returns None when refused.
    """
    try:
        return registry.call(tool.name, _args(tool.name))
    except registry.ToolError:
        return None


def _args(name):
    return ARGS.get(name, {})


# ── descriptor hygiene ───────────────────────────────────────────────────────

def test_registry_is_populated():
    assert ALL, "no tools registered — did tools/__init__ stop importing them?"


@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_descriptor_wellformed(tool):
    assert tool.name == tool.name.lower().replace(" ", "_")
    assert tool.name.replace("_", "").isalnum(), f"{tool.name}: snake_case only"
    assert len(tool.name) <= 40
    assert tool.description.strip(), f"{tool.name}: needs a model-facing description"
    assert tool.cost in registry.COSTS
    assert tool.returns in ("json", "json+images")
    assert tool.engine, f"{tool.name}: declare the engine functions it calls"


@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_schema_is_legal_json_schema(tool):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema(tool.params)
    assert tool.params.get("type") == "object"
    assert tool.params.get("additionalProperties") is False
    # Models read these; an undescribed parameter gets guessed at.
    for pname, spec in tool.params.get("properties", {}).items():
        assert spec.get("description"), f"{tool.name}.{pname}: needs a description"


@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_engine_provenance_resolves(tool):
    """`engine` entries must name real functions — the explain-the-numbers skill
    cites them, so a stale string would become a fabricated citation."""
    for dotted in tool.engine:
        mod_name, _, attr = dotted.rpartition(".")
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, attr), f"{tool.name}: {dotted} does not exist"


# ── argument validation ──────────────────────────────────────────────────────

def test_unknown_tool_raises_input_error():
    with pytest.raises(registry.ToolInputError):
        registry.call("no_such_tool", {})


def test_rejects_unexpected_argument():
    with pytest.raises(registry.ToolInputError):
        registry.call("list_objects", {"nope": 1})


def test_rejects_wrong_type_and_out_of_range():
    with pytest.raises(registry.ToolInputError):
        registry.call("list_objects", {"limit": "five"})
    with pytest.raises(registry.ToolInputError):
        registry.call("list_objects", {"limit": 10_000})
    # bool must not satisfy an integer field
    with pytest.raises(registry.ToolInputError):
        registry.call("list_objects", {"limit": True})


# ── results are JSON-safe ────────────────────────────────────────────────────

@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_result_is_json_serializable(tool, seed_root):
    result = _invoke(tool)
    if result is None:
        pytest.skip(f"{tool.name} declined against the bare fixture store")
    # allow_nan=False: json.dumps emits bare NaN/Infinity by default, which is
    # invalid JSON and breaks strict clients.
    json.dumps(result, allow_nan=False)


# ── the read-only proof (three independent layers) ───────────────────────────

def _manifest(root: Path) -> dict:
    """Hash every file under root, including mtime, so an idempotent rewrite is
    still caught."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (
                st.st_mtime_ns, st.st_size,
                hashlib.sha256(p.read_bytes()).hexdigest(),
            )
    return out


@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_layer1_store_is_byte_identical_after_call(tool, seed_root):
    """Nothing under the data root may change — content, size, or mtime."""
    before = _manifest(config.DATA_ROOT)
    _invoke(tool)
    after = _manifest(config.DATA_ROOT)
    assert before == after, (
        f"{tool.name} modified the data store: "
        f"changed={sorted(set(before) ^ set(after)) or 'contents differ'}"
    )


@pytest.mark.parametrize("tool", ALL, ids=lambda t: t.name)
def test_layer2_no_write_syscalls_into_the_store(tool, seed_root, monkeypatch):
    """Intercept the write paths themselves, so a write to a path this test's
    arguments happen not to create is still caught."""
    guarded = [config.DATA_ROOT.resolve(), config.APP_CONFIG_DIR.resolve()]

    def _under_guard(path) -> bool:
        try:
            rp = Path(path).resolve()
        except (OSError, TypeError, ValueError):
            return False
        return any(rp == g or g in rp.parents for g in guarded)

    def _boom(label):
        def f(self, *a, **k):
            if _under_guard(self):
                raise AssertionError(f"{tool.name} attempted {label} on {self}")
            return getattr(_orig[label], "__wrapped__", _orig[label])(self, *a, **k)
        return f

    _orig = {}
    for name in ("write_text", "write_bytes", "mkdir", "touch", "unlink", "rename"):
        _orig[name] = getattr(Path, name)
        monkeypatch.setattr(Path, name, _boom(name))

    real_open = open

    def guarded_open(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+") and _under_guard(file):
            raise AssertionError(f"{tool.name} opened {file} for writing (mode={mode})")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr("builtins.open", guarded_open)

    real_replace, real_remove = os.replace, os.remove
    monkeypatch.setattr(os, "replace", lambda s, d, *a, **k: (
        (_ for _ in ()).throw(AssertionError(f"{tool.name} os.replace -> {d}"))
        if _under_guard(d) else real_replace(s, d, *a, **k)))
    monkeypatch.setattr(os, "remove", lambda p, *a, **k: (
        (_ for _ in ()).throw(AssertionError(f"{tool.name} os.remove -> {p}"))
        if _under_guard(p) else real_remove(p, *a, **k)))

    _invoke(tool)


# Engine functions that write. A tool may never call one of these.
ENGINE_WRITERS = {
    "save_weights", "save_strategy", "save_visible_tonight", "save_setting",
    "save_data_root", "set_data_root", "ensure_data_root", "set_state",
    "write_journal", "set_frontmatter_key", "set_frontmatter_list", "set_curation",
    "set_publish_flag", "set_active_goals", "create_custom_goal", "edit_custom_goal",
    "delete_custom_goal", "add_library_entry", "add_captured_objects",
    "remove_library_entry", "remove_goal_members_from_library",
    "add_goal_members_to_library", "fill_missing_metadata", "fill_all_missing_metadata",
    "enrich_online", "write_contexts", "refresh_prioritized", "run_refresh",
    "export_for_sharing", "apply_prep", "apply_import", "autoprep", "apply_ops",
    "discard_holding", "add_alias", "save_site", "set_active_profile",
    "import_horizon_mask", "write_glow_masks", "create_snapshot", "restore",
    "apply_retention", "sweep_incomplete", "run_publish", "deploy", "set_hints",
    "write_jsonl", "render_images", "rebuild_hero", "migrate_store", "save",
}


def test_layer3_no_engine_writer_is_referenced_statically():
    """AST-walk the package. Catches a write path before it is ever executed —
    the layers above only see what the test's arguments happen to reach."""
    offenders = []
    for py in sorted(ASSISTANT_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                called = fn.attr if isinstance(fn, ast.Attribute) else (
                    fn.id if isinstance(fn, ast.Name) else None)
                if called in ENGINE_WRITERS:
                    offenders.append(
                        f"{py.relative_to(ASSISTANT_DIR.parent)}:{node.lineno} -> {called}()")
    assert not offenders, (
        "assistant tools must not call engine writers:\n  " + "\n  ".join(offenders))


# ── astropy must not be reachable from a non-slow tool ───────────────────────

def test_no_astropy_at_import_time():
    """The handshake budget is about IMPORT cost, not per-tool execution cost.

    `initialize`/`tools/list` must answer well under a second — a client that
    times out never reaches a tool at all, and the failure reads as "the server
    is broken". Importing astropy at module scope would blow that on its own, so
    the planning tools keep it behind function-level imports (as
    `m110.planning` itself does). Checked in a subprocess because astropy is
    almost certainly already imported in this one.
    """
    code = (
        "import sys;"
        "import m110.assistant.tools;"
        "bad=[m for m in sys.modules if m.split('.')[0]=='astropy'];"
        "print('ASTROPY' if bad else 'CLEAN')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=Path(registry.__file__).parents[2])
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "CLEAN", (
        "importing m110.assistant.tools pulled in astropy — the MCP handshake "
        "budget depends on it not doing that"
    )


@pytest.mark.parametrize("tool", [t for t in ALL if t.cost == "instant"],
                         ids=lambda t: t.name)
def test_instant_tools_never_touch_astropy(tool, seed_root, monkeypatch):
    """A tool advertised as instant must not secretly run an astronomy pass.

    Only `instant` tools: `object_observability` and `plan_night` compute real
    astronomy and say so in their cost class.
    """
    for mod in [m for m in sys.modules if m.split(".")[0] == "astropy"]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] == "astropy":
                raise AssertionError(f"{tool.name} imported astropy ({name})")
            return None

    monkeypatch.setattr(sys, "meta_path", [Blocker(), *sys.meta_path])
    _invoke(tool)


def test_assistant_package_is_qt_free():
    """The engine rule, enforced. Importing any assistant module must not pull Qt."""
    for py in sorted(ASSISTANT_DIR.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        assert "PySide6" not in src, f"{py.name} imports Qt; the assistant layer is Qt-free"

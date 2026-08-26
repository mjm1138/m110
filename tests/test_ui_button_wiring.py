"""Guards for names that are only resolved when a user clicks something.

A `lambda` body is not evaluated at import time, so a missing import inside one
sails past every construct-the-page test and only fails in the user's hands. That
is exactly how `widgets.stack_in_stackingwizard(...)` shipped: `detail.py` imports
*names* from `m110.ui.widgets`, never the module, so the callback raised
`NameError` the first time the button was pressed.

Two guards, deliberately different in kind: one walks the source for the whole
class of mistake, the other actually presses the button.
"""
import ast
import builtins
import pathlib

import pytest

UI = pathlib.Path(__file__).resolve().parent.parent / "m110" / "ui"


def _bound_names(tree: ast.AST) -> set:
    """Every name bound anywhere in the module — imports, defs, classes,
    assignments, args, comprehension and for targets, except handlers.

    Deliberately over-generous: scope is ignored, so a name bound in *any*
    function counts everywhere. That trades precision for a zero false-positive
    rate — anything this still flags is genuinely bound nowhere in the file."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {(a.asname or a.name) for a in n.names}
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
            pass
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.Global) or isinstance(n, ast.Nonlocal):
            out |= set(n.names)
    return out


@pytest.mark.parametrize("path", sorted(UI.rglob("*.py")), ids=lambda p: p.name)
def test_no_name_is_read_that_is_bound_nowhere_in_the_file(path):
    """The `widgets.` bug, generalised to every deferred read — not just lambdas.

    Both halves of that mistake were invisible until clicked: the lambda called
    `widgets.…` with no such import, and the helper it reached read `config` which
    `widgets.py` binds nowhere. A function body is as unevaluated as a lambda's,
    so the check covers the whole module.

    It cannot see *scope* — a name bound in any function counts everywhere — so it
    misses "imported in a different function". The click test below is the guard
    for that; these two are complementary on purpose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    known = _bound_names(tree) | set(dir(builtins)) | {"__file__", "__name__"}
    missing = {n.id for n in ast.walk(tree)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
               and n.id not in known}
    assert not missing, (
        f"{path.name} reads {sorted(missing)}, bound nowhere in the file — "
        f"this only fails when the user reaches that code")


# ── and actually press it ────────────────────────────────────────────────────

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QPushButton  # noqa: E402

from m110 import config  # noqa: E402


def test_stack_in_stackingwizard_button_actually_runs(tmp_path, monkeypatch, qapp):
    """Construction is not enough: the callback body only runs on click."""
    root = tmp_path / "M110"
    for name, val in (("DATA_ROOT", root), ("IMAGES_DIR", root / "Images"),
                      ("OBJECTS_DIR", root / "Objects"),
                      ("DERIVED_DIR", tmp_path / "derived"),
                      ("RENDERS_DIR", tmp_path / "renders"),
                      ("HERO_DIR", tmp_path / "renders" / "hero"),
                      ("LIBRARY_TOML", tmp_path / "absent.toml"),
                      ("SETTINGS_FILE", tmp_path / "settings.json")):
        monkeypatch.setattr(config, name, val)
    aw_lights = root / "Images" / "M1" / "astrowizard" / "lights"
    aw_lights.mkdir(parents=True)
    (aw_lights / "Light_M1.fit").write_bytes(b"x" * 64)

    from m110 import launch
    from m110.ui import widgets
    from m110.ui.detail import DetailPane
    seen = {}
    # `launch` is imported inside the helper, so patch the real module, not a
    # module attribute of `widgets` — there isn't one.
    monkeypatch.setattr(widgets, "reveal_in_manager",
                        lambda p: seen.update(revealed=str(p)))
    monkeypatch.setattr(launch, "launch_processing",
                        lambda tool, d: seen.update(launched=(tool, str(d))))

    # The button is gated on having a stack to hand off; force the gate so the
    # test is about the wiring, not about building a plausible stack fixture.
    import m110.ui.detail as detail_mod
    monkeypatch.setattr(detail_mod, "can_hand_off", lambda slug, tool="astrowizard": True)
    monkeypatch.setattr(detail_mod, "targets_for_slug", lambda slug: ["M1"])
    monkeypatch.setattr(widgets, "targets_for_slug", lambda slug: ["M1"])

    d = DetailPane()
    d.show_object("m1", {"id": "M1", "name": "Crab", "type": "nebula"},
                  {"status": "initial", "integration_hms": "1:00",
                   "session_count": 1, "frames": 10})
    qapp.processEvents()
    btns = [b for b in d.findChildren(QPushButton)
            if b.text().startswith("Stack in StackingWizard")]
    assert btns, "the button must render, or this test guards nothing"
    btns[0].click()          # raised NameError three ways before the fix
    qapp.processEvents()
    assert seen.get("launched") == ("stackingwizard", str(aw_lights.parent))
    assert seen.get("revealed") == str(aw_lights.parent)

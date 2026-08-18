"""The synthetic-corpus generator is engine code, and must not rot like it.

`tools/make_test_corpus.py` builds the store `create_test_harness.sh` launches the
app against — it is how the GUI flows in TESTING.md get exercised at all. But it
lives outside the package and outside the suite, so it only ever failed *when a
human went to run a manual test*: `media.scan()` was removed in the media-first-class
work and the generator kept calling it for a whole release cycle, with the break
surfacing as a traceback at the start of a test session.

Running the real generator is the guard, not an import check or an AST scan of the
names it touches: `media.scan` → `media.list_media` also changed the *return type*
(dicts → `MediaItem` dataclasses), which a symbol-existence check would have waved
through. It costs ~1s and ~10MB in a temp dir.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GEN = REPO / "tools" / "make_test_corpus.py"


def _load_generator():
    """Import `tools/make_test_corpus.py` by path — `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location("_make_test_corpus", GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_generator_builds_and_verifies_a_corpus(tmp_path, capsys):
    """Build + self-check the whole corpus, exactly as the harness script does.

    `build()` re-points `config` at its output; the autouse `_reset_to_seal` fixture
    puts it back afterwards, so this can't leak into another test — and the seal
    means even a failure mid-build cannot touch the live store.
    """
    gen = _load_generator()
    out = gen.build(tmp_path / "M110-test")
    assert out.is_dir()
    # `verify` asserts its own invariants and raises on any mismatch.
    gen.verify(out)

    # The two sibling fixtures the Import flows are driven from ship beside it.
    assert (tmp_path / "M110-test-import-source").is_dir()
    assert (tmp_path / "M110-test-device-mount").is_dir()


def test_harness_script_points_at_the_generator():
    """`create_test_harness.sh` rebuilds when the generator is newer than the
    tarball, so the path it resolves has to be the real one — a rename here fails
    only at manual-test time otherwise."""
    script = (REPO / "create_test_harness.sh").read_text()
    assert 'GEN="$REPO/tools/make_test_corpus.py"' in script
    assert GEN.is_file()


@pytest.mark.parametrize("call", [
    # The engine surface the generator drives. Listed so a rename shows up here as
    # a named failure rather than deep inside a build.
    "media.list_media", "media.cleanup_candidates", "media.poster_for",
    "refresh.run_refresh", "scan_sessions.scan",
    "ingest.scan_directory_plan", "ingest.scan_holding", "ingest.group_ops",
    "objects.write_journal", "objects.set_curation", "objects.get_curation",
    "siril.has_unimported_output", "siril.prune_rejected",
    "catalog.load_coords", "catalog.load_library", "catalog.load_bundled_catalog",
    "goals.set_active_goals", "goals.active_goal_ids",
])
def test_engine_api_the_generator_depends_on(call):
    import importlib
    mod, attr = call.split(".")
    assert hasattr(importlib.import_module(f"m110.{mod}"), attr), (
        f"m110.{mod}.{attr} is gone — update tools/make_test_corpus.py with it")

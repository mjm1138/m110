"""Guard: packaged builds must bundle the online-enrichment stack (issue #64).

The `build` extra self-references `online`, so every `pip install -e '.[build]'`
(the CI + build-script install) pulls in astroquery and the packaging specs can
bundle it. Without this the frozen app can't do "Enrich online" / "Look up online"
and there's no way for a packaged user to add it (no pip in a frozen bundle)."""
import tomllib
from pathlib import Path


def test_build_extra_pulls_in_online():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    extras = tomllib.loads(pyproject.read_text(encoding="utf-8"))[
        "project"]["optional-dependencies"]
    assert any("m110[online]" in dep.replace(" ", "") for dep in extras["build"]), (
        "the `build` extra must self-reference m110[online] so packaged builds "
        "bundle astroquery (issue #64)")
    assert any("astroquery" in dep for dep in extras["online"]), (
        "the `online` extra defines astroquery")


def test_specs_copy_astropy_metadata():
    """astroquery calls `minversion('astropy')` at import, which reads astropy's
    dist-info metadata — so every spec must `copy_metadata("astropy")`, or the frozen
    Simbad import raises KeyError('astropy') and Enrich online is dead (#74). We bundle
    astropy's modules (hook-astropy) but not, by default, its metadata."""
    specs = Path(__file__).resolve().parents[1] / "packaging"
    for platform in ("macos", "linux", "windows"):
        text = (specs / platform / "M110.spec").read_text(encoding="utf-8")
        assert 'copy_metadata("astropy")' in text, (
            f"{platform}/M110.spec must copy_metadata('astropy') for astroquery (#74)")


def test_hook_astropy_bundles_unit_parser_tables():
    """astropy's PLY unit-parser tables (generic_parsetab/lextab, under
    astropy/units/format) must be bundled as on-disk .py DATA — collect_submodules only
    puts them in the PYZ, and astropy's parser looks for the *file*, regenerating (and
    failing to write) in a read-only frozen bundle. Missing, the FIRST unit parse — at
    `import astropy.units` — dies, so every coordinate transform fails: planning + the
    prioritizer show "astronomy engine unavailable" (#75), and astroquery can't import
    either (#74)."""
    hook = (Path(__file__).resolve().parents[1]
            / "packaging/common/pyinstaller-hooks/hook-astropy.py")
    text = hook.read_text(encoding="utf-8")
    assert "astropy.units.format" in text and "include_py_files" in text, (
        "hook-astropy must collect_data_files('astropy.units.format', "
        "include_py_files=True) so the PLY unit-parser tables ship as files (#75)")


# ── the bundled stdio MCP server (ROADMAP item 4) ────────────────────────────

SPEC_DIR = Path(__file__).resolve().parents[1] / "packaging"
PLATFORMS = ("macos", "linux", "windows")


def _spec(platform):
    return (SPEC_DIR / platform / "M110.spec").read_text(encoding="utf-8")


def test_build_extra_pulls_in_the_assistant():
    """A frozen user has no pip, so the MCP server's dependency must be bundled —
    the same reasoning as issue #64 for astroquery."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    extras = tomllib.loads(pyproject.read_text(encoding="utf-8"))[
        "project"]["optional-dependencies"]
    assert any("m110[assistant]" in dep.replace(" ", "") for dep in extras["build"])
    assert any("mcp" in dep for dep in extras["assistant"])


def test_mcp_server_is_a_console_script_not_a_gui_script():
    """On Windows a gui-script produces a pythonw launcher with no console and no
    usable stdio, which is fatal for a stdio JSON-RPC server."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    assert data["scripts"]["m110-mcp"] == "m110.assistant.mcp_server:main"
    assert "m110-mcp" not in data.get("gui-scripts", {})


def test_every_spec_builds_the_second_executable():
    for platform in PLATFORMS:
        text = _spec(platform)
        assert 'name="m110-mcp"' in text, f"{platform} builds no MCP server binary"
        assert "MCP_ENTRY" in text and "m110_mcp_launch.py" in text
        # Both entry scripts must go through ONE Analysis, or the second binary
        # duplicates the whole ~200 MB payload.
        assert "[str(ENTRY), str(MCP_ENTRY)]" in text
        # And each EXE must take only its own script, or both binaries run
        # whichever entry point came first.
        assert '_scripts_for("m110_launch")' in text
        assert '_scripts_for("m110_mcp_launch")' in text
        assert "mcp_exe," in text, f"{platform} never collects the MCP binary"


def test_mcp_binary_is_built_with_a_console():
    """console=False links Windows binaries against the GUI subsystem, where
    sys.stdout is None — no argv flag can rescue that, which is exactly why this
    is a separate executable."""
    for platform in PLATFORMS:
        # Close on a newline-anchored paren: the call's own args contain ")".
        mcp_block = _spec(platform).split("mcp_exe = EXE(")[1].split("\n)")[0]
        assert "console=True" in mcp_block, f"{platform} MCP binary has no console"
        assert "argv_emulation=False" in mcp_block
        # The GUI binary must stay windowed — this test would otherwise pass on a
        # spec that accidentally gave both a console.
        gui_block = _spec(platform).split("exe = EXE(")[1].split("\n)")[0]
        assert "console=False" in gui_block, f"{platform} GUI binary gained a console"


def test_appimage_apprun_dispatches_to_the_server():
    """An AppImage has no persistent internal path, so a client config points at
    the .AppImage itself with --mcp and AppRun routes it."""
    script = (SPEC_DIR / "linux" / "build_appimage.sh").read_text(encoding="utf-8")
    assert '"$1" = "--mcp"' in script
    assert "usr/bin/m110-mcp" in script


def test_packaged_skills_are_declared():
    """Skills are package data; without the glob they vanish from frozen builds
    and the assistant silently has no procedures."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    globs = tomllib.loads(pyproject.read_text(encoding="utf-8"))[
        "tool"]["setuptools"]["package-data"]["m110"]
    assert any("assistant/skills" in g for g in globs)


def test_assistant_subpackages_are_installed():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    packages = tomllib.loads(pyproject.read_text(encoding="utf-8"))[
        "tool"]["setuptools"]["packages"]
    assert "m110.assistant" in packages and "m110.assistant.tools" in packages

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


def test_specs_collect_the_sky_map_data():
    """uranometria reads its bundled catalogs (`data/constellations.json` and
    friends) AT IMPORT, and PyInstaller collects package *data* for nobody by
    default. 0.3.0b1 shipped the modules without the data, so `import uranometria`
    raised FileNotFoundError — during the Library's map render, i.e. while the main
    window was being built, which killed the app at launch."""
    specs = Path(__file__).resolve().parents[1] / "packaging"
    for platform in ("macos", "linux", "windows"):
        text = (specs / platform / "M110.spec").read_text(encoding="utf-8")
        assert 'collect_data_files("uranometria")' in text, (
            f"{platform}/M110.spec must collect uranometria's package data")
        # Data only: `uranometria.annotate` imports matplotlib, which every spec
        # excludes — collecting its submodules would drag that back in.
        assert 'collect_submodules("uranometria")' not in text


def test_release_workflow_installs_the_sky_map_dependency():
    """uranometria isn't on PyPI, so it can't ride in the `build` extra — and a
    frozen app has no pip, so if the build env lacks it packaged users get no Map
    view at all. Both packaged jobs must install it explicitly."""
    workflow = (Path(__file__).resolve().parents[1]
                / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert workflow.count("uranometria @ git+") >= 2, (
        "both the Linux and Windows release jobs must install uranometria")


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


# The console helper binaries built alongside the GUI, as
# (spec variable, output name, entry-shim stem, AppRun flag). Each is a further
# EXE from the same Analysis/PYZ. Add a row when a new one is added to the specs —
# the checks below, the notarization signing list and the AppRun dispatch all read
# from it, so one row is the whole registration.
HELPERS = [
    ("mcp_exe", "m110-mcp", "m110_mcp_launch", "--mcp"),
    ("stack_exe", "m110-stack", "m110_stack_launch", "--stack"),
]


def test_every_spec_builds_the_helper_executables():
    for platform in PLATFORMS:
        text = _spec(platform)
        # Every entry script goes through ONE Analysis, or each extra binary
        # duplicates the whole ~200 MB payload.
        assert "[str(ENTRY), str(MCP_ENTRY), str(STACK_ENTRY)]" in text
        assert '_scripts_for("m110_launch")' in text
        for var, name, stem, _flag in HELPERS:
            assert f'name="{name}"' in text, f"{platform} builds no {name} binary"
            assert f"{stem}.py" in text
            # Each EXE must take only its own script, or every binary runs
            # whichever entry point came first.
            assert f'_scripts_for("{stem}")' in text
            assert f"{var}," in text, f"{platform} never collects {name}"


def test_helper_binaries_are_built_with_a_console():
    """console=False links Windows binaries against the GUI subsystem, where
    sys.stdout is None — no argv flag can rescue that, which is exactly why these
    are separate executables. The MCP server needs stdout for JSON-RPC; the
    stacker needs it for a heartbeat that is the only sign a multi-hour run is
    alive rather than wedged."""
    for platform in PLATFORMS:
        for var, name, _stem, _flag in HELPERS:
            # Close on a newline-anchored paren: the call's own args contain ")".
            block = _spec(platform).split(f"{var} = EXE(")[1].split("\n)")[0]
            assert "console=True" in block, f"{platform} {name} has no console"
            assert "argv_emulation=False" in block
        # The GUI binary must stay windowed — this test would otherwise pass on a
        # spec that accidentally gave everything a console.
        gui_block = _spec(platform).split("exe = EXE(")[1].split("\n)")[0]
        assert "console=False" in gui_block, f"{platform} GUI binary gained a console"


def test_macos_signing_covers_every_helper_binary():
    """A further executable beside the main binary is neither a dylib nor a
    framework, so the find-based sweeps miss it — and an unsigned Mach-O in the
    bundle fails notarization outright, which only shows up at release time."""
    script = (SPEC_DIR / "macos" / "sign_notarize.sh").read_text(encoding="utf-8")
    for _var, name, _stem, _flag in HELPERS:
        assert name in script, f"sign_notarize.sh never signs {name}"


def test_macos_bundle_is_not_background_only():
    """The .app must declare LSBackgroundOnly=False *explicitly*. BUNDLE inherits
    `console` from the COLLECT, which inherits it from its EXE args last-one-wins —
    and ours is the console=True MCP server — so PyInstaller would otherwise stamp
    LSBackgroundOnly=True and the app launches with no menu bar, no Dock icon, and
    no entry in Force Quit (0.3.0-beta.2)."""
    assert '"LSBackgroundOnly": False' in _spec("macos"), (
        "packaging/macos/M110.spec must set LSBackgroundOnly False — the console=True "
        "MCP binary makes PyInstaller default it to True")


def test_appimage_apprun_dispatches_to_every_helper():
    """An AppImage has no persistent internal path, so nothing outside can point
    at usr/bin/<helper> the way it can on macOS and Windows. Callers point at the
    .AppImage itself with a flag, and AppRun routes it."""
    script = (SPEC_DIR / "linux" / "build_appimage.sh").read_text(encoding="utf-8")
    for _var, name, _stem, flag in HELPERS:
        assert flag in script, f"AppRun never dispatches {flag}"
        assert f"usr/bin/{name}" in script


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

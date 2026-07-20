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

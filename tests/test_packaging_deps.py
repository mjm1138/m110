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

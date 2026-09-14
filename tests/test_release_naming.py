"""Release artifacts are named by the *full* version, on every platform.

Every beta of 0.3.0 shipped as `M110-0.3.0.dmg` (and the same for the AppImage
and the Windows installer), because each builder named its output by the numeric
version — the only form Apple's `CFBundleShortVersionString` and Inno Setup's
`AppVersion` accept. A Downloads folder holding several became `M110-0.3.0-4.dmg`
and nobody could tell which build was which. `packaging/common/artifact_version.py`
is now the one place the artifact spelling lives; these tests pin it, pin the
release tool's derived forms, and source-scan each builder so a later edit can't
quietly regress one platform.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging" / "common"))
sys.path.insert(0, str(ROOT / "tools"))
from artifact_version import artifact_version  # noqa: E402


@pytest.mark.parametrize("pep440, artifact", [
    ("0.3.0b6", "0.3.0-beta.6"),
    ("0.3.0", "0.3.0"),               # a final release keeps the plain numeric form
    ("1.0.0rc1", "1.0.0-rc.1"),
    ("0.4.0a2", "0.4.0-alpha.2"),
    ("0.4.0.dev3", "0.4.0-dev.3"),
])
def test_artifact_version_is_the_tag_without_its_v(pep440, artifact):
    assert artifact_version(pep440) == artifact


def test_the_helper_prints_it_on_the_command_line():
    """The shell and PowerShell builders shell out to it — with an explicit
    version (make_dmg.sh passes the .app's CFBundleVersion) and without one
    (the Linux/Windows builders read the installed metadata)."""
    helper = ROOT / "packaging" / "common" / "artifact_version.py"
    out = subprocess.run([sys.executable, str(helper), "0.3.0b6"],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "0.3.0-beta.6"
    out = subprocess.run([sys.executable, str(helper)],
                         capture_output=True, text=True, check=True).stdout
    from importlib.metadata import version
    assert out.strip() == artifact_version(version("m110"))


def test_release_tool_derives_every_spelling_from_one_input():
    import release
    for arg in ("0.3.0b6", "v0.3.0-beta.6"):        # both spellings are safe to type
        V = release.versions(arg)
        assert V["pep440"] == "0.3.0b6"
        assert V["numeric"] == "0.3.0"              # the plist / AppVersion form
        assert V["artifact"] == "0.3.0-beta.6"      # the download's name
        assert V["tag"] == "v" + V["artifact"]      # the tag IS the artifact, plus v
        assert V["prerelease"]
    V = release.versions("0.3.0")
    assert V["artifact"] == "0.3.0" and V["tag"] == "v0.3.0" and not V["prerelease"]


def test_every_builder_names_its_output_by_the_artifact_version():
    """Source scan: a builder that goes back to the numeric version regresses
    exactly one platform, silently, until the next beta lands as `-4`."""
    helper = "artifact_version.py"
    dmg = (ROOT / "packaging/macos/make_dmg.sh").read_text()
    assert helper in dmg and 'DMG="$ROOT/dist/M110-${ARTIFACT}.dmg"' in dmg
    assert "CFBundleVersion" in dmg              # named by what's *inside* the .app
    appimage = (ROOT / "packaging/linux/build_appimage.sh").read_text()
    assert helper in appimage
    assert 'OUT="$ROOT/dist/M110-${ARTIFACT}-${ARCH}.AppImage"' in appimage
    ps1 = (ROOT / "packaging/windows/build_windows.ps1").read_text()
    assert helper in ps1 and '"/DMyArtifactVersion=$Artifact"' in ps1
    iss = (ROOT / "packaging/windows/M110.iss").read_text()
    assert "OutputBaseFilename=M110-{#MyArtifactVersion}-setup" in iss
    assert "AppVersion={#MyAppVersion}" in iss    # metadata stays numeric
    tool = (ROOT / "tools/release.py").read_text()
    assert "M110-{V['numeric']}" not in tool and "M110-{V['artifact']}.dmg" in tool
    # release.yml collects by glob, so it needs no change — but it must stay a glob.
    yml = (ROOT / ".github/workflows/release.yml").read_text()
    assert "dist/M110-*.AppImage" in yml and "dist/M110-*setup.exe" in yml

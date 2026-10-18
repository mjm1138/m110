"""Windows portable-package contract; the real PyInstaller build stays opt-in."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows packaging only")


def test_package_only_creates_isolated_portable_zip(tmp_path: Path) -> None:
    """A missing app copy or isolation launcher would make the ZIP unsafe to test."""
    repo = Path(__file__).resolve().parents[1]
    script = repo / "packaging" / "windows" / "build_portable.ps1"
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    assert pwsh is not None

    app = tmp_path / "M110"
    (app / "_internal").mkdir(parents=True)
    (app / "M110.exe").write_bytes(b"fake executable")
    (app / "_internal" / "marker.txt").write_text("bundled", encoding="utf-8")
    output = tmp_path / "artifacts"

    completed = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-PackageOnly", "-AppDirectory", str(app), "-OutputDirectory", str(output),
         "-ArtifactSuffix", "test123", "-DevRoot", str(tmp_path / "dev")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    archive = output / "M110-portable-test123.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        assert {"M110/M110.exe", "M110/_internal/marker.txt", "run-dev.cmd"} <= names
        launcher = package.read("run-dev.cmd").decode("ascii")
    assert "USERPROFILE" in launcher
    assert "M110_DATA_ROOT" in launcher
    assert 'start "" "%~dp0M110\\M110.exe"' in launcher

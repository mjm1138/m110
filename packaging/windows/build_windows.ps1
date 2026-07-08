<#
Build the M110 Windows installer: PyInstaller onedir -> icon -> Inno Setup.

    pip install -e ".[build]"
    powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1

Produces dist\M110-<version>-setup.exe. Unsigned (per the beta plan) — users will
see a SmartScreen prompt; see README.md. Must run on Windows.
#>
#Requires -Version 5
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $Here "..\..")).Path
Set-Location $Root

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "pyinstaller not found. Run: pip install -e `".[build]`""
}

Write-Host "==> generating M110.ico"
python (Join-Path $Here "make_ico.py")

# Marketing version (numeric release) from the installed package metadata.
$Version = (python -c "from importlib.metadata import version; from packaging.version import Version; print('.'.join(map(str, Version(version('m110')).release)))").Trim()
if (-not $Version) { $Version = "0.0.0" }

Write-Host "==> PyInstaller onedir build"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "build\M110"), (Join-Path $Root "dist\M110")
pyinstaller (Join-Path $Here "M110.spec") --noconfirm --clean

# Locate the Inno Setup compiler (PATH, else the default install location).
$Iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
    $default = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $default) { $Iscc = $default }
    else { throw "Inno Setup (ISCC.exe) not found. Install Inno Setup 6.3+ from https://jrsoftware.org/isdl.php" }
}

Write-Host "==> Inno Setup installer"
& $Iscc "/DMyAppVersion=$Version" (Join-Path $Here "M110.iss")

Write-Host "==> built: dist\M110-$Version-setup.exe"
Write-Host "    (unsigned - a first run trips SmartScreen: More info -> Run anyway. See README.md.)"

#Requires -Version 5.1
<#!
.SYNOPSIS
Builds a self-contained M110 ZIP that launches against an isolated data store.

.DESCRIPTION
Without -PackageOnly this invokes the same PyInstaller spec used by the Windows
installer, then packages dist\M110.  -PackageOnly packages an already-built app;
it exists for fast packaging checks and CI-like validation.
#>
[CmdletBinding()]
param(
    [switch] $PackageOnly,
    [string] $AppDirectory,
    [string] $OutputDirectory,
    [string] $ArtifactSuffix,
    [string] $DevRoot = "D:\m110-dev"
)

$ErrorActionPreference = "Stop"
$oldUserProfile = $env:USERPROFILE
$oldDataRoot = $env:M110_DATA_ROOT
$env:USERPROFILE = Join-Path $DevRoot "home"
$env:M110_DATA_ROOT = Join-Path $DevRoot "data"
New-Item -ItemType Directory -Force -Path $env:USERPROFILE, $env:M110_DATA_ROOT | Out-Null
$buildRoot = $null

try {
    $repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $python = Join-Path $repo ".venv\Scripts\python.exe"

    if (-not $AppDirectory) {
        $AppDirectory = Join-Path $repo "dist\M110"
    }
    if (-not $OutputDirectory) {
        $OutputDirectory = Join-Path $repo "dist"
    }
    if (-not $ArtifactSuffix) {
        try {
            $ArtifactSuffix = (& git -C $repo rev-parse --short HEAD).Trim()
        } catch {
            $ArtifactSuffix = Get-Date -Format "yyyyMMdd-HHmmss"
        }
    }

    if (-not $PackageOnly) {
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw "Project Python was not found at $python. Create .venv and install .[build] first."
        }
        & $python (Join-Path $repo "packaging\windows\make_ico.py")
        if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }
        $buildRoot = Join-Path $repo (".portable-build-" + [guid]::NewGuid().ToString("N"))
        $workPath = Join-Path $buildRoot "work"
        $distPath = Join-Path $buildRoot "dist"
        & $python -m PyInstaller (Join-Path $repo "packaging\windows\M110.spec") `
            --noconfirm --clean --workpath $workPath --distpath $distPath
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
        $AppDirectory = Join-Path $distPath "M110"
    }

    if (-not (Test-Path -LiteralPath $AppDirectory -PathType Container)) {
        throw "Portable app directory was not found: $AppDirectory"
    }
    $resolvedApp = (Resolve-Path -LiteralPath $AppDirectory).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedApp "M110.exe") -PathType Leaf)) {
        throw "Portable app directory must contain M110.exe: $resolvedApp"
    }

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $output = (Resolve-Path -LiteralPath $OutputDirectory).Path
    $archive = Join-Path $output "M110-portable-$ArtifactSuffix.zip"
    $stage = Join-Path $output (".portable-stage-" + [guid]::NewGuid().ToString("N"))

    try {
        New-Item -ItemType Directory -Path $stage | Out-Null
        Copy-Item -LiteralPath $resolvedApp -Destination (Join-Path $stage "M110") -Recurse
        $launcher = @"
@echo off
rem Runs this portable M110 build isolated from any installed M110.
rem Override the location with: set M110_DEV_ROOT=E:\somewhere
if "%M110_DEV_ROOT%"=="" set "M110_DEV_ROOT=$DevRoot"
set "USERPROFILE=%M110_DEV_ROOT%\home"
set "M110_DATA_ROOT=%M110_DEV_ROOT%\data"
if not exist "%USERPROFILE%" mkdir "%USERPROFILE%"
if not exist "%M110_DATA_ROOT%" mkdir "%M110_DATA_ROOT%"
start "" "%~dp0M110\M110.exe"
"@
        [System.IO.File]::WriteAllText((Join-Path $stage "run-dev.cmd"), $launcher,
                                       [System.Text.Encoding]::ASCII)
        Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -Force
    } finally {
        if (Test-Path -LiteralPath $stage) {
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
    }

    Write-Output "Portable package: $archive"
} finally {
    if ($buildRoot -and (Test-Path -LiteralPath $buildRoot)) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
    $env:USERPROFILE = $oldUserProfile
    $env:M110_DATA_ROOT = $oldDataRoot
}

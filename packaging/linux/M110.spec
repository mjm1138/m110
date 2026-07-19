# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the M110 Linux build (onedir, feeds the AppImage).

Build on a Linux host from the repo root:

    pyinstaller packaging/linux/M110.spec --noconfirm

Produces `dist/M110/` (a self-contained directory: launcher + bundled Python/Qt).
`build_appimage.sh` wraps that into `M110-<version>-x86_64.AppImage`.

NOTE: PyInstaller is not a cross-compiler — a Linux build must run on Linux
(ideally the oldest glibc you want to support, e.g. Ubuntu 22.04 LTS, so the
AppImage runs on newer distros too).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# SPECPATH = the directory holding this spec (packaging/linux).
ROOT = Path(SPECPATH).resolve().parents[1]                       # repo root
ENTRY = ROOT / "packaging" / "common" / "m110_launch.py"         # shared entry shim
HOOKS = ROOT / "packaging" / "common" / "pyinstaller-hooks"      # shared hook overrides

datas = collect_data_files("m110")          # engine package data (seed, guidance, fonts, brand)
datas += collect_data_files("tzdata")       # IANA tz db — bundle so zoneinfo is self-contained (#56)
hiddenimports = ["tifffile", "PIL"]         # astropy handled by the shared hook override
hiddenimports += collect_submodules("tzdata")   # zoneinfo loads these region subpackages

# Online enrichment (Simbad via astroquery) — bundled so packaged users get "Enrich
# online" / "Look up online" (issue #64). The source `online` extra stays opt-in; the
# `build` extra pulls it in for builds. No PyInstaller-contrib hooks exist for these and
# they load submodules/data dynamically (keyring's backends via entry points, astroquery's
# per-service modules), so collect them explicitly — the hook-astropy lesson: name the
# package, collect its submodules; don't hand-pick. certifi/urllib3/charset_normalizer
# carry their own contrib hooks; requests/bs4/html5lib are static-import only.
for _pkg in ("astroquery", "pyvo", "keyring"):
    hiddenimports += collect_submodules(_pkg)
    datas += collect_data_files(_pkg, excludes=["**/tests/**", "**/test/**"])
datas += copy_metadata("astroquery")            # version / entry points
datas += copy_metadata("keyring")               # keyring finds its backends via entry points

block_cipher = None

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HOOKS)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "matplotlib", "pytest", "pytestqt"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="M110",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app, no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,   # macOS-only feature
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="M110",
)

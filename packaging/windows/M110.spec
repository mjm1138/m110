# -*- mode: python ; coding: utf-8 -*-
r"""PyInstaller spec for the M110 Windows build (onedir, feeds the Inno Setup installer).

Build on a Windows host from the repo root:

    pyinstaller packaging\windows\M110.spec --noconfirm

Produces `dist\M110\` (launcher M110.exe + bundled Python/Qt). `M110.iss`
(Inno Setup) wraps that into `M110-<version>-setup.exe`.

NOTE: PyInstaller is not a cross-compiler — a Windows build must run on Windows.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH = the directory holding this spec (packaging\windows).
ROOT = Path(SPECPATH).resolve().parents[1]                       # repo root
ENTRY = ROOT / "packaging" / "common" / "m110_launch.py"         # shared entry shim
HOOKS = ROOT / "packaging" / "common" / "pyinstaller-hooks"      # shared hook overrides
ICON = ROOT / "packaging" / "windows" / "M110.ico"               # from make_ico.py

datas = collect_data_files("m110")          # engine package data (seed, guidance, fonts, brand)
datas += collect_data_files("tzdata")       # IANA tz db — Windows has no system copy (#56)
hiddenimports = ["tifffile", "PIL"]         # astropy handled by the shared hook override
hiddenimports += collect_submodules("tzdata")   # zoneinfo loads these region subpackages

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
    console=False,                                  # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,                           # macOS-only feature
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,      # embeds the .exe icon
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

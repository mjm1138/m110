# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the M110 macOS .app bundle.

Build from the repo root:

    pyinstaller packaging/macos/M110.spec --noconfirm

Produces `dist/M110.app`. Signing / notarization / DMG are separate steps (see
the sibling scripts + README) so the unsigned build stays fast to iterate on.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# --- project layout -------------------------------------------------------
# SPECPATH is provided by PyInstaller = the directory holding this spec.
ROOT = Path(SPECPATH).resolve().parents[1]          # repo root (…/m110)
ENTRY = ROOT / "packaging" / "common" / "m110_launch.py"     # shared entry shim
ICNS = ROOT / "packaging" / "macos" / "M110.icns"    # produced by make_icns.sh
HOOKS = ROOT / "packaging" / "common" / "pyinstaller-hooks"  # shared hook overrides

# --- version (for the Info.plist) -----------------------------------------
# CFBundleShortVersionString must be a plain numeric x.y.z — PEP 440 prerelease
# suffixes (0.1.0b1) are illegal there. Derive the marketing version from the
# release tuple, and stash the full PEP 440 string in CFBundleVersion so the real
# build is still identifiable.
def _versions():
    try:
        from importlib.metadata import version
        raw = version("m110")
    except Exception:
        raw = "0.0.0"
    try:
        from packaging.version import Version
        short = ".".join(str(n) for n in Version(raw).release) or "0.0.0"
    except Exception:
        short = raw.split("b")[0].split("a")[0].split("rc")[0]
    return short, raw

SHORT_VERSION, FULL_VERSION = _versions()

# --- data files + hidden imports ------------------------------------------
# Bundle the engine's package data (seed catalogs, guidance, fonts, brand,
# publish templates). collect_data_files reads pyproject's package-data globs.
datas = collect_data_files("m110")
datas += collect_data_files("tzdata")       # IANA tz db — self-contained zoneinfo (#56)

# astropy is handled by the local hook override in pyinstaller-hooks/ (the contrib
# hook's blanket collect_submodules chokes on the matplotlib-requiring wcsaxes
# module). Here we only name the non-astropy dynamic bits.
hiddenimports = ["tifffile", "PIL"]
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
    hookspath=[str(HOOKS)],       # local hook-astropy override (see that file)
    hooksconfig={},
    runtime_hooks=[],
    # Trim heavy, unused optional deps to keep the bundle smaller. Add back here
    # if a build/runtime ImportError points at one.
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "matplotlib", "pytest", "pytestqt"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    console=False,          # windowed GUI app (no terminal)
    disable_windowed_traceback=False,
    argv_emulation=True,    # let macOS "open with"/file-drop args reach the app
    target_arch=None,       # None = build for the host arch; see README for universal2
    codesign_identity=None, # signing handled by sign_notarize.sh (inside-out)
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

app = BUNDLE(
    coll,
    name="M110.app",
    icon=str(ICNS) if ICNS.exists() else None,
    bundle_identifier="space.m110.M110",
    info_plist={
        "CFBundleName": "M110",
        "CFBundleDisplayName": "M110",
        "CFBundleShortVersionString": SHORT_VERSION,
        "CFBundleVersion": FULL_VERSION,
        "NSHumanReadableCopyright": "Copyright © 2026 Michael Merideth. Apache-2.0.",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        # Follow the OS light/dark appearance (the app is theme-aware).
        "NSRequiresAquaSystemAppearance": False,
        "LSApplicationCategoryType": "public.app-category.photography",
    },
)

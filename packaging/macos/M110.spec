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
MCP_ENTRY = ROOT / "packaging" / "common" / "m110_mcp_launch.py"  # stdio MCP server shim
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
# Bundle the engine's package data (seed catalogs, fonts, brand,
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
# Four astroquery services M110 never touches misbehave when the walk imports them:
# `vamdc`, `exoplanet_orbit_database` and `cds` each raise an AstropyDeprecationWarning
# (astropy's class, and it subclasses Warning rather than DeprecationWarning — so the
# default filters *don't* hide it and the build prints astropy-branded deprecations that
# have nothing to do with astropy), and `dace` was removed upstream and raises ImportError
# outright, which PyInstaller catches and reports as a failed collection. M110 uses
# astroquery.simbad only. Filtering them keeps the noise (and the dead weight) out —
# the same move as the astropy.visualization filter in pyinstaller-hooks/hook-astropy.py,
# and as there, a filtered subtree is never recursed into, so it's never imported.
_SKIP = ("astroquery.vamdc", "astroquery.exoplanet_orbit_database",
         "astroquery.cds", "astroquery.dace")

for _pkg in ("astroquery", "pyvo", "keyring"):
    hiddenimports += collect_submodules(_pkg, filter=lambda n: not n.startswith(_SKIP))
    datas += collect_data_files(_pkg, excludes=["**/tests/**", "**/test/**"])
datas += copy_metadata("astroquery")            # version / entry points
datas += copy_metadata("keyring")               # keyring finds its backends via entry points
datas += copy_metadata("astropy")               # astroquery's minversion('astropy') reads astropy's
                                                # dist-info AT IMPORT; without it Simbad import raises
                                                # KeyError('astropy') in the frozen app (#74). We bundle
                                                # astropy's modules (hook-astropy) but not its metadata.

# Sky map (ROADMAP item 12) — uranometria's package DATA. PyInstaller finds the
# module itself (m110.skymap imports it lazily) but not `data/*.json|csv|tsv` or the
# base64 font assets, which `uranometria.catalog` reads AT IMPORT — so a bundle
# without them dies with FileNotFoundError on constellations.json the first time the
# Library renders the Map view, i.e. at launch (0.3.0b1). Data only, no
# collect_submodules: `uranometria.annotate` imports matplotlib, which we exclude.
# Not a declared dependency (it isn't on PyPI — see pyproject), so a build env
# without it is legal: warn and skip, and the app degrades to "map unavailable".
try:
    datas += collect_data_files("uranometria")
except Exception as _exc:                       # pragma: no cover - build-time
    print(f"WARNING: uranometria not collected ({_exc}) — this build has no sky map")

block_cipher = None

a = Analysis(
    [str(ENTRY), str(MCP_ENTRY)],   # both entry points share ONE Analysis (see below)
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

# One Analysis, two executables. `a.scripts` holds the runtime hooks plus BOTH
# entry scripts, so each EXE takes the shared prefix and only its own script —
# otherwise each binary would run whichever entry point happened to come first.
def _scripts_for(stem):
    other = {"m110_launch", "m110_mcp_launch"} - {stem}
    return [e for e in a.scripts if e[0] not in other]

exe = EXE(
    pyz,
    _scripts_for("m110_launch"),
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

# The stdio MCP server. console=True (it speaks JSON-RPC on stdout) and
# argv_emulation=False — the GUI's Carbon/AppleEvent arg pump assumes a
# LaunchServices context and is exactly wrong for a headless child process.
# sign_notarize.sh must sign this inside-out, before the outer bundle.
mcp_exe = EXE(
    pyz,
    _scripts_for("m110_mcp_launch"),
    [],
    exclude_binaries=True,
    name="m110-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    mcp_exe,
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
        # MUST be explicit, and must stay False. BUNDLE inherits `console` from the
        # COLLECT, which inherits it from its EXE args — LAST ONE WINS, and ours is
        # the console=True MCP server. PyInstaller then stamps LSBackgroundOnly=True
        # ("console=True implies…", building/osx.py), which makes the whole app a
        # background app: no menu bar, no Dock icon, absent from Force Quit. The
        # user info_plist is merged over the defaults, so this key is the fix.
        # Latent since the MCP binary landed; invisible in 0.3.0-beta.1 only because
        # that build crashed before a window ever appeared.
        "LSBackgroundOnly": False,
        "NSHighResolutionCapable": True,
        # Follow the OS light/dark appearance (the app is theme-aware).
        "NSRequiresAquaSystemAppearance": False,
        "LSApplicationCategoryType": "public.app-category.photography",
    },
)

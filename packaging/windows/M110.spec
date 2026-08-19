# -*- mode: python ; coding: utf-8 -*-
r"""PyInstaller spec for the M110 Windows build (onedir, feeds the Inno Setup installer).

Build on a Windows host from the repo root:

    pyinstaller packaging\windows\M110.spec --noconfirm

Produces `dist\M110\` (launcher M110.exe + bundled Python/Qt). `M110.iss`
(Inno Setup) wraps that into `M110-<version>-setup.exe`.

NOTE: PyInstaller is not a cross-compiler — a Windows build must run on Windows.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# SPECPATH = the directory holding this spec (packaging\windows).
ROOT = Path(SPECPATH).resolve().parents[1]                       # repo root
ENTRY = ROOT / "packaging" / "common" / "m110_launch.py"         # shared entry shim
MCP_ENTRY = ROOT / "packaging" / "common" / "m110_mcp_launch.py"  # stdio MCP server shim
STACK_ENTRY = ROOT / "packaging" / "common" / "m110_stack_launch.py"  # m110-stack CLI shim
HOOKS = ROOT / "packaging" / "common" / "pyinstaller-hooks"      # shared hook overrides
ICON = ROOT / "packaging" / "windows" / "M110.ico"               # from make_ico.py

datas = collect_data_files("m110")          # engine package data (seed, fonts, brand)
datas += collect_data_files("tzdata")       # IANA tz db — Windows has no system copy (#56)
hiddenimports = ["tifffile", "PIL"]         # astropy handled by the shared hook override
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
    [str(ENTRY), str(MCP_ENTRY), str(STACK_ENTRY)],  # every entry point shares ONE Analysis
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

# One Analysis, two executables. `a.scripts` holds the runtime hooks plus BOTH
# entry scripts, so each EXE takes the shared prefix and only its own script —
# otherwise each binary would run whichever entry point happened to come first.
def _scripts_for(stem):
    other = {"m110_launch", "m110_mcp_launch", "m110_stack_launch"} - {stem}
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
    console=False,                                  # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,                           # macOS-only feature
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,      # embeds the .exe icon
)

# The stdio MCP server. console=True is MANDATORY here, not cosmetic:
# console=False links against the Windows GUI subsystem, where a process has
# no console and no inherited standard handles at all — sys.stdout is None
# under a frozen Python. A stdio JSON-RPC server cannot exist in that binary,
# and no argv flag can fix it: the subsystem is baked into the PE header at
# link time. Hence a second executable rather than a mode switch.
# No icon= — this is a headless helper, never shown in a shell or on a desktop.
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

# The `m110-stack` CLI: headless Siril stacking. console=True because a
# multi-hour job's entire progress story is stdout — on Windows a windowed build
# links against the GUI subsystem, where the standard handles do not exist, so
# the heartbeat would vanish and a long stack would look like a hang.
stack_exe = EXE(
    pyz,
    _scripts_for("m110_stack_launch"),
    [],
    exclude_binaries=True,
    name="m110-stack",
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
    stack_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="M110",
)

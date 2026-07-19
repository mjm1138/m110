"""Local override of PyInstaller-contrib's hook-astropy.

Two competing constraints have to be satisfied at once:

1. **astropy imports several submodules dynamically**, via
   ``importlib.import_module()`` rather than a literal ``import`` statement, so
   PyInstaller's static analysis never sees them. The load-bearing one is
   ``astropy.constants.config``, which does
   ``importlib.import_module("astropy.constants.codata2018")`` (and iau2015, …)
   at import time — so *every* ``import astropy.units`` / ``astropy.coordinates``
   transitively needs ``astropy.constants.codata2018`` present. Naming a handful
   of top packages in ``hiddenimports`` (the previous approach here) left those
   data-versioned constant modules out of the bundle, and the frozen app raised
   ``ModuleNotFoundError: No module named 'astropy.constants.codata2018'`` the
   moment any session-planning code touched astropy — which the engine swallows,
   silently degrading the whole Planning feature (no ranking, "no astronomical
   darkness"). So we must collect astropy's submodules, like the upstream hook.

2. The upstream hook's blanket ``collect_submodules("astropy")`` walks *every*
   astropy submodule at analysis time, and ``astropy.visualization.wcsaxes``
   calls ``pytest.importorskip("matplotlib")`` at import. With matplotlib absent
   (we don't ship it) that raises pytest's ``Skipped`` — a ``BaseException`` the
   collector doesn't catch — aborting the whole build.

The fix is to collect all astropy submodules but **filter out the
matplotlib-requiring ``astropy.visualization`` subtree** (which M110 never uses).
The filter also stops the walker from recursing into — and thus importing —
that subtree, so the build no longer chokes on the ``Skipped`` from wcsaxes.

A user hookspath entry shadows the contrib hook of the same name, so this file
replaces it for all three platform specs (macos/linux/windows share this dir).
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# astropy.visualization pulls in matplotlib at import (pytest.importorskip) and
# M110 uses none of it — exclude the whole subtree so collect_submodules neither
# imports it (build abort) nor bundles it (dead weight).
def _keep(name: str) -> bool:
    return not name.startswith("astropy.visualization")


datas = collect_data_files("astropy")
hiddenimports = collect_submodules("astropy", filter=_keep)

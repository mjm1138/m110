"""Local override of PyInstaller-contrib's hook-astropy.

The upstream hook does a blanket `collect_submodules('astropy')`, which imports
*every* astropy submodule at analysis time. `astropy.visualization.wcsaxes` calls
`pytest.importorskip("matplotlib")` at import — and when matplotlib is absent (we
don't ship it) that raises pytest's `Skipped`, a `BaseException` PyInstaller's
collector doesn't catch, aborting the whole build.

M110 only uses a few astropy subpackages (FITS I/O, coordinates, time, units), so
we name those explicitly and still bundle astropy's data files. A user hookspath
entry shadows the contrib hook of the same name, so this replaces it.
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("astropy")

hiddenimports = [
    "astropy.io.fits",
    "astropy.coordinates",
    "astropy.time",
    "astropy.units",
]

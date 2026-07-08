"""PyInstaller entry point for the macOS .app bundle.

PyInstaller needs a concrete script to analyze; the installed `m110` gui-script
(`m110.ui.main:main`) isn't a file on disk. This thin shim just calls it, so the
bundle's behavior is identical to running `m110` from a dev install.
"""
from m110.ui.main import main

if __name__ == "__main__":
    main()

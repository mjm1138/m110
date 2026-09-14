#!/usr/bin/env python3
"""Print the version string that names a release artifact.

    python packaging/common/artifact_version.py            # from the installed m110 metadata
    python packaging/common/artifact_version.py 0.3.0b6    # from a PEP 440 string

PEP 440 ``0.3.0b6`` → ``0.3.0-beta.6``: the git tag's form without the ``v``, so
the download is named after the release it came from (``M110-0.3.0-beta.6.dmg``,
``M110-0.3.0-beta.6-x86_64.AppImage``, ``M110-0.3.0-beta.6-setup.exe``). A final
release is just the numeric version (``0.3.0`` → ``M110-0.3.0.dmg``).

Why this exists: the builders used to name every artifact by the *numeric*
version alone — the only form Apple's ``CFBundleShortVersionString`` and Inno
Setup's ``AppVersion`` accept — so every beta of 0.3.0 shipped as ``M110-0.3.0.dmg``.
A Downloads folder holding several became ``M110-0.3.0-4.dmg``, and nobody could
tell which build was which. The plist and installer metadata keep the numeric
form; only the *filenames* carry the full version. All three platform builders
and ``tools/release.py`` derive it from this one function.
"""
from __future__ import annotations

import sys


def artifact_version(pep440: str) -> str:
    """``0.3.0b6`` → ``0.3.0-beta.6``; ``1.0.0rc1`` → ``1.0.0-rc.1``; ``0.3.0`` → ``0.3.0``."""
    from packaging.version import Version
    v = Version(pep440)
    out = v.base_version
    if v.pre:
        kind = {"a": "alpha", "b": "beta", "rc": "rc"}[v.pre[0]]
        out += f"-{kind}.{v.pre[1]}"
    if v.dev is not None:
        out += f"-dev.{v.dev}"
    return out


def main(argv: list[str]) -> None:
    if len(argv) > 1:
        raw = argv[1]
    else:
        from importlib.metadata import version
        raw = version("m110")
    print(artifact_version(raw))


if __name__ == "__main__":
    main(sys.argv)

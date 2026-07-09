"""Guard against the cp1252-on-Windows bug class.

Engine text I/O must pass `encoding="utf-8"`. A missing `encoding=` defaults to the
OS locale encoding — UTF-8 on macOS/Linux but **cp1252 on Windows** — so an em-dash,
smart quote, or accented object name is written as cp1252 and then fails to decode as
UTF-8 on read. This exact bug crashed first-run on Windows (a seeded `library.toml`
comment with an em-dash → `UnicodeDecodeError` in `tomllib.load`). This scans the
engine source so a new unencoded `open`/`read_text`/`write_text` can't reintroduce it.
"""
import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[1] / "m110"

# `.open()` on these receivers is a library reader (binary/handled), not a text file.
_NON_TEXT_OPEN_RECEIVERS = {"fits", "Image", "np", "cv2"}


def _has_encoding(call: ast.Call) -> bool:
    return any(k.arg == "encoding" for k in call.keywords)


def _is_binary(call: ast.Call) -> bool:
    """A file mode arg containing 'b' means binary — encoding is N/A."""
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return "b" in a.value
    for k in call.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            return "b" in str(k.value.value)
    return False


def _offenders(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute):
            if fn.attr in ("read_text", "write_text") and not _has_encoding(node):
                yield node.lineno, f"{fn.attr}()"
            elif fn.attr == "open":
                recv = fn.value
                name = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", None)
                if name in _NON_TEXT_OPEN_RECEIVERS:
                    continue
                if not _is_binary(node) and not _has_encoding(node):
                    yield node.lineno, "path.open()"
        elif isinstance(fn, ast.Name) and fn.id == "open":
            if not _is_binary(node) and not _has_encoding(node):
                yield node.lineno, "open()"


def test_engine_text_io_specifies_utf8():
    bad = []
    for path in sorted(ENGINE.rglob("*.py")):
        for lineno, kind in _offenders(path):
            bad.append(f"{path.relative_to(ENGINE.parent)}:{lineno} {kind}")
    assert not bad, (
        'engine text I/O without encoding="utf-8" (cp1252 corrupts non-ASCII on '
        "Windows):\n  " + "\n  ".join(bad)
    )


def test_load_library_rejects_non_utf8_gracefully(tmp_path, monkeypatch):
    """A cp1252-encoded library.toml (e.g. written by an older Windows build) must
    raise the actionable LibraryParseError, not a raw UnicodeDecodeError crash."""
    from m110 import config, catalog
    p = tmp_path / "library.toml"
    p.write_bytes(b"# M110 Library \x97 written as cp1252\n")   # 0x97 = em-dash, invalid UTF-8
    monkeypatch.setattr(config, "LIBRARY_TOML", p)
    with pytest.raises(catalog.LibraryParseError):
        catalog.load_library()

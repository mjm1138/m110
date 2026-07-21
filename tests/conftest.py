"""Shared pytest configuration.

Forces Qt onto the offscreen platform *before* anything imports PySide6, so the
pytest-qt `qtbot`/`qapp` fixtures (and any widget construction) run headless in CI.
Reusable store/builder helpers live in `tests/_helpers.py`.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _seal_live_store(tmp_path_factory):
    """Hard safety net: for the whole test session, point M110 at a throwaway data
    root (env + config path globals + settings) so **no test — nor a worker thread
    that leaks past its per-test monkeypatch — can ever read or write the real
    ~/Documents/M110 store**. Per-test `seed_root` monkeypatches over this and unwinds
    back *to it*, never to the live default. (Regression net for the leaked
    RefreshWorker that once corrupted a live `library.toml`.)"""
    from m110 import config
    base = tmp_path_factory.mktemp("m110_live_seal")
    os.environ["M110_DATA_ROOT"] = str(base)        # any _resolve_data_root → throwaway
    config._apply(base)                             # all DATA_ROOT/* path globals → base
    config.SETTINGS_FILE = base / "settings.json"   # never touch ~/.m110/settings.json
    config.ensure_data_root(base)
    yield base
    os.environ.pop("M110_DATA_ROOT", None)


@pytest.fixture(autouse=True)
def _reset_to_seal(_seal_live_store):
    """Before each test, reset config to the throwaway baseline so a per-test
    `monkeypatch` records *that* as its restore target (not whatever a previous test
    left, and never the live root)."""
    from m110 import config
    config._apply(_seal_live_store)
    config.SETTINGS_FILE = _seal_live_store / "settings.json"
    yield


@pytest.fixture(autouse=True)
def _drain_qt_threadpool():
    """After each test, wait for background QThreadPool work (async thumbnail
    decodes — `ThumbnailLoader`) to finish before pytest-qt tears the widgets and,
    at session end, the QApplication down. A decode still running on a pool thread
    when Qt is torn down runs native image code against a half-destroyed Qt and
    **segfaults the whole process** — the intermittent CI SIGSEGV (exit 139) that
    "passes on re-run" because it's a thread-timing race, not a test failure.
    No-op when Qt was never imported (pure-engine tests)."""
    yield
    import sys
    qtcore = sys.modules.get("PySide6.QtCore")
    if qtcore is None or qtcore.QCoreApplication.instance() is None:
        return
    qtcore.QThreadPool.globalInstance().waitForDone(10000)

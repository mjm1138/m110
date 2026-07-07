"""Rotating file logging (BETA §5)."""
import logging

import pytest

from m110 import config, logsetup


@pytest.fixture
def isolated_logging(tmp_path, monkeypatch):
    """Point the log at a temp config dir and reset the module + logger state so
    each test configures from scratch (the `m110` logger is process-global)."""
    monkeypatch.setattr(config, "APP_CONFIG_DIR", tmp_path / ".m110")
    monkeypatch.setattr(logsetup, "_configured", False)
    logger = logging.getLogger("m110")
    for h in list(logger.handlers):
        logger.removeHandler(h)
    yield tmp_path
    for h in list(logger.handlers):
        logger.removeHandler(h)


def test_setup_creates_log_and_writes(isolated_logging):
    path = logsetup.setup_logging()
    assert path == logsetup.log_path()
    assert path.is_file()                       # created under APP_CONFIG_DIR/logs
    logsetup.get_logger().info("hello-marker")
    for h in logging.getLogger("m110").handlers:
        h.flush()
    assert "hello-marker" in path.read_text()


def test_setup_is_idempotent(isolated_logging):
    logsetup.setup_logging()
    n = len(logging.getLogger("m110").handlers)
    logsetup.setup_logging()                    # second call must not stack handlers
    assert len(logging.getLogger("m110").handlers) == n


def test_read_log_tail(isolated_logging):
    logsetup.setup_logging()
    for i in range(60):
        logsetup.get_logger().info("line-%d", i)
    for h in logging.getLogger("m110").handlers:
        h.flush()
    tail = logsetup.read_log_tail(10)
    assert "line-59" in tail and "line-40" not in tail   # only the last ~10 lines


def test_read_log_tail_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_CONFIG_DIR", tmp_path / "nope")
    assert logsetup.read_log_tail() == ""       # no file → '' (never raises)

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


def test_startup_logs_the_data_root_and_where_it_came_from(isolated_logging):
    """A store nobody meant to open is invisible without this line.

    A leftover `data_root` preference (e.g. left pointing at a test corpus)
    outranks the default on every launch and never expires, and the status bar
    shows the path but never its origin — so "why did it open that folder?"
    could not be answered from a bug report at all.
    """
    path = logsetup.setup_logging()
    for h in logging.getLogger("m110").handlers:
        h.flush()
    text = path.read_text()
    assert f"data root: {config.DATA_ROOT} — from {config.data_root_source()}" in text


@pytest.mark.parametrize("tier", ["env", "saved", "default"])
def test_data_root_source_names_the_tier_that_won(tmp_path, monkeypatch, tier):
    """`_resolve_data_root` is env → saved preference → default; the reported
    source has to follow the branch actually taken, including the precedence
    (an env var wins even when a preference exists)."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "APP_CONFIG_DIR", tmp_path / "cfg")
    if tier != "default":                       # a preference is present for both
        config.save_setting("data_root", str(tmp_path / "saved"))
    if tier == "env":
        monkeypatch.setenv("M110_DATA_ROOT", str(tmp_path / "from-env"))
    else:
        monkeypatch.delenv("M110_DATA_ROOT", raising=False)

    root = config._resolve_data_root()
    expected = {"env": config.DATA_ROOT_ENV,
                "saved": config.DATA_ROOT_SAVED,
                "default": config.DATA_ROOT_DEFAULT}[tier]
    assert config.data_root_source() == expected
    if tier == "env":                           # precedence, not just the label
        assert root == tmp_path / "from-env"
    elif tier == "saved":
        assert root == tmp_path / "saved"
    else:
        assert root == config.DEFAULT_DATA_ROOT


def test_a_runtime_repoint_does_not_keep_claiming_the_old_source(tmp_path, monkeypatch):
    """`set_data_root` bypasses resolution entirely, so it must not leave the
    log asserting a preference or env var chose the root it is now on."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "APP_CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setenv("M110_DATA_ROOT", str(tmp_path / "from-env"))
    config._resolve_data_root()
    assert config.data_root_source() == config.DATA_ROOT_ENV

    config.set_data_root(tmp_path / "elsewhere")
    assert config.data_root_source() == config.DATA_ROOT_RUNTIME

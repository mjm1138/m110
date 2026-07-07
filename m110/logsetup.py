"""Application logging — a rotating file log in a known location.

Qt-free (stdlib `logging` + `config` only), so it can be initialized before the
GUI and reused by the headless engine. The log lives beside the other app config
(`~/.m110/logs/m110.log`) and is surfaced in the crash/report dialog (see
`m110/ui/error_report.py`) so a beta user can attach it to a bug report.
"""
from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import config

_LOGGER_NAME = "m110"
_configured = False


def log_dir() -> Path:
    return config.APP_CONFIG_DIR / "logs"


def log_path() -> Path:
    return log_dir() / "m110.log"


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure the `m110` logger with a rotating file handler (+ stderr).
    Idempotent — safe to call more than once (won't stack handlers). Returns the
    log path. Never raises: a logging setup failure must not break app launch."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return log_path()

    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # e.g. a read-only home — fall back to stderr-only logging

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    _configured = True
    try:
        from m110.ui.about_dialog import app_version
        version = app_version()
    except Exception:
        version = "?"
    logger.info("M110 %s starting — %s (Python %s)", version,
                platform.platform(), platform.python_version())
    return log_path()


def read_log_tail(max_lines: int = 40) -> str:
    """The last `max_lines` of the log file (for the report), or '' if unreadable."""
    try:
        lines = log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])

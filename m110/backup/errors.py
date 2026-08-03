"""Backup failures (mirrors `publish/errors.py`)."""
from __future__ import annotations


class BackupError(Exception):
    """Base for backup failures."""


class BackupDestinationError(BackupError):
    """The destination is missing, unwritable, or unreachable."""

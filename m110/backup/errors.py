"""Backup failures (mirrors `publish/errors.py`)."""
from __future__ import annotations


class BackupError(Exception):
    """Base for backup failures."""


class BackupDestinationError(BackupError):
    """The destination is missing, unwritable, or unreachable."""


class BackupDepsMissing(BackupError):
    """The optional `s3` extra (boto3 + keyring) isn't installed.

    Raised by `backends.s3` so the UI can show an actionable message instead of a
    raw ImportError — the same degrade-gracefully pattern as
    `publish.PublishDepsMissing` and `catalog.OnlineLookupError`.
    """


def deps_missing_message() -> str:
    """The message for "boto3 can't be imported", tailored to how M110 is run.

    A **frozen** app has no pip, so telling the user to `pip install` is
    impossible — and packaged builds are *meant* to bundle the extra (the issue
    #64 lesson), so its absence there is a build defect worth reporting. From
    **source**, the extra is the fix. Mirrors `catalog._astroquery_missing_message`.
    """
    import sys
    if getattr(sys, "frozen", False):
        return ("Cloud backup isn't available in this build. It should be included — "
                "please report it via Help → Report a problem.")
    return ("Cloud backup needs the optional 's3' extra "
            "(pip install 'm110[s3]').")

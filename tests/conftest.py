"""Shared pytest configuration.

Forces Qt onto the offscreen platform *before* anything imports PySide6, so the
pytest-qt `qtbot`/`qapp` fixtures (and any widget construction) run headless in CI.
Reusable store/builder helpers live in `tests/_helpers.py`.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

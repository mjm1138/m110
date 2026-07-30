"""Data-store preflight shared by every tool.

The server is read-only, so it cannot bootstrap a missing store the way the app
does on launch (`config.ensure_data_root`). When the configured root is wrong or
un-bootstrapped, the honest move is a clear message naming the path, not a
FileNotFoundError traceback the model has to guess at.
"""
from __future__ import annotations

from m110 import config
from m110.assistant.registry import StoreUnavailable


def require_store() -> None:
    """Raise StoreUnavailable unless the data root looks like a real M110 store."""
    root = config.DATA_ROOT
    if not root.is_dir():
        raise StoreUnavailable(
            f"No M110 data store at {root}. The server was started with that path "
            "(usually via M110_DATA_ROOT in the MCP client's config). Check the path, "
            "or open M110 once to create the store."
        )
    if not config.LIBRARY_TOML.is_file():
        raise StoreUnavailable(
            f"{root} exists but is not an initialized M110 store "
            f"({config.LIBRARY_TOML.name} is missing). Open M110 once pointed at this "
            "folder to set it up."
        )

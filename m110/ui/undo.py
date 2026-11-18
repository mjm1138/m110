"""The app's Undo stack (Edit › Undo / Redo).

Two kinds of change join it in Phase 7 (UI_ROADMAP → open decision "Undo scope"):
**Remove from Library** and **Pin / Deprioritize** overrides — the edits a user
makes with one click from a context menu and could otherwise only reverse by
remembering what was there. Each command snapshots the state it replaces and calls
the same engine writer in both directions (`catalog.remove_library_entry` /
`add_library_entry`, `pins.set_state`); nothing new writes to the store.

Pages don't hold the stack. They call `run(command)`: with a stack installed (the
main window installs one) the command is pushed — which performs it — otherwise it
simply runs, so a page built standalone in a test behaves as before.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QUndoCommand, QUndoStack

_STACK: QUndoStack | None = None


def install(stack: QUndoStack | None) -> None:
    global _STACK
    _STACK = stack


def stack() -> QUndoStack | None:
    return _STACK


def run(cmd: QUndoCommand) -> None:
    """Perform `cmd`, recording it for Undo when a stack is installed."""
    if _STACK is not None:
        _STACK.push(cmd)          # push() calls redo()
    else:
        cmd.redo()


def _noop() -> None:
    pass


class SetPinCommand(QUndoCommand):
    """Pin / deprioritize / clear an object's priority override."""

    _LABELS = {"pin": "Pin as Priority", "deprioritize": "Deprioritize",
               None: "Clear Priority Override"}

    def __init__(self, slug: str, state: str | None,
                 on_change: Callable[[], None] = _noop):
        from m110 import pins
        self._slug, self._new = slug, state
        self._old = pins.get_state(slug)
        self._on_change = on_change
        label = self._LABELS.get(state, "Priority Override")
        if state is None and self._old is not None:
            label = {"pin": "Unpin", "deprioritize": "Un-deprioritize"}[self._old]
        super().__init__(label)

    def redo(self):
        from m110 import pins
        pins.set_state(self._slug, self._new)
        self._on_change()

    def undo(self):
        from m110 import pins
        pins.set_state(self._slug, self._old)
        self._on_change()


class RemoveFromLibraryCommand(QUndoCommand):
    """Drop an (uncaptured) object from `library.toml`; Undo puts the same entry
    back. The journal under `Objects/` is never touched either way."""

    def __init__(self, slug: str, on_change: Callable[[], None] = _noop):
        from m110 import catalog
        self._slug = slug
        self._entry = dict(catalog.load_library().get(slug, {}))
        self._on_change = on_change
        super().__init__(f"Remove {self._entry.get('id') or slug} from Library")

    def redo(self):
        from m110 import catalog
        catalog.remove_library_entry(self._slug)
        self._on_change()

    def undo(self):
        from m110 import catalog
        if self._entry and self._slug not in catalog.load_library():
            catalog.add_library_entry(self._slug, self._entry)
        self._on_change()

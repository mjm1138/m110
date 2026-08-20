"""Send a stack to a post-processing workflow (ROADMAP item 14a).

Preview-then-confirm, like ingest and import: the list is built read-only, and
nothing is written until the user picks a stack and confirms. The write itself
goes through `stacking.apply_handoff` — the same function `m110-stack --handoff`
calls — so the CLI and the app cannot drift on what the convention is.

Why the launch is a *suggestion* rather than the point: AstroWizard takes no
working-directory argument and registers no document types, so nothing can hand
it a file. Opening the destination folder is what actually makes the stack
findable, which is why Reveal sits beside Open rather than behind a failure.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidgetItem, QVBoxLayout,
)

from m110 import config, launch, stacking
from m110.ui.widgets import (
    NumItem, fit_table_height, make_table, reveal_in_manager, targets_for_slug,
)


# No "Size" column on purpose: the handoff is a hardlink, so it costs nothing,
# and showing a size next to that claim invites the opposite conclusion. "State"
# earns the space instead — it is the question this dialog exists to answer.
_COLUMNS = ["Stack", "Target", "From", "Frames", "Integration", "Stacked", "State"]
_COL_STACKED = _COLUMNS.index("Stacked")


def _state(stretched: bool | None) -> str:
    if stretched is None:
        return "—"
    return "stretched" if stretched else "linear"


class HandoffDialog(QDialog):
    """Pick one of an object's stacks and hand it to `tool`."""

    def __init__(self, slug: str, tool: str = "astrowizard", parent=None):
        super().__init__(parent)
        self._slug, self._tool = slug, tool
        self._label = launch.tool_label(tool)
        self._sent: Path | None = None
        self.setWindowTitle(f"Send a stack to {self._label}")
        self.setMinimumWidth(900)     # stack names are long; give them the room

        lay = QVBoxLayout(self)
        note = QLabel(
            f"Pick the stack to finish in {self._label} — it starts from a "
            f"<b>linear</b> stack, so choose the one straight off the stacker "
            f"rather than something you have already stretched. M110 links it into "
            f"the object's <code>{tool}/</code> folder — a hardlink, so it costs no "
            f"extra disk — and records which stack it came from. Your originals are "
            f"not moved or changed."
        )
        note.setWordWrap(True)
        lay.addWidget(note)

        self._rows = self._gather()
        self._table = make_table(_COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._fill()
        lay.addWidget(self._table)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setProperty("caption", True)
        lay.addWidget(self._status)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._send = QPushButton(f"Send to {self._label}")
        self._send.setDefault(True)
        self._send.clicked.connect(self._do_send)
        close = QPushButton("Cancel")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        btns.addWidget(self._send)
        lay.addLayout(btns)

        self._table.itemSelectionChanged.connect(self._sync)
        self._preselect()
        self._sync()

    # ── building the list ────────────────────────────────────────────────────

    def _gather(self) -> list[tuple[str, stacking.HandoffCandidate]]:
        """(target, candidate) across every capture target feeding this object.

        Gathered into one list rather than asking the user to choose a target
        first: a target is a folder, and which folder a stack lives in is not a
        question they should have to answer before seeing the stacks.
        """
        out: list[tuple[str, stacking.HandoffCandidate]] = []
        for target in targets_for_slug(self._slug):
            try:
                out += [(target, c)
                        for c in stacking.handoff_candidates(target, self._tool)]
            except stacking.StackingError:
                continue
        out.sort(key=lambda tc: (tc[1].stacked_at or "", tc[1].size_bytes),
                 reverse=True)
        return out

    def _fill(self) -> None:
        # `make_table` turns sorting on, and a sortable QTableWidget re-sorts as
        # each item is set — which scrambles the newest-first order this dialog
        # computed. Populate with sorting off, then restore it.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._rows))
        for r, (target, c) in enumerate(self._rows):
            name = QTableWidgetItem(c.name)
            # The row's index into `self._rows`, carried on the item rather than
            # inferred from its position: the user can re-sort by any column, and
            # reading the visual row back into the list would then hand over a
            # DIFFERENT stack than the one highlighted.
            name.setData(Qt.UserRole, r)
            # Elided in the column, so the full name has to be reachable — these
            # names are how the user tells one stack from another.
            tip = str(c.path.name)
            if c.already:
                tip += f"\n\nAlready in {self._tool}/ — sending again is a no-op"
            name.setToolTip(tip)
            cells = [
                name,
                QTableWidgetItem(target),
                QTableWidgetItem(c.tier),
                NumItem(f"{c.frames:,}" if c.frames else "—", c.frames or 0),
                NumItem(f"{c.integration_min:.0f} min" if c.integration_min else "—",
                        c.integration_min or 0),
                # Sorted on the raw header value, not the display string: an
                # undated stack shows "—", which would sort *first* descending.
                NumItem((c.stacked_at or "—")[:16].replace("T", " "),
                        c.stacked_at or ""),
                # Sorts linear first, so a click on this header surfaces the
                # usable stacks rather than ordering them alphabetically.
                NumItem(_state(c.stretched), (0 if c.stretched is False else
                                              1 if c.stretched is None else 2)),
            ]
            for col, item in enumerate(cells):
                self._table.setItem(r, col, item)
        self._table.setSortingEnabled(True)
        # Re-enabling sorting sorts immediately, by whatever the sort indicator
        # happens to be — column 0, which is alphabetical by filename and
        # meaningless here. Point it at the order this dialog actually computed,
        # so what the user sees and what the header indicator claims agree.
        self._table.sortByColumn(_COL_STACKED, Qt.DescendingOrder)
        # Size the short columns to their content and let the filename absorb the
        # rest. `resizeColumnsToContents` alone gives the name column everything it
        # asks for — these run past 60 characters — which pushes frames,
        # integration and date off behind a horizontal scrollbar. Those are the
        # columns the choice is actually made on, so they get the fixed space and
        # the name elides.
        self._table.resizeColumnsToContents()
        # Elide the LEFT: every name in a target's list opens with the same object
        # prefix, and what distinguishes them — the date and the step suffix — is
        # at the tail. Middle elision produced two rows both reading
        # "M_27_202...ssed.fit". The full name is on the tooltip either way.
        self._table.setTextElideMode(Qt.ElideLeft)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        fit_table_height(self._table, max_rows=10)

    def _preselect(self) -> None:
        """Highlight the newest stack that is still **linear**.

        AstroWizard starts at background extraction and stretching, so a stretched
        input is the wrong thing. On a real library `stacks/` accumulates the
        user's own saved steps beside the stacker's output, and the newest file is
        very often one of those — defaulting to row 0 handed over a denoised,
        already-stretched image.

        Judged from the header's HISTORY, not the filename: `_denoise` sounds like
        a linear step and is not. Falls back to newest overall when nothing is
        recorded as linear, since a guess the user can see and change beats no
        selection at all.
        """
        if not self._rows:
            return
        for r in range(self._table.rowCount()):
            _target, c = self._rows[self._table.item(r, 0).data(Qt.UserRole)]
            if c.stretched is False:
                self._table.selectRow(r)
                return
        self._table.selectRow(0)

    # ── state ────────────────────────────────────────────────────────────────

    def _selected(self) -> tuple[str, stacking.HandoffCandidate] | None:
        """The highlighted candidate, resolved through the index stored on the
        item — never through its visual row, which moves when the user sorts."""
        rows = self._table.selectionModel().selectedRows() if self._rows else []
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        idx = item.data(Qt.UserRole) if item is not None else None
        return self._rows[idx] if idx is not None else None

    def _sync(self) -> None:
        if not self._rows:
            self._status.setText(
                "No stacks yet for this object. Stack it first — in Siril, or with "
                "<code>m110-stack</code> — and the result will show up here.")
            self._send.setEnabled(False)
            return
        sel = self._selected()
        if sel is None:
            self._status.setText("Pick a stack.")
            self._send.setEnabled(False)
            return
        target, c = sel
        dest = config.astrowizard_dir(target)
        rel = dest.relative_to(config.DATA_ROOT) if _within(dest) else dest
        if c.already:
            msg = "Already there — sending again changes nothing."
        else:
            msg = f"Will link into <code>{rel}/</code>"
        if c.stretched:
            msg = (f"<b>This one has already been stretched</b> — its history "
                   f"records it. {self._label} expects a linear stack and will say "
                   f"so. {msg}")
        self._status.setText(msg)
        self._send.setEnabled(True)

    # ── the write ────────────────────────────────────────────────────────────

    def _do_send(self) -> None:
        sel = self._selected()
        if sel is None:
            return
        _target, c = sel
        try:
            self._sent = stacking.apply_handoff(c.path, self._tool)
        except (stacking.StackingError, OSError) as exc:
            QMessageBox.warning(self, f"Send to {self._label}", str(exc))
            return
        self._offer_to_open()
        self.accept()

    def _offer_to_open(self) -> None:
        """Offer to open the tool and/or the folder holding the stack."""
        folder = self._sent.parent
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(f"Sent to {self._label}")
        box.setText(f"{self._sent.name} is ready for {self._label}.")
        found = launch.find_app(self._tool)
        if found and not launch.sets_working_dir(self._tool):
            box.setInformativeText(
                f"{self._label} can't be pointed at a folder, so open the file from "
                f"inside it — Reveal folder opens the right place.")
        elif not found:
            box.setInformativeText(
                f"{self._label} wasn't found on this machine. You can set its "
                f"location in Preferences → Processing tools.")
        reveal = box.addButton("Reveal folder", QMessageBox.AcceptRole)
        open_btn = box.addButton(f"Open {self._label}",
                                 QMessageBox.AcceptRole) if found else None
        box.addButton("Done", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is reveal:
            reveal_in_manager(folder)
        elif open_btn is not None and clicked is open_btn:
            try:
                launch.launch_processing(self._tool, folder)
            except launch.LaunchError as exc:
                QMessageBox.warning(self, f"Open {self._label}", str(exc))
            else:
                reveal_in_manager(folder)     # it can't open the file itself


def _within(p: Path) -> bool:
    try:
        p.relative_to(config.DATA_ROOT)
        return True
    except ValueError:
        return False


def can_hand_off(slug: str, tool: str = "astrowizard") -> bool:
    """True when the object has at least one stack that could be handed over.

    Deliberately the header-free check: the detail pane asks this on every render,
    and reading provenance for every stack of every target just to grey out a
    button would be a directory-and-header storm per repaint.
    """
    if tool not in stacking.handoff_targets():
        return False
    return any(stacking.has_handoff_candidates(t) for t in targets_for_slug(slug))

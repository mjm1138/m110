"""Reviewing what the assistant handed over — banner + modal.

Deliberately split, because the two jobs want opposite behaviour:

* **Notification is a banner.** M110 auto-syncs on every window focus, and a
  user with Siril open alt-tabs constantly — a modal on launch or foreground
  would fire over and over. A banner that persists while the queue is non-empty
  also *guarantees* the queue is seen, which a dismissible modal does not:
  dismiss that once and the reminder is gone.
* **Review is a modal.** Applying a change deserves a focused, blocking confirm
  with the before/after and the drift warning — triggered by intent, when the
  user clicks Review, not by the app's lifecycle.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QSplitter,
)

from m110.assistant import apply as apply_mod, outbox
from m110.ui import theme


class AssistantBanner(QFrame):
    """Quiet strip: "N items from the assistant — Review". Hidden when empty."""

    review = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("assistantBanner")
        t = theme.active_tokens()
        s = theme.tokens.SPACE
        r = theme.tokens.RADIUS["md"]
        self.setStyleSheet(
            f"#assistantBanner {{ background:{t.surface_alt}; "
            f"border:1px solid {t.border}; border-radius:{r}px; }}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(s["md"], s["sm"], s["sm"], s["sm"])
        lay.setSpacing(s["sm"])
        self._msg = QLabel()
        lay.addWidget(self._msg)
        lay.addStretch(1)

        btn = QPushButton("Review…")
        btn.setDefault(True)
        btn.clicked.connect(self.review.emit)
        lay.addWidget(btn)
        # No dismiss button on purpose: the banner IS the queue indicator, and
        # it goes away by emptying the queue rather than by hiding it.
        self.refresh()

    def refresh(self) -> int:
        """Re-read the queue; show or hide accordingly. Returns the count."""
        try:
            items = outbox.items()
        except OSError:
            items = []
        n = len(items)
        if n:
            kinds = {"proposal": 0, "artifact": 0}
            for i in items:
                kinds[i.kind] = kinds.get(i.kind, 0) + 1
            bits = []
            if kinds["artifact"]:
                bits.append(f"{kinds['artifact']} saved plan"
                            f"{'s' if kinds['artifact'] != 1 else ''}")
            if kinds["proposal"]:
                bits.append(f"{kinds['proposal']} suggested change"
                            f"{'s' if kinds['proposal'] != 1 else ''}")
            self._msg.setText("From the assistant: " + " and ".join(bits) + ".")
        self.setVisible(bool(n))
        return n


class AssistantReviewDialog(QDialog):
    """Accept an artifact, or apply a proposal after seeing what it would do."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("From the assistant")
        self.resize(760, 520)
        self._applied_any = False

        s = theme.tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        lay.setSpacing(s["md"])

        blurb = QLabel(
            "Things the assistant has prepared for you. Nothing here has changed "
            "your library — accepting is what applies it.")
        blurb.setWordWrap(True)
        lay.addWidget(blurb)

        split = QSplitter(Qt.Horizontal)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(lambda *_: self._show_current())
        split.addWidget(self._list)
        self._detail = QTextBrowser()
        self._detail.setOpenExternalLinks(False)
        split.addWidget(self._detail)
        split.setSizes([260, 500])
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        self._status = QLabel()
        self._status.setProperty("caption", True)
        self._status.setWordWrap(True)
        row.addWidget(self._status, 1)
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.setDefault(True)
        self._accept_btn.clicked.connect(self._accept)
        self._discard_btn = QPushButton("Discard")
        self._discard_btn.clicked.connect(self._discard)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for b in (self._accept_btn, self._discard_btn, close):
            row.addWidget(b)
        lay.addLayout(row)

        self.reload()

    # ── data ────────────────────────────────────────────────────────────────

    def reload(self):
        self._list.clear()
        for item in outbox.items():
            label = ("📄  " if item.kind == "artifact" else "⚙  ") + (
                item.title or item.name)
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item)
            self._list.addItem(row)
        if self._list.count():
            self._list.setCurrentRow(0)
        else:
            self._detail.setMarkdown(
                "### Nothing pending\n\nAsk the assistant to plan a night and "
                "save it, and it will show up here.")
            self._status.clear()
        for b in (self._accept_btn, self._discard_btn):
            b.setEnabled(bool(self._list.count()))

    def _current(self):
        row = self._list.currentItem()
        return row.data(Qt.UserRole) if row else None

    def _show_current(self):
        item = self._current()
        if item is None:
            return
        if item.kind == "artifact":
            self._accept_btn.setText("Accept")
            self._detail.setMarkdown(outbox.read(item.name))
            self._status.setText("Accepting files this into your Plans folder.")
            return

        self._accept_btn.setText("Apply")
        import json
        envelope = json.loads(outbox.read(item.name))
        body = [envelope.get("summary", "")]

        # Re-run the preview against the store as it is NOW — the stored one may
        # describe a library that has since moved on.
        fresh = apply_mod.repreview(envelope)
        if fresh and fresh.get("after"):
            from m110.assistant.proposals import markdown_table
            body += ["\n---\n\n**Ranking if you apply this, as of now:**\n",
                     markdown_table(fresh["after"][:8])]
        self._detail.setMarkdown("\n".join(body))

        drift = apply_mod.check_drift(envelope)
        if drift.drifted:
            self._status.setText(
                f"⚠ Your library has changed since this was suggested — "
                f"{drift.describe()}. Check the updated ranking above before applying.")
        else:
            self._status.setText("Nothing has changed since this was suggested.")

    # ── actions ─────────────────────────────────────────────────────────────

    def _accept(self):
        item = self._current()
        if item is None:
            return
        try:
            if item.kind == "artifact":
                path = apply_mod.accept_artifact(item.name)
                msg = f"Saved to Plans as {path.name}."
            else:
                envelope_drifted = apply_mod.check_drift(
                    __import__("json").loads(outbox.read(item.name))).drifted
                if envelope_drifted and QMessageBox.question(
                        self, "Apply anyway?",
                        "Your library has changed since this was suggested.\n\n"
                        "Apply it anyway?") != QMessageBox.Yes:
                    return
                msg = apply_mod.apply_proposal(item.name, force=envelope_drifted)
        except apply_mod.ApplyError as exc:
            QMessageBox.warning(self, "Couldn't apply", str(exc))
            self.reload()
            return

        self._applied_any = True
        self.changed.emit()
        self.reload()
        self._status.setText(msg)

    def _discard(self):
        item = self._current()
        if item is None:
            return
        if QMessageBox.question(
                self, "Discard",
                f"Discard “{item.title or item.name}”?\n\n"
                "Nothing in your library changes.") != QMessageBox.Yes:
            return
        apply_mod.discard(item.name)
        self.changed.emit()
        self.reload()

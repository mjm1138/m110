"""Set an object's integration goal on one telescope model (#184).

A minutes spinbox (seeded with the current goal; the model's default shown beside
it) and an optional one-line reason, kept with the goal so the number doesn't lose
its justification. When the goal is the user's own, **Use default** goes back to the
model's default — the one place to change a goal, so the detail pane's row needs a
single button. The caller writes it — this dialog only collects it.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout,
)


class GoalDialog(QDialog):
    def __init__(self, object_label: str, model_label: str, goal_min: float,
                 default_min: float, reason: str = "", *, calibrated: bool = True,
                 custom: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Integration goal — {object_label}")
        self.setMinimumWidth(440)        # else the title truncates and the intro wraps tall
        lay = QVBoxLayout(self)
        intro = QLabel(
            f"How many minutes of captured integration {object_label} needs on the "
            f"<b>{model_label}</b>. Its status turns Deep Stack when it gets there, "
            "and Planning stops pushing it for this telescope.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        form = QFormLayout()
        self._minutes = QSpinBox()
        self._minutes.setRange(5, 100_000)
        self._minutes.setSingleStep(15)
        self._minutes.setSuffix(" min")
        self._minutes.setValue(int(round(goal_min)))
        default = f"Default for this telescope: {default_min:.0f} min"
        if not calibrated:
            default += " (its f-ratio is unknown, so the S50's numbers)"
        hint = QLabel(default)
        hint.setProperty("caption", True)
        hint.setWordWrap(True)
        self._reason = QLineEdit(reason)
        self._reason.setPlaceholderText("Why this number (optional)")
        form.addRow("Goal", self._minutes)
        form.addRow("", hint)
        form.addRow("Reason", self._reason)
        lay.addLayout(form)

        buttons = QDialogButtonBox()
        self._use_default = False
        self._default_btn = None
        if custom:                       # only a goal you set has a default to go back to
            self._default_btn = buttons.addButton("Use default",
                                                  QDialogButtonBox.ResetRole)
            self._default_btn.setToolTip(f"Back to {default_min:.0f} min")
            self._default_btn.clicked.connect(self._choose_default)
        self._save_btn = buttons.addButton("Save", QDialogButtonBox.AcceptRole)
        self._reject_btn = buttons.addButton("Close", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._dirty = False
        self._minutes.valueChanged.connect(self._mark_dirty)
        self._reason.textChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_):
        self._dirty = True
        self._reject_btn.setText("Cancel")       # "Cancel" only while there are edits

    def _choose_default(self):
        self._use_default = True
        self.accept()

    def use_default(self) -> bool:
        """True when the dialog closed on **Use default** (clear the goal)."""
        return self._use_default

    def minutes(self) -> int:
        return self._minutes.value()

    def reason(self) -> str:
        return self._reason.text().strip()

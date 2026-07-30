"""Connection details for any MCP client.

M110's assistant server is plain MCP over stdio — nothing about it is specific
to one vendor. What differs between clients is only how they're configured, so
this offers the same connection in the three shapes clients actually ask for:
a `mcpServers` JSON block, a command plus environment, or a CLI one-liner.

Preferences has a one-click path for Claude Desktop because its config is a
JSON file M110 can merge into safely. This dialog is for everything else.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from m110.assistant import client_config as cc
from m110.ui import theme


class _CopyPane(QWidget):
    """A read-only block of text with a Copy button."""

    def __init__(self, explanation: str, payload: str, parent=None):
        super().__init__(parent)
        s = theme.tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, s["sm"], 0, 0)
        lay.setSpacing(s["sm"])

        note = QLabel(explanation)
        note.setWordWrap(True)
        note.setProperty("caption", True)
        lay.addWidget(note)

        self._text = QPlainTextEdit(payload)
        self._text.setReadOnly(True)
        self._text.setFont(theme.mono_font())
        self._text.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self._text, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self._copy = QPushButton("Copy")
        self._copy.clicked.connect(self._on_copy)
        row.addWidget(self._copy)
        lay.addLayout(row)

    def _on_copy(self):
        QApplication.clipboard().setText(self._text.toPlainText())
        self._copy.setText("Copied")
        self._copy.setEnabled(False)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self._reset)

    def _reset(self):
        self._copy.setText("Copy")
        self._copy.setEnabled(True)


class ConnectionDetailsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MCP connection details")
        self.resize(660, 470)

        s = theme.tokens.SPACE
        d = cc.connection_details()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        lay.setSpacing(s["md"])

        intro = QLabel(
            f"M110 exposes an <b>MCP server</b> over stdio, named "
            f"<code>{d['name']}</code>. Any MCP-compatible client can connect using "
            "the details below. The data folder is pinned explicitly, so the client "
            "always reads the library you're looking at.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        tabs = QTabWidget()
        tabs.addTab(_CopyPane(
            "Most clients (Claude Desktop, and others that use the same format) "
            "read a JSON config. Merge this into yours, keeping any servers you "
            "already have.", d["json"]), "JSON config")
        tabs.addTab(_CopyPane(
            "If your client asks for a command and environment variables "
            "separately, use these.",
            f"command:\n  {d['command']}\n\n"
            f"args:\n  {' '.join(d['args']) or '(none)'}\n\n"
            f"env:\n  M110_DATA_ROOT={d['env']['M110_DATA_ROOT']}\n\n"
            f"transport:\n  {d['transport']}"), "Command")
        tabs.addTab(_CopyPane(
            "Claude Code adds servers from the terminal rather than a config "
            "file. Run this once.", d["cli"]), "Claude Code")
        lay.addWidget(tabs, 1)

        disclosure = QLabel(cc.DISCLOSURE)
        disclosure.setWordWrap(True)
        disclosure.setProperty("caption", True)
        lay.addWidget(disclosure)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

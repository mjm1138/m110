"""The Settings window — a macOS-style settings window (UI Phase 8 · E).

One non-modal, single-instance window (`MainWindow._show_settings` owns it). A pane
bar of icon-over-label buttons across the top — General · Processing · Tools ·
Backup · Assistant · Appearance — switches between panes; the window title follows
the pane and the window fits each pane's height. **Every change applies at once**:
there is no OK, Save or Close button (⌘W / the close box closes it). The data folder
too is saved the moment it's chosen, with an inline note that it takes effect after
a restart.

Each pane is a short one-line description per group plus caption help text — the
old single sheet of explanatory paragraphs (critique §P2 *Dialogs*) is gone. The
Backup pane is `backup_pane.BackupPane`, the former Back up dialog.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from m110 import config, hints, ingest, launch, processing, stackhammer, updates
from m110.ui import theme

# (key, title, Lucide icon) in bar order.
PANES = (
    ("general", "General", "settings"),
    ("processing", "Processing", "layers"),
    ("tools", "Tools", "wrench"),
    ("backup", "Backup", "hard-drive"),
    ("assistant", "Assistant", "sparkles"),
    ("appearance", "Appearance", "sun-moon"),
)
PANE_TITLES = {k: t for k, t, _ in PANES}
PANE_SETTING = "settings_pane"      # the pane the window last showed
WIDTH = 600                         # fixed, like a macOS Settings window
TAB_ICON = 24
SCREEN_FRACTION = 0.85              # never open taller than this much of the screen


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("caption", True)
    lbl.setWordWrap(True)
    return lbl


def _line(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return lbl


def _tab_icon(name: str) -> QIcon:
    """Muted when unselected, primary text when selected — a checkable
    QToolButton picks the On/Off state, not the Selected mode `icons.icon` fills."""
    from m110.ui.theme import icons, tokens
    t = tokens.active()
    ic = QIcon()
    for dpr in (1.0, 2.0):
        ic.addPixmap(icons.pixmap(name, t.text_secondary, TAB_ICON, dpr),
                     QIcon.Mode.Normal, QIcon.State.Off)
        ic.addPixmap(icons.pixmap(name, t.text_primary, TAB_ICON, dpr),
                     QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(icons.pixmap(name, t.text_disabled, TAB_ICON, dpr),
                     QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


class SettingsWindow(QWidget):
    def __init__(self, parent=None, *, pane: str | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        from m110.ui.theme import tokens
        s = tokens.SPACE

        # ── the pane bar ──
        self._bar = QFrame()
        self._bar.setObjectName("settingsBar")
        bar_row = QHBoxLayout(self._bar)
        bar_row.setContentsMargins(s["sm"], s["sm"], s["sm"], s["sm"])
        bar_row.setSpacing(s["xs"])
        bar_row.addStretch(1)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tabs: dict[str, QToolButton] = {}
        for key, title, icon_name in PANES:
            b = QToolButton()
            b.setObjectName("settingsTab")
            b.setText(title)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIcon(_tab_icon(icon_name))
            b.setIconSize(QSize(TAB_ICON, TAB_ICON))
            b.setProperty("iconName", icon_name)
            b.setMinimumWidth(64)
            b.clicked.connect(lambda _=False, k=key: self.show_pane(k))
            self._tab_group.addButton(b)
            self._tabs[key] = b
            bar_row.addWidget(b)
        bar_row.addStretch(1)

        # ── the panes: all in one scrolling column, only the current one shown,
        # so the column's height-for-width is that pane's (see `_fit`) ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Never scroll sideways: content wraps to the viewport (a long data-folder
        # path would otherwise widen the column and clip every caption).
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(s["xl"], s["lg"], s["xl"], s["xl"])
        body.setSpacing(0)
        self._scroll.setWidget(self._body)

        builders = {"general": self._build_general,
                    "processing": self._build_processing,
                    "tools": self._build_tools,
                    "backup": self._build_backup,
                    "assistant": self._build_assistant,
                    "appearance": self._build_appearance}
        self._panes: dict[str, QWidget] = {}
        for key, _title, _icon in PANES:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(s["md"])
            builders[key](lay)
            page.setVisible(False)
            self._panes[key] = page
            body.addWidget(page)
        body.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._bar)
        outer.addWidget(self._scroll, 1)

        self.setFixedWidth(WIDTH)
        self.setMinimumHeight(240)
        self._current = ""
        mgr = theme.manager()
        if mgr is not None:
            mgr.changed.connect(self._restyle)
        start = pane or config.get_setting(PANE_SETTING) or "general"
        self.show_pane(start if start in PANE_TITLES else "general")

    # ── panes ────────────────────────────────────────────────────────────────

    def show_pane(self, key: str):
        if key not in self._panes:
            return
        if self._current and self._current != key and key != "backup":
            self._backup.stop_probes()
        self._current = key
        for k, page in self._panes.items():
            page.setVisible(k == key)
        self._tabs[key].setChecked(True)
        self.setWindowTitle(PANE_TITLES[key])
        config.save_setting(PANE_SETTING, key)
        self._fit()

    def current_pane(self) -> str:
        return self._current

    def needed_height(self) -> int:
        """What the pane on screen needs so nothing in it scrolls.
        Height-for-width, not sizeHint: wrapped captions need it."""
        lay = self._body.layout()
        lay.activate()
        body_h = (lay.heightForWidth(WIDTH) if lay.hasHeightForWidth()
                  else lay.sizeHint().height())
        return self._bar.sizeHint().height() + body_h

    def _fit(self):
        """Size the window to the pane on screen, never taller than the screen
        (which is what the scroll area is for)."""
        need = self.needed_height()
        screen = self.screen().availableGeometry().height() if self.screen() else 0
        self.resize(WIDTH, min(need, int(screen * SCREEN_FRACTION)) if screen else need)

    def showEvent(self, event):
        super().showEvent(event)
        # Styles are polished on show; measure again once they have been.
        QTimer.singleShot(0, self._fit)

    def _restyle(self):
        for key, _title, icon_name in PANES:
            self._tabs[key].setIcon(_tab_icon(icon_name))
        self._sync_theme_combo()           # View › Night Vision may have moved it

    def _sync_theme_combo(self):
        mgr = theme.manager()
        cur = mgr.mode if mgr is not None else config.get_setting(theme.SETTING_KEY,
                                                                   "system")
        idx = self._theme_combo.findData(cur)
        blocked = self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._theme_combo.blockSignals(blocked)

    def hideEvent(self, event):
        # A probe of a slow share mustn't keep running for a window nobody sees.
        self._backup.stop_probes()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._backup.teardown()
        super().closeEvent(event)

    @staticmethod
    def _group(lay: QVBoxLayout, title: str) -> QVBoxLayout:
        from m110.ui.theme import tokens
        box = QGroupBox(title)
        inner = QVBoxLayout(box)
        inner.setSpacing(tokens.SPACE["sm"])
        lay.addWidget(box)
        return inner

    # ── General ──────────────────────────────────────────────────────────────

    def _build_general(self, lay: QVBoxLayout):
        g = self._group(lay, "Data folder")
        row = QHBoxLayout()
        self._root_edit = QLineEdit(self._pending_root())
        self._root_edit.setReadOnly(True)
        self._root_edit.setMinimumWidth(180)      # a deep path mustn't set the width
        self._root_edit.setCursorPosition(0)
        self._root_btn = QPushButton("Change…")
        self._root_btn.clicked.connect(self._change_root)
        row.addWidget(self._root_edit, 1)
        row.addWidget(self._root_btn)
        g.addLayout(row)
        g.addWidget(_caption("Where M110 keeps your Library, captures and renders. "
                             f"Default: {config.DEFAULT_DATA_ROOT}"))
        self._root_note = _caption("")
        g.addWidget(self._root_note)
        self._sync_root_note()

        g = self._group(lay, "Import")
        self._sub_previews_cb = QCheckBox("Import the Seestar's per-sub JPG previews")
        self._sub_previews_cb.setChecked(
            bool(config.get_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, False)))
        self._sub_previews_cb.toggled.connect(
            lambda on: config.save_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, bool(on)))
        g.addWidget(self._sub_previews_cb)
        g.addWidget(_caption("Kept in Images/<object>/previews/, out of the raw "
                             "lights and the gallery."))

        g = self._group(lay, "Updates")
        self._update_cb = QCheckBox("Check for updates on launch")
        self._update_cb.setChecked(updates.check_enabled())
        self._update_cb.toggled.connect(lambda on: updates.set_check_enabled(bool(on)))
        g.addWidget(self._update_cb)
        g.addWidget(_caption("At most once a day, from GitHub. Nothing about you "
                             "or your Library is sent."))

    @staticmethod
    def _pending_root() -> str:
        """The folder M110 will open next launch: the saved choice, else the one
        it's using now."""
        saved = config.get_setting("data_root")
        return str(Path(saved).expanduser()) if saved else str(config.DATA_ROOT)

    def _sync_root_note(self):
        pending = self._pending_root()
        changed = Path(pending) != Path(config.DATA_ROOT)
        self._root_note.setText(
            f"M110 is using {config.DATA_ROOT} until you restart it." if changed else "")
        self._root_note.setVisible(changed)

    def _change_root(self):
        d = QFileDialog.getExistingDirectory(self, "Choose data folder",
                                             self._root_edit.text())
        if not d or d == self._root_edit.text():
            return
        config.save_data_root(d)
        config.ensure_data_root(d)          # create + seed now, ready on restart
        self._root_edit.setText(self._pending_root())
        self._root_edit.setCursorPosition(0)
        self._sync_root_note()
        self._fit()

    # ── Processing ───────────────────────────────────────────────────────────

    def _build_processing(self, lay: QVBoxLayout):
        g = self._group(lay, "Workflows")
        g.addWidget(_line("M110 keeps a working folder ready on each object for "
                          "every workflow you tick."))
        enabled = set(processing.enabled_workflow_ids())
        self._wf_checks: dict[str, QCheckBox] = {}
        for w in processing.WORKFLOWS:
            cb = QCheckBox(w.label if w.available else f"{w.label}  (soon)")
            cb.setChecked(w.available and w.id in enabled)
            cb.setEnabled(w.available)
            if not w.available:
                cb.setToolTip("Support for this workflow is coming.")
            g.addWidget(cb)
            self._wf_checks[w.id] = cb
        # Wire after building so the initial setChecked() can't fire a half-built save.
        for cb in self._wf_checks.values():
            cb.toggled.connect(self._save_workflows)
        g.addWidget(_caption("Siril's holds your subs and a preset tuned to the frame "
                             "count; AstroWizard's holds the subs, the stack you're "
                             "finishing and your exports."))

        # Retention. Every import archives the run it just imported, and those only
        # ever accumulate — measured at 42 GB on a real library — so this is the
        # bound on that growth, and the one place M110 deletes processing history.
        g = self._group(lay, "Processing history")
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Keep the last"))
        self._keep_spin = QSpinBox()
        self._keep_spin.setRange(0, 99)
        self._keep_spin.setSpecialValueText("all")      # 0 reads as "all"
        self._keep_spin.setValue(processing.archive_keep())
        keep_row.addWidget(self._keep_spin)
        keep_row.addWidget(QLabel("processing sessions"))
        keep_row.addStretch(1)
        g.addLayout(keep_row)
        g.addWidget(_caption("Importing finished work archives the run behind it; "
                             "older runs beyond this many are deleted, and the newest "
                             "is always kept."))
        self._keep_spin.valueChanged.connect(processing.set_archive_keep)

        g = self._group(lay, "Finished-image hints")
        g.addWidget(_line("Filename keywords that mark finished work, and by-products "
                          "to skip, when you import."))
        cur = hints.get_hints()
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self._finished_edit = QLineEdit(", ".join(cur["finished"]))
        self._finished_edit.setToolTip(
            "A file whose name contains any of these is treated as finished output.")
        self._intermediate_edit = QLineEdit(", ".join(cur["intermediate"]))
        self._intermediate_edit.setToolTip(
            "A file whose name contains any of these is skipped as a by-product "
            "(e.g. star layers), never imported as finished.")
        grid.addWidget(QLabel("Finished:"), 0, 0)
        grid.addWidget(self._finished_edit, 0, 1)
        grid.addWidget(QLabel("Intermediate:"), 1, 0)
        grid.addWidget(self._intermediate_edit, 1, 1)
        g.addLayout(grid)
        g.addWidget(_caption("Comma-separated; case doesn't matter."))
        self._finished_edit.editingFinished.connect(self._save_hints)
        self._intermediate_edit.editingFinished.connect(self._save_hints)

    def _save_workflows(self, *_):
        """Persist the processing-workflow selection (read at ingest time)."""
        chosen = [wid for wid, cb in self._wf_checks.items()
                  if cb.isEnabled() and cb.isChecked()]
        # Written as an explicit map over every workflow, so one added later can
        # tell "never asked" from "switched off" — see processing.enabled_workflow_ids.
        processing.set_enabled_workflows(chosen)

    def _save_hints(self, *_):
        """Persist the finished/intermediate filename hints (read at classify time)."""
        def _split(text):
            return [t.strip() for t in text.split(",") if t.strip()]
        hints.set_hints(_split(self._finished_edit.text()),
                        _split(self._intermediate_edit.text()))

    # ── Tools ────────────────────────────────────────────────────────────────

    def _build_tools(self, lay: QVBoxLayout):
        g = self._group(lay, "Processing tools")
        g.addWidget(_line("M110 finds these in the usual places. Set a path only if "
                          "one is installed somewhere else."))
        # One row per registered tool, so adding a tool to `launch._TOOLS` gets a
        # path override here without touching this window.
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self._tool_edits: dict[str, QLineEdit] = {}
        self._tool_browse: dict[str, QPushButton] = {}
        for row, tool_id in enumerate(launch.tool_ids()):
            label = launch.tool_label(tool_id)
            edit = QLineEdit(self._tool_override(tool_id))
            detected = self._detect_tool(tool_id)
            kind = "binary" if launch.is_cli(tool_id) else "application"
            edit.setPlaceholderText(
                f"Auto-detected: {detected}" if detected
                else f"Not found — Browse to your {label} {kind}")
            edit.setMinimumWidth(160)
            browse = QPushButton("Browse…")
            # Bind the id per row: a bare closure over the loop variable would give
            # every button the last tool.
            browse.clicked.connect(lambda _=False, t=tool_id: self._browse_tool(t))
            edit.editingFinished.connect(self._save_app_paths)
            grid.addWidget(QLabel(f"{label}:"), row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(browse, row, 2)
            self._tool_edits[tool_id] = edit
            self._tool_browse[tool_id] = browse
        g.addLayout(grid)
        g.addWidget(_caption("Siril opens in the object's working folder. "
                             "AstroWizard can't be pointed at a folder, so M110 opens "
                             "the folder beside it. Stackhammer is the command-line "
                             "stacker m110-stack and the assistant run; left empty, "
                             "M110 uses the one Siril's script names."))

    @staticmethod
    def _detect_tool(tool_id: str) -> str | None:
        """Where auto-detection finds a tool, for the row's placeholder. A CLI
        tool has its own search (Stackhammer: the script installed in Siril,
        the usual install places, PATH)."""
        if tool_id == stackhammer.TOOL_ID:
            found = stackhammer.find_binary()
            return found[0] if found else None
        return launch.find_app(tool_id)

    @staticmethod
    def _tool_override(tool_id: str) -> str:
        paths = config.get_setting(launch.APP_PATHS_SETTING, {}) or {}
        return str(paths.get(tool_id) or "")

    def _browse_tool(self, tool_id: str):
        # .app bundles on macOS (selectable as a file in the native dialog) and
        # plain executables elsewhere.
        label = launch.tool_label(tool_id)
        cli = launch.is_cli(tool_id)
        start = self._tool_edits[tool_id].text() or (
            "/Applications" if sys.platform == "darwin" and not cli else "")
        f, _ = QFileDialog.getOpenFileName(
            self, f"Choose the {label} {'binary' if cli else 'application'}", start)
        if f:
            self._tool_edits[tool_id].setText(f)
            self._save_app_paths()

    def _save_app_paths(self, *_):
        """Persist the external-app path overrides (read at launch time). An empty
        field clears that tool's override → auto-detection."""
        paths = dict(config.get_setting(launch.APP_PATHS_SETTING, {}) or {})
        for tool_id, edit in self._tool_edits.items():
            val = edit.text().strip()
            if val:
                paths[tool_id] = val
            else:
                paths.pop(tool_id, None)
        config.save_setting(launch.APP_PATHS_SETTING, paths)

    # ── Backup ───────────────────────────────────────────────────────────────

    def _build_backup(self, lay: QVBoxLayout):
        from m110.ui.backup_pane import BackupPane
        self._backup = BackupPane(self)
        self._backup.size_changed.connect(
            lambda: self._fit() if self._current == "backup" else None)
        lay.addWidget(self._backup)

    # ── Assistant ────────────────────────────────────────────────────────────
    # The server is plain MCP over stdio, so the framing is client-neutral:
    # "Connection details…" serves everything, and the Claude Desktop button is a
    # convenience because its config is a JSON file we can merge into safely.

    def _build_assistant(self, lay: QVBoxLayout):
        g = self._group(lay, "AI assistant")
        g.addWidget(_line("M110 can act as an <b>MCP server</b>, so an AI assistant "
                          "can read your Library and help you plan a night — but never "
                          "change it."))
        g.addWidget(_caption("Works with any MCP-compatible client. Claude Desktop can "
                             "be set up for you; for anything else use Connection "
                             "details."))
        self._assistant_status = _caption("")
        g.addWidget(self._assistant_status)

        row = QHBoxLayout()
        self._details_btn = QPushButton("Connection Details…")
        self._details_btn.setToolTip(
            "The command, environment and JSON any MCP client needs.")
        self._details_btn.clicked.connect(self._show_connection_details)
        self._connect_btn = QPushButton("Set Up Claude Desktop…")
        self._connect_btn.clicked.connect(self._connect_desktop)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect_desktop)
        row.addWidget(self._details_btn)
        row.addWidget(self._connect_btn)
        row.addWidget(self._disconnect_btn)
        row.addStretch(1)
        g.addLayout(row)

        from m110.assistant.tools.saving import SETTING_DIRECT_SAVE
        g = self._group(lay, "Saving plans")
        self._direct_save_cb = QCheckBox("Let the assistant save plans straight to Plans/")
        self._direct_save_cb.setChecked(
            bool(config.get_setting(SETTING_DIRECT_SAVE, False)))
        self._direct_save_cb.toggled.connect(
            lambda on: config.save_setting(SETTING_DIRECT_SAVE, bool(on)))
        g.addWidget(self._direct_save_cb)
        g.addWidget(_caption("Off, a plan it saves waits for you to accept it here. "
                             "Either way it can only add files, never change or "
                             "delete anything."))
        self._refresh_assistant_status()

    def _refresh_assistant_status(self):
        from m110.assistant import client_config as cc
        ok, why = cc.server_available()
        connected = cc.is_connected()
        if not ok:
            self._assistant_status.setText(why)
        elif connected:
            self._assistant_status.setText(
                "Claude Desktop is set up. Quit and reopen it to pick up changes.")
        else:
            self._assistant_status.setText("Claude Desktop isn't set up yet.")
        self._details_btn.setEnabled(ok)
        self._connect_btn.setEnabled(ok)
        self._connect_btn.setText("Update Claude Desktop…" if connected
                                  else "Set Up Claude Desktop…")
        self._disconnect_btn.setEnabled(ok and connected)

    def _connect_desktop(self):
        from m110.assistant import client_config as cc
        try:
            existing = cc.read_desktop_config()          # refuses to clobber bad JSON
        except cc.ClientConfigError as exc:
            QMessageBox.warning(self, "Can't read Claude Desktop's config", str(exc))
            return

        others = sorted(k for k in (existing.get("mcpServers") or {})
                        if k != cc.SERVER_KEY)
        keep = (f"\n\nYour other configured servers ({', '.join(others)}) are kept."
                if others else "")

        # Show exactly what will be written, and what connecting means, before
        # touching another application's configuration file.
        box = QMessageBox(self)
        box.setWindowTitle("Connect Claude Desktop")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Add M110 to Claude Desktop?\n\n{cc.DISCLOSURE}{keep}")
        box.setInformativeText(f"This will be written to:\n{cc.desktop_config_path()}")
        box.setDetailedText(cc.preview_desktop_json())
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Ok:
            return

        try:
            _path, backup_path = cc.write_desktop_config()
        except cc.ClientConfigError as exc:
            QMessageBox.warning(self, "Couldn't update Claude Desktop", str(exc))
            return

        note = (f"\n\nA backup of the previous config is at:\n{backup_path}"
                if backup_path else "")
        QMessageBox.information(
            self, "Connected",
            f"M110 was added to Claude Desktop.\n\nQuit and reopen Claude Desktop, "
            f"then ask it something like \"what should I shoot tonight?\"{note}")
        self._refresh_assistant_status()

    def _disconnect_desktop(self):
        from m110.assistant import client_config as cc
        if QMessageBox.question(
                self, "Disconnect",
                "Remove M110 from Claude Desktop's configuration?\n\n"
                "Your other configured servers are left alone.") != QMessageBox.Yes:
            return
        try:
            cc.remove_from_desktop_config()
        except cc.ClientConfigError as exc:
            QMessageBox.warning(self, "Couldn't update Claude Desktop", str(exc))
            return
        QMessageBox.information(self, "Disconnected",
                                "M110 was removed. Restart Claude Desktop to apply.")
        self._refresh_assistant_status()

    def _show_connection_details(self):
        """Client-neutral setup info — the server is plain MCP over stdio."""
        from m110.ui.mcp_details_dialog import ConnectionDetailsDialog
        ConnectionDetailsDialog(self).exec()

    # ── Appearance ───────────────────────────────────────────────────────────

    def _build_appearance(self, lay: QVBoxLayout):
        g = self._group(lay, "Theme")
        row = QHBoxLayout()
        row.addWidget(QLabel("Appearance:"))
        self._theme_combo = QComboBox()
        for mode, label in (("system", "Follow System"), ("light", "Light"),
                            ("dark", "Dark"), ("night", "Night Vision")):
            self._theme_combo.addItem(label, mode)
        self._sync_theme_combo()
        # Applied live (no restart); the initial setCurrentIndex is pre-connect.
        self._theme_combo.currentIndexChanged.connect(
            lambda *_: theme.set_mode(self._theme_combo.currentData()))
        row.addWidget(self._theme_combo)
        row.addStretch(1)
        g.addLayout(row)
        keys = QKeySequence("Ctrl+Shift+N").toString(QKeySequence.SequenceFormat.NativeText)
        g.addWidget(_caption("Follow System switches with macOS, Windows or your "
                             "desktop's light and dark setting. Night Vision is red on "
                             f"black for use at the telescope (View › Night Vision, "
                             f"{keys}), with images in dimmed red."))

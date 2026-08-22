"""Preferences dialog — data folder + processing-prep workflows."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QCheckBox, QComboBox, QScrollArea,
    QWidget,
    QSpinBox,
)

from m110 import config, hints, ingest, launch, processing, updates
from m110.ui import theme


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(640, 620)

        from m110.ui.theme import tokens
        s = tokens.SPACE

        # The settings column scrolls. Without this the dialog's natural height
        # exceeds a laptop screen (it has grown a group at a time), and Qt
        # squeezes word-wrapped labels below their heightForWidth — which shows
        # up as explanatory text with its last line sliced off, not as an
        # obviously-too-small window. Close stays pinned outside the scroll area.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        # Never scroll sideways: the content must wrap to the viewport width.
        # Allowed to overflow horizontally, a long data-folder path widens the
        # whole column and every explanatory line gets clipped at the right edge.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        lay = QVBoxLayout(body)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        lay.setSpacing(s["md"])
        folder_note = QLabel("Data folder — where M110 stores its catalog, "
                             "captures, and renders:")
        folder_note.setWordWrap(True)
        lay.addWidget(folder_note)

        row = QHBoxLayout()
        self._edit = QLineEdit(str(config.DATA_ROOT))
        # A deep path would otherwise set the dialog's minimum width.
        self._edit.setMinimumWidth(180)
        self._edit.setCursorPosition(0)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._edit)
        row.addWidget(browse)
        lay.addLayout(row)

        hint = QLabel(f"Default: {config.DEFAULT_DATA_ROOT}\n"
                      "The folder is created (with a starter catalog) if it doesn't exist. "
                      "Changing it applies on Close and takes effect after you restart M110.")
        hint.setProperty("caption", True)
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # ── processing-prep workflows (persist live on toggle) ───────────────
        box = QGroupBox("Processing workflows you use:")
        bl = QVBoxLayout(box)
        wf_note = QLabel(
            "M110 keeps a ready-to-go working folder on each object for every "
            "workflow you tick. Siril's holds your subs and a preset tuned to the "
            "frame count. AstroWizard's holds your subs too — so StackingWizard "
            "can stack them in place — alongside the stack you're finishing and "
            "your exports on the way back into the library.")
        wf_note.setWordWrap(True)
        bl.addWidget(wf_note)
        enabled = set(processing.enabled_workflow_ids())
        self._wf_checks = {}
        for w in processing.WORKFLOWS:
            cb = QCheckBox(w.label if w.available else f"{w.label}  (soon)")
            cb.setChecked(w.available and w.id in enabled)
            cb.setEnabled(w.available)
            if not w.available:
                cb.setToolTip("Support for this workflow is coming.")
            bl.addWidget(cb)
            self._wf_checks[w.id] = cb
        # Wire after building so the initial setChecked() can't fire a half-built save.
        for cb in self._wf_checks.values():
            cb.toggled.connect(self._save_workflows)

        # Retention. Every import archives the run it just imported, and those
        # only ever accumulate — measured at 42 GB on a real library — so this is
        # the bound on that growth. It is the one place M110 deletes processing
        # history, hence the explicit "keep everything" position at 0.
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Keep the last"))
        self._keep_spin = QSpinBox()
        self._keep_spin.setRange(0, 99)
        self._keep_spin.setSpecialValueText("all")      # 0 reads as "all"
        self._keep_spin.setValue(processing.archive_keep())
        self._keep_spin.setFixedWidth(70)
        keep_row.addWidget(self._keep_spin)
        keep_row.addWidget(QLabel("processing sessions"))
        keep_row.addStretch(1)
        bl.addLayout(keep_row)
        keep_note = QLabel(
            "When you import finished work, the run that produced it is archived "
            "inside the object's working folder. Older archived runs beyond this "
            "many are deleted; the most recent is always kept. Set to \u201call\u201d "
            "to keep every run.")
        keep_note.setWordWrap(True)
        keep_note.setProperty("caption", True)
        bl.addWidget(keep_note)
        self._keep_spin.valueChanged.connect(processing.set_archive_keep)

        lay.addWidget(box)

        # ── processing tools (external app paths; persist live) ──────────────
        tbox = QGroupBox("Processing tools")
        tl = QVBoxLayout(tbox)
        tool_note = QLabel(
            "M110 launches these for you and gets out of the way. It finds them "
            "automatically in the usual place — set a path here only if one is "
            "installed somewhere else. Siril opens with the object's working folder "
            "already set as its working directory; AstroWizard can't be pointed at a "
            "folder, so M110 opens the folder alongside it for you to pick the stack "
            "from.")
        tool_note.setWordWrap(True)
        tl.addWidget(tool_note)
        # One row per registered tool, so adding a workflow to `launch._TOOLS` gets
        # a path override here without touching this dialog.
        self._tool_edits: dict[str, QLineEdit] = {}
        for tool_id in launch.tool_ids():
            label = launch.tool_label(tool_id)
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            edit = QLineEdit(self._tool_override(tool_id))
            detected = launch.find_app(tool_id)
            edit.setPlaceholderText(
                f"Auto-detected: {detected}" if detected
                else f"Not found — Browse to your {label} application")
            browse = QPushButton("Browse…")
            # Bind the id per row: a bare closure over the loop variable would give
            # every button the last tool.
            browse.clicked.connect(lambda _=False, t=tool_id: self._browse_tool(t))
            edit.editingFinished.connect(self._save_app_paths)
            row.addWidget(edit, 1)
            row.addWidget(browse)
            tl.addLayout(row)
            self._tool_edits[tool_id] = edit
        lay.addWidget(tbox)

        # ── finished-image hints (persist live on edit) ──────────────────────
        hbox = QGroupBox("Finished-image hints")
        hl = QVBoxLayout(hbox)
        hint_note = QLabel(
            "When importing processed work, M110 recognizes finished renders/stacks "
            "and skips intermediate by-products by keywords in the filename "
            "(case-insensitive, comma-separated).")
        hint_note.setWordWrap(True)
        hl.addWidget(hint_note)
        cur_hints = hints.get_hints()
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Finished:"))
        self._finished_edit = QLineEdit(", ".join(cur_hints["finished"]))
        self._finished_edit.setToolTip(
            "A file whose name contains any of these is treated as finished output.")
        frow.addWidget(self._finished_edit, 1)
        hl.addLayout(frow)
        irow = QHBoxLayout()
        irow.addWidget(QLabel("Intermediate:"))
        self._intermediate_edit = QLineEdit(", ".join(cur_hints["intermediate"]))
        self._intermediate_edit.setToolTip(
            "A file whose name contains any of these is skipped as a by-product "
            "(e.g. star layers), never imported as finished.")
        irow.addWidget(self._intermediate_edit, 1)
        hl.addLayout(irow)
        # Persist live on edit (mirrors the workflows; read at classify time).
        self._finished_edit.editingFinished.connect(self._save_hints)
        self._intermediate_edit.editingFinished.connect(self._save_hints)
        lay.addWidget(hbox)

        # ── import options (persist live) ────────────────────────────────────
        ibox = QGroupBox("Import")
        il = QVBoxLayout(ibox)
        self._sub_previews_cb = QCheckBox(
            "Import per-sub JPG previews into a previews/ folder")
        self._sub_previews_cb.setToolTip(
            "The Seestar saves a full-size .jpg beside every raw sub. Off by default; "
            "when on, they're archived under Images/<object>/previews/ (kept out of the "
            "raw lights/ and out of the gallery).")
        self._sub_previews_cb.setChecked(
            bool(config.get_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, False)))
        self._sub_previews_cb.toggled.connect(
            lambda on: config.save_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, bool(on)))
        il.addWidget(self._sub_previews_cb)
        lay.addWidget(ibox)

        # ── appearance (theme) ───────────────────────────────────────────────
        appearance = QGroupBox("Appearance")
        al = QHBoxLayout(appearance)
        al.addWidget(QLabel("Theme:"))
        self._theme_combo = QComboBox()
        for mode, label in (("system", "Follow system"), ("light", "Light"),
                            ("dark", "Dark")):
            self._theme_combo.addItem(label, mode)
        cur = config.get_setting(theme.SETTING_KEY, "system")
        idx = self._theme_combo.findData(cur)
        self._theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        # Apply live as the user changes it (no restart; mirrors the workflows).
        self._theme_combo.currentIndexChanged.connect(
            lambda *_: theme.set_mode(self._theme_combo.currentData()))
        al.addWidget(self._theme_combo, 1)
        lay.addWidget(appearance)

        # ── updates (persist live) ───────────────────────────────────────────
        ubox = QGroupBox("Updates")
        ul = QVBoxLayout(ubox)
        self._update_cb = QCheckBox("Check for updates on launch")
        self._update_cb.setToolTip(
            "Once a day at most, M110 checks GitHub for a newer release and shows "
            "a dismissible banner if one is available. No data is sent.")
        self._update_cb.setChecked(updates.check_enabled())
        self._update_cb.toggled.connect(
            lambda on: updates.set_check_enabled(bool(on)))
        ul.addWidget(self._update_cb)
        lay.addWidget(ubox)

        # ── AI assistant (any MCP client) ───────────────────────────────────
        # The server is plain MCP over stdio, so the framing here is
        # client-neutral: "Connection details…" serves everything, and the
        # Claude Desktop button is a convenience because its config is a JSON
        # file we can merge into safely — not because it's the only option.
        abox = QGroupBox("AI assistant")
        al2 = QVBoxLayout(abox)
        blurb = QLabel(
            "M110 can act as an <b>MCP server</b>, so an AI assistant can read your "
            "library and help you plan a night, explain the priority ranking, or "
            "critique an image — grounded in your own data. It can hand you a plan "
            "or suggest a change, but it can never alter your library.")
        blurb.setWordWrap(True)
        al2.addWidget(blurb)

        works_with = QLabel(
            "Works with any MCP-compatible client. Claude Desktop can be set up for "
            "you; for anything else use Connection details.")
        works_with.setProperty("caption", True)
        works_with.setWordWrap(True)
        al2.addWidget(works_with)

        self._assistant_status = QLabel()
        self._assistant_status.setProperty("caption", True)
        self._assistant_status.setWordWrap(True)
        al2.addWidget(self._assistant_status)

        arow = QHBoxLayout()
        self._details_btn = QPushButton("Connection details…")
        self._details_btn.setToolTip(
            "The command, environment and JSON any MCP client needs.")
        self._details_btn.clicked.connect(self._show_connection_details)
        self._connect_btn = QPushButton("Set up Claude Desktop…")
        self._connect_btn.clicked.connect(self._connect_desktop)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect_desktop)
        arow.addWidget(self._details_btn)
        arow.addWidget(self._connect_btn)
        arow.addWidget(self._disconnect_btn)
        arow.addStretch(1)
        al2.addLayout(arow)

        from m110.assistant.tools.saving import SETTING_DIRECT_SAVE
        self._direct_save_cb = QCheckBox("Let the assistant save plans straight to Plans/")
        self._direct_save_cb.setToolTip(
            "Off (default): a plan the assistant saves waits for you to accept it in "
            "M110.\nOn: it goes straight into your Plans folder.\n\nEither way the "
            "assistant can only ADD files — it can never change or delete anything.")
        self._direct_save_cb.setChecked(
            bool(config.get_setting(SETTING_DIRECT_SAVE, False)))
        self._direct_save_cb.toggled.connect(
            lambda on: config.save_setting(SETTING_DIRECT_SAVE, bool(on)))
        al2.addWidget(self._direct_save_cb)
        lay.addWidget(abox)
        self._refresh_assistant_status()

        # Goals (catalogs / custom lists) are managed on the Goals page, not here.

        # Settings here persist live (workflows + theme); only the data folder is
        # applied on Close (it needs a restart), so a single Close button suffices
        # — no "Save" (#62).
        lay.addStretch(1)

        btns = QHBoxLayout()
        btns.setContentsMargins(s["lg"], s["sm"], s["lg"], s["lg"])
        btns.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self._close)
        btns.addWidget(close)
        outer.addLayout(btns)

    # ── AI assistant ─────────────────────────────────────────────────────────

    def _refresh_assistant_status(self):
        from m110.assistant import client_config as cc
        ok, why = cc.server_available()
        path = cc.desktop_config_path()
        connected = cc.is_connected()

        if not ok:
            self._assistant_status.setText(why)
        elif connected:
            self._assistant_status.setText(
                "Claude Desktop is set up. Quit and reopen it to pick up changes.")
        else:
            # The line above already points at Connection details; don't repeat it.
            self._assistant_status.setText("Claude Desktop isn't set up yet.")

        self._details_btn.setEnabled(ok)
        self._connect_btn.setEnabled(ok)
        self._connect_btn.setText("Update Claude Desktop…" if connected
                                  else "Set up Claude Desktop…")
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
            path, backup = cc.write_desktop_config()
        except cc.ClientConfigError as exc:
            QMessageBox.warning(self, "Couldn't update Claude Desktop", str(exc))
            return

        note = f"\n\nA backup of the previous config is at:\n{backup}" if backup else ""
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

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose data folder", self._edit.text())
        if d:
            self._edit.setText(d)

    def _save_workflows(self, *_):
        """Persist the processing-workflow selection immediately (read at ingest
        time — no restart)."""
        chosen = [wid for wid, cb in self._wf_checks.items()
                  if cb.isEnabled() and cb.isChecked()]
        # Written as an explicit map over every workflow, so one added later can
        # tell "never asked" from "switched off" — see processing.enabled_workflow_ids.
        processing.set_enabled_workflows(chosen)

    def _tool_override(self, tool_id: str) -> str:
        paths = config.get_setting(launch.APP_PATHS_SETTING, {}) or {}
        return str(paths.get(tool_id) or "")

    def _browse_tool(self, tool_id: str):
        # These are .app bundles on macOS (selectable as a file in the native
        # dialog) and plain executables elsewhere.
        import sys
        label = launch.tool_label(tool_id)
        start = self._tool_edits[tool_id].text() or (
            "/Applications" if sys.platform == "darwin" else "")
        f, _ = QFileDialog.getOpenFileName(
            self, f"Choose the {label} application", start)
        if f:
            self._tool_edits[tool_id].setText(f)
            self._save_app_paths()

    def _save_app_paths(self, *_):
        """Persist the external-app path overrides (read at launch time — no
        restart). An empty field clears that tool's override → auto-detection."""
        paths = dict(config.get_setting(launch.APP_PATHS_SETTING, {}) or {})
        for tool_id, edit in self._tool_edits.items():
            val = edit.text().strip()
            if val:
                paths[tool_id] = val
            else:
                paths.pop(tool_id, None)
        config.save_setting(launch.APP_PATHS_SETTING, paths)

    def _save_hints(self, *_):
        """Persist the finished/intermediate filename hints (read at classify
        time — no restart)."""
        def _split(text):
            return [t.strip() for t in text.split(",") if t.strip()]
        hints.set_hints(_split(self._finished_edit.text()),
                        _split(self._intermediate_edit.text()))

    def _close(self):
        """Apply a data-folder change (if any) on the way out, then close.
        Workflows + theme were already persisted live."""
        path = self._edit.text().strip()
        if path and path != str(config.DATA_ROOT):
            config.save_data_root(path)
            config.ensure_data_root(path)   # create + seed now, ready on restart
            QMessageBox.information(
                self, "Restart needed",
                f"Data folder set to:\n{path}\n\nRestart M110 to use it.")
        self.accept()

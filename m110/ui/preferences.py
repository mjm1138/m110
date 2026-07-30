"""Preferences dialog — data folder + processing-prep workflows."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QCheckBox, QComboBox,
)

from m110 import config, hints, ingest, launch, processing, updates
from m110.ui import theme


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(620, 340)

        from m110.ui.theme import tokens
        s = tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        lay.setSpacing(s["md"])
        lay.addWidget(QLabel("Data folder — where M110 stores its catalog, "
                             "captures, and renders:"))

        row = QHBoxLayout()
        self._edit = QLineEdit(str(config.DATA_ROOT))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._edit)
        row.addWidget(browse)
        lay.addLayout(row)

        hint = QLabel(f"Default: {config.DEFAULT_DATA_ROOT}\n"
                      "The folder is created (with a starter catalog) if it doesn't exist. "
                      "Changing it applies on Close and takes effect after you restart M110.")
        hint.setProperty("caption", True)
        lay.addWidget(hint)

        # ── processing-prep workflows (persist live on toggle) ───────────────
        box = QGroupBox("Prepare objects for processing in:")
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel(
            "M110 sets up a ready-to-go working folder for each object as you "
            "ingest it — pick your stacking app(s)."))
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
        lay.addWidget(box)

        # ── processing tools (external app paths; persist live) ──────────────
        tbox = QGroupBox("Processing tools")
        tl = QVBoxLayout(tbox)
        tl.addWidget(QLabel(
            "“Process in Siril” launches Siril with the object's working "
            "folder set as its working directory. M110 finds Siril automatically in "
            "the usual place — set a path here only if it's installed elsewhere."))
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Siril:"))
        self._siril_edit = QLineEdit(self._siril_override())
        detected = launch.find_app("siril")
        self._siril_edit.setPlaceholderText(
            f"Auto-detected: {detected}" if detected
            else "Not found — Browse to your Siril application")
        sbrowse = QPushButton("Browse…")
        sbrowse.clicked.connect(self._browse_siril)
        srow.addWidget(self._siril_edit, 1)
        srow.addWidget(sbrowse)
        tl.addLayout(srow)
        self._siril_edit.editingFinished.connect(self._save_app_paths)
        lay.addWidget(tbox)

        # ── finished-image hints (persist live on edit) ──────────────────────
        hbox = QGroupBox("Finished-image hints")
        hl = QVBoxLayout(hbox)
        hl.addWidget(QLabel(
            "When importing processed work, M110 recognizes finished renders/stacks "
            "and skips intermediate by-products by keywords in the filename "
            "(case-insensitive, comma-separated)."))
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

        # ── AI assistant (connect an external MCP client) ────────────────────
        abox = QGroupBox("AI assistant")
        al2 = QVBoxLayout(abox)
        blurb = QLabel(
            "Connect Claude Desktop or Claude Code to M110 and ask it to plan a "
            "night, explain the priority ranking, or critique an image. The "
            "connection is read-only — it can look and suggest, never change "
            "your library.")
        blurb.setWordWrap(True)
        al2.addWidget(blurb)

        self._assistant_status = QLabel()
        self._assistant_status.setProperty("caption", True)
        self._assistant_status.setWordWrap(True)
        al2.addWidget(self._assistant_status)

        arow = QHBoxLayout()
        self._connect_btn = QPushButton("Connect Claude Desktop…")
        self._connect_btn.clicked.connect(self._connect_desktop)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect_desktop)
        copy_cli = QPushButton("Copy Claude Code command")
        copy_cli.clicked.connect(self._copy_cli_command)
        arow.addWidget(self._connect_btn)
        arow.addWidget(self._disconnect_btn)
        arow.addWidget(copy_cli)
        arow.addStretch(1)
        al2.addLayout(arow)
        lay.addWidget(abox)
        self._refresh_assistant_status()

        # Goals (catalogs / custom lists) are managed on the Goals page, not here.

        # Settings here persist live (workflows + theme); only the data folder is
        # applied on Close (it needs a restart), so a single Close button suffices
        # — no "Save" (#62).
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self._close)
        btns.addWidget(close)
        lay.addLayout(btns)

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
                f"Connected to Claude Desktop. Restart Claude Desktop if you've "
                f"just connected.\nConfig: {path}")
        else:
            self._assistant_status.setText(f"Not connected.\nConfig would be: {path}")

        self._connect_btn.setEnabled(ok)
        self._connect_btn.setText("Update Claude Desktop…" if connected
                                  else "Connect Claude Desktop…")
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

    def _copy_cli_command(self):
        from PySide6.QtWidgets import QApplication
        from m110.assistant import client_config as cc
        cmd = cc.cli_add_command()
        QApplication.clipboard().setText(cmd)
        QMessageBox.information(
            self, "Copied",
            f"Run this in a terminal to connect Claude Code:\n\n{cmd}\n\n"
            f"{cc.DISCLOSURE}")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose data folder", self._edit.text())
        if d:
            self._edit.setText(d)

    def _save_workflows(self, *_):
        """Persist the processing-workflow selection immediately (read at ingest
        time — no restart)."""
        chosen = [wid for wid, cb in self._wf_checks.items()
                  if cb.isEnabled() and cb.isChecked()]
        config.save_setting(processing.SETTING_KEY, chosen)

    def _siril_override(self) -> str:
        paths = config.get_setting(launch.APP_PATHS_SETTING, {}) or {}
        return str(paths.get("siril") or "")

    def _browse_siril(self):
        # Siril is an .app bundle on macOS (selectable as a file in the native
        # dialog) and a plain executable elsewhere.
        import sys
        start = self._siril_edit.text() or (
            "/Applications" if sys.platform == "darwin" else "")
        f, _ = QFileDialog.getOpenFileName(self, "Choose the Siril application", start)
        if f:
            self._siril_edit.setText(f)
            self._save_app_paths()

    def _save_app_paths(self, *_):
        """Persist the external-app path override (read at launch time — no
        restart). Empty clears the override → back to auto-detection."""
        paths = dict(config.get_setting(launch.APP_PATHS_SETTING, {}) or {})
        val = self._siril_edit.text().strip()
        if val:
            paths["siril"] = val
        else:
            paths.pop("siril", None)
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

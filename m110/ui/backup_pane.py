"""Settings › Backup — two backup slots (a local drive and the cloud), each
snapshotting the store to its own destination on a worker thread.

A summary of both slots sits on top, then a Local drive | Cloud segmented control
over one slot's settings. The Cloud slot is always one click away, even
unconfigured: it used to be reachable only by typing `s3://` into the one
destination field, and people who knew the feature existed still didn't find it —
while the guide recommended exactly the both-at-once pattern ("Everything to a
local drive, Essentials to the cloud") that one destination couldn't automate.

UI Phase 8 · E folded the old Back up dialog into the Settings window, so there is
no Save: **every field persists when it's committed** (a toggle, a combo, a spin
step, a text field on Return or focus-out), through `backup.update_slot`, which
writes only that slot's own keys. A destination is saved only when it's non-empty
and valid for its slot; otherwise the status line says why and nothing is written.

A `_BackupWorker` (QThread) emits progress/done/failed, a `threading.Event` backs
Cancel, workers are torn down when the Settings window closes.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from m110.ui.widgets import drain_worker, make_segment, ProgressDialog
from m110 import backup, config

LOCAL, CLOUD = backup.SLOT_LOCAL, backup.SLOT_CLOUD

TAB_LABELS = {LOCAL: "Local drive", CLOUD: "Cloud"}

INTRO = "Keep one copy on a local drive and another offsite in the cloud."
INTRO_HELP = ("Only what changed is stored each time, and every backup can be "
              "restored on its own.")

# The providers, named. "S3" alone reads as "Amazon only" to most people, and the
# cheaper S3-compatible services are exactly the ones a hobbyist would pick.
PROVIDERS = "Amazon S3, Backblaze B2, Cloudflare R2, Wasabi"

CLOUD_INTRO = f"Keep an offsite copy in {PROVIDERS}, or any S3-compatible storage."
CLOUD_INTRO_HELP = (
    "Essentials — everything except your raw light frames — is usually a few "
    "percent of your Library, so it uploads quickly and costs little to keep.")

# Written for a bucket rather than assembled from the pooled blurb. Concatenating
# them said "stored once, named by its contents" twice and then finished with "a
# browsable copy of the newest backup is kept alongside" — which is exactly what
# object storage cannot do, since that copy is a hardlink tree.
CLOUD_FORMAT_NOTE = (
    "Files are stored once, named by their contents, and each backup is a small "
    "index of what it contains — so after the first backup only new files upload. "
    "Every backup can be restored on its own, and M110 keeps a plain-Python "
    "restore script beside them so you can get your files back without it.")


def _fmt_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit in ("B", "KB") else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


def _ago(when: datetime, now: datetime | None = None) -> str:
    secs = ((now or datetime.now()) - when).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 48 * 3600:
        return f"{int(secs // 3600)} h ago"
    if secs < 30 * 86400:
        return f"{int(secs // 86400)} days ago"
    return f"on {when:%Y-%m-%d}"


class _ProbeWorker(QThread):
    """Inspect a destination off the GUI thread.

    `backup.probe_destination` stats the volume, link-probes the filesystem and
    reads every existing manifest — seconds on a slow share, and indefinite on a
    dead SMB mount. Running it inline (as the status line used to, on every
    keystroke) froze the dialog."""
    probed = Signal(object)     # backup.DestinationInfo

    def __init__(self, dest: str, parent=None):
        super().__init__(parent)
        self._dest = dest

    def run(self):
        try:
            self.probed.emit(backup.probe_destination(self._dest))
        except Exception as exc:  # pragma: no cover - defensive
            self.probed.emit(backup.DestinationInfo(
                path=None, exists=False, writable=False, hardlinks=False,
                free_bytes=None, snapshot_count=0, destination=self._dest,
                error=f"{type(exc).__name__}: {exc}"))


class _BackupWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, options, cancel_event, parent=None):
        super().__init__(parent)
        self._options = options
        self._cancel = cancel_event

    def run(self):
        try:
            res = backup.create_snapshot(
                self._options, should_cancel=self._cancel.is_set,
                progress=lambda i, t: self.progressed.emit(i, t))
            self.done.emit(res)
        except backup.BackupError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _SlotPanel(QWidget):
    """Everything about one slot: destination, format (local only), cloud
    credentials (cloud only), scope, automation and retention. Each control
    persists on commit and writes only its own slot (`_commit`); the pane's Back
    Up Now runs it (`_do_backup`)."""
    changed = Signal()          # something the summary shows may have moved
    busy = Signal(bool)         # a backup is running (the pane disables Back Up Now)
    backed_up = Signal(dict)

    def __init__(self, slot: str, parent=None):
        super().__init__(parent)
        self.slot = slot
        self._is_cloud_slot = slot == CLOUD
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self._probe_worker = None
        self._probe_cache: dict[str, object] = {}
        saved = backup.load_slot(slot)
        self._saved_scope = saved.scope

        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s["sm"])

        if self._is_cloud_slot:
            intro = QLabel(CLOUD_INTRO)
            intro.setWordWrap(True)
            layout.addWidget(intro)
            intro_help = QLabel(CLOUD_INTRO_HELP)
            intro_help.setProperty("caption", True)
            intro_help.setWordWrap(True)
            layout.addWidget(intro_help)

        # ── destination ──
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destination:"))
        self._dest = QLineEdit(saved.destination)
        self._dest.setPlaceholderText(
            "s3://your-bucket/m110-backups" if self._is_cloud_slot
            else "An external drive, network share, or folder")
        # Save + probe on commit, not per keystroke — see _ProbeWorker.
        self._dest.editingFinished.connect(self._commit_destination)
        dest_row.addWidget(self._dest, 1)
        if not self._is_cloud_slot:
            browse = QPushButton("Browse…")
            browse.clicked.connect(self._browse)
            dest_row.addWidget(browse)
        layout.addLayout(dest_row)

        self._status = QLabel()
        self._status.setProperty("muted", True)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # ── format ──  (a property of the destination, so it sits with it.) A
        # bucket has no choice to make, so the cloud slot just says what it is.
        self._format = None
        if not self._is_cloud_slot:
            fmt_row = QHBoxLayout()
            fmt_row.addWidget(QLabel("Backups are stored as:"))
            self._format = QComboBox()
            for fid in backup.FORMATS:
                self._format.addItem(backup.FORMAT_LABELS[fid], fid)
            self._select_format(saved.format)
            self._format.currentIndexChanged.connect(self._on_format_changed)
            # `_select_format` blocks signals, so only a user's pick is saved here.
            self._format.currentIndexChanged.connect(
                lambda *_: self._commit(format=self._current_format()))
            fmt_row.addWidget(self._format, 1)
            layout.addLayout(fmt_row)

        self._format_note = QLabel()
        self._format_note.setProperty("caption", True)
        self._format_note.setWordWrap(True)
        layout.addWidget(self._format_note)
        self._on_format_changed()

        # ── cloud credentials ──
        if self._is_cloud_slot:
            self._cloud_box = self._build_cloud_box(s)
            layout.addWidget(self._cloud_box)

        # ── scope ──  (what goes to this destination)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Back up:"))
        self._scope = QComboBox()
        for sid in backup.SCOPES:
            self._scope.addItem(backup.SCOPE_LABELS[sid], sid)
        self._select_scope(saved.scope)
        self._scope.currentIndexChanged.connect(self._on_scope_changed)
        self._scope.currentIndexChanged.connect(
            lambda *_: self._commit(scope=self._current_scope()))
        scope_row.addWidget(self._scope, 1)
        layout.addLayout(scope_row)

        self._scope_note = QLabel()
        self._scope_note.setProperty("caption", True)
        self._scope_note.setWordWrap(True)
        layout.addWidget(self._scope_note)

        # ── automation + retention ──
        # "&&" renders one literal ampersand: Qt reads a single "&" in a QGroupBox
        # title as a mnemonic marker, so "Automation & retention" displayed as
        # "Automation  retention" with the R underlined.
        settings_box = QGroupBox("Automation && retention")
        sl = QVBoxLayout(settings_box)
        auto_row = QHBoxLayout()
        self._auto = QCheckBox("Back up automatically")
        self._auto.setChecked(saved.auto)
        self._auto.setToolTip(
            "Backs up in the background: at launch if the last one is older than the "
            "interval below, and daily at 02:00 while the app stays running.")
        auto_row.addWidget(self._auto)
        auto_row.addStretch(1)
        sl.addLayout(auto_row)

        auto_hint = QLabel("Runs at launch and daily at 02:00 while the app is open.")
        auto_hint.setProperty("caption", True)
        auto_hint.setWordWrap(True)
        sl.addWidget(auto_hint)

        # One grid, not independent QHBoxLayouts: independent rows gave each label
        # its own width, so the fields started at different x and had different
        # widths. A shared label column lines them up.
        grid = QGridLayout()
        grid.setHorizontalSpacing(s["sm"])
        grid.setVerticalSpacing(s["xs"])
        grid.setColumnStretch(3, 1)               # trailing space absorbs the slack

        self._interval = QSpinBox()
        self._interval.setRange(1, 24 * 30)
        self._interval.setSuffix(" h")
        self._interval.setValue(int(saved.interval_hours))

        self._keep = QSpinBox()
        self._keep.setRange(0, 999)
        self._keep.setSpecialValueText("all")     # 0 → "all" (no limit)
        self._keep.setValue(saved.retention_keep)

        rows = [("…at most once every", self._interval, ""),
                ("Keep newest", self._keep, "backups")]
        # A bucket has no volume to run out of, so the engine skips this rule and
        # the cloud slot has no control implying a policy that won't run.
        self._min_free = None
        if not self._is_cloud_slot:
            self._min_free = QDoubleSpinBox()
            self._min_free.setRange(0.0, 1_000_000.0)
            self._min_free.setDecimals(0)
            self._min_free.setSpecialValueText("off")     # 0 → disabled
            self._min_free.setToolTip("Prune the oldest backups to maintain this "
                                      "much free space on the destination. 0 = off.")
            self._min_free.setValue(float(saved.min_free_gb))
            rows.append(("Keep at least", self._min_free,
                         "GB free on the destination volume"))
        spins = [field for _, field, _ in rows]
        for row, (label, field, suffix) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(field, row, 1)
            if suffix:
                grid.addWidget(QLabel(suffix), row, 2)
        # One width for all, from the widest — `min_free` used to carry a hardcoded
        # 90px that was 18px BELOW its own sizeHint, so it clipped at large values.
        field_w = max(w.sizeHint().width() for w in spins)
        for w in spins:
            w.setFixedWidth(field_w)
        sl.addLayout(grid)
        layout.addWidget(settings_box)

        self._wire_commits()
        self._on_scope_changed()
        self._refresh_status()

    # ---- what the summary reads ----
    def destination(self) -> str:
        return self._dest.text().strip()

    def auto_enabled(self) -> bool:
        return self._auto.isChecked()

    def last_backup(self) -> datetime | None:
        """Newest known backup: what the probe found at the destination when it
        has run, else the time the slot recorded after its last run. The probe
        wins because it's the truth at the destination; the record is what makes
        a cloud slot's summary possible without a network call on open."""
        info = self._probe_cache.get(self.destination())
        if info is not None and getattr(info, "newest", None) is not None:
            return info.newest.created
        return backup.load_slot(self.slot).last_backup

    # ---- cloud credentials ----
    def _build_cloud_box(self, s) -> QGroupBox:
        """Endpoint, region and keys for an S3-compatible destination.

        The **secret** key is never displayed, not even masked: the field starts
        empty with a placeholder saying one is already saved, and an empty field
        means "leave it alone" rather than "clear it". Reading the secret back out
        of the keyring just to repaint it as dots would put it in the process for
        no benefit the user can see."""
        box = QGroupBox("Cloud storage")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(s["sm"])
        grid.setVerticalSpacing(s["xs"])
        grid.setColumnStretch(1, 1)

        self._s3_endpoint = QLineEdit(
            str(config.get_setting(backup.SETTING_S3_ENDPOINT, "") or ""))
        self._s3_endpoint.setPlaceholderText("Leave blank for Amazon S3")
        self._s3_endpoint.setToolTip(
            "The API URL of your provider. This is what makes Backblaze B2, "
            "Cloudflare R2 and Wasabi work — they speak the same protocol at a "
            "different address.")
        self._s3_region = QLineEdit(
            str(config.get_setting(backup.SETTING_S3_REGION, "") or ""))
        self._s3_region.setPlaceholderText("e.g. us-east-1")
        self._s3_access = QLineEdit(
            str(config.get_setting(backup.SETTING_S3_ACCESS_KEY, "") or ""))
        self._s3_access.setPlaceholderText("Access key ID")
        self._s3_secret = QLineEdit()
        self._s3_secret.setEchoMode(QLineEdit.Password)
        self._sync_secret_placeholder()

        for row, (label, field) in enumerate((
                ("Endpoint URL:", self._s3_endpoint),
                ("Region:", self._s3_region),
                ("Access key ID:", self._s3_access),
                ("Secret key:", self._s3_secret))):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(field, row, 1)

        # Cloud destinations are checked on request rather than on blur. A probe
        # has to use the credentials in these boxes, and the only way to give them
        # to it is to save them — so an automatic probe would write the user's keys
        # to the keyring as a side effect of clicking out of a field. An explicit
        # button keeps both the network call and the save where the user put them.
        self._test_btn = QPushButton("Test connection")
        self._test_btn.clicked.connect(self._test_cloud)
        grid.addWidget(self._test_btn, 4, 1, alignment=Qt.AlignLeft)

        note = QLabel("Your secret key is stored in your operating system's "
                      "keyring, never in M110's settings file. Leave the fields "
                      "blank to use credentials you've already configured for the "
                      "AWS command line.")
        note.setProperty("caption", True)
        note.setWordWrap(True)
        grid.addWidget(note, 5, 0, 1, 2)
        self._s3_access.textChanged.connect(self._sync_secret_placeholder)
        return box

    def _test_cloud(self):
        """Save the cloud credentials, then probe with them."""
        self._persist_cloud_settings()
        self._sync_secret_placeholder()
        self._refresh_status(force=True)

    def _sync_secret_placeholder(self, *_):
        """Say whether a key is already saved for *this* access key id, so
        switching key ids doesn't imply the old secret came along."""
        from m110.backup.backends import s3 as s3backend
        saved = bool(s3backend.get_secret(self._s3_access.text().strip()))
        self._s3_secret.setPlaceholderText(
            "Saved — leave blank to keep it" if saved else "Secret access key")

    # ---- scope ----
    def _current_scope(self) -> str:
        return self._scope.currentData() or backup.DEFAULT_SCOPE

    def _select_scope(self, scope: str):
        idx = self._scope.findData(scope)
        if idx >= 0:
            blocked = self._scope.blockSignals(True)
            self._scope.setCurrentIndex(idx)
            self._scope.blockSignals(blocked)

    def _on_scope_changed(self, *_args):
        """Describe the tier, and — when it's a narrowing — say what that means
        for backups that already exist.

        Nothing disappears at the moment of narrowing: the object sweep marks from
        every surviving manifest, so the frames stay referenced until retention
        prunes the older, wider backups. Saying so is the difference between a user
        understanding a delayed change and discovering it."""
        scope = self._current_scope()
        note = backup.SCOPE_BLURBS[scope]
        # Only for a real narrowing of *this* slot. Essentials is the cloud slot's
        # default, and warning about existing backups there — before it has any —
        # reads as though something is about to be lost.
        if (scope == backup.SCOPE_ESSENTIALS
                and self._saved_scope == backup.SCOPE_EVERYTHING):
            note += ("  Backups you already have keep their light frames until "
                     "they're pruned by the retention settings below.")
        self._scope_note.setText(note)

    # ---- persist on commit ----
    def _wire_commits(self):
        """The controls that save themselves. The destination, format and scope
        are wired where they're built (each has its own rule); these are the
        plain values. Spin boxes save per step: there is no "finished" for an
        arrow click, and a settings write is cheap."""
        self._auto.toggled.connect(lambda on: self._commit(auto=bool(on)))
        self._interval.valueChanged.connect(
            lambda v: self._commit(interval_hours=int(v)))
        self._keep.valueChanged.connect(lambda v: self._commit(retention_keep=int(v)))
        if self._min_free is not None:
            # 0 is stored explicitly ("off") rather than falling back to the default.
            self._min_free.valueChanged.connect(
                lambda v: self._commit(min_free_gb=float(v)))
        if self._is_cloud_slot:
            for field in (self._s3_endpoint, self._s3_region, self._s3_access):
                field.editingFinished.connect(self._persist_cloud_fields)
            # The secret is committed when the user leaves the field (or presses
            # Return) — then cleared, so it is never left sitting in a widget.
            self._s3_secret.editingFinished.connect(self._persist_secret)

    def _commit(self, **changes):
        """Write these fields of this slot only — `update_slot` leaves the rest,
        notably the last-backup time a run stamps, and the other slot alone."""
        backup.update_slot(self.slot, **changes)
        self.changed.emit()

    def _commit_destination(self):
        """Save the destination when it's real, then describe it.

        Never let an empty field erase a configured destination: it's a path the
        user chose once and may not remember, and losing it silently disables
        their backups. An empty box means "not entered", not "clear it". A
        destination in the wrong slot (a bucket on Local drive) isn't saved; the
        status line says why."""
        dest = self.destination()
        if dest and self.validation_error() is None:
            try:
                backup.parse_destination(dest)
            except backup.BackupError as exc:
                self._status.setText(f"⚠ {exc}")
                return
            if dest != backup.load_slot(self.slot).destination:
                self._commit(destination=dest)
        self._refresh_status()

    # ---- helpers ----
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose backup destination",
                                             self._dest.text() or str(Path.home()))
        if d:
            self._dest.setText(d)
            self._commit_destination()

    def validation_error(self) -> str | None:
        return backup.check_slot_destination(self.slot, self.destination())

    def _refresh_status(self, *, force: bool = False):
        """Probe the destination on a worker and describe it. Results are memoized
        per path for the dialog's lifetime; `force=True` re-probes (after a run)."""
        dest = self.destination()
        if not dest:
            self._status.setText(
                "Enter a bucket address, add your keys below, then choose Test "
                "connection." if self._is_cloud_slot else
                "Choose a destination folder — an external drive or network share.")
            self.changed.emit()
            return
        err = self.validation_error()
        if err:
            self._status.setText(f"⚠ {err}")
            return
        if self._is_cloud_slot and not force and dest not in self._probe_cache:
            # Never reach for the network just because a field lost focus.
            self._status.setText("Enter your cloud details, then choose "
                                 "Test connection.")
            return
        if force:
            self._probe_cache.pop(dest, None)
        cached = self._probe_cache.get(dest)
        if cached is not None:
            self._show_destination(cached)
            return
        self._status.setText("Checking destination…")
        self._stop_probe()
        self._probe_worker = _ProbeWorker(dest, self)
        self._probe_worker.probed.connect(self._on_probed)
        self._probe_worker.start()

    # ---- format ----
    def _current_format(self) -> str:
        if self._format is None:
            return backup.FORMAT_POOLED
        return self._format.currentData() or backup.DEFAULT_FORMAT

    def _select_format(self, fmt: str):
        idx = self._format.findData(fmt)
        if idx >= 0:
            blocked = self._format.blockSignals(True)
            self._format.setCurrentIndex(idx)
            self._format.blockSignals(blocked)

    def _on_format_changed(self, *_args):
        self._format_note.setText(
            CLOUD_FORMAT_NOTE if self._format is None
            else backup.FORMAT_BLURBS[self._current_format()])

    def _apply_format(self, info):
        """Reflect what this destination actually allows.

        A destination that can't share files leaves no choice — mirrored backups
        there would each be a full copy of the Library — so the choice is made and
        persisted rather than left as a trap the user discovers a month later."""
        if self._format is None:
            return                  # a bucket: pooled is simply what it is
        self._format.setEnabled(not info.format_forced)
        self._select_format(info.format)
        self._on_format_changed()
        if info.format_forced:
            backup.update_slot(LOCAL, format=info.format)
            self._format_note.setText(
                "This destination can't share files between backups, so M110 will "
                "use pooled backups here. " + backup.FORMAT_BLURBS[info.format])
        elif info.detected_format and info.detected_format != info.format:
            self._format_note.setText(
                f"{backup.FORMAT_BLURBS[info.format]}  This destination already has "
                f"{backup.FORMAT_LABELS[info.detected_format].lower()}; those stay "
                "restorable either way.")

    def _on_probed(self, info):
        # Keyed on the destination *string*, not `info.path` — a cloud destination
        # has no path, and `str(None)` would collapse every bucket to one cache key.
        self._probe_cache[info.destination] = info
        self._finish_probe()
        if info.destination == self.destination():
            self._show_destination(info)
            if info.exists and info.writable:
                self._apply_format(info)
        self.changed.emit()

    def _show_destination(self, info):
        """One line describing what this destination is and what it can do. The
        hardlink answer is stated *before* the first backup — that's the whole
        point of probing (issue #92): a destination that can't share files stores
        a full copy every night, and silence about that is the bug."""
        if not info.exists:
            self._status.setText(info.error or "Choose a destination folder (an "
                                 "external drive or network share).")
            return
        if not info.writable:
            self._status.setText(f"⚠ {info.error or 'Folder is not writable'}.")
            return
        if info.snapshot_count:
            newest = info.newest
            head = (f"{info.snapshot_count} backup(s) · latest "
                    f"{newest.created:%Y-%m-%d %H:%M} · {_fmt_bytes(newest.total_bytes)}")
        else:
            head = "No backups here yet."
        if info.free_bytes is not None:
            head += f" · {_fmt_bytes(info.free_bytes)} free"
        if info.kind == backup.KIND_S3:
            # No free-space figure: a bucket doesn't have one, and inventing a
            # reassuring number would be worse than omitting it. What matters here
            # instead is that the first upload is metered.
            note = ("  ·  Connected. Each file is stored once; only new files "
                    "upload after the first backup.")
            self._status.setText(head + note)
            return
        if info.hardlinks:
            note = "  ·  Unchanged files are shared between backups."
        elif info.format == backup.FORMAT_POOLED:
            note = ("  ·  This destination can't share files between backups, so "
                    "M110 stores each file once instead — repeat backups stay small.")
        else:
            note = ("  ⚠ This destination can't share files between backups — "
                    "every backup stores a full copy.")
        self._status.setText(head + note)

    # ---- persistence ----
    def persist(self):
        """Write every field of this slot at once (and, for the cloud slot, the
        credentials) — Back Up Now's step before it runs, so a field still being
        typed in counts. Each field also saves itself on commit.

        Only the fields this panel owns: `update_slot` leaves the rest — notably
        the last-backup time a run stamps — alone, and never touches the other
        slot."""
        changes = dict(
            scope=self._current_scope(),
            auto=self._auto.isChecked(),
            interval_hours=self._interval.value(),
            retention_keep=self._keep.value(),
        )
        # Never let an empty field erase a configured destination. Everything else
        # here has a real value whatever the widget state, but the destination is a
        # path the user chose once and may not remember — and losing it silently
        # disables their backups. An empty box means "not entered", not "clear it".
        dest = self.destination()
        if dest:
            changes["destination"] = dest
        if self._format is not None:
            changes["format"] = self._current_format()
        if self._min_free is not None:
            # Store 0 explicitly ("off") rather than falling back to the default.
            changes["min_free_gb"] = self._min_free.value()
        backup.update_slot(self.slot, **changes)
        if self._is_cloud_slot:
            self._persist_cloud_settings()
        self.changed.emit()

    def _persist_cloud_settings(self):
        """Endpoint/region/access key to settings, secret to the keyring."""
        self._persist_cloud_fields()
        self._persist_secret()

    def _persist_cloud_fields(self):
        config.save_setting(backup.SETTING_S3_ENDPOINT,
                            self._s3_endpoint.text().strip() or None)
        config.save_setting(backup.SETTING_S3_REGION,
                            self._s3_region.text().strip() or None)
        config.save_setting(backup.SETTING_S3_ACCESS_KEY,
                            self._s3_access.text().strip() or None)

    def _persist_secret(self):
        """The secret to the keyring, under the access key in the box.

        An **empty** secret field means "keep what's saved", not "clear it" — the
        field is never populated from the keyring (see `_build_cloud_box`), so
        treating blank as a deletion would wipe the key every time the user
        visited the pane to change the interval. Same instinct as the destination
        field refusing to let a blank erase a configured path. With no access key
        yet there is nothing to file it under, so it waits in the field."""
        access = self._s3_access.text().strip()
        secret = self._s3_secret.text()
        if access and secret:
            from m110.backup.backends import s3 as s3backend
            try:
                s3backend.set_secret(access, secret)
            except backup.BackupError as exc:
                QMessageBox.warning(self, "Cloud storage", str(exc))
                return
            self._s3_secret.clear()
            # Re-read the keyring so the placeholder says a key is saved. Without
            # this, saving cleared the field and left it reading "Secret access
            # key" — which says the opposite of what just happened.
            self._sync_secret_placeholder()

    # ---- run ----
    def _do_backup(self):
        dest = self.destination()
        if not dest:
            QMessageBox.warning(self, "Back up",
                                "Enter a bucket address first." if self._is_cloud_slot
                                else "Choose a destination folder.")
            return
        err = self.validation_error()
        if err:
            QMessageBox.warning(self, "Back up", err)
            return
        try:
            backup.parse_destination(dest)
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Back up", str(exc))
            return
        self.persist()
        options = backup.options_from_settings(self.slot)

        self._cancel_event = threading.Event()
        pd = ProgressDialog("Backing up…", "Cancel", 0, 0, self)
        pd.setWindowTitle("Backing up")
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd

        self.busy.emit(True)
        self._worker = _BackupWorker(options, self._cancel_event, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        pd.show()

    def _on_progress(self, i, total):
        if self._progress is not None:
            self._progress.setLabelText(f"Backing up… {i}/{total} files")
            self._progress.setMaximum(total)
            self._progress.setValue(i)

    def _on_done(self, result):
        self._finish_worker()
        self._close_progress()
        if result.get("cancelled"):
            self.busy.emit(False)
            return
        self.backed_up.emit(result)
        self._refresh_status(force=True)
        self.changed.emit()
        self.busy.emit(False)
        new = result.get("bytes_new", 0)
        msg = QMessageBox(self)
        msg.setWindowTitle("Backed up")
        pruned = result.get("pruned", 0)
        extra = f"\nPruned {pruned} old backup(s)." if pruned else ""
        msg.setText(f"Backed up {result.get('file_count', 0)} files "
                    f"({_fmt_bytes(new)} new) to:\n{result.get('snapshot', '')}{extra}")
        # There is no folder to open for a bucket, and a button that silently does
        # nothing is worse than no button.
        open_btn = (None if self._is_cloud_slot
                    else msg.addButton("Open folder", QMessageBox.AcceptRole))
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()
        if open_btn is not None and msg.clickedButton() is open_btn:
            _open_folder(result.get("snapshot", ""))

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        QMessageBox.warning(self, "Backup failed", message)
        self.busy.emit(False)

    # ---- teardown ----
    def _close_progress(self):
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _finish_probe(self):
        self._probe_worker = drain_worker(self._probe_worker)

    def _stop_probe(self):
        self._probe_worker = drain_worker(self._probe_worker)

    def _finish_worker(self):
        self._worker = drain_worker(self._worker)

    def _stop_worker(self):
        # Ask it to stop before waiting, or the wait is for the whole backup.
        if self._worker is not None and self._cancel_event is not None:
            self._cancel_event.set()
        self._worker = drain_worker(self._worker)

    def teardown(self):
        self._stop_worker()
        self._stop_probe()
        self._close_progress()


class BackupPane(QWidget):
    """Settings › Backup: the summary of both slots, a Local drive | Cloud
    segment over one slot's settings, then Restore… and Back Up Now.

    Only the selected slot's panel is shown — the other is hidden, not stacked —
    so the pane's height-for-width is that panel's, and the Settings window can
    fit itself to it (`size_changed`)."""
    backed_up = Signal(dict)
    size_changed = Signal()         # the shown slot changed: refit the window

    def __init__(self, parent=None, *, slot: str | None = None):
        super().__init__(parent)
        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s["sm"])
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        intro_help = QLabel(INTRO_HELP)
        intro_help.setProperty("caption", True)
        intro_help.setWordWrap(True)
        layout.addWidget(intro_help)

        # ── summary: one line per slot, so the cloud option is visible before
        # anyone switches to it. Plain text: the segment below is the way there
        # (the old "Set up…" / "Edit…" links read as primary actions styled as
        # hyperlinks — critique §P2 Dialogs).
        summary = QGridLayout()
        summary.setContentsMargins(0, s["xs"], 0, s["xs"])
        summary.setHorizontalSpacing(s["md"])
        summary.setVerticalSpacing(s["xs"])
        summary.setColumnStretch(1, 1)
        self._summary: dict[str, QLabel] = {}
        for row, name in enumerate(backup.SLOTS):
            head = QLabel(f"<b>{backup.SLOT_LABELS[name]}</b>")
            summary.addWidget(head, row, 0, alignment=Qt.AlignTop)
            detail = QLabel()
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.PlainText)
            summary.addWidget(detail, row, 1)
            self._summary[name] = detail
        layout.addLayout(summary)

        # ── the segment: which slot's settings are shown ──
        if slot is None:
            configured = backup.configured_slots()
            slot = CLOUD if configured == [CLOUD] else LOCAL
        seg, self._seg_group, self._seg_btns = make_segment(
            [(name, TAB_LABELS[name]) for name in backup.SLOTS], slot)
        seg_row = QHBoxLayout()
        seg_row.addStretch(1)
        seg_row.addWidget(seg)
        seg_row.addStretch(1)
        layout.addSpacing(s["xs"])
        layout.addLayout(seg_row)
        for name, btn in self._seg_btns.items():
            btn.clicked.connect(lambda _=False, n=name: self.show_slot(n))

        self._panels: dict[str, _SlotPanel] = {}
        for name in backup.SLOTS:
            panel = _SlotPanel(name, self)
            panel.changed.connect(self._refresh_summary)
            panel.backed_up.connect(self.backed_up.emit)
            panel.busy.connect(self._on_busy)
            self._panels[name] = panel
            layout.addWidget(panel)
        self._local, self._cloud = self._panels[LOCAL], self._panels[CLOUD]

        # ── actions ── Restore spans both slots (its own From: picker); Back Up
        # Now runs the slot on screen. It is the pane's default action, so it
        # carries the accent.
        actions = QHBoxLayout()
        actions.setContentsMargins(0, s["sm"], 0, 0)
        self._restore_btn = QPushButton("Restore…")
        self._restore_btn.clicked.connect(self._open_restore)
        actions.addWidget(self._restore_btn)
        actions.addStretch(1)
        self._backup_btn = QPushButton("Back Up Now")
        self._backup_btn.setDefault(True)
        self._backup_btn.clicked.connect(self._do_backup)
        actions.addWidget(self._backup_btn)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._current = slot
        self.show_slot(slot)
        self._refresh_summary()

    def show_slot(self, slot: str):
        self._current = slot
        for name, panel in self._panels.items():
            panel.setVisible(name == slot)
        btn = self._seg_btns[slot]
        if not btn.isChecked():
            btn.setChecked(True)
        self.size_changed.emit()

    def current_slot(self) -> str:
        return self._current

    def _current_panel(self) -> _SlotPanel:
        return self._panels[self._current]

    # ---- summary ----
    def _refresh_summary(self):
        for name, panel in self._panels.items():
            self._summary[name].setText(self._summary_text(name, panel))

    @staticmethod
    def _summary_text(name: str, panel: _SlotPanel) -> str:
        slot = backup.load_slot(name)
        if not slot.destination:
            return ("Not set up — back up your essentials offsite to " + PROVIDERS + "."
                    if name == CLOUD else
                    "Not set up — back up to an external drive or network share.")
        last = panel.last_backup()
        return " · ".join((slot.destination,
                           f"last backup {_ago(last)}" if last else "no backups yet",
                           "automatic" if slot.auto else "manual"))

    # ---- actions ----
    def _on_busy(self, running: bool):
        for btn in (self._backup_btn, self._restore_btn, *self._seg_btns.values()):
            btn.setEnabled(not running)

    def _do_backup(self):
        self._current_panel()._do_backup()

    def _open_restore(self):
        """Restore from the slot on screen first, the other one a combo away."""
        from m110.ui.restore_dialog import RestoreDialog
        current = self.current_slot()
        order = [current] + [n for n in backup.SLOTS if n != current]
        sources = [(backup.SLOT_LABELS[n], self._panels[n].destination()
                    or backup.load_slot(n).destination) for n in order]
        RestoreDialog([src for src in sources if src[1]], self).exec()
        self._panels[current]._refresh_status(force=True)

    # ---- teardown ----
    def stop_probes(self):
        for panel in self._panels.values():
            panel._stop_probe()

    def teardown(self):
        for panel in self._panels.values():
            panel.teardown()


def _open_folder(path: str):
    import subprocess
    import sys
    if not path:
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            import os
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass

"""Back up dialog — snapshot the store to a destination on a worker thread.

Mirrors `publish_dialog.py`: a `_BackupWorker` (QThread) emits progress/done/failed,
a `threading.Event` backs Cancel, the worker is torn down safely on close. The
destination is pre-seeded from the saved setting so the common case is one click;
Browse only overrides it for an ad-hoc destination, and a successful run saves the
chosen destination back as the new default.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QSpinBox, QVBoxLayout,
)

from m110.ui.widgets import drain_worker
from m110 import backup, config


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


class BackupDialog(QDialog):
    backed_up = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Back up Library")
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self._probe_worker = None
        self._probe_cache: dict[str, object] = {}

        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        layout.setSpacing(s["md"])
        intro = QLabel(
            "Back up your Library to another drive, folder, or cloud storage. Only "
            "what changed is stored each time, so repeat backups are fast and "
            "small — and every backup can be restored on its own, whatever its age.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ── destination ──
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destination:"))
        self._dest = QLineEdit(str(config.get_setting(backup.SETTING_DEST, "")))
        self._dest.setPlaceholderText("A folder, or s3://your-bucket/backups")
        # Probe on commit, not per keystroke — see _ProbeWorker.
        self._dest.editingFinished.connect(self._refresh_status)
        # The cloud fields appear as soon as the destination *looks* like a bucket,
        # so the user isn't asked to commit a URI before being shown where the keys
        # go. Cheap and synchronous — a string prefix test, not the probe.
        self._dest.textChanged.connect(self._sync_cloud_visibility)
        dest_row.addWidget(self._dest, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dest_row.addWidget(browse)
        layout.addLayout(dest_row)

        self._status = QLabel()
        self._status.setProperty("muted", True)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # ── format ──  (a property of the destination, so it sits with it)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Backups are stored as:"))
        self._format = QComboBox()
        for fid in backup.FORMATS:
            self._format.addItem(backup.FORMAT_LABELS[fid], fid)
        self._select_format(backup.preferred_format())
        self._format.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self._format, 1)
        layout.addLayout(fmt_row)

        self._format_note = QLabel()
        self._format_note.setProperty("caption", True)
        self._format_note.setWordWrap(True)
        layout.addWidget(self._format_note)
        self._on_format_changed()

        # ── cloud credentials ──  (only for an s3:// destination)
        self._cloud_box = self._build_cloud_box(s)
        layout.addWidget(self._cloud_box)

        # ── scope ──  (what goes to this destination)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Back up:"))
        self._scope = QComboBox()
        for sid in backup.SCOPES:
            self._scope.addItem(backup.SCOPE_LABELS[sid], sid)
        self._select_scope(config.get_setting(backup.SETTING_SCOPE,
                                              backup.DEFAULT_SCOPE))
        self._scope.currentIndexChanged.connect(self._on_scope_changed)
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
        self._auto.setChecked(bool(config.get_setting(backup.SETTING_AUTO, False)))
        self._auto.setToolTip(
            "Backs up in the background: at launch if the last one is older than the "
            "interval below, and daily at 02:00 while the app stays running.")
        auto_row.addWidget(self._auto)
        auto_row.addStretch(1)
        self._backup_btn = QPushButton("Back up now")
        self._backup_btn.clicked.connect(self._do_backup)
        auto_row.addWidget(self._backup_btn)
        sl.addLayout(auto_row)

        auto_hint = QLabel("Runs at launch and daily at 02:00 while the app is open.")
        auto_hint.setProperty("muted", True)
        sl.addWidget(auto_hint)

        # One grid, not three QHBoxLayouts: independent rows gave each label its own
        # width, so the three fields started at three different x (a 48px spread) and
        # had three different widths. A shared label column lines them up.
        grid = QGridLayout()
        grid.setHorizontalSpacing(s["sm"])
        grid.setVerticalSpacing(s["xs"])
        grid.setColumnStretch(3, 1)               # trailing space absorbs the slack

        self._interval = QSpinBox()
        self._interval.setRange(1, 24 * 30)
        self._interval.setSuffix(" h")
        self._interval.setValue(int(config.get_setting(
            backup.SETTING_INTERVAL, backup.DEFAULT_INTERVAL_HOURS)))

        self._keep = QSpinBox()
        self._keep.setRange(0, 999)
        self._keep.setSpecialValueText("all")     # 0 → "all" (no limit)
        self._keep.setValue(int(config.get_setting(backup.SETTING_KEEP, 0) or 0))

        self._min_free = QDoubleSpinBox()
        self._min_free.setRange(0.0, 1_000_000.0)
        self._min_free.setDecimals(0)
        self._min_free.setSpecialValueText("off")     # 0 → disabled
        self._min_free.setToolTip("Prune the oldest backups to maintain this much "
                                  "free space on the destination. 0 = off.")
        self._min_free.setValue(float(config.get_setting(
            backup.SETTING_MIN_FREE, backup.DEFAULT_MIN_FREE_GB)))

        for row, (label, field, suffix) in enumerate((
                ("…at most once every", self._interval, ""),
                ("Keep newest", self._keep, "backups"),
                ("Keep at least", self._min_free, "GB free on the destination volume"))):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(field, row, 1)
            if suffix:
                grid.addWidget(QLabel(suffix), row, 2)
        # One width for all three, from the widest — `min_free` used to carry a
        # hardcoded 90px that was 18px BELOW its own sizeHint, so it clipped at large
        # values ("1000000" needs 54px in a 58px field).
        field_w = max(w.sizeHint().width()
                      for w in (self._interval, self._keep, self._min_free))
        for w in (self._interval, self._keep, self._min_free):
            w.setFixedWidth(field_w)
        sl.addLayout(grid)
        layout.addWidget(settings_box)

        buttons = QDialogButtonBox()
        self._restore_btn = buttons.addButton("Restore…", QDialogButtonBox.ActionRole)
        self._restore_btn.clicked.connect(self._open_restore)
        self._save_btn = buttons.addButton("Save", QDialogButtonBox.AcceptRole)
        self._save_btn.clicked.connect(self._save_and_close)
        # Label depends on whether there is anything to discard — see `_set_dirty`.
        self._reject_btn = buttons.addButton("Close", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._dirty = False
        self._wire_dirty_tracking()
        self._sync_exit_buttons()
        self._sync_cloud_visibility()
        self._on_scope_changed()
        self._refresh_status()

        # Size the window LAST, once the layout knows what it needs. This used to be
        # `self.resize(560, 0)` at the top of __init__ — before any widget existed —
        # and a zero height is clamped to the layout's minimum *as it stands at that
        # moment*, which was nothing. The dialog therefore opened 58px shorter than
        # the layout's real minimum, and the retention rows were squeezed until the
        # three spin boxes physically OVERLAPPED by 3px each (6px once the async
        # destination probe wrapped the status line to two lines). That, not the
        # control padding, is what still looked broken after the padding fix.
        # heightForWidth is what the layout actually needs at this width; sizeHint
        # can be shorter when word-wrapped labels are involved.
        self.setMinimumWidth(420)
        w = 560
        self.resize(w, max(self.sizeHint().height(),
                           self.layout().heightForWidth(w)))

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

    def _is_cloud(self) -> bool:
        return self._dest.text().strip().lower().startswith("s3://")

    def _sync_cloud_visibility(self, *_):
        """Reflect the *kind* of destination as soon as it's typed.

        Everything here is knowable from the string alone, so none of it waits for
        the probe — which for a bucket doesn't run until Test connection. Before
        this, an `s3://` destination sat there reading "Mirrored backups … needs a
        destination that supports file links", beside a min-free box offering to
        manage free space on a volume that doesn't exist. All three were false,
        and all three were on screen for as long as the user hadn't pressed a
        button they had no reason to press yet."""
        was = self._cloud_box.isVisibleTo(self)
        now = self._is_cloud()
        self._cloud_box.setVisible(now)

        if now:
            self._select_format(backup.FORMAT_POOLED)
            self._format.setEnabled(False)
            self._format_note.setText(
                CLOUD_FORMAT_NOTE)
        elif not self._format.isEnabled():
            # Coming back from a bucket: hand the choice back rather than leaving
            # it stuck on whatever the cloud forced.
            self._format.setEnabled(True)
            self._select_format(backup.preferred_format())
            self._on_format_changed()

        # A bucket has no volume to run out of, so the engine skips this rule —
        # the control has to say so rather than imply a policy that won't run.
        self._min_free.setEnabled(not now)
        self._min_free.setToolTip(
            "Cloud storage has no free-space limit to manage." if now else
            "Prune the oldest backups to maintain this much free space on the "
            "destination. 0 = off.")

        if now != was:
            self._fit_height()

    def _fit_height(self):
        """Grow to whatever the layout needs at the current width.

        The dialog is sized once in `__init__`, with the cloud group hidden.
        Revealing four fields, a button and a wrapped note afterwards adds real
        height, and a layout that doesn't fit gets *squeezed* rather than
        scrolled — which is how the retention spin boxes once ended up physically
        overlapping. `heightForWidth`, not `sizeHint`: word-wrapped labels report
        short from `sizeHint`."""
        w = max(self.width(), self.minimumWidth())
        needed = max(self.sizeHint().height(), self.layout().heightForWidth(w))
        if needed > self.height():
            self.resize(w, needed)

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
        if scope != backup.DEFAULT_SCOPE:
            note += ("  Backups you already have keep their light frames until "
                     "they're pruned by the retention settings below.")
        self._scope_note.setText(note)

    # ---- dirty tracking ----
    def _wire_dirty_tracking(self):
        """Every control whose value `_persist_settings` writes.

        Kept as one list beside that method on purpose: if a new setting is added to
        one and not the other, the dialog either forgets a change (offers "Close"
        over unsaved edits) or nags about one that doesn't exist."""
        # `textChanged`, NOT `textEdited`. Only two things ever write this field: the
        # constructor (before this wiring runs, so it can't arm anything) and
        # **Browse**, which is a user action that changes the setting and absolutely
        # must enable Save. `textEdited` skips programmatic writes, so picking a
        # folder with Browse left Save greyed out and the correction unsavable —
        # exactly the "I fixed the path and couldn't save it" report. The probe
        # writes `_status`, never `_dest`, so nothing else can arm this.
        self._dest.textChanged.connect(self._mark_dirty)
        self._format.currentIndexChanged.connect(self._mark_dirty)
        self._scope.currentIndexChanged.connect(self._mark_dirty)
        self._auto.toggled.connect(self._mark_dirty)
        for field in (self._s3_endpoint, self._s3_region, self._s3_access,
                      self._s3_secret):
            field.textChanged.connect(self._mark_dirty)
        for spin in (self._interval, self._keep, self._min_free):
            spin.valueChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_):
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self._sync_exit_buttons()

    def _sync_exit_buttons(self):
        """"Cancel" only when it can actually undo something.

        With no pending edits the dialog has nothing to discard — and after "Back up
        now" (which persists the settings itself before running) a button labelled
        "Cancel" reads as though it would roll back the snapshot that just ran. It
        can't: `reject()` only closes the window. So it says **Close** until an edit
        is made, and Save is disabled while there's nothing to save."""
        self._reject_btn.setText("Cancel" if self._dirty else "Close")
        self._save_btn.setEnabled(self._dirty)

    # ---- helpers ----
    def _browse(self):
        # Start at the current folder, unless it's a bucket — a file dialog can't
        # open `s3://…`, and passing it produces an empty panel at an odd place.
        start = "" if self._is_cloud() else self._dest.text()
        d = QFileDialog.getExistingDirectory(self, "Choose backup destination",
                                             start or str(Path.home()))
        if d:
            self._dest.setText(d)
            self._refresh_status()

    def _refresh_status(self, *, force: bool = False):
        """Probe the destination on a worker and describe it. Results are memoized
        per path for the dialog's lifetime; `force=True` re-probes (after a run)."""
        dest = self._dest.text().strip()
        if not dest:
            self._status.setText("Choose a destination folder (an external drive or "
                                 "network share), or enter an s3:// address.")
            return
        if self._is_cloud() and not force and dest not in self._probe_cache:
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
        return self._format.currentData() or backup.DEFAULT_FORMAT

    def _select_format(self, fmt: str):
        idx = self._format.findData(fmt)
        if idx >= 0:
            blocked = self._format.blockSignals(True)
            self._format.setCurrentIndex(idx)
            self._format.blockSignals(blocked)

    def _on_format_changed(self, *_args):
        self._format_note.setText(backup.FORMAT_BLURBS[self._current_format()])

    def _apply_format(self, info):
        """Reflect what this destination actually allows.

        A destination that can't share files leaves no choice — mirrored backups
        there would each be a full copy of the Library — so the choice is made and
        persisted rather than left as a trap the user discovers a month later."""
        self._format.setEnabled(not info.format_forced)
        self._select_format(info.format)
        self._on_format_changed()
        if info.kind == backup.KIND_S3:
            # Not a limitation being worked around — object storage has no notion
            # of a shared file, so pooled is simply what a bucket is. Said as a
            # fact rather than as the apology the link-less-share wording is. The
            # preference is deliberately not persisted here: it's global, and a
            # bucket says nothing about the user's external drive.
            self._format_note.setText(CLOUD_FORMAT_NOTE)
        elif info.format_forced:
            config.save_setting(backup.SETTING_FORMAT, info.format)
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
        if info.destination == self._dest.text().strip():
            self._show_destination(info)
            if info.exists and info.writable:
                self._apply_format(info)

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

    def _persist_settings(self, dest: str):
        # Whatever the caller was doing (Save, or "Back up now" saving before it
        # runs), the on-disk settings now match the widgets — so there is nothing
        # left to discard and the exit button goes back to "Close".
        self._set_dirty(False)
        # Never let an empty field erase a configured destination. Everything else
        # here has a real value whatever the widget state, but the destination is a
        # path the user chose once and may not remember — and losing it silently
        # disables their backups. An empty box means "not entered", not "clear it".
        if dest:
            config.save_setting(backup.SETTING_DEST, dest)
        config.save_setting(backup.SETTING_FORMAT, self._current_format())
        config.save_setting(backup.SETTING_SCOPE, self._current_scope())
        self._persist_cloud_settings()
        config.save_setting(backup.SETTING_AUTO, self._auto.isChecked())
        config.save_setting(backup.SETTING_INTERVAL, self._interval.value())
        config.save_setting(backup.SETTING_KEEP, self._keep.value() or None)
        # Store 0 explicitly ("off"); an absent key is what triggers the 100 GB
        # default, so we must persist the user's 0 rather than collapse it to None.
        config.save_setting(backup.SETTING_MIN_FREE, self._min_free.value())

    def _persist_cloud_settings(self):
        """Endpoint/region/access key to settings, secret to the keyring.

        An **empty** secret field means "keep what's saved", not "clear it" — the
        field is never populated from the keyring (see `_build_cloud_box`), so
        treating blank as a deletion would wipe the key every time the user opened
        the dialog to change the interval. Same instinct as the destination field
        refusing to let a blank erase a configured path."""
        config.save_setting(backup.SETTING_S3_ENDPOINT,
                            self._s3_endpoint.text().strip() or None)
        config.save_setting(backup.SETTING_S3_REGION,
                            self._s3_region.text().strip() or None)
        access = self._s3_access.text().strip()
        config.save_setting(backup.SETTING_S3_ACCESS_KEY, access or None)
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
            # this, Save cleared the field and left it reading "Secret access
            # key" — which says the opposite of what just happened.
            self._sync_secret_placeholder()

    def _open_restore(self):
        from m110.ui.restore_dialog import RestoreDialog
        RestoreDialog(self._dest.text().strip(), self).exec()
        self._refresh_status(force=True)

    def _save_and_close(self):
        """Persist the destination + automation/retention settings without running a
        backup, then close. (A manual "Back up now" also persists, but the user must
        be able to change the interval etc. without triggering a snapshot.)"""
        self._persist_settings(self._dest.text().strip())
        self.accept()

    def accept(self):
        self._stop_probe()
        super().accept()

    # ---- run ----
    def _do_backup(self):
        dest = self._dest.text().strip()
        if not dest:
            QMessageBox.warning(self, "Back up", "Choose a destination folder.")
            return
        try:
            backup.parse_destination(dest)
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Back up", str(exc))
            return
        self._persist_settings(dest)
        options = backup.options_from_settings(dest)

        self._cancel_event = threading.Event()
        pd = QProgressDialog("Backing up…", "Cancel", 0, 0, self)
        pd.setWindowTitle("Backing up")
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd

        self._backup_btn.setEnabled(False)
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
            self._backup_btn.setEnabled(True)
            return
        self.backed_up.emit(result)
        self._refresh_status(force=True)
        self._backup_btn.setEnabled(True)
        new = result.get("bytes_new", 0)
        msg = QMessageBox(self)
        msg.setWindowTitle("Backed up")
        pruned = result.get("pruned", 0)
        extra = f"\nPruned {pruned} old backup(s)." if pruned else ""
        msg.setText(f"Backed up {result.get('file_count', 0)} files "
                    f"({_fmt_bytes(new)} new) to:\n{result.get('snapshot', '')}{extra}")
        # There is no folder to open for a bucket, and a button that silently does
        # nothing is worse than no button.
        open_btn = (None if self._is_cloud()
                    else msg.addButton("Open folder", QMessageBox.AcceptRole))
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()
        if open_btn is not None and msg.clickedButton() is open_btn:
            self._open_folder(result.get("snapshot", ""))

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        QMessageBox.warning(self, "Backup failed", message)
        self._backup_btn.setEnabled(True)

    @staticmethod
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

    def reject(self):
        self._stop_worker()
        self._stop_probe()
        self._close_progress()
        super().reject()

    def closeEvent(self, event):
        self._stop_worker()
        self._stop_probe()
        self._close_progress()
        super().closeEvent(event)

"""Settings › Backup: the cloud and scope controls, driven rather than constructed.

Constructing a dialog proves its constructor runs and nothing more — the
`stack_in_stackingwizard` lesson. Every control added for issue #93 is therefore
*used* here: the destination is typed into, the buttons are clicked, the combos
are changed, and the assertion is about what actually happened to settings, the
keyring and the widgets.
"""
import pytest

from m110 import backup, config
from m110.ui.backup_pane import BackupPane

pytestmark = pytest.mark.usefixtures("qtbot")


@pytest.fixture
def keyring_stub(monkeypatch):
    """A dict standing in for the OS keyring — the real one would prompt, and on
    CI there isn't one."""
    store: dict[tuple, str] = {}
    from m110.backup.backends import s3 as s3backend
    monkeypatch.setattr(s3backend, "get_secret",
                        lambda access: store.get(("m110-backup-s3", access)))
    monkeypatch.setattr(s3backend, "set_secret",
                        lambda access, secret: store.__setitem__(
                            ("m110-backup-s3", access), secret))
    return store


@pytest.fixture(autouse=True)
def clean_settings():
    """Settings are sealed to a throwaway path by conftest, but they persist
    *between* tests in the run — and this dialog both reads them on open and
    writes them on save. Without a reset, a test that saves `essentials` leaves
    the next dialog already at `essentials`, so its "change the scope" step is a
    no-op and the test passes or fails on ordering rather than on behaviour."""
    for key in (backup.SETTING_DESTINATIONS, backup.SETTING_DEST,
                backup.SETTING_SCOPE, backup.SETTING_S3_ENDPOINT,
                backup.SETTING_S3_REGION, backup.SETTING_S3_ACCESS_KEY):
        config.save_setting(key, None)
    yield


@pytest.fixture
def dlg(qtbot):
    d = BackupPane()
    qtbot.addWidget(d)
    return d


# ── two slots: the cloud option is always on screen ────────────────────────

def test_both_slots_have_a_segment_and_a_summary_line(dlg):
    """The whole point: cloud backup used to be reachable only by typing
    `s3://`. It now has its own segment and a summary line naming the providers,
    on screen before anyone looks for it."""
    labels = [b.text() for b in dlg._seg_btns.values()]
    assert labels == ["Local drive", "Cloud"]
    cloud = dlg._summary[backup.SLOT_CLOUD].text()
    assert "Not set up" in cloud
    assert "Backblaze B2" in cloud and "Cloudflare R2" in cloud


def test_the_segment_shows_one_slot_at_a_time(dlg):
    """Clicked, both ways. Only the chosen slot's panel is shown — the other is
    hidden, not stacked — so the pane's height is that slot's."""
    sizes = []
    dlg.size_changed.connect(lambda: sizes.append(dlg.current_slot()))
    assert dlg.current_slot() == backup.SLOT_LOCAL
    assert not dlg._cloud.isVisibleTo(dlg) and dlg._local.isVisibleTo(dlg)
    dlg._seg_btns[backup.SLOT_CLOUD].click()
    assert dlg.current_slot() == backup.SLOT_CLOUD
    assert dlg._cloud.isVisibleTo(dlg) and not dlg._local.isVisibleTo(dlg)
    dlg._seg_btns[backup.SLOT_LOCAL].click()
    assert dlg.current_slot() == backup.SLOT_LOCAL
    assert sizes == [backup.SLOT_CLOUD, backup.SLOT_LOCAL]


def test_the_summary_has_no_links(dlg):
    """The old "Set up…" / "Edit…" links were primary actions dressed as
    hyperlinks (critique §P2 Dialogs); the segment is the way to a slot."""
    from PySide6.QtCore import Qt
    for label in dlg._summary.values():
        assert label.textFormat() == Qt.PlainText and "<a" not in label.text()


def test_a_configured_slot_summarises_destination_and_schedule(qtbot, tmp_path):
    from datetime import datetime, timedelta
    backup.update_slot(backup.SLOT_LOCAL, destination=str(tmp_path), auto=True)
    backup.record_backup(backup.SLOT_CLOUD, datetime.now() - timedelta(hours=3))
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://bucket/m110")
    d = BackupPane()
    qtbot.addWidget(d)

    local = d._summary[backup.SLOT_LOCAL].text()
    assert str(tmp_path) in local and "automatic" in local
    cloud = d._summary[backup.SLOT_CLOUD].text()
    assert "s3://bucket/m110" in cloud
    assert "3 h ago" in cloud and "manual" in cloud


def test_opens_on_the_cloud_tab_when_only_cloud_is_set_up(qtbot):
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://bucket/m110")
    d = BackupPane()
    qtbot.addWidget(d)
    assert d.current_slot() == backup.SLOT_CLOUD


def test_each_slot_saves_only_its_own_settings(dlg, tmp_path, keyring_stub):
    """No Save button: a committed field is saved at once, to its own slot."""
    backup.update_slot(backup.SLOT_CLOUD, destination="s3://keep/me", auto=True)
    dlg._local._dest.setText(str(tmp_path))
    dlg._local._dest.editingFinished.emit()
    dlg._local._auto.setChecked(True)

    local, cloud = backup.load_slot("local"), backup.load_slot("cloud")
    assert local.destination == str(tmp_path) and local.auto is True
    assert cloud.destination == "s3://keep/me" and cloud.auto is True


def test_both_slots_save_as_they_are_edited(dlg, tmp_path, keyring_stub):
    dlg._local._dest.setText(str(tmp_path))
    dlg._local._dest.editingFinished.emit()
    dlg._cloud._dest.setText("s3://bucket/m110")
    dlg._cloud._dest.editingFinished.emit()
    dlg._cloud._auto.setChecked(True)

    assert backup.configured_slots() == [backup.SLOT_LOCAL, backup.SLOT_CLOUD]
    assert backup.load_slot("cloud").auto is True


@pytest.mark.parametrize("slot,dest,words", [
    ("local", "s3://bucket/x", "under Cloud"),
    ("cloud", "/Volumes/Backup", "s3://"),
])
def test_a_destination_in_the_wrong_slot_is_refused(dlg, slot, dest, words):
    """Committed, it isn't saved; the status line says why."""
    panel = dlg._panels[slot]
    panel._dest.setText(dest)
    panel._dest.editingFinished.emit()

    assert words in panel._status.text()
    assert backup.load_slot(slot).destination == ""


def test_the_cloud_tab_is_always_pooled_and_has_no_free_space_rule(dlg):
    """A bucket has no choice of format and no volume to fill; controls that
    implied otherwise would promise things that never happen."""
    from m110.ui.backup_pane import CLOUD_FORMAT_NOTE
    cloud = dlg._cloud
    assert cloud._format is None and cloud._min_free is None
    assert cloud._current_format() == backup.FORMAT_POOLED
    assert cloud._format_note.text() == CLOUD_FORMAT_NOTE
    # The pooled blurb promises a browsable copy of the newest backup — a
    # hardlink tree, which is the one thing object storage can't do.
    assert "browsable" not in CLOUD_FORMAT_NOTE
    assert "file links" not in CLOUD_FORMAT_NOTE
    assert dlg._local._format is not None and dlg._local._min_free is not None


def test_cloud_defaults_to_essentials_local_to_everything(dlg):
    assert dlg._local._current_scope() == backup.SCOPE_EVERYTHING
    assert dlg._cloud._current_scope() == backup.SCOPE_ESSENTIALS


def test_a_cloud_destination_is_not_probed_until_asked(dlg, monkeypatch):
    """A probe means a network round-trip and needs the credentials saved to make
    it — neither should happen because a field lost focus."""
    calls = []
    monkeypatch.setattr(backup, "probe_destination",
                        lambda d: calls.append(d) or backup.DestinationInfo(
                            path=None, exists=True, writable=True, hardlinks=False,
                            free_bytes=None, snapshot_count=0, destination=str(d),
                            kind="s3"))
    dlg._cloud._dest.setText("s3://my-bucket/backups")
    dlg._cloud._refresh_status()

    assert calls == []
    assert "Test connection" in dlg._cloud._status.text()


# ── credentials ─────────────────────────────────────────────────────────────

def test_test_connection_saves_credentials_then_probes(dlg, qtbot, keyring_stub,
                                                       monkeypatch):
    """The click path end to end — this is the one that would have caught a
    NameError in the button's own callback."""
    probed = []
    monkeypatch.setattr(backup, "probe_destination",
                        lambda d: probed.append(str(d)) or backup.DestinationInfo(
                            path=None, exists=True, writable=True, hardlinks=False,
                            free_bytes=None, snapshot_count=0, destination=str(d),
                            kind="s3"))
    dlg._cloud._dest.setText("s3://my-bucket/backups")
    dlg._cloud._s3_endpoint.setText("https://s3.us-west-002.backblazeb2.com")
    dlg._cloud._s3_region.setText("us-west-002")
    dlg._cloud._s3_access.setText("KEY123")
    dlg._cloud._s3_secret.setText("SUPERSECRET")

    dlg._cloud._test_btn.click()
    qtbot.waitUntil(lambda: bool(probed), timeout=3000)

    assert config.get_setting(backup.SETTING_S3_ENDPOINT) == \
        "https://s3.us-west-002.backblazeb2.com"
    assert config.get_setting(backup.SETTING_S3_REGION) == "us-west-002"
    assert config.get_setting(backup.SETTING_S3_ACCESS_KEY) == "KEY123"
    # The secret goes to the keyring and NOWHERE near settings.json.
    assert keyring_stub[("m110-backup-s3", "KEY123")] == "SUPERSECRET"
    assert "SUPERSECRET" not in config.SETTINGS_FILE.read_text()
    assert probed == ["s3://my-bucket/backups"]


def test_the_secret_field_is_masked_and_cleared_after_saving(dlg, keyring_stub):
    from PySide6.QtWidgets import QLineEdit
    assert dlg._cloud._s3_secret.echoMode() == QLineEdit.Password

    dlg._cloud._s3_access.setText("KEY123")
    dlg._cloud._s3_secret.setText("SUPERSECRET")
    dlg._cloud._persist_cloud_settings()

    assert dlg._cloud._s3_secret.text() == ""
    assert "Saved" in dlg._cloud._s3_secret.placeholderText()


def test_a_blank_secret_keeps_the_saved_one(dlg, keyring_stub):
    """Opening the dialog to change the interval must not wipe the key — the
    field is never populated from the keyring, so blank means "unchanged"."""
    dlg._cloud._s3_access.setText("KEY123")
    dlg._cloud._s3_secret.setText("SUPERSECRET")
    dlg._cloud._persist_cloud_settings()

    dlg._cloud._s3_secret.setText("")
    dlg._cloud._persist_cloud_settings()

    assert keyring_stub[("m110-backup-s3", "KEY123")] == "SUPERSECRET"


def test_the_placeholder_follows_the_access_key(dlg, keyring_stub):
    """Switching key ids must not imply the old secret came along."""
    dlg._cloud._s3_access.setText("KEY123")
    dlg._cloud._s3_secret.setText("SUPERSECRET")
    dlg._cloud._persist_cloud_settings()
    assert "Saved" in dlg._cloud._s3_secret.placeholderText()

    dlg._cloud._s3_access.setText("OTHERKEY")
    assert "Saved" not in dlg._cloud._s3_secret.placeholderText()


# ── scope ───────────────────────────────────────────────────────────────────

def test_scope_defaults_to_everything_and_persists(dlg):
    assert dlg._local._current_scope() == backup.SCOPE_EVERYTHING

    dlg._local._select_scope(backup.SCOPE_ESSENTIALS)
    dlg._local._scope.currentIndexChanged.emit(dlg._local._scope.currentIndex())
    dlg._local._dest.setText("/tmp/dest")
    dlg._local.persist()

    assert backup.load_slot("local").scope == backup.SCOPE_ESSENTIALS
    assert backup.load_slot("cloud").destination == ""


def test_narrowing_scope_explains_what_happens_to_existing_backups(dlg):
    """Shipping the tier without a byte estimate is only defensible if the delay
    is stated — otherwise the frames vanish later with no warning at all."""
    idx = dlg._local._scope.findData(backup.SCOPE_ESSENTIALS)
    dlg._local._scope.setCurrentIndex(idx)          # a real change, so the signal fires

    note = dlg._local._scope_note.text()
    assert "light frames" in note
    assert "pruned" in note or "retention" in note


@pytest.mark.parametrize("slot", ["local", "cloud"])
def test_every_setting_saves_itself(dlg, slot):
    """Every field `persist` writes must also save on its own commit — there is
    no Save button to catch the one that doesn't."""
    panel = dlg._panels[slot]
    other = (backup.SCOPE_EVERYTHING if panel._current_scope() == backup.SCOPE_ESSENTIALS
             else backup.SCOPE_ESSENTIALS)
    panel._scope.setCurrentIndex(panel._scope.findData(other))
    panel._auto.setChecked(not panel._auto.isChecked())
    panel._interval.setValue(panel._interval.value() + 5)
    panel._keep.setValue(panel._keep.value() + 2)
    if panel._min_free is not None:
        panel._min_free.setValue(42)
    if panel._format is not None:
        panel._format.setCurrentIndex(panel._format.findData(backup.FORMAT_POOLED))

    saved = backup.load_slot(slot)
    assert saved.scope == other
    assert saved.auto is panel._auto.isChecked()
    assert saved.interval_hours == panel._interval.value()
    assert saved.retention_keep == panel._keep.value()
    if panel._min_free is not None:
        assert saved.min_free_gb == 42
    if panel._format is not None:
        assert saved.format == backup.FORMAT_POOLED


def test_cloud_credentials_save_when_their_field_is_left(dlg, keyring_stub):
    cloud = dlg._cloud
    cloud._s3_endpoint.setText("https://example.r2.dev")
    cloud._s3_endpoint.editingFinished.emit()
    cloud._s3_access.setText("KEY9")
    cloud._s3_access.editingFinished.emit()
    cloud._s3_secret.setText("S3CRET")
    cloud._s3_secret.editingFinished.emit()

    assert config.get_setting(backup.SETTING_S3_ENDPOINT) == "https://example.r2.dev"
    assert config.get_setting(backup.SETTING_S3_ACCESS_KEY) == "KEY9"
    assert keyring_stub[("m110-backup-s3", "KEY9")] == "S3CRET"
    assert cloud._s3_secret.text() == ""


def test_a_malformed_bucket_is_not_saved(dlg):
    dlg._cloud._dest.setText("s3://")
    dlg._cloud._dest.editingFinished.emit()
    assert "bucket" in dlg._cloud._status.text().lower()
    assert backup.load_slot("cloud").destination == ""


# ── destination validation ──────────────────────────────────────────────────

# ── layout ──────────────────────────────────────────────────────────────────

def test_the_cloud_default_scope_carries_no_narrowing_warning(dlg):
    """Essentials is where the cloud tab starts, not a change the user made —
    warning about "backups you already have" there is noise before the first
    backup exists."""
    assert "already have" not in dlg._cloud._scope_note.text()


@pytest.mark.parametrize("slot", ["local", "cloud"])
def test_no_explanatory_text_is_cut_off(dlg, slot):
    """Every wrapped caption must have room for the lines it actually needs at
    the dialog's width — the Preferences lesson, where the overflow showed up as
    text with a line sliced off rather than an obviously-too-small window."""
    panel = dlg._panels[slot]
    dlg.show_slot(slot)
    dlg.resize(560, dlg.heightForWidth(560))
    dlg.show()
    dlg.layout().activate()
    labels = [panel._status, panel._format_note, panel._scope_note,
              *dlg._summary.values()]
    for label in labels:
        if not label.text():
            continue
        assert label.height() >= label.heightForWidth(label.width()), label.text()[:60]


def test_a_malformed_bucket_uri_is_refused_before_any_work(dlg, monkeypatch):
    warned = []
    monkeypatch.setattr("m110.ui.backup_pane.QMessageBox.warning",
                        lambda *a, **k: warned.append(a[2]))
    started = []
    monkeypatch.setattr(backup, "options_from_settings",
                        lambda d: started.append(d))
    dlg._cloud._dest.setText("s3://")

    dlg.show_slot(backup.SLOT_CLOUD)
    dlg._backup_btn.click()

    assert warned and "bucket" in warned[0].lower()
    assert started == []


def test_back_up_now_runs_the_slot_on_screen(dlg, tmp_path, monkeypatch):
    """The pane's one Back Up Now, clicked on each slot: each run builds options
    for the slot shown."""
    started = []

    class _Stub:
        def __init__(self, options, *_a, **_k):
            started.append(options.slot)
            self.progressed = self.done = self.failed = type(
                "S", (), {"connect": lambda *_: None})()

        def start(self):
            pass

    monkeypatch.setattr("m110.ui.backup_pane._BackupWorker", _Stub)
    monkeypatch.setattr("m110.ui.backup_pane.ProgressDialog.show",
                        lambda self: None)
    dlg._local._dest.setText(str(tmp_path))
    dlg._backup_btn.click()
    # A run disables the pane's actions until it finishes (the stub never does).
    assert not dlg._backup_btn.isEnabled()
    assert not dlg._seg_btns[backup.SLOT_CLOUD].isEnabled()
    dlg._local._worker = None
    dlg._local._close_progress()
    dlg._local.busy.emit(False)
    dlg._seg_btns[backup.SLOT_CLOUD].click()
    dlg._cloud._dest.setText("s3://bucket/m110")
    dlg._backup_btn.click()
    dlg._cloud._worker = None

    assert started == [backup.SLOT_LOCAL, backup.SLOT_CLOUD]
    for panel in (dlg._local, dlg._cloud):
        panel._close_progress()

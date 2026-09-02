"""The backup dialog's cloud and scope controls, driven rather than constructed.

Constructing a dialog proves its constructor runs and nothing more — the
`stack_in_stackingwizard` lesson. Every control added for issue #93 is therefore
*used* here: the destination is typed into, the buttons are clicked, the combos
are changed, and the assertion is about what actually happened to settings, the
keyring and the widgets.
"""
import pytest

from m110 import backup, config
from m110.ui.backup_dialog import BackupDialog

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
    for key in (backup.SETTING_SCOPE, backup.SETTING_S3_ENDPOINT,
                backup.SETTING_S3_REGION, backup.SETTING_S3_ACCESS_KEY):
        config.save_setting(key, None)
    yield


@pytest.fixture
def dlg(qtbot):
    d = BackupDialog()
    qtbot.addWidget(d)
    return d


# ── cloud fields appear with an s3:// destination ───────────────────────────

def test_cloud_fields_are_hidden_for_a_folder_and_shown_for_a_bucket(dlg, tmp_path):
    dlg._dest.setText(str(tmp_path))
    assert dlg._cloud_box.isVisibleTo(dlg) is False

    dlg._dest.setText("s3://my-bucket/backups")
    assert dlg._cloud_box.isVisibleTo(dlg) is True


def test_a_bucket_shows_the_right_format_before_any_probe(dlg, tmp_path):
    """A cloud destination doesn't get probed until Test connection, so anything
    the probe would have corrected is on screen until then. Format is knowable
    from the destination string alone — leaving it reading "Mirrored backups …
    needs a destination that supports file links" is simply false."""
    dlg._dest.setText("s3://my-bucket/backups")

    from m110.ui.backup_dialog import CLOUD_FORMAT_NOTE
    assert dlg._current_format() == backup.FORMAT_POOLED
    assert dlg._format.isEnabled() is False
    assert dlg._format_note.text() == CLOUD_FORMAT_NOTE
    # The pooled blurb promises a browsable copy of the newest backup — a
    # hardlink tree, which is the one thing object storage can't do.
    assert "browsable" not in CLOUD_FORMAT_NOTE
    assert "file links" not in CLOUD_FORMAT_NOTE


def test_switching_back_to_a_folder_returns_the_format_choice(dlg, tmp_path):
    dlg._dest.setText("s3://my-bucket/backups")
    dlg._dest.setText(str(tmp_path))

    assert dlg._format.isEnabled() is True


def test_min_free_is_disabled_for_a_bucket(dlg, tmp_path):
    """The engine skips the min-free rule where there's no volume to measure; an
    enabled control would promise a policy that never runs."""
    dlg._dest.setText(str(tmp_path))
    assert dlg._min_free.isEnabled() is True

    dlg._dest.setText("s3://my-bucket/backups")
    assert dlg._min_free.isEnabled() is False
    assert "no free-space limit" in dlg._min_free.toolTip()


def test_a_cloud_destination_is_not_probed_until_asked(dlg, monkeypatch):
    """A probe means a network round-trip and needs the credentials saved to make
    it — neither should happen because a field lost focus."""
    calls = []
    monkeypatch.setattr(backup, "probe_destination",
                        lambda d: calls.append(d) or backup.DestinationInfo(
                            path=None, exists=True, writable=True, hardlinks=False,
                            free_bytes=None, snapshot_count=0, destination=str(d),
                            kind="s3"))
    dlg._dest.setText("s3://my-bucket/backups")
    dlg._refresh_status()

    assert calls == []
    assert "Test connection" in dlg._status.text()


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
    dlg._dest.setText("s3://my-bucket/backups")
    dlg._s3_endpoint.setText("https://s3.us-west-002.backblazeb2.com")
    dlg._s3_region.setText("us-west-002")
    dlg._s3_access.setText("KEY123")
    dlg._s3_secret.setText("SUPERSECRET")

    dlg._test_btn.click()
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
    assert dlg._s3_secret.echoMode() == QLineEdit.Password

    dlg._s3_access.setText("KEY123")
    dlg._s3_secret.setText("SUPERSECRET")
    dlg._persist_cloud_settings()

    assert dlg._s3_secret.text() == ""
    assert "Saved" in dlg._s3_secret.placeholderText()


def test_a_blank_secret_keeps_the_saved_one(dlg, keyring_stub):
    """Opening the dialog to change the interval must not wipe the key — the
    field is never populated from the keyring, so blank means "unchanged"."""
    dlg._s3_access.setText("KEY123")
    dlg._s3_secret.setText("SUPERSECRET")
    dlg._persist_cloud_settings()

    dlg._s3_secret.setText("")
    dlg._persist_cloud_settings()

    assert keyring_stub[("m110-backup-s3", "KEY123")] == "SUPERSECRET"


def test_the_placeholder_follows_the_access_key(dlg, keyring_stub):
    """Switching key ids must not imply the old secret came along."""
    dlg._s3_access.setText("KEY123")
    dlg._s3_secret.setText("SUPERSECRET")
    dlg._persist_cloud_settings()
    assert "Saved" in dlg._s3_secret.placeholderText()

    dlg._s3_access.setText("OTHERKEY")
    assert "Saved" not in dlg._s3_secret.placeholderText()


# ── scope ───────────────────────────────────────────────────────────────────

def test_scope_defaults_to_everything_and_persists(dlg):
    assert dlg._current_scope() == backup.SCOPE_EVERYTHING

    dlg._select_scope(backup.SCOPE_ESSENTIALS)
    dlg._scope.currentIndexChanged.emit(dlg._scope.currentIndex())
    dlg._persist_settings("/tmp/dest")

    assert config.get_setting(backup.SETTING_SCOPE) == backup.SCOPE_ESSENTIALS


def test_narrowing_scope_explains_what_happens_to_existing_backups(dlg):
    """Shipping the tier without a byte estimate is only defensible if the delay
    is stated — otherwise the frames vanish later with no warning at all."""
    idx = dlg._scope.findData(backup.SCOPE_ESSENTIALS)
    dlg._scope.setCurrentIndex(idx)          # a real change, so the signal fires

    note = dlg._scope_note.text()
    assert "light frames" in note
    assert "pruned" in note or "retention" in note


def test_scope_change_marks_the_dialog_dirty(dlg):
    """Every control `_persist_settings` writes has to arm Save, or the user makes
    a change they can't save."""
    assert dlg._save_btn.isEnabled() is False
    dlg._scope.setCurrentIndex(dlg._scope.findData(backup.SCOPE_ESSENTIALS))
    assert dlg._save_btn.isEnabled() is True


# ── destination validation ──────────────────────────────────────────────────

# ── layout ──────────────────────────────────────────────────────────────────

def test_the_dialog_grows_when_the_cloud_fields_appear(dlg, tmp_path):
    """A layout that doesn't fit is squeezed, not scrolled — which is how the
    retention spin boxes once came to overlap by 3px each. The dialog is sized in
    __init__ with this group hidden, so revealing it has to re-fit."""
    dlg._dest.setText(str(tmp_path))
    folder_height = dlg.height()

    dlg._dest.setText("s3://my-bucket/backups")

    assert dlg._cloud_box.isVisibleTo(dlg)
    assert dlg.height() >= dlg.layout().heightForWidth(dlg.width())
    assert dlg.height() > folder_height


def test_no_explanatory_text_is_cut_off(dlg):
    """Every wrapped caption must have room for the lines it actually needs at
    the dialog's width — the Preferences lesson, where the overflow showed up as
    text with a line sliced off rather than an obviously-too-small window."""
    dlg._dest.setText("s3://my-bucket/backups")
    dlg.show()
    dlg.layout().activate()
    for label in (dlg._status, dlg._format_note, dlg._scope_note):
        if not label.text():
            continue
        assert label.height() >= label.heightForWidth(label.width()), label.text()[:60]


def test_a_malformed_bucket_uri_is_refused_before_any_work(dlg, monkeypatch):
    warned = []
    monkeypatch.setattr("m110.ui.backup_dialog.QMessageBox.warning",
                        lambda *a, **k: warned.append(a[2]))
    started = []
    monkeypatch.setattr(backup, "options_from_settings",
                        lambda d: started.append(d))
    dlg._dest.setText("s3://")

    dlg._backup_btn.click()

    assert warned and "bucket" in warned[0].lower()
    assert started == []

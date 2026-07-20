"""Offscreen test for the update-availability UI (`m110.ui.update_notice`).

The engine (`m110.updates`) is tested separately; this pins the *surfacing*:
the banner's Skip persists a skip and hides, Download opens the release URL, and
the launch worker emits its result and records the throttle only when asked
(the `record=False` manual-check path must not suppress the next launch check).
"""
import pytest

pytest.importorskip("PySide6")

from m110 import updates  # noqa: E402
from m110.updates import UpdateInfo  # noqa: E402
from m110.ui import update_notice  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _info(newer=True):
    return UpdateInfo(current="0.2.0b6", latest="0.2.0b7",
                      url="https://github.com/mjm1138/m110/releases", is_newer=newer)


def test_banner_skip_persists_and_hides(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    b = update_notice.UpdateBanner(_info())
    try:
        assert not updates.is_skipped("0.2.0b7")
        b._skip()
        assert updates.is_skipped("0.2.0b7")
        assert b.isHidden()
    finally:
        b.deleteLater(); qapp.processEvents()


def test_banner_download_opens_release_url(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: (opened.append(url.toString()), True)[1])
    b = update_notice.UpdateBanner(_info())
    try:
        b._download()
        assert opened and "releases" in opened[0]
    finally:
        b.deleteLater(); qapp.processEvents()


def test_worker_emits_result_without_recording(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    info = _info()
    monkeypatch.setattr(updates, "check", lambda: info)
    recorded = []
    monkeypatch.setattr(updates, "record_check", lambda *a, **k: recorded.append(True))
    w = update_notice.UpdateCheckWorker(record=False)
    got = []
    w.done.connect(got.append)
    w.run()                                  # run the worker body on the test thread
    assert got and got[0] is info
    assert not recorded                      # manual check must not stamp the throttle


def test_worker_records_and_emits_none_on_failure(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(updates, "check", lambda: None)
    recorded = []
    monkeypatch.setattr(updates, "record_check", lambda *a, **k: recorded.append(True))
    w = update_notice.UpdateCheckWorker(record=True)
    got = []
    w.done.connect(got.append)
    w.run()
    assert got and got[0] is None            # a failed/absent check emits None
    assert recorded                          # launch check advances the throttle

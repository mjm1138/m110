"""A recursive directory scan must stay cancellable *within* a directory, not only
at directory boundaries — otherwise reading a FITS header per frame over a slow
share (a VM shared drive, a Seestar SMB mount) makes the Cancel button unresponsive
and the scan looks hung."""
from m110 import ingest


def test_scan_cancellable_within_a_directory(tmp_path):
    d = tmp_path / "Messier"
    d.mkdir()
    for n in ("a.fit", "b.fit", "c.fit"):      # loose FITS → the raw-fits classifier loop
        (d / n).write_bytes(b"")

    # False for the per-directory check (os.walk boundary), True on the first
    # per-frame check inside the classifier — so this only passes if cancellation is
    # threaded into the per-file loop, not just checked between directories.
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1

    import pytest
    with pytest.raises(ingest.IngestCancelled):
        ingest.scan_directory_plan(d, should_cancel=should_cancel)

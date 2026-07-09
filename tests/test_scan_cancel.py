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


def test_scan_reports_progress_per_directory(tmp_path):
    """The scan reports a running file count + current folder so a slow scan (SMB /
    shared drive) shows live progress instead of an opaque spinner."""
    d = tmp_path / "Messier"
    d.mkdir()
    (d / "loose.fit").write_bytes(b"")
    for sub in ("M42", "M51"):
        (d / sub).mkdir()
        (d / sub / "a.fit").write_bytes(b"")

    calls = []
    ingest.scan_directory_plan(d, progress=lambda n, label: calls.append((n, label)))

    labels = [label for _n, label in calls]
    assert labels == ["Messier", "M42", "M51"]      # one report per directory, in order
    counts = [n for n, _ in calls]
    assert counts == sorted(counts)                  # running count is monotonic
    assert counts == [0, 1, 2]                        # announced before each dir's files

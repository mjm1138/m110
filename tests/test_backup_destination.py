"""What a backup destination *is*, now that it isn't necessarily a folder.

`parse_destination` is the one place a typed string becomes a routed destination,
so the interesting cases are the ambiguous ones — above all a Windows drive
letter, which a naive `urlparse().scheme` reads as a URI scheme.
"""
import pytest

from m110.backup import backend_for, parse_destination
from m110.backup.backends.local import LocalBackend
from m110.backup.backends.s3 import S3Backend
from m110.backup.destination import KIND_LOCAL, KIND_S3, backup_root_key
from m110.backup.errors import BackupDestinationError


@pytest.mark.parametrize("raw", [
    "/Volumes/Backup",
    "/Users/someone/Backups",
    "relative/folder",
    # The trap: `urlparse("C:\\Backups").scheme == "c"`. A drive letter is not a
    # scheme, and reading it as one would route a Windows user's external disk to
    # a cloud backend.
    r"C:\Backups",
    r"D:\M110\Backups",
])
def test_a_path_is_local(raw):
    dest = parse_destination(raw)
    assert dest.kind == KIND_LOCAL
    assert dest.is_local is True
    assert str(dest.path) == raw


@pytest.mark.parametrize("raw,bucket,prefix", [
    ("s3://my-bucket", "my-bucket", ""),
    ("s3://my-bucket/", "my-bucket", ""),
    ("s3://my-bucket/m110", "my-bucket", "m110"),
    ("s3://my-bucket/nested/prefix/", "my-bucket", "nested/prefix"),
    ("S3://Mixed-Case", "Mixed-Case", ""),      # scheme is case-insensitive
])
def test_an_s3_uri_splits_into_bucket_and_prefix(raw, bucket, prefix):
    dest = parse_destination(raw)
    assert dest.kind == KIND_S3
    assert dest.is_local is False
    assert (dest.bucket, dest.prefix) == (bucket, prefix)


@pytest.mark.parametrize("raw", ["s3://", "s3:///", "s3:///no-bucket"])
def test_a_bucketless_s3_uri_is_rejected(raw):
    with pytest.raises(BackupDestinationError):
        parse_destination(raw)


def test_a_path_mangled_uri_is_refused_rather_than_read_as_a_folder():
    """`Path("s3://bucket/x")` normalises to `s3:/bucket/x` — one slash — which
    would otherwise parse as an ordinary relative folder and back the library up
    to a directory literally named `s3:`. Silently.

    This is not hypothetical: `ui.main`'s scheduled-backup path wrapped the saved
    destination in `Path()`, so every automatic backup to a bucket would have gone
    to disk instead. The caller is fixed; this makes the next one an error."""
    from pathlib import Path
    with pytest.raises(BackupDestinationError) as exc:
        parse_destination(Path("s3://my-bucket/backups"))
    assert "two slashes" in str(exc.value)

    with pytest.raises(BackupDestinationError):
        parse_destination("s3:/my-bucket/backups")


def test_parsing_is_idempotent():
    once = parse_destination("s3://b/p")
    assert parse_destination(once) is once


def test_a_cloud_destination_refuses_to_pretend_it_is_a_path():
    """Anything reaching for a filesystem path on a bucket is a call site that
    hasn't moved onto the backend seam — it must fail loudly, not build a path
    like `s3:/b/p` (which is what `Path("s3://b/p")` silently produces)."""
    from pathlib import Path
    dest = parse_destination("s3://b/p")
    with pytest.raises(TypeError):
        Path(dest)
    # …while a local one stays usable exactly as before.
    assert Path(parse_destination("/tmp/x")) == Path("/tmp/x")


def test_backup_root_key_places_the_store_under_the_prefix():
    assert backup_root_key("s3://b/p", "MyStore") == "p/M110-Backups/MyStore"
    assert backup_root_key("s3://b", "MyStore") == "M110-Backups/MyStore"


def test_backend_for_routes_by_kind(tmp_path, monkeypatch):
    assert isinstance(backend_for(tmp_path, "store"), LocalBackend)
    # Built lazily and never connected here — constructing must not need boto3 or
    # a network, or the probe couldn't report a bad endpoint as an error.
    b = backend_for("s3://bucket/prefix", "store")
    assert isinstance(b, S3Backend)
    assert b.bucket == "bucket"
    assert b.root == "prefix/M110-Backups/store"

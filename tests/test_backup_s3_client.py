"""`S3Backend`'s wiring to the *real* boto3, which the fake client can't reach.

`test_backup_backends.py` proves the adapter satisfies the storage contract with
an injected fake, deliberately without the AWS SDK. That leaves one class of bug
uncovered: everything between us and boto3 — the client kwargs, the botocore
`Config`, the transfer settings, and the mapping of botocore's exceptions onto
ours. Those only fail with the real library installed, which is the same shape as
the frozen-build dependency failures in #64/#74/#75: the code is fine, the wiring
to a library is not, and it fails somewhere no test was looking.

**No network.** Clients are pointed at a port nothing listens on, so a connection
error proves the request was built, configured and signed; a `TypeError` would
prove it wasn't.

Skipped where boto3 is absent, so a lean `pip install -e '.[dev]'` still passes —
but boto3 *is* in `dev`, so CI runs this rather than trusting a comment.
"""
import pytest

boto3 = pytest.importorskip("boto3", reason="needs the optional 's3' extra")

from m110.backup.backends.s3 import S3Backend, _client_config, _transfer_config
from m110.backup.errors import BackupDestinationError

DEAD = "http://127.0.0.1:1"     # reserved, nothing listens


def _backend(**kw):
    kw.setdefault("endpoint_url", DEAD)
    kw.setdefault("region_name", "us-east-1")
    kw.setdefault("access_key", "AKIA_TEST")
    kw.setdefault("secret_key", "secret")
    return S3Backend("bucket", "prefix", **kw)


def test_transfer_config_is_built_and_bounded():
    """Per-file concurrency multiplies with the across-file pool, so it stays low."""
    cfg = _transfer_config()
    assert cfg is not None
    assert cfg.max_concurrency == 2


def test_a_dead_endpoint_is_given_up_on_promptly():
    """`probe_destination` runs on a worker the dialog is waiting on, and
    botocore's defaults retry for around two minutes before answering "no"."""
    cfg = _client_config(custom_endpoint=True)
    assert cfg.connect_timeout <= 15
    assert cfg.retries["max_attempts"] <= 3
    # …and generous where cutting it short would break a real transfer.
    assert cfg.read_timeout >= 60


def test_the_checksum_pin_is_accepted_by_this_botocore():
    """botocore >=1.36 attaches `x-amz-checksum-crc32` to every PUT by default and
    several S3-compatible services reject it. The pin is guarded against older
    botocore raising TypeError — this asserts it actually took effect on the
    version we ship against, so the guard can't silently become the only path."""
    cfg = _client_config(custom_endpoint=False)
    assert cfg is not None
    assert cfg.request_checksum_calculation == "when_required"


def test_aws_keeps_default_addressing_and_custom_endpoints_get_path_style():
    """Virtual-host addressing needs the provider to serve bucket subdomains with
    matching TLS; MinIO-style deployments often serve nothing but path-style. AWS
    is the one place virtual-host is the supported direction."""
    assert not getattr(_client_config(custom_endpoint=False), "s3", None)
    assert _client_config(custom_endpoint=True).s3 == {"addressing_style": "path"}


def test_a_real_client_is_built_with_our_endpoint_and_paginator():
    client = _backend().client
    assert client.meta.endpoint_url.startswith(DEAD)
    assert hasattr(client.get_paginator("list_objects_v2"), "paginate")


def test_missing_credentials_fall_back_to_boto3s_own_chain():
    """Someone with a working AWS CLI should have to enter nothing — so no keys
    must mean "let boto3 resolve", not an error at construction."""
    assert S3Backend("bucket", "prefix", endpoint_url=DEAD).client is not None


def test_an_unreachable_endpoint_becomes_our_error_with_a_readable_reason():
    """The probe shows this string to the user; a raw botocore traceback isn't an
    answer to "why can't I back up?"."""
    with pytest.raises(BackupDestinationError) as exc:
        _backend().ensure_root()
    assert "bucket" in str(exc.value).lower()


def test_a_failed_read_maps_onto_what_restore_already_handles():
    """`pooled.restore` skips `(OSError, KeyError)`. Anything else aborts a whole
    restore over one file."""
    with pytest.raises((KeyError, BackupDestinationError)):
        _backend().get_bytes("objects/aa/bb/aabb")

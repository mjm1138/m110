"""An in-process stand-in for a boto3 S3 client.

Why this and not `moto`: the suite is fixture-based and offline by instinct, and
the thing worth proving is that **`S3Backend` satisfies the storage contract** —
which the parameterized conformance suite in `test_backup_backends.py` proves by
running the real adapter against this. A heavyweight AWS mock would add a
dependency to test our code rather than boto3's, and `boto3` is deliberately not
in the `dev` extra, so the suite must pass with no AWS SDK installed at all.

What it does model, because the adapter's correctness depends on it:

* keys are **flat** (no directories), so prefix listing is a string match
* `list_objects_v2` **paginates**, with a small page size so the paginator loop
  is actually exercised rather than always fitting in one page
* a missing key raises a **ClientError-shaped** exception, carrying the
  `response["Error"]["Code"]` the adapter reads to map it to `KeyError`
* `LastModified` is a real datetime, since the GC grace window calls `.timestamp()`
"""
from __future__ import annotations

import datetime as _dt
import itertools
from pathlib import Path

PAGE_SIZE = 2       # deliberately tiny: makes multi-page listing the normal case


class FakeClientError(Exception):
    """Shaped like `botocore.exceptions.ClientError` in the two ways the adapter
    actually reads: `.response["Error"]["Code"]` and `["Message"]`."""

    def __init__(self, code: str, message: str = "not found"):
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeS3Client:
    """A single-bucket object store in a dict."""

    def __init__(self, bucket: str = "test-bucket", *, clock=None):
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}
        self._stamps: dict[str, _dt.datetime] = {}
        self._tick = clock or itertools.count(1_700_000_000, 1).__next__
        self.calls: dict[str, int] = {}     # crude call counter for cost assertions

    # ---- helpers ----
    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def _check_bucket(self, bucket: str) -> None:
        if bucket != self.bucket:
            raise FakeClientError("NoSuchBucket", f"no bucket {bucket}")

    def _stamp(self, key: str) -> None:
        self._stamps[key] = _dt.datetime.fromtimestamp(self._tick(), _dt.timezone.utc)

    def set_mtime(self, key: str, when: float) -> None:
        """Test affordance: age an object past the GC grace window."""
        if key in self._stamps:
            self._stamps[key] = _dt.datetime.fromtimestamp(when, _dt.timezone.utc)

    # ---- the client surface S3Backend uses ----
    def head_bucket(self, *, Bucket):
        self._count("head_bucket")
        self._check_bucket(Bucket)
        return {}

    def head_object(self, *, Bucket, Key):
        self._count("head_object")
        self._check_bucket(Bucket)
        if Key not in self.objects:
            raise FakeClientError("404")
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body):
        self._count("put_object")
        self._check_bucket(Bucket)
        self.objects[Key] = bytes(Body)
        self._stamp(Key)
        return {}

    def get_object(self, *, Bucket, Key):
        self._count("get_object")
        self._check_bucket(Bucket)
        if Key not in self.objects:
            raise FakeClientError("NoSuchKey")
        return {"Body": _Body(self.objects[Key])}

    def upload_file(self, filename, bucket, key, **kwargs):
        self._count("upload_file")
        self._check_bucket(bucket)
        self.objects[key] = Path(filename).read_bytes()
        self._stamp(key)

    def download_file(self, bucket, key, filename):
        self._count("download_file")
        self._check_bucket(bucket)
        if key not in self.objects:
            raise FakeClientError("404")
        Path(filename).write_bytes(self.objects[key])

    def delete_object(self, *, Bucket, Key):
        self._count("delete_object")
        self._check_bucket(Bucket)
        self.objects.pop(Key, None)
        self._stamps.pop(Key, None)
        return {}

    def delete_objects(self, *, Bucket, Delete):
        self._count("delete_objects")
        self._check_bucket(Bucket)
        for item in Delete.get("Objects", []):
            self.objects.pop(item["Key"], None)
            self._stamps.pop(item["Key"], None)
        return {}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return _Paginator(self)


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class _Paginator:
    def __init__(self, client: FakeS3Client):
        self._client = client

    def paginate(self, *, Bucket, Prefix=""):
        self._client._count("list_objects_v2")
        self._client._check_bucket(Bucket)
        keys = sorted(k for k in self._client.objects if k.startswith(Prefix))
        if not keys:
            yield {}            # a real paginator yields a page with no Contents
            return
        for i in range(0, len(keys), PAGE_SIZE):
            yield {"Contents": [
                {"Key": k, "Size": len(self._client.objects[k]),
                 "LastModified": self._client._stamps[k]}
                for k in keys[i:i + PAGE_SIZE]
            ]}

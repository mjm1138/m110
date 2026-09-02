"""S3 and S3-compatible object storage (issue #93).

The adapter the `backends/` seam was shaped for. Nothing about the pooled format
changes to reach a bucket: the same content-addressed objects, the same manifests,
the same restore path — only put/get/list are spoken over HTTP instead of a
filesystem.

**`endpoint_url` is the point, not a nicety.** S3-only would be the less useful
feature; Backblaze B2, Cloudflare R2 and Wasabi are where the money argument for
offsite backup actually works, and all three are the same API at a different host.

Three things here are shaped by what object storage charges for:

* **`object_sizes()` is one paginated LIST**, never a HEAD per file. A 100k-file
  library would otherwise cost ~$0.04 in requests and minutes of latency *per run*.
* **`cheap_list=False`** tells `pooled.verify` to check presence-and-size from that
  one enumeration rather than re-reading every object — a deep verify over the
  internet is a full download of the backup, with the egress bill to match.
* **`parallel_puts`** is what makes a first sync finish. Throughput here is
  latency-bound, not bandwidth-bound: a serial loop leaves the link mostly idle.

**Atomicity comes free.** A PUT is atomic and a multipart upload only becomes
visible on completion, so there is no `.part`-then-rename dance to do — S3
satisfies the base contract's "appear complete or not at all" natively, which is
what the invariant *a manifest exists ⇒ every object it names exists* rests on.

Credentials: the **secret** key lives in the OS keyring, never `settings.json`.
The access key *id* is an identifier rather than a secret and stays in settings,
because the UI has to be able to show which key is configured. With neither set,
boto3's own resolution chain applies (environment, `~/.aws/credentials`, an
instance role), so someone who already has the AWS CLI working needs to enter
nothing.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

from .. import options as _options
from ..errors import BackupDepsMissing, BackupDestinationError, deps_missing_message
from .base import Backend, Capabilities

KEYRING_SERVICE = "m110-backup-s3"
OBJECT_PREFIX = "objects/"
DELETE_BATCH = 1000             # the API's own cap on one delete_objects call
# Per-file transfer concurrency. Deliberately low: `pooled.create_snapshot`
# already runs several files at once, and the two multiply.
PER_FILE_CONCURRENCY = 2
PARALLEL_PUTS = 8
CONNECT_TIMEOUT = 10        # seconds; a wrong endpoint should say so quickly
READ_TIMEOUT = 60           # per socket read, NOT per transfer — safe for big files
MAX_ATTEMPTS = 3


def _boto3():
    try:
        import boto3                                     # noqa: F401
        import botocore                                  # noqa: F401
    except ImportError as e:
        raise BackupDepsMissing(deps_missing_message()) from e
    return boto3


def _client_config(custom_endpoint: bool):
    """botocore client settings that decide whether the non-AWS providers work.

    Two defensive settings, each a known way an S3-*compatible* service rejects a
    request Amazon accepts — and the whole point of `endpoint_url` is that those
    services are the interesting ones:

    * **`request_checksum_calculation="when_required"`.** botocore ≥1.36 attaches
      `x-amz-checksum-crc32` to every PUT by default; several S3-compatible
      services reject the header outright, so an unpinned client fails on the
      first upload against a provider that otherwise works fine.
    * **path-style addressing when a custom endpoint is set.** Virtual-host style
      (`bucket.host`) needs the provider to serve bucket subdomains with matching
      TLS. B2, R2 and Wasabi all accept path-style; MinIO-style deployments often
      accept nothing else. AWS itself keeps the default, where virtual-host is
      the supported direction.

    Both are guarded: an older botocore raises `TypeError` on the checksum kwarg,
    and returning None simply means boto3's own defaults apply.
    """
    try:
        from botocore.config import Config
    except ImportError:
        return None
    opts = {
        # botocore's defaults retry a dead endpoint for around two minutes. That
        # is the wrong answer for `probe_destination`, which exists to tell the
        # user promptly that their endpoint or bucket is wrong — and it's a
        # worker thread the dialog is waiting on. Read timeout stays generous:
        # it's per socket read, so it must not cut a slow upload short.
        "connect_timeout": CONNECT_TIMEOUT,
        "read_timeout": READ_TIMEOUT,
        "retries": {"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
    }
    if custom_endpoint:
        opts["s3"] = {"addressing_style": "path"}
    try:
        return Config(request_checksum_calculation="when_required", **opts)
    except TypeError:
        return Config(**opts)


def _transfer_config():
    """boto3's per-file transfer tuning, or None when boto3 isn't importable.

    Returning None rather than raising is what lets an **injected** client work
    with no AWS SDK installed: the conformance suite runs the real adapter
    against a fake client, which is how the contract gets proved offline."""
    try:
        from boto3.s3.transfer import TransferConfig
    except ImportError:
        return None
    return TransferConfig(max_concurrency=PER_FILE_CONCURRENCY)


# ── credentials ─────────────────────────────────────────────────────────────

def get_secret(access_key: str) -> str | None:
    """The secret key stored for this access key id, or None."""
    if not access_key:
        return None
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, access_key)
    except Exception:
        # A locked or unavailable keyring is not a crash — fall through to
        # boto3's own credential chain and let the request fail if it must.
        return None


def set_secret(access_key: str, secret: str) -> None:
    """Store (or clear) the secret key for an access key id."""
    try:
        import keyring
    except ImportError as e:
        raise BackupDepsMissing(deps_missing_message()) from e
    try:
        if secret:
            keyring.set_password(KEYRING_SERVICE, access_key, secret)
        else:
            keyring.delete_password(KEYRING_SERVICE, access_key)
    except Exception as e:
        if secret:
            raise BackupDestinationError(f"Couldn't save the key to the keyring: {e}")


def settings_credentials() -> dict:
    """Endpoint / region / access key from settings, plus the keyring secret."""
    from ... import config
    access = config.get_setting(_options.SETTING_S3_ACCESS_KEY, "") or ""
    return {
        "endpoint_url": config.get_setting(_options.SETTING_S3_ENDPOINT, "") or None,
        "region_name": config.get_setting(_options.SETTING_S3_REGION, "") or None,
        "access_key": access or None,
        "secret_key": get_secret(access),
    }


# ── the backend ─────────────────────────────────────────────────────────────

class S3Backend(Backend):

    kind = "s3"

    def __init__(self, bucket: str, root: str = "", *, client=None,
                 endpoint_url: str | None = None, region_name: str | None = None,
                 access_key: str | None = None, secret_key: str | None = None):
        self.bucket = bucket
        self.root = (root or "").strip("/")
        self._client = client           # injected in tests; built lazily otherwise
        self._conf = {
            "endpoint_url": endpoint_url, "region_name": region_name,
            "access_key": access_key, "secret_key": secret_key,
        }

    # ---- client ----
    @property
    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self):
        boto3 = _boto3()
        conf = dict(self._conf)
        if not any(conf.values()):
            conf = settings_credentials()
        endpoint = conf.get("endpoint_url")
        kwargs = {}
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if conf.get("region_name"):
            kwargs["region_name"] = conf["region_name"]
        # Only pass explicit keys when we have both; otherwise let boto3 resolve
        # from the environment, ~/.aws/credentials, or an instance role.
        if conf.get("access_key") and conf.get("secret_key"):
            kwargs["aws_access_key_id"] = conf["access_key"]
            kwargs["aws_secret_access_key"] = conf["secret_key"]
        cfg = _client_config(bool(endpoint))
        if cfg is not None:
            kwargs["config"] = cfg
        try:
            return boto3.client("s3", **kwargs)
        except Exception as e:
            raise BackupDestinationError(f"Couldn't connect to cloud storage: {e}")

    # ---- identity ----
    def describe(self) -> str:
        return f"s3://{self.bucket}/{self.root}".rstrip("/")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            hardlinks=False,        # no such concept — `latest/` is simply absent
            free_bytes=None,        # no volume to measure; a bucket has no "full"
            cheap_list=False,       # LIST is billed, so verify goes shallow
            parallel_puts=PARALLEL_PUTS,
        )

    def ensure_root(self) -> None:
        """Object stores have no directories to create, so this is the
        reachability and permission check instead — which is exactly when the
        caller wants to hear that the bucket is wrong."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except BackupDepsMissing:
            raise
        except Exception as e:
            raise BackupDestinationError(
                f"Can't reach bucket '{self.bucket}': {_reason(e)}")

    # ---- keys ----
    def _key(self, key: str) -> str:
        return f"{self.root}/{key}" if self.root else key

    def _rel(self, key: str) -> str:
        if self.root and key.startswith(self.root + "/"):
            return key[len(self.root) + 1:]
        return key

    def _paginate(self, prefix: str) -> Iterator[dict]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []) or []:
                yield item

    # ---- objects ----
    def object_sizes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in self._paginate(self._key(OBJECT_PREFIX)):
            sha = item["Key"].rsplit("/", 1)[-1]
            if sha:
                out[sha] = int(item.get("Size", 0))
        return out

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def put_file(self, key: str, src: Path, *, size: int | None = None) -> None:
        # `Config` is passed only when boto3 is importable, so an injected client
        # (the conformance suite's fake) needs no AWS SDK present at all.
        kwargs = {}
        cfg = _transfer_config()
        if cfg is not None:
            kwargs["Config"] = cfg
        try:
            self.client.upload_file(str(src), self.bucket, self._key(key), **kwargs)
        except Exception as e:
            raise BackupDestinationError(
                f"Upload failed for {Path(src).name}: {_reason(e)}")

    def put_bytes(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)
        except Exception as e:
            raise BackupDestinationError(f"Write failed for {key}: {_reason(e)}")

    def get_file(self, key: str, dst: Path) -> None:
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        try:
            self.client.download_file(self.bucket, self._key(key), str(tmp))
        except Exception as e:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise _read_error(key, e)
        os.replace(tmp, dst)

    def get_bytes(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            return resp["Body"].read()
        except Exception as e:
            raise _read_error(key, e)

    def list_keys(self, prefix: str) -> Iterator[tuple[str, int, float]]:
        for item in self._paginate(self._key(prefix)):
            last = item.get("LastModified")
            # The GC grace window compares against *storage* time, which is what
            # LastModified is — a re-put of identical bytes refreshes it, which is
            # the behaviour the grace window wants.
            mtime = last.timestamp() if hasattr(last, "timestamp") else 0.0
            yield self._rel(item["Key"]), int(item.get("Size", 0)), mtime

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
        except Exception:
            pass                    # a missing key is not an error (base contract)

    def delete_many(self, keys: Iterable[str]) -> int:
        batch: list[dict] = []
        removed = 0
        for key in keys:
            batch.append({"Key": self._key(key)})
            if len(batch) >= DELETE_BATCH:
                removed += self._delete_batch(batch)
                batch = []
        if batch:
            removed += self._delete_batch(batch)
        return removed

    def _delete_batch(self, batch: list[dict]) -> int:
        try:
            self.client.delete_objects(Bucket=self.bucket,
                                       Delete={"Objects": batch, "Quiet": True})
            return len(batch)
        except Exception:
            # Fall back to one-by-one rather than reporting a sweep that didn't
            # happen — a wrong "swept N" is worse than a slow sweep.
            removed = 0
            for item in batch:
                try:
                    self.client.delete_object(Bucket=self.bucket, Key=item["Key"])
                    removed += 1
                except Exception:
                    pass
            return removed

    def close(self) -> None:
        self._client = None


def _read_error(key: str, e: Exception) -> Exception:
    """Missing keys surface as `KeyError` because that is what the format's
    callers already handle — `pooled.restore` skips `(OSError, KeyError)` — so a
    gap in the store degrades to a skipped file rather than a failed restore."""
    name = e.__class__.__name__
    code = ""
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        code = str(resp.get("Error", {}).get("Code", ""))
    if code in ("NoSuchKey", "404", "NotFound") or name in ("NoSuchKey", "ClientError"):
        return KeyError(key)
    return BackupDestinationError(f"Read failed for {key}: {_reason(e)}")


def _reason(e: Exception) -> str:
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        msg = resp.get("Error", {}).get("Message")
        if msg:
            return str(msg)
    return str(e)

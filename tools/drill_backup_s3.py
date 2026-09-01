"""TESTING.md §2.5b — the cloud-backup drill, against a REAL MinIO server.

Usage (from the repo root, per TESTING §0.1 — tools/ needs the path set):

    PYTHONPATH=$PWD python tools/drill_backup_s3.py /path/to/minio [scratch-dir]

Give it a MinIO server binary (https://dl.min.io/server/minio/release/…) and it
does the rest: starts MinIO on 127.0.0.1:9000 with throwaway credentials, builds
the synthetic corpus, and drives the backup engine through everything §2.5b asks
for that isn't about the dialog itself — probe, both scope tiers, verify at both
depths, whole-tree restore with a byte-for-byte diff, retention, the object sweep,
recovery with `restore.py` from a mirror of the bucket, boto3's own credential
chain with M110's fields blank, and a server killed mid-backup. Then it stops
MinIO. ~5 seconds, 57 checks. Exit status is the verdict.

Why this exists rather than a pytest: `tests/test_backup_backends.py` proves the
adapter against an injected fake, and `tests/test_backup_s3_client.py` proves the
boto3 wiring with no network — but neither talks to a real S3 implementation. This
does: real path-style addressing behind a custom endpoint, real multipart, real
LIST pagination, real error shapes. It needs a binary that isn't a Python package,
so it lives beside `smoke_mcp.py` as a tool, not in the suite.

SAFETY: settings live at ~/.m110/settings.json, OUTSIDE the data root. Both are
isolated to a scratch directory BEFORE anything that reads them is imported. The
OS keyring is never touched — the secret is supplied by patching `get_secret` —
so no keychain entry is written and no permission prompt can hang the run. Needs
boto3 (`pip install -e ".[dev]"`).
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
ENDPOINT = "http://127.0.0.1:9000"
BUCKET = "m110test"
DEST = f"s3://{BUCKET}/backups"
KEY, SECRET = "minioadmin", "minioadmin"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    minio_bin = pathlib.Path(sys.argv[1]).resolve()
    if not minio_bin.is_file():
        print(f"no MinIO binary at {minio_bin}")
        return 2
    scratch = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else \
        pathlib.Path(tempfile.mkdtemp(prefix="m110-drill-"))
    if len(sys.argv) > 2 and scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    print(f"scratch: {scratch}")

    # ── the worktree trap (TESTING §0.1): launched by path, sys.path[0] is tools/
    # and the editable finder then serves the MAIN checkout — a clean green run
    # from code that may have no S3 backend at all. PYTHONPATH makes this repo
    # win; the assertion makes a silent miss impossible.
    import m110
    assert pathlib.Path(m110.__file__).is_relative_to(REPO), \
        f"running {m110.__file__}, not this repo — run with PYTHONPATH=$PWD from {REPO}"
    print(f"m110 from {m110.__file__}")

    # ── isolate settings + data root before any m110 import that reads them ──
    from m110 import config
    config.SETTINGS_FILE = scratch / "settings.json"
    config.APP_CONFIG_DIR = scratch / "app_config"
    config.APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    from m110 import backup
    from m110.backup.backends import s3 as s3backend

    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        print("boto3 is needed: pip install -e '.[dev]'")
        return 2

    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))
        print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))

    def section(title: str) -> None:
        print(f"\n── {title}")

    # ── corpus ───────────────────────────────────────────────────────────────
    section("corpus")
    store = scratch / "corpus"          # --out DIR is the store itself
    subprocess.run([sys.executable, str(REPO / "tools" / "make_test_corpus.py"),
                    "--out", str(store), "--no-tar"],
                   check=True, capture_output=True,
                   env={**os.environ, "PYTHONPATH": str(REPO)})
    config.set_data_root(store)
    n_files = sum(1 for p in store.rglob("*") if p.is_file())
    check("corpus store built", store.is_dir() and n_files > 50, f"{n_files} files")
    if n_files <= 50:
        print("no corpus — nothing below would mean anything")
        return 1

    # ── MinIO ────────────────────────────────────────────────────────────────
    section("minio")
    minio_data = scratch / "minio-data"
    minio_data.mkdir(exist_ok=True)
    minio_log = open(scratch / "minio.log", "w")
    env = {**os.environ, "MINIO_ROOT_USER": KEY, "MINIO_ROOT_PASSWORD": SECRET}
    argv = [str(minio_bin), "server", str(minio_data), "--address", ":9000",
            "--console-address", ":9001"]

    def start_minio():
        return subprocess.Popen(argv, env=env, stdout=minio_log, stderr=subprocess.STDOUT)

    def raw():
        return boto3.client("s3", endpoint_url=ENDPOINT, region_name="us-east-1",
                            aws_access_key_id=KEY, aws_secret_access_key=SECRET,
                            config=BotoConfig(s3={"addressing_style": "path"},
                                              connect_timeout=2,
                                              retries={"max_attempts": 1}))

    def wait_up(proc) -> bool:
        for _ in range(60):
            try:
                raw().list_buckets()
                return True
            except Exception:
                time.sleep(0.5)
        return False

    def keys(prefix: str = "") -> list[str]:
        out: list[str] = []
        for page in raw().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
            out += [o["Key"] for o in page.get("Contents", [])]
        return out

    def objects() -> set[str]:
        return {k for k in keys() if "/objects/" in k}

    minio = start_minio()
    try:
        if not wait_up(minio):
            print(f"MinIO did not come up — see {scratch / 'minio.log'}")
            return 1
        check("MinIO server up", True, f"pid {minio.pid}")
        raw().create_bucket(Bucket=BUCKET)
        check("bucket created", BUCKET in {b["Name"] for b in raw().list_buckets()["Buckets"]})

        # ── credentials as the dialog saves them (secret patched, keyring untouched)
        section("credentials")
        config.save_setting(backup.SETTING_S3_ENDPOINT, ENDPOINT)
        config.save_setting(backup.SETTING_S3_REGION, "us-east-1")
        config.save_setting(backup.SETTING_S3_ACCESS_KEY, KEY)
        config.save_setting(backup.SETTING_DEST, DEST)
        secrets = {KEY: SECRET}
        s3backend.get_secret = lambda access: secrets.get(access)
        settings = json.loads(config.SETTINGS_FILE.read_text())
        check("only the access key id is in settings.json",
              settings.get(backup.SETTING_S3_ACCESS_KEY) == KEY
              and "secret" not in json.dumps(settings).lower())

        # ── probe / Test connection ──────────────────────────────────────────
        section("probe / Test connection")
        t0 = time.time()
        info = backup.probe_destination(DEST)
        check("Test connection → connected", info.exists and info.writable and info.error is None,
              f"{time.time() - t0:.2f}s")
        check("kind=s3, pooled forced, no free_bytes, no hardlinks",
              info.kind == "s3" and info.format == backup.FORMAT_POOLED and info.format_forced
              and info.free_bytes is None and info.hardlinks is False)
        check("no backups here yet", info.snapshot_count == 0)

        secrets[KEY] = "wrong-secret"
        t0 = time.time()
        bad = backup.probe_destination(DEST)
        dt = time.time() - t0
        check("wrong secret → clear error, fast", (not bad.exists) and bool(bad.error) and dt < 15,
              f"{dt:.2f}s: {bad.error!r}")
        secrets[KEY] = SECRET

        t0 = time.time()
        bad = backup.probe_destination(f"s3://no-such-bucket-{os.getpid()}/x")
        dt = time.time() - t0
        check("wrong bucket → clear error, fast", (not bad.exists) and bool(bad.error) and dt < 15,
              f"{dt:.2f}s: {bad.error!r}")

        try:
            backup.parse_destination("s3:///backups")
            check("malformed s3:/// rejected", False)
        except backup.BackupError as e:
            check("malformed s3:/// rejected", True, str(e)[:60])

        # ── first backup — everything ────────────────────────────────────────
        section("Back up now — everything")
        opts = backup.options_from_settings(DEST)
        check("scope defaults to everything", opts.scope == backup.SCOPE_EVERYTHING)
        t0 = time.time()
        r1 = backup.create_snapshot(opts)
        check("backup completed", not r1.get("cancelled") and r1["file_count"] > 0,
              f"{r1['file_count']} files, {r1['objects_new']} objects, "
              f"{r1['bytes_new']:,} B in {time.time() - t0:.1f}s")
        check("snapshot location is an s3:// URI",
              r1["snapshot"].startswith(f"s3://{BUCKET}/backups/M110-Backups/"), r1["snapshot"])
        check("no hardlinks, nothing linked", r1["hardlinks"] is False and r1["linked"] == 0)
        check("scope recorded in the result", r1["scope"] == backup.SCOPE_EVERYTHING)

        rel_keys = {k.split("/M110-Backups/", 1)[1].split("/", 1)[1]
                    for k in keys() if "/M110-Backups/" in k}
        top = {k.split("/")[0] for k in rel_keys}
        check("pooled layout present", {"objects", "snapshots"} <= top, str(sorted(top)))
        check("recovery artifacts present",
              {"INDEX.tsv", "restore.py", "README.txt", "latest-manifest.json.gz"} <= top)
        check("NO latest/ tree", "latest" not in top)
        check("objects sharded objects/ab/cd/<sha256>",
              all(len(k.split("/")) == 4 and len(k.split("/")[3]) == 64
                  for k in rel_keys if k.startswith("objects/")))

        # ── second backup ────────────────────────────────────────────────────
        section("second backup")
        snaps = backup.list_snapshots(DEST)
        check("list_snapshots sees it, with a ref and no path",
              len(snaps) == 1 and snaps[0].path is None and snaps[0].ref is not None)
        check("snapshot carries its scope", snaps[0].scope == backup.SCOPE_EVERYTHING)
        before = objects()
        r2 = backup.create_snapshot(backup.options_from_settings(DEST))
        check("second backup uploads ~nothing", r2["objects_new"] == 0 and r2["bytes_new"] == 0,
              f"objects_new={r2['objects_new']} bytes_new={r2['bytes_new']}")
        check("no new objects in the bucket", objects() == before)
        check("two snapshots listed", len(backup.list_snapshots(DEST)) == 2)

        # ── verify ───────────────────────────────────────────────────────────
        section("verify")
        snap = backup.list_snapshots(DEST)[0]
        t0 = time.time()
        v = backup.verify(snap)
        dt = time.time() - t0
        check("shallow verify ok (default on a bucket)", v["ok"] and v["deep"] is False,
              f"{v['checked']} checked in {dt:.2f}s")
        t0 = time.time()
        vd = backup.verify(snap, deep=True)
        dtd = time.time() - t0
        check("deep verify ok on request", vd["ok"] and vd["deep"] is True, f"{dtd:.2f}s")
        check("shallow is faster than deep", dt < dtd, f"{dt:.2f}s vs {dtd:.2f}s")
        obj_key = next(iter(objects()))
        orig = raw().get_object(Bucket=BUCKET, Key=obj_key)["Body"].read()
        raw().put_object(Bucket=BUCKET, Key=obj_key, Body=orig[:-1] if len(orig) > 1 else b"x")
        vbad = backup.verify(snap)
        check("shallow verify catches a truncated object", (not vbad["ok"]) and vbad["mismatched"])
        raw().put_object(Bucket=BUCKET, Key=obj_key, Body=orig)
        check("…and passes again once repaired", backup.verify(snap)["ok"])

        # ── restore ──────────────────────────────────────────────────────────
        section("restore")
        files = backup.snapshot_files(snap)
        journal = next(f for f in files if f.endswith("journal.md"))
        few = sorted(files)[:3] + [journal]
        out_few = scratch / "restored-few"
        rr = backup.restore(snap, few, out_few)
        check("restore a few files", rr["written"] == len(set(few))
              and (out_few / journal).read_bytes() == (store / journal).read_bytes())
        out_all = scratch / "restored-all"
        t0 = time.time()
        ra = backup.restore(snap, sorted(files), out_all)
        check("restore whole tree", ra["written"] == len(files) and ra["skipped"] == 0,
              f"{ra['written']} files in {time.time() - t0:.1f}s")
        differ = [f for f in files if not (out_all / f).is_file()
                  or (store / f).read_bytes() != (out_all / f).read_bytes()]
        check("every restored file is byte-identical", not differ, f"{len(differ)} differ")
        left_out = [str(p.relative_to(store)) for p in store.rglob("*") if p.is_file()
                    and str(p.relative_to(store)) not in files
                    and not backup.is_excluded(str(p.relative_to(store)).replace(os.sep, "/"))]
        check("nothing in scope was left out of the backup", not left_out, str(left_out[:5]))

        # ── Essentials scope ─────────────────────────────────────────────────
        section("Essentials scope")
        config.save_setting(backup.SETTING_SCOPE, backup.SCOPE_ESSENTIALS)
        r3 = backup.create_snapshot(backup.options_from_settings(DEST))
        check("essentials backs up fewer files", r3["file_count"] < r1["file_count"],
              f"{r3['file_count']} vs {r1['file_count']}")
        newest = backup.list_snapshots(DEST)[0]
        nf = backup.snapshot_files(newest)
        check("no frame tiers in the essentials manifest",
              not any(t in f for f in nf for t in ("/lights/", "/rejected/", "/previews/")))
        check("no archived runs in the essentials manifest", not any("/archive/" in f for f in nf))
        check("journals, finished, stacks, presets still there",
              any(f.endswith("journal.md") for f in nf) and any("/finished/" in f for f in nf)
              and any("/stacks/" in f or "/seestar-stacks/" in f for f in nf)
              and any("/presets/" in f for f in nf))
        check("essentials snapshot labelled with its scope", newest.scope == backup.SCOPE_ESSENTIALS)
        older = next(s for s in backup.list_snapshots(DEST) if s.scope == backup.SCOPE_EVERYTHING)
        light = next(f for f in backup.snapshot_files(older) if "/lights/" in f)
        out_light = scratch / "restored-light"
        rl = backup.restore(older, [light], out_light)
        check("a light frame still restores from the older wide snapshot after narrowing",
              rl["written"] == 1 and (out_light / light).read_bytes() == (store / light).read_bytes())

        # ── retention + sweep ────────────────────────────────────────────────
        section("retention")
        check("three snapshots present", len(backup.list_snapshots(DEST)) == 3)
        n_before = len(objects())
        rr = backup.apply_retention(DEST, min_free_gb=1_000_000)
        check("min-free has no effect on a bucket", rr["pruned"] == 0 and len(backup.list_snapshots(DEST)) == 3)
        rr = backup.apply_retention(DEST, keep=1)
        check("keep=1 prunes to the newest", rr["pruned"] == 2 and len(backup.list_snapshots(DEST)) == 1,
              f"pruned={rr['pruned']} swept={rr['swept']} (0 is right: the 24h grace window)")
        check("the survivor is the essentials snapshot",
              backup.list_snapshots(DEST)[0].scope == backup.SCOPE_ESSENTIALS)
        check("objects untouched inside the grace window", len(objects()) == n_before)
        sw = backup.sweep_objects(DEST, now=time.time() + 2 * 86400)
        n_after = len(objects())
        check("past the window, the sweep frees unreferenced objects", sw["swept"] > 0 and n_after < n_before,
              f"{n_before} → {n_after}, swept {sw['swept']}")
        check("…and the survivor still verifies", backup.verify(backup.list_snapshots(DEST)[0])["ok"])
        check("never deletes the last one", backup.apply_retention(DEST, keep=1)["pruned"] == 0)

        # ── recovery without M110 ────────────────────────────────────────────
        section("recovery without M110")
        mirror = scratch / "frombucket"
        prefix = "backups/M110-Backups/"
        for k in keys(prefix=prefix):
            rel = k[len(prefix):].split("/", 1)[1]
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw().get_object(Bucket=BUCKET, Key=k)["Body"].read())
        check("restore.py + README.txt travelled with the data",
              (mirror / "restore.py").is_file() and (mirror / "README.txt").is_file())
        rec = scratch / "recovered"
        proc = subprocess.run([sys.executable, "restore.py", "latest-manifest.json.gz", str(rec)],
                              cwd=mirror, capture_output=True, text=True)
        rec_files = [p for p in rec.rglob("*") if p.is_file()] if rec.exists() else []
        check("stdlib-only restore.py rebuilds the tree from a bucket mirror",
              proc.returncode == 0 and len(rec_files) == len(nf), f"rc={proc.returncode} {len(rec_files)} files")
        check("recovered journal matches",
              (rec / journal).is_file() and (rec / journal).read_bytes() == (store / journal).read_bytes())

        # ── blank fields → boto3's own chain ─────────────────────────────────
        section("blank fields → boto3's own credential chain")
        config.save_setting(backup.SETTING_S3_ACCESS_KEY, None)
        config.save_setting(backup.SETTING_S3_ENDPOINT, None)
        s3backend.get_secret = lambda access: None
        os.environ.update(AWS_ACCESS_KEY_ID=KEY, AWS_SECRET_ACCESS_KEY=SECRET,
                          AWS_ENDPOINT_URL_S3=ENDPOINT)
        p = backup.probe_destination(DEST)
        check("connects with no M110 credentials configured", p.exists and p.writable, p.error or "")
        for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3"):
            os.environ.pop(var, None)
        config.save_setting(backup.SETTING_S3_ENDPOINT, ENDPOINT)
        config.save_setting(backup.SETTING_S3_ACCESS_KEY, KEY)
        s3backend.get_secret = lambda access: secrets.get(access)

        # ── server disappears mid-run ────────────────────────────────────────
        section("server disappears mid-run")
        config.save_setting(backup.SETTING_SCOPE, backup.SCOPE_EVERYTHING)
        manifests_before = {k for k in keys() if "/snapshots/" in k}
        real_put = s3backend.S3Backend.put_file

        def slow_put(self, key, src, **kw):        # so the kill lands mid-run
            time.sleep(0.15)
            return real_put(self, key, src, **kw)

        s3backend.S3Backend.put_file = slow_put
        outcome: dict = {}

        def run():
            try:
                outcome["res"] = backup.create_snapshot(backup.options_from_settings(DEST))
            except Exception as e:                  # noqa: BLE001 — that's the point
                outcome["exc"] = e

        th = threading.Thread(target=run)
        t0 = time.time()
        th.start()
        time.sleep(1.5)
        minio.terminate()
        minio.wait(timeout=10)
        th.join(timeout=120)
        dt = time.time() - t0
        s3backend.S3Backend.put_file = real_put
        exc = outcome.get("exc")
        check("backup fails rather than hangs when the server vanishes", exc is not None and dt < 90,
              f"{dt:.1f}s: {type(exc).__name__}: {str(exc)[:60]}")
        check("it is our error type, not a raw botocore exception", isinstance(exc, backup.BackupError))
        minio = start_minio()
        check("MinIO restarted", wait_up(minio))
        check("no snapshot manifest left behind by the failed run",
              {k for k in keys() if "/snapshots/" in k} == manifests_before)
        r4 = backup.create_snapshot(backup.options_from_settings(DEST))
        check("re-run completes and resumes", not r4.get("cancelled") and r4["file_count"] == r1["file_count"]
              and r4["objects_new"] < r1["objects_new"],
              f"objects_new={r4['objects_new']} of {r4['file_count']} files")
    finally:
        section("teardown")
        if minio.poll() is None:
            minio.terminate()
            minio.wait(timeout=10)
        minio_log.close()
        check("MinIO stopped", minio.poll() is not None)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print(f"\n{'=' * 70}\n{passed} passed, {len(failed)} failed")
    for n, d in failed:
        print(f"  FAIL  {n}  {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# Backing up your library

← [Back to the guide](README.md)

M110 has a built-in backup system that makes **dated snapshots** of your library to a
destination you choose — an external or network drive separate from your working
disk, or cloud storage. Open it from **Library → Back up / Restore**.

Whatever the details below, two things are always true:

- **Only what changed is stored** each time. Your raw subs never change, so they're
  stored once and shared by every later backup.
- **Every backup restores on its own.** There is no chain to replay: restoring a
  backup from three months ago is exactly as easy, and as complete, as restoring
  last night's.

## Two ways to store backups

Some destinations can *share* a file between backups — that is, record "this backup
also contains that file" without storing a second copy. Most local and external
drives can; some network shares, appliance NASes and exFAT drives can't. M110 checks
when you choose a destination and tells you which kind you have.

That check decides how backups are stored. You'll see the choice under the
destination, and normally you can leave it alone.

### Mirrored backups (the default)

```
<destination>/M110-Backups/<your-library-name>/
  2026-07-10_02-00-00/    a full tree — Objects/, Images/, etc.
  2026-07-09_02-00-00/
  …
```

Every backup is a complete, browsable copy of your library — dated folders you can
open in Finder or Explorer and just *use*. Files unchanged since the previous backup
are **hardlinked** to it rather than copied again (see
[Hardlinks](processing.md#hardlinks--what-they-are-and-why-it-matters)), the same
trick `rsync --link-dest` and Time Machine use. Ten backups of a 200 GB library cost
~200 GB plus what changed, not 2 TB.

Its real advantage is what happens on the worst day: **a mirrored backup needs no
software at all to restore.** It's your files, in the right folders. Drag them back.

This is why it stays the default wherever it works.

### Pooled backups

For destinations that *can't* share files, mirrored backups would quietly store a
complete copy of your library every single night. So M110 switches to pooling
instead, and says so:

```
<destination>/M110-Backups/<your-library-name>/
  objects/…               every file, stored once, named by its contents
  snapshots/…             one small index per backup, listing what it contained
  latest/                 a browsable copy of the newest backup (where possible)
  INDEX.tsv  restore.py  README.txt
```

Each file is stored once under a name derived from its contents, and each backup is a
small index naming the files it contained. Two backups that contain the same sub
point at the same stored copy — which is the same saving as hardlinking, done by
M110 instead of by the disk. That's what makes it work anywhere.

**Getting your files back out.** The trade is that `objects/` on its own isn't
browsable — the stored files are named by content, not by path. So a pooled backup
carries its own way back, right next to the data:

- **`latest/`** — a browsable copy of the most recent backup with real filenames,
  costing no extra space. Present whenever the destination can manage it.
- **`INDEX.tsv`** — every file in the newest backup as plain text: path, name of the
  stored copy, size. Readable in any text editor.
- **`restore.py`** — rebuilds files from any backup using nothing but a standard
  Python install. No M110 required:
  ```
  python3 restore.py                                    # newest backup → ./restored
  python3 restore.py snapshots/<name>.json.gz ~/out      # a specific backup
  python3 restore.py latest-manifest.json.gz ~/out Images/M51   # just one target
  ```
- **`README.txt`** — the same explanation, in the folder, for future you.

The indexes themselves are gzipped JSON — `gunzip -c` reads them anywhere.

### Switching between them

You can change the setting at any time. Backups already at that destination stay
listable, verifiable and restorable in both formats — switching never strands a
backup you already have. The only case where M110 decides for you is a destination
that can't share files, where mirrored isn't a real option.

## Backing up to cloud storage

Instead of choosing a folder, you can type a bucket address as the destination:

```
s3://your-bucket/m110-backups
```

That works with **Amazon S3** and with anything that speaks the same protocol —
**Backblaze B2**, **Cloudflare R2**, **Wasabi**, MinIO and others. The cheaper
providers are usually the point, which is why the **Endpoint URL** field matters:
it's the address of your provider's API. Leave it blank for Amazon S3.

A **Cloud storage** section appears as soon as the destination starts with `s3://`:

| Field | What to put in it |
|---|---|
| **Endpoint URL** | Your provider's API URL. Blank for Amazon S3. B2: `https://s3.<region>.backblazeb2.com`. R2: `https://<account-id>.r2.cloudflarestorage.com`. |
| **Region** | Your bucket's region. Cloudflare R2 uses `auto`. |
| **Access key ID** | The key's identifier. |
| **Secret key** | The secret half. |

Press **Test connection** to check them before you rely on it. If you already use
the AWS command line, you can leave all four blank and M110 will use the
credentials you've already configured.

**Your secret key is stored in your operating system's keyring** — macOS Keychain,
Windows Credential Manager, or your Linux desktop's secret service — never in
M110's settings file. Once saved, the field stays empty and says so; leaving it
blank keeps the key you already have.

Cloud backups are always stored in the pooled format, because a bucket has no
concept of sharing a file between folders. Everything else works the same: each
file is stored once, only new files upload after the first backup, and every
backup restores on its own.

### Choosing how much goes to the cloud

Your light frames are usually around **99% of your library's size**. Backing all of
them up to metered storage can take days and cost real money, and for many people
that's not what "offsite" needs to mean.

The **Back up:** setting offers two choices:

- **Everything** — the whole library, light frames included. The right choice for a
  drive or network share, and the default.
- **Essentials** — everything *except* your raw light frames and archived
  processing runs. Your journals, finished images, stacks, plans, presets and
  settings all still go. This is typically a few percent of the size.

A good pattern is Everything to a local drive, and Essentials to the cloud: the
frames stay where there's room for them, and the work you can't recapture is
offsite.

**Changing to Essentials doesn't delete anything.** Backups you already made keep
their light frames until they're eventually pruned by your retention settings, so
nothing disappears the moment you switch. When you restore, a backup made without
light frames is labelled, so you can't mistake it for one that lost them.

> **A note on cost:** on Amazon S3, *downloading* is the expensive direction, so a
> full restore costs more than the backups did. On B2 and R2 it's cheap or free.
> It's also worth setting a lifecycle rule on your bucket to abort incomplete
> multipart uploads — a cancelled upload can otherwise leave fragments that quietly
> accrue charges.

## What the sharing means (and how it differs from the sandbox)

Worth being clear about, because backups and the processing sandbox both share files
but the implications are **opposite**:

- The **processing sandbox** shares storage with your *live* library — so the sandbox
  is *not* a backup.
- **Backups** share only with each other on the backup disk, and are byte-copied from
  your live library. So they are a **real, independent copy** — deleting or losing
  your working library does not touch them.

Practical consequences:

- **Deleting a backup is safe.** Only the data unique to it is freed; everything
  another backup still needs stays. (Retention, below, does exactly this.)
- **Keep it on one volume.** All backups for a library live under one destination.
- **Don't edit files inside the backup folder.** In both formats a file may be shared
  by several backups, so an edit would change all of them. Pooled backups mark stored
  files read-only for this reason; copy a file out before working on it.

## Automation & retention

- **Automatic backups** run on a schedule (default: at most one every 12 hours), so a
  fresh capture session gets protected without you thinking about it.
- **Retention** lets you keep the *N* newest backups; older ones are pruned. The
  default keeps everything — there is deliberately no "delete anything older than *X*
  days" rule, so a gap in use can never silently wipe your history.
- **A minimum-free-space guard** prunes old backups rather than filling the
  destination. (Not applicable to cloud storage, which has no volume to fill — the
  setting is greyed out for a bucket.)

## Restoring

**Library → Back up / Restore → Restore…** lets you pick a backup by date, choose
specific files or the whole tree, and either **extract to a folder** (safe default)
or restore **into your library** (with a conflict preview and confirmation first).
There's also a **Verify integrity** action that re-checks a backup against its
recorded checksums. For a cloud backup, verifying checks that every file is present
and the right size rather than re-reading all of it — a full re-check would mean
downloading the entire backup, which you'd be billed for.

> **What's not in a backup:** regenerable app state — thumbnails, derived rollups,
> the session index, and the Siril sandboxes — is skipped, because M110 rebuilds it
> automatically. Your catalog, notes, subs, stacks, and finished renders are all
> included.

Next: **[Session planning →](planning.md)**

# Backing up your library

← [Back to the guide](README.md)

M110 has a built-in backup system that makes **dated snapshots** of your library to a
destination you choose — ideally an external or network drive, separate from your
working disk. Open it from **Library → Back up / Restore**.

## How it works

Each backup is a **complete, dated snapshot** of your library:

```
<destination>/M110-Backups/<your-library-name>/
  2026-07-10_02-00-00/    a full tree — Objects/, Images/, etc.
  2026-07-09_02-00-00/
  …
```

The first snapshot is a full copy. Every later snapshot is *also* a full,
independent tree — but files that haven't changed since the previous snapshot are
**hardlinked** to it instead of copied again. (See
[Hardlinks](processing.md#hardlinks--what-they-are-and-why-it-matters) for the
concept.) This is the same trick `rsync --link-dest` and Time Machine use.

**Why that's good:**

- **Incrementals are nearly free.** Ten snapshots of a 200 GB library don't cost
  2 TB — they cost ~200 GB plus whatever changed between them. Since your raw subs
  never change, they're stored once and shared across every snapshot.
- **Every snapshot is browsable and complete.** There's no chain of "diffs" to
  replay — each dated folder is a full library you can open directly in your file
  manager or restore from.

## What the hardlinks mean here (and how it differs from the sandbox)

This is worth being clear about, because backups and the processing sandbox both use
hardlinks but the implications are **opposite**:

- The **processing sandbox** links share storage with your *live* library — so the
  sandbox is *not* a backup.
- **Backup snapshots** link only to *each other* on the backup disk, and are
  byte-copied from your live library. So the snapshots are a **real, independent
  copy** — deleting or losing your working library does not touch them.

Practical consequences:

- **Deleting a snapshot is safe.** Because unchanged files are shared between
  snapshots, removing one only frees the bytes *unique* to it — your other snapshots
  and your live library are unaffected. (Retention, below, does exactly this.)
- **The destination must support hardlinks to get the space savings.** A normal
  local/attached disk does. Some SMB shares and exFAT drives don't — M110 probes the
  destination and automatically falls back to full copies if needed (correct, just
  larger).
- **Keep it on one volume.** Snapshots dedup by sharing inodes, which only works
  within a single filesystem, so all snapshots for a library live under one
  destination.

## Automation & retention

- **Automatic backups** run on a schedule (default: at most one every 12 hours), so a
  fresh capture session gets protected without you thinking about it.
- **Retention** lets you keep the *N* newest snapshots; older ones are pruned (which,
  per the note above, only frees their unique data). The default keeps everything —
  there is deliberately no "delete anything older than *X* days" rule, so a gap in
  use can never silently wipe your history.
- **A minimum-free-space guard** stops a backup that would fill the destination.

## Restoring

**Library → Back up / Restore → Restore…** lets you pick a snapshot by date, choose
specific files or the whole tree, and either **extract to a folder** (safe default)
or restore **into your library** (with a conflict preview and confirmation first).
There's also a **Verify integrity** action that checks a snapshot against its
recorded checksums.

> **What's not in a snapshot:** regenerable app state — thumbnails, derived rollups,
> the session index, and the Siril sandboxes — is skipped, because M110 rebuilds it
> automatically. Your catalog, notes, subs, stacks, and finished renders are all
> included.

Next: **[Session planning →](planning.md)**

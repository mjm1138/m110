# Processing prep & hardlinks

← [Back to the guide](README.md)

M110 **prepares a clean, self-contained workspace** so you can process in
[Siril](https://siril.org/), then imports your finished work back into the library.
This is the "prepare-and-guide" model — with one exception: M110 *can* run the
**stacking** step for you, unattended, because that's the part nobody wants to sit
through. See [Stacking without opening Siril](#stacking-without-opening-siril) below.

## What M110 sets up

After an ingest (and again whenever it notices a target missing one), M110 builds a
**Siril sandbox** at `Images/<target>/siril/`:

```
Images/<target>/siril/
  lights/            your light subs, ready for Siril (see "Hardlinks" below)
  presets/           a Siril preset tuned to your frame count
  process/           scratch space for Siril's intermediate files
  next-steps.md      a short, per-target guide to what to do in Siril
  archive/<ts>/      past runs, kept so you can re-process later
```

Open `next-steps.md`, follow it in Siril, and when you have a result, use **Import
finished work** (from the object's detail pane) to pull the render into `finished/`
and the stack into `stacks/`. M110 then archives the run so the sandbox is ready for
next time — it never deletes your lights or your work.

You don't trigger any of this by hand: prep is automatic and idempotent. If you edit
a preset, M110 preserves your edits and won't overwrite them.

## Process in Siril (one click)

You don't have to find the working folder yourself. **Right-click an object** — in the
Library, on the Processing page, or use the **Process in Siril** button on its detail
page — and M110 launches Siril already pointed at that object's `siril/` sandbox as its
**working directory**.

M110 finds Siril automatically in the usual place. If yours is installed somewhere
unusual, set its location under **Preferences → Processing tools** (on macOS you can pick
`Siril.app` directly; elsewhere, the Siril executable).

> ### ⚠ Quit Siril when you finish an object
>
> **When you're done processing an object, quit Siril before moving to the next one.**
>
> M110 can only set Siril's working directory *as Siril launches*. If Siril is **already
> open**, clicking "Process in Siril" for a different object just brings the existing
> window to the front — it **does not** switch the working directory. You'd then be
> processing the new object while Siril is still pointed at the previous object's folder,
> and your results would land in the wrong place.
>
> Quitting Siril between objects guarantees the next "Process in Siril" opens fresh, at
> the correct folder. (If you'd rather keep Siril open, use **Reveal working folder** and
> set the directory yourself — see below.)

### If you prefer to open Siril yourself

The one easy mistake when doing it by hand is pointing Siril's working directory at the
object folder (`Images/<target>/`) instead of its `siril/` sub-folder — Siril then saves
your results one level too high. To avoid it, use **Reveal working folder** (the button
beside Process in Siril, and a right-click option): it opens the `siril/` folder in your
file manager so you can set *that* as Siril's working directory.

(And if you do save outside the sandbox anyway, M110 also scans the object folder as a
fallback when importing, so your work isn't lost.)

You can also right-click any image in an object's gallery to **Open in default app** or
**Reveal in file manager**.

---

## Stacking without opening Siril

Stacking is the long, unattended part: load hundreds of subs, calibrate, register,
reject the bad ones, combine. There's nothing to look at while it happens, and on a
mosaic it runs for hours. So M110 will do it for you, from the command line:

```
m110-stack "M101"
```

That **measures and proposes — it doesn't stack**. You get how many frames you have,
whether exposures or gain are mixed, whether it's a mosaic, how deep the coverage
actually is, and the settings that supports (drizzle, rejection, weighting,
feathering), each with the reason it was picked. Read it, then:

```
m110-stack "M101" --run
```

It prints the current stage every minute with how long it's been there, so a quiet
hour looks like progress rather than a hang, and the full Siril log streams to
`siril_stack.log` in the working folder. The result lands in the sandbox, where
**Import finished work** already looks for it.

Useful flags: `--only-exposure 30` (stack one exposure when a set mixes them),
`--exclude-night 2026-06-10`, `--restack` (retry stack settings without repeating
registration), `--handoff` (see below). `m110-stack --help` lists the rest.

### When some frames won't plate-solve

Before it can register anything, Siril has to work out where each frame is pointing.
Some frames won't: thin cloud, a bump to the mount, a night that just wasn't good
enough to show the stars needed. That's normal, and it doesn't stop the run — the
frames that *did* solve are registered and stacked, and you're told what was left out:

```
  Plate solving solved 123 of 221 frames (56%).
  Failures by night:
      2026-06-05      0 of   33    0%
      2026-06-10      1 of   81    1%
      2026-06-28     94 of  104   90%  <--
      2026-07-03      3 of    3  100%  <--
```

Failures almost always belong to a session rather than being scattered, and that's
the useful part: here two nights account for nearly all of them, and the other two
were fine. If you'd rather drop those nights outright than stack a thinned version of
them, the run prints the flags to do it:

```
m110-stack "M101" --run --exclude-night 2026-06-28 --exclude-night 2026-07-03
```

If almost nothing solves, it stops instead. At that point the problem is more likely
your setup than the sky — usually a missing local star catalogue, or a focal length
or pixel size Siril has wrong — and a spread of failures across *every* night is the
sign of it. Set your own bar with `--min-solved` (a percentage; 25 by default).

This needs **Siril installed** — M110 runs Siril's own commands rather than
reimplementing anything. If you've connected an [AI assistant](assistant.md), it can
talk the settings through with you and hand you the command; it can't start a stack
itself.

### Handing a stack to AstroWizard

`m110-stack "M101" --run --handoff` also drops the finished stack into
`Images/M101/astrowizard/`, ready to open in
[AstroWizard](https://astrowizard.lukomatico.com/). It's a hardlink, so it costs no
extra disk, and it's kept apart from the Siril sandbox on purpose: your stack took
hours and won't change, while a finishing pass is cheap and you'll redo it often.

## Hardlinks — what they are, and why it matters

This is the one technical detail worth understanding, because M110 uses **hardlinks**
in two places (processing sandboxes and backups) and their behavior surprises people.

**A hardlink is a second name for the exact same file on disk** — not a copy, and not
a shortcut/alias. The file's data exists once; two (or more) names point at it. So:

- **It costs no extra disk space.** Hardlinking 40 GB of subs into the sandbox adds
  ~0 bytes — both `Images/<target>/lights/` and `Images/<target>/siril/lights/` are
  names for the same bytes.
- **The names are equal peers.** Neither is "the original." The data lives until the
  *last* name is removed.
- **Deleting one name is safe** for the others. Removing a hardlink just drops that
  one directory entry; the data stays as long as another name points at it.
- **Editing the *contents* through one name changes it for all of them** — it's the
  same file. (In practice this rarely bites you, because Siril and M110 write *new*
  files for outputs rather than modifying subs in place.)
- **Hardlinks only work within one filesystem/volume.** Across drives — or on some
  network/SMB and exFAT shares — M110 automatically falls back to a real copy.

### What this means for the processing sandbox

The subs in `Images/<target>/siril/lights/` are **the same files** as your real
`Images/<target>/lights/` subs — hardlinked so M110 doesn't duplicate gigabytes of
data for every processing run.

- ✅ **Safe:** letting Siril read them, stack them, and write outputs. Siril doesn't
  modify raw subs.
- ✅ **Safe:** deleting the whole `siril/` sandbox — your `lights/` originals remain
  untouched (they're a separate name for the same data).
- ⚠️ **Not a backup.** Because the sandbox subs share storage with your originals,
  the sandbox is *not* a second copy of your data. If a disk fails, both names are
  gone. For real redundancy, use [Backup](backup.md).
- ⚠️ **Don't hand-edit a sub inside the sandbox** expecting the original to be spared
  — it's the same file. Treat subs as read-only everywhere.

Next: **[Backing up your library →](backup.md)**

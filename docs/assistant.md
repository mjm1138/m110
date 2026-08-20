# Using an AI assistant with your library

M110 can act as an **MCP server** — a small program that lets an AI assistant read
your library and answer questions grounded in *your* data instead of guessing.
"What should I shoot tonight?", "why is M101 ranked above M51?", "how does this
stack look?" — answered from your actual captures, your site, and your integration
times.

You bring your own assistant. M110 doesn't include one, doesn't need an API key,
and doesn't send your library anywhere on its own: the assistant you connect runs
on your machine and reads your files directly.

> 🔒 **The assistant cannot change your library.** Every tool below is read-only
> except one, and that one can only *create* a new file in a staging area you
> approve. There is no path by which an assistant edits or deletes anything you
> made. [More on this below](#what-it-can-and-cant-do).

## Contents

- [Connecting an assistant](#connecting-an-assistant)
- [What it can and can't do](#what-it-can-and-cant-do)
- [Skills — the procedures it follows](#skills--the-procedures-it-follows)
- [Tools — what it can look at](#tools--what-it-can-look-at)
- [Reviewing what it hands you](#reviewing-what-it-hands-you)
- [Troubleshooting](#troubleshooting)

---

## Connecting an assistant

Open **Preferences → AI assistant** (Library → Preferences, or Cmd+, on macOS).

### Claude Desktop — one click

Click **Set up Claude Desktop…**. M110 adds itself to Claude Desktop's config file
and tells you to **quit and reopen Claude Desktop** — then just ask it something
like *"what should I shoot tonight?"*. That's the whole setup. The button becomes
**Update Claude Desktop…** afterwards, and **Disconnect** removes the entry again,
leaving any other servers you've configured alone.

Claude Desktop gets the one-click path only because its configuration is a JSON
file M110 can safely merge into — not because it's the only assistant that works.

### Any other MCP client

Click **Connection details…**. M110 is a plain MCP server over stdio, so the same
connection is offered in the three shapes clients ask for, each with a **Copy**
button:

- **A `mcpServers` JSON block** — for clients configured by a JSON file:

  ```json
  {
    "mcpServers": {
      "m110": {
        "command": "/path/to/python",
        "args": ["-m", "m110.assistant.mcp_server"],
        "env": { "M110_DATA_ROOT": "/Users/you/Documents/M110" }
      }
    }
  }
  ```

- **Command + environment** — for clients with fields to fill in.
- **A `claude mcp add …` line** — for Claude Code, paste it into a terminal.

The exact values differ per machine, which is why the dialog generates them rather
than this page printing them. Two things are always true: the server is launched as
a command (not a URL — there's no network service and nothing listening on a port),
and `M110_DATA_ROOT` tells it **which library to read**. If you keep more than one
data folder, that variable is what picks between them.

> **Packaged builds include everything needed.** If you installed M110 from a
> `.dmg`, AppImage or Windows installer, the MCP server ships inside it — nothing to
> install. Running from source needs the optional extra:
> `pip install 'm110[assistant]'`.

---

## What it can and can't do

This is worth reading once, because it's the difference between a tool you can
leave connected and one you have to supervise.

**It can read everything in your library.** Objects, coordinates, capture sessions,
integration times, your journal notes, the priority ranking and the reasoning
behind it, your site profile, and the actual image files.

**It cannot modify or delete anything. At all.** Not your journals, not your
settings, not your priority list, not a single FITS file. This isn't a promise about
good behaviour — the server contains no code that can alter or remove an existing
file, and M110's test suite proves it: the code that *does* write is in a separate
module the server has no way to reach, and a test fails the build if that ever
stops being true.

**It can create one kind of thing: a new file, and only a plan.** The single
exception to read-only is saving an observing plan. By default that lands in a
staging area for you to accept (see [below](#reviewing-what-it-hands-you)); if you
tick *Let the assistant save plans straight to `Plans/`* it goes there directly.
Either way it can only ever **add** a file, in that one folder: if a plan of the
same name already exists, the new one is saved alongside it under a numbered name
rather than replacing it.

**Changes are proposed, never applied.** When an assistant suggests pinning a
target or retuning the ranking weights, it hands you the *proposal* plus the
before/after ranking M110's own scorer computes. You make the change in M110, or you
don't. The assistant never has a way to apply it.

**One thing to be aware of.** Object names and filenames in your library come from
your telescope's own files. An assistant reads that text as data, and a
maliciously-crafted capture file could in principle contain text intended to
mislead it. The ceiling on that is a *plausible-looking suggestion you decline* —
nothing can be changed without you doing it yourself — but it's a reason to read
proposals rather than rubber-stamping them, the same as with any AI suggestion.

---

## Skills — the procedures it follows

M110 ships four **skills**: written procedures the assistant reads before working,
so it uses the engine properly instead of improvising. Most MCP clients surface
these as slash-commands or prompts; an assistant can also fetch one itself.

| Skill | What it's for |
|---|---|
| **Plan a night** | Build an imaging plan for a night (or a multi-night trip) from M110's own ranking, site profile and astronomy engine. Use when you ask what to shoot tonight, on a given date, or from a different site. Takes an optional date and site. |
| **Critique an image** | Look at one of your astrophotos and give grounded, actionable feedback — anchored to what you actually captured, and careful not to blame you for M110's preview rendering. Takes the object. |
| **Stack with Siril** | Measure a target's light frames and propose Siril stacking settings — coverage depth, drizzle, rejection, weighting, feathering — with the reason for each, plus the disk cost and the command to run. Also covers the awkward cases: mosaics, mixed exposures, and targets shot through more than one filter (which stack separately and are combined afterwards). It measures; **you** run the stack. Takes the object. |
| **Explain the numbers** | How to talk about M110's figures without inventing any. This one applies to *every* answer about your library, not just when you invoke it — the others build on it. |

The most useful thing these do is stop the assistant from doing astronomy in its
head. *Plan a night*, for instance, forbids hand-assembling a schedule — slot
packing, setting times, the start-altitude ceiling and moon impact all interact, and
M110's sequencer already handles them together. The assistant asks the engine and
reports the answer.

---

## Tools — what it can look at

Sixteen operations, grouped by what you'd ask for. **Every one is read-only except
*Save field guide***, which can only create a new file.

### Getting oriented

| Tool | What it returns |
|---|---|
| `get_store_overview` | Orientation: object counts, capture totals, active goals, current prioritizer tuning, and whether the cached ranking is stale. Assistants call this first. |
| `list_objects` | Search and filter your library — designations, type, season, captured integration time. |
| `get_object` | Everything M110 knows about one object: designations, catalogs, coordinates, capture totals and per-session history, images on disk, your journal notes, pin state, and how its integration compares to the deep-stack threshold for its type. |
| `get_processing_state` | Siril state per capture folder: integration, frame counts, the latest stack, frames arrived since it was made, and whether finished output is waiting to be imported. |
| `plan_stack` | Measures a capture folder's light frames and proposes Siril stacking settings, each with its reason, plus the projected disk cost and the exact command to run. Ask it "what if we skipped drizzle?" and it recomputes the whole proposal, disk included, so the answer is a real number. It reads headers only — it does not stack. |
| `get_skill` | Fetches one of the procedures above. |

### Planning a night

| Tool | What it returns |
|---|---|
| `plan_night` | The whole plan for one night: dark window, moon conditions, ranked targets actually up, and a non-overlapping schedule of what to shoot when — plus a printable field guide. This is M110's full pipeline in one call. |
| `rank_targets` | The prioritizer's ranked list with the per-factor breakdown behind each score (goal, urgency, completion, tonight, type weight, feasibility). Instant — it never recomputes astronomy. |
| `object_observability` | Whether specific objects are up on a night from your site, when each transits, how long it stays above the altitude and light-dome floor, and moon separation. |
| `saved_plans` | Your saved field guides from the `Plans/` folder — list them, or read one. |

### Looking at images

| Tool | What it returns |
|---|---|
| `get_image` | One of an object's images, so the assistant can actually look at it, with the capture facts needed to judge it — integration, frames, filters, and how the file was rendered. |

The rendering note matters: M110 percentile-stretches FITS and float-TIF sources so
they're visible at all, and the metadata says so. A flat or grey look may be that
preview rather than your processing, and the skill tells the assistant not to blame
you for it.

### Suggesting changes (proposals — nothing is applied)

| Tool | What it does |
|---|---|
| `propose_weights` | Proposes a change to the prioritizer's strategy, factor weights or per-type multipliers, and returns the **engine-computed before/after ranking** it would produce. You apply it in M110, or don't. |
| `propose_pins` | Proposes pinning targets to the top, deprioritizing them, or clearing overrides — with the resulting ranking. |
| `propose_journal_entry` | Proposes text for an object's journal (a critique, a session note, a processing decision). Returns markdown for you to paste — it does not write. |
| `list_pending` | What's been handed to you and not yet accepted. |

The before/after rankings aren't the assistant's opinion — M110 runs its own scorer
twice, so a proposal can't come with a made-up outcome attached.

### The one that writes

| Tool | What it does |
|---|---|
| `save_field_guide` | Saves an observing plan as a field guide you keep. **Staged by default** for you to accept in M110; if you've ticked *Let the assistant save plans straight to `Plans/`* in Preferences it goes there directly. Either way it can only **add** a new file — never change or delete one. |

---

## Reviewing what it hands you

When an assistant stages something, a quiet strip appears above the page —
**"From the assistant: 1 saved plan and 2 suggested changes."** — with a
**Review…** button. Click it to see each item and accept or discard it. The strip
stays until the queue is empty, and is hidden entirely when there's nothing
waiting.

For a proposal, M110 re-runs the preview **against your library as it is now**, not
as it was when the assistant made the suggestion. If your data changed in between —
you imported a session, or retuned the weights yourself — you see the current
consequence, not a stale one.

If you'd rather skip the queue for plans, tick **Let the assistant save plans
straight to `Plans/`** in Preferences → AI assistant. That only affects saved plans,
and only ever creates new files.

---

## Troubleshooting

**"The assistant can't see my library."** Almost always `M110_DATA_ROOT` pointing at
the wrong folder — check it against the path shown in **Connection details…**. The
server reports this clearly rather than appearing broken.

**"It says there's no capture data."** The assistant reads M110's *cached* rollups,
so a brand-new library needs one **Refresh** (Ctrl+R) first. Rankings additionally
need one **Recompute** on the Planning page — building them is a slow astronomy pass
that the read-only server deliberately can't run for you.

**"Rankings look out of date."** They may be: `rank_targets` flags a stale cache
rather than silently recomputing, and a well-behaved assistant will tell you. Press
**Recompute** on the Planning page.

**"It's not connecting at all."** Restart the client after setting it up — most read
their config only at startup. If it still fails, Preferences → AI assistant shows a
status line explaining what's wrong.

---

Back to the **[User Guide contents](README.md)**.

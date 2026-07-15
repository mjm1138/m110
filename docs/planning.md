# Session planning

← [Back to the guide](README.md)

The **Planning** page answers two questions: *what should I shoot next?* and *what
should I shoot **tonight**, in what order?* Everything on it is computed from your
own library — what you've captured, what your goals are, and where you observe from.

## Site profiles

Planning starts with **where you are**. A *site profile* holds a location's
coordinates, elevation, and timezone; open **Manage site profiles** to create one
(the online **Look up location…** can fill in coordinates from a place name).

Two optional layers make the math match *your* sky:

- **Horizon mask.** Import a `.hrz` skyline of your trees and rooftops — the free
  [theo.rocks](https://theo.rocks) web app builds one by panning your phone around
  the horizon. Targets behind an obstruction don't count as "up".
- **Light dome.** **Compute light-dome…** estimates how high the sky is washed out
  toward nearby towns in each direction, from a bundled worldwide town dataset
  (optionally calibrated by your Bortle number). Planning then favors targets away
  from your brightest horizons — and is gentler about it for narrowband filters,
  which punch through the glow.

The **Location** selector at the top picks the active profile; the ranking and the
planner both use it.

## Priority targets — the ranking

The table ranks every target you're pursuing (your active goals plus everything
you've captured), weighing:

- **goal membership** — catalogs you're actually working toward rank above the rest;
- **seasonal urgency** — an object about to leave the evening sky outranks one that
  will keep for months;
- **completion** — read through the **Strategy** toggle: *capture many* favors
  untouched targets, *go deep* favors started-but-shallow ones. Thresholds are
  type-aware (a faint nebula needs far more integration than a cluster);
- **tonight** — how high, and for how long, it sits in *your* dark sky.

The **tuning weights** re-rank instantly as you adjust them. Right-click
**Pin as priority** (▲) / **Deprioritize** (▼) always composes on top. The heavy sky
math runs about once a day in the background; **Recompute** forces it.

Non-imaging catalog entries (M40 is a double star, M73 an asterism) and very faint,
diffuse targets are automatically down-ranked so they don't claim your dark-sky time.

## Plan a night

Pick a **Night**, choose how many **Targets** (default 4), and **Generate plan**.
M110 builds a real schedule: back-to-back slots on 10-minute boundaries, from
astronomical dusk to dawn.

**How it chooses.** The highest-priority target that's *startable* right at dark
goes first; each next target starts when the previous slot ends; near-equal
priorities go to whichever sets sooner. Durations split the night by your target
count, but adapt — a target that reaches *deep stack* status sooner gets a shorter
slot, and after your requested targets the schedule keeps filling until dawn rather
than wasting dark hours.

**Reading the schedule:**

| Column | Meaning |
|---|---|
| **Start** | The slot's start time — always at or below your telescope's start-altitude ceiling (a Seestar refuses to *start* near the zenith; the capture may climb past it once running). |
| **Duration** | Slot length. **⚠** marks a short *last-chance* slot on a target sinking toward the horizon — expect heavy frame rejection; keep or drop it knowingly. |
| **Alt** | Altitude at the start. **^** means a start above the ceiling (only on devices where that's a quality guideline, not a hard refusal). |
| **Moon** | Separation from the moon at that slot, with its impact (phase × proximity, filter-aware — narrowband is largely immune). **—** means the moon is below the horizon then: no impact. |

The **altitude timeline** draws each target's curve across the dark window, the
moon's track while it's up, the start ceiling, and the scheduled slots as colored
bands.

Uncheck a slot to drop that target (the schedule re-chains, and a substitute may
take its place); **Move up / Move down** reorders and re-chains the start times.
Changing the night or the location clears the plan — generate again for the new
conditions.

## Field guides

**Save field guide…** writes the plan as clean Markdown into the **`Plans/`** folder
of your library — dark window, moon summary, the schedule table, and your per-object
remarks. Saved guides are listed on the Planning page: view them in the app, print
them, or open the folder. Each guide records both when it was generated and which
night it's for.

Next: **[On the roadmap →](upcoming.md)**

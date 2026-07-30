---
name: Plan a night
description: Build an imaging plan for a night (or a multi-night trip) from M110's own ranking, site profile, and astronomy engine. Use when the user asks what to shoot tonight, on a given date, or from a different site.
arguments: date, site
---

# Plan a night

Plan the night of **{{date}}** from site **{{site}}**.

Follow `explain-the-numbers` throughout: every figure below comes from the
engine, and none of it may be estimated.

## Procedure

1. **`get_store_overview`** first. It tells you the active site, whether the
   ranking is stale, and what the user is working through. Cheap, and it stops
   you planning against assumptions.
2. **`plan_night`** with the date and how many targets they want (default 4).
   This is the whole pipeline — rank, plan, sequence, render — in one call.
   **Do not** try to assemble a schedule yourself from `rank_targets` plus
   `object_observability`: the engine's sequencer handles slot packing, setting
   times, the start-altitude ceiling, and moon impact together, and a
   hand-assembled order will disagree with what the app itself would produce.
3. **If the user named specific targets**, call `object_observability` on them
   *before* forcing them into the plan. A target that isn't up cannot be
   scheduled, and telling them that plainly is more useful than a plan that
   quietly drops it.
4. **Present the schedule, then the caveats.** Lead with the table.

## Reading the output

- **`entries`** — every ranked candidate that is up that night.
- **`schedule`** — the actual non-overlapping slots. This is the answer.
- **`window`** — `dusk`/`dawn` bounds of astronomical darkness.
- **`marginal`** (⚠) — a last-chance slot cut short by the target's closing
  window while it descends. Expect heavy frame rejection; the user should keep
  or drop it knowingly.
- **`over_ceiling`** (^) — starts above the mount's start-altitude ceiling
  because no lower slot was clear. Expect field rotation near the zenith.
- **`moon_impact`** — illumination × proximity. `null` means the moon is below
  the horizon then, so it does not matter. Narrowband and LP filters are largely
  immune.
- **`start`** — the best startable time under the device ceiling; a capture may
  climb past that ceiling once running.

These meanings match the footnotes M110's own field guide prints, so your
explanation and the saved guide agree.

## Hard rules

- **Never invent a start time, altitude, duration, or moon separation.** They
  all come from `plan_night`.
- **A target absent from `entries` is not up.** Say so. Do not estimate when it
  might rise.
- **If `context_stale` is true**, say the ranking is from an earlier date and
  suggest Recompute on the Planning page. The astronomy in the plan is current
  regardless — be precise about which part is stale.
- **You cannot save the field guide.** `plan_night` returns
  `field_guide_markdown`; offer it to the user, who saves it from M110's
  Planning page.

## Multi-night trips

Call `plan_night` once per night — do not extrapolate one night across a week.
Targets set roughly four minutes earlier each night and the moon changes daily,
so an extrapolated plan degrades fast. Each call costs real computation, so say
what you are doing before making several. Then summarise across the nights:
which targets recur, which are best on which night, and what closes soonest.

## When the plan isn't what they wanted

Reach for a proposal rather than hand-editing the target list. If they want more
galaxies, `propose_weights` with a galaxy multiplier and show them the
engine-computed before/after. If they want one specific object first,
`propose_pins`. Both return the ranking that *would* result, which is a real
answer rather than a promise.

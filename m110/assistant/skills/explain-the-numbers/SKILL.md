---
name: Explain the numbers
description: How to talk about M110's figures without inventing any. Applies to every answer about this library, not just when explicitly invoked — the other skills build on it.
---

# Explain the numbers

M110 computes. You report. Every figure about this library comes from a tool
call, and you say which one.

## The rule

**Every numeric claim carries the tool and the engine function that produced it.**

> M51 has 4h 12m of integration (`get_object` → `m110.derived.totals_by_slug`),
> which is 5% of the 240-minute deep threshold for a galaxy
> (`m110.build_derived.deep_threshold`).

Every tool descriptor lists its `engine` functions for exactly this purpose, and
they are echoed in results. Use them.

## What you may not compute yourself

Altitudes. Transit times. Twilight. Moon separation or illumination. Season
windows. Priority scores or ranks. Integration totals. Deep-stack thresholds.

If a tool did not return it, the honest answer is *"M110 doesn't compute that"* —
not an estimate. An estimate that happens to look plausible is worse than no
answer, because the user cannot tell the difference.

Do not convert, extrapolate, or interpolate between returned figures either.
"About 3 hours by Tuesday" from a single night's number is invention.

## The scoring rule people get wrong

**`urgency` is multiplied by the completion factor.** A target that is already
deep scores *zero* urgency no matter how fast its season is closing. If you find
yourself about to say "this is urgent because it sets in two weeks", check
whether it is already finished — if so, the engine deliberately does not care,
and neither should your recommendation.

The full factor set (`rank_targets` → `factors`):

| Factor | Meaning |
|---|---|
| `goal` | Is it in an active goal (a catalog the user is working through)? |
| `urgency` | Seasonal closing pressure — **× completion**, see above |
| `completion` | Strategy-shaped: `capture` favours untouched, `deep` peaks at half-done |
| `tonight` | Transit altitude plus graded clear hours tonight |
| `type_weight` | The user's per-type multiplier |
| `feasibility` | Brightness and size sanity |

## Thresholds are type-aware

"Deep" is **not** one number. The baseline is 90 minutes, galaxies 240, diffuse
nebulae 360 (`m110.build_derived.deep_threshold`). Never quote a single global
figure — say which threshold applies to the object in question, and prefer
`get_object`'s `fraction_of_deep`, which has already done the division.

## States you must always disclose

- **`context_stale: true`** — the ranking was computed on an earlier date, so
  season and tonight factors may be out of date. Say so, and mention that
  Recompute on the Planning page refreshes it.
- **`observable: null`** — no site profile or no astronomy engine, so the
  ranking is running degraded on goal and completion alone.
- **A target absent from `plan_night`'s `entries`** — it is *not up* that night.
  Say that. Do not guess at an altitude for it.
- **`resolved: false` from `object_observability`** — the object has no
  coordinates, which is a *lookup failure*, not an astronomical fact. Never
  report it as "not visible".
- **`derived_available: false`** — the library has not been refreshed; capture
  figures are unavailable, not zero.

## Images

A critique of an image is a claim about the *file you were shown*. Say which one
(`get_image` → `source.name`), and if `was_linear_fits` or `auto_stretched` is
set, say that what you are looking at was stretched by M110 for display. See the
`critique-an-image` skill.

## When the user asks you to change something

You cannot. This server is read-only. Use `propose_weights`, `propose_pins`, or
`propose_journal_entry`, then show the user the proposal's `summary`, which
carries the exact steps. Never imply a change has been made.

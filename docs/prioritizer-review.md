# Prioritizer / planner review — 2026-07-13

Point-in-time review of the in-progress prioritization + session-planner
feature, from the Astronomy session. Reviewed the live derived outputs in
`~/Documents/M110/.m110_internal_data/derived/` (`prioritized.json`,
`priorities.json`, `goals.json`) and the first planner output
(`Plans/2026-07-18_home-rear-deck-sat-18-jul.md`).

Actionable items are filed in [`BUGS.md`](../BUGS.md) under *Planning /
prioritization*; this doc is the reasoning behind them.

---

## 1. Two derived files, each holding half the picture

The system currently has two disjoint priority artifacts and **does not join
them**:

- **`priorities.json`** — the *curated* path: `priorities.toml` joined with
  capture progress. Narrow (~40 hand-authored entries) but rich with intent —
  `priority` (high/med/low), `filter` (ON/OFF/IRCUT/LP), `type_hint`,
  per-target `target_integration_min`, `strategy`, plus `progress` +
  `percent_complete`. No astronomy, and its season/intent is **stale** (Arches
  trip past, "window closes late June", nearly everything at 100%+ /
  `deep_stack`).
- **`prioritized.json`** — the *engine* path: full-catalog sweep (110 Messier +
  30 Sharpless) with **fresh observability for the date** — `observable`,
  `hours_clear`, `transit_alt`, `nights_to_close`, `in_active_goal`. Broad and
  current, but **intent-free**: no filter, no priority weight, no per-target
  goal, no strategy.

Neither is a superset. The observability engine is the strong part and is
astronomically sound (e.g. M94 correctly `observable:false` for mid-July because
it transits before astronomical dark and is into the WNW tree by full dark; the
`nights_to_close` urgency gradient — M25/M107 = 7, M5/M40 = 14 — is genuinely
useful). But most of what I first read as "missing from the engine" is not
missing from the *system* — it already lives in `priorities.json`. The defect is
that the two files aren't merged.

### Recommendation
Compose a single ranked view. Take **durable** fields (filter, type,
`target_integration_min`, priority weight) from the curated store *and the
catalog*; recompute **time-varying** fields (season/urgency/window/altitude)
from the engine. Do **not** naively inherit `priorities.toml`'s `season`
strings or "target met" prose — they're months stale and would drag June logic
over July geometry. Curated `strategy` prose is human-only; keep it out of
ranking.

## 2. `type` is `unknown` for every uncaptured target

In `prioritized.json`, `type` is only inferred from existing captures, so every
object with no data yet (m8, m16, m87, all Sharpless…) is `type:"unknown"`. The
catalog knows the type of all of them. Type is exactly what the planner needs
downstream — it drives **filter** (LP vs IRCUT), **star-removal**, **exposure
strategy**, and **moon-tolerance**. So the objects that most need planning are
the ones the engine can least reason about. Fix: read type from the catalog for
the full sweep, not from session data.

## 3. Missing from *both* files

- **Moon.** No illumination, altitude, or separation in either derived file.
  This is the single biggest per-night driver (bright moon ⇒ drop IRCUT
  broadband, pivot to LP narrowband) and it's absent. See §5 for how this
  manifested in the first plan.
- **Structured feasibility.** Magnitudes appear only in `strategy` *prose*
  (M109 "mag 9.8", M67 "mag 6.1"); there's no structured
  magnitude / surface-brightness / angular-size field anywhere. So the 30
  Sharpless targets and catalog oddities can't be gated for a 50 mm f/5 scope.
- **Device start-altitude ceiling (~78°)** applied to the usable window, and
  **effort-to-goal** (capture-nights to close, vs the engine's calendar-only
  `nights_to_close`).

## 4. Concrete engine bug — combined-folder under-count

`priorities.json` correctly rolls the pair to the `M81 M82` folder — 1743 min,
145%. `prioritized.json` fragments the same data into `m81` (126 min), **`m82`
(13 min)**, and `m81-m82` (1743 min, but `obs:null`). So in the engine's world
M82 looks like it desperately needs data when the pair actually has ~29 h. Any
"what needs work" ranking off `prioritized.json` will badly misjudge companion
pairs and mosaics. The combined/mosaic slugs also get `obs:null` because the
slug doesn't resolve to a single coordinate.

---

## 5. First planner output — `2026-07-18_home-rear-deck-sat-18-jul.md`

The plan surfaced several problems. Some are already tracked (target count,
sequencing); the moon and start-altitude issues are new.

### 5a. Moon figures are wrong (flagged by Mike, confirmed)

Plan header: **"Moon: 0% lit, down at dusk (−17°)."** Computed for Boulder
(40.015°N, 105.27°W, MDT) on 2026-07-18:

| Local time | Real moon alt | Real illum |
|---|---|---|
| 22:30 (dusk) | **+4.9°** (up, setting) | **~24%** |
| 00:00 | −12.0° | ~24% |
| 02:00 | −33.6° | ~25% |
| 03:50 (dark end) | −49.1° | ~25% |

So the moon is a **~24%-lit waxing crescent** (4 days after the July 14 new
moon; illumination is climbing ~8–9%/day here, so the exact evening instant
matters), **up at +5° at dusk and setting ~23:00**, then down the rest of the
night. Two distinct bugs:

1. **Illumination: reported 0%, actual ~28%.** This is dangerous in general —
   0% tells the planner it's a perfect dark night and greenlights broadband
   freely. It happened to be benign here (moon really is down most of the
   night), but the same bug on a moon-up night would wrongly load IRCUT
   galaxies. Suspect a phase-formula error or wrong-instant evaluation.
2. **"Down at dusk (−17°)" is both wrong and a misleading single snapshot.**
   Actual dusk altitude is +5°, not −17° (smells like a timezone / evaluation-
   instant bug). More importantly, a 5.3-hour night can't be described by one
   dusk value — the moon state changes across slots. The planner needs
   **per-slot** moon altitude, not a global header.

### 5b. `Moon°` column is shown without gating on moon altitude

The per-target `Moon°` separations (44…118) are printed even for slots where the
moon is **below the horizon** (most of this night), where separation has no
physical meaning. "Moon impact" is a function of *illumination × moon-altitude ×
separation × filter*, not separation alone. When the moon is down, impact is
nil regardless of separation — show "—" / "moon down". LP (narrowband) targets
should read near-immune even when the moon is up. (BUGS #193 already asks the
planner to *explain* moon impact; this is the correctness half of that.)

### 5c. Start-altitude ceiling (~78°) ignored in slot selection — **new**

The Seestar app rejects captures whose target is above ~78° at the **start**.
Four of the eight proposed targets have a best-time altitude over the ceiling:

| Target | Best-time alt |
|---|---|
| M29 | 88° |
| Sh2-112 | 84° |
| Sh2-115 | 83° |
| M39 | 82° |

Starting any of these at the listed time would be rejected by the app. The
planner must pick a start on the rising side below ~75°, or after the target
descends back through ~75° — see the Astronomy CLAUDE.md "Session Planning
Rules" and `scripts/sky.py`'s `^` (over-ceiling) flag, which already encodes
this. This is the live manifestation of the "start-ceiling not applied" gap.

### 5d. No feasibility / worthiness gate — **new-ish (relates to #21)**

- **M40** is proposed as a deep-sky slot, but the plan's own note admits it's
  "an optical double star (Winnecke 4), not a deep-sky object." It's a
  catalog-completion entry with 0 integration, so the completion goal surfaces
  it — but it shouldn't consume a dark-sky imaging slot. A worthiness flag
  (asterism / non-DSO Messier entries: M40, M73, M45-as-cluster, etc.) should
  down-rank or annotate these.
- **Sh2-112/115/129** are faint emission nebulae that are marginal on a 50 mm;
  they're at least correctly assigned LP, but without a surface-brightness /
  size gate the planner can't tell a showpiece from a stretch target.

### 5e. Already-tracked issues this plan confirms

- 8 targets proposed with no target-count control → **BUGS #192** (default 4).
- Output is a list of per-target "best times" that overlap heavily (two share
  22:30, two share 03:00, two share 02:10), not a non-overlapping sequence with
  durations on 10-min boundaries → **BUGS #190, #193, #196–201**.
- Season labels in the notes ("Aug–Oct" targets recommended on Jul 18) are
  decorative, not driving selection — fine, but surfacing them next to a
  recommendation reads as contradictory; suppress or reframe.

---

## 6. Suggested fix order (highest leverage first)

1. **Join `prioritized.json` + `priorities.json` + catalog type** into one
   ranked view (§1, §2). Unblocks filter-awareness and everything below.
2. **Fix the moon model** (§5a): correct illumination, per-slot altitude,
   evaluate at the right local instant. Then gate `Moon°` on moon-up (§5b) and
   make impact filter-aware.
3. **Apply the ~78° start ceiling** to slot start selection (§5c) — the logic
   already exists in `scripts/sky.py`.
4. **Combined-folder rollup** in the engine so pairs/mosaics aren't
   under-counted (§4).
5. **Feasibility / worthiness gate** (§5d) — needs structured magnitude/size in
   the catalog (§3).

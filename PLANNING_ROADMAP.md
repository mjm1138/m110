# Planning / prioritization — tuning roadmap to release

Status target: get the **Planning** pane (prioritizer + session planner) from
"foundation shipped, output not trustworthy" to **shippable in a release**.

Source material:
- [`prioritizer-review.md`](prioritizer-review.md) — the 2026-07-13 review of the
  live derived outputs + the first real planner run (reasoning behind the bug items).
- [`BUGS.md`](BUGS.md) → *Planning / prioritization* (#35–39 + the Session Planner
  bullets).
- ROADMAP **item 1** (auto-prioritizer scoring model + the three checkpoints) and
  the Astronomy `astro-session-planner` skill / `scripts/sky.py` (the proven logic
  to port; **use it, don't hand-derive astropy**).

The through-line from the review: **the observability engine is astronomically
sound; the defects are (a) two derived files that were never joined, (b) a broken
moon model, (c) device/feasibility constraints not applied to slot selection, and
(d) the planner emits overlapping "best times" instead of a real sequence.** Fix
those and the feature is releasable.

---

## Phase 1 — Correct the data the ranker sees  *(highest leverage; everything else builds on it)*

Nothing downstream can be trusted until the ranked view is correct and complete.

### 1.1 — Single ranked view; retire the `priorities.toml` dependency  *(BUGS #35, review §1–2)* ✅ **landed** (`feature/session-planner`)
> **Shipped:** the prioritizer was already the single source; the real fix was
> `prioritize.build_contexts` reading object `type` from the bundled **reference** when
> the Library lacks it (uncaptured goal members were scoring as `type:"unknown"` → IRCUT +
> the 90-min floor). The legacy `priorities.toml` → `priorities.json` path is retired end
> to end (`build_priorities`/`load_priorities`/`filter_priorities` deleted; the published
> site's Priority Targets section dropped). Remaining acceptance below is met.
The review framed this as "join the two disjoint artifacts" (`prioritized.json` =
observability, full sweep, but intent-free + `type:"unknown"` for uncaptured;
`priorities.json` = curated intent + progress, but stale + no astronomy). **Revised
decision (2026-07-13):** the curated `priorities.toml` is a personal, non-generalizable
workflow file (it already ships **empty** in `seed/`) — so rather than depend on it,
**make the engine artifact the single source** and derive its durable fields
generalizably:
- `filter` → `prioritize.filter_for_type()` (emission/planetary → LP, else IRCUT).
- `type` → the **catalog**, for the full sweep (not from session data).
- `target_integration_min` → `build_derived.deep_threshold` (type-aware).
- `priority` weight → the scorer (goal + urgency + completion) **+ pins** (#3) for
  manual intent; a pin-style **exclude** covers the old `track=false` campaign flag.
- **Recompute** all time-varying fields (season / urgency / window / altitude) from
  the engine for the requested date; never inherit stale `season` / "target met"
  strings.
- **Acceptance:** every uncaptured target carries a real `type` and `filter`; one
  artifact drives both the Priority-targets table and the planner candidate set;
  **no code path reads `priorities.toml`** for ranking (the personal workflow leak
  is gone).
- Unblocks filter-awareness for the whole sweep.

*What's lost by dropping the curated file:* only the hand-tuned deviations from the
type defaults (a bespoke per-target integration goal or a manual priority) — both of
which the scorer + pins express generalizably. See the field-by-field table in the
session notes.

### 1.2 — Combined-folder rollup before scoring  *(BUGS #39, review §4)* ✅ **landed** (`feature/session-planner`)
> **Shipped (prioritizer-only, by decision):** `build_contexts` credits each combined
> folder's integration to its constituent catalog **members** (via
> `scan_sessions.folder_to_slugs`) and drops the synthetic combined slug. Live store:
> `m81` → 1870, `m82` → 1757, `m81-m82` dropped. The combined members carry their real
> reference coordinates, so observability resolves (no more `obs:null`).
>
> **Not** addressed here: the Processing queue + Library still show separate solo
> folders (`M81`, `M82`) as their own rows because those are real on-disk folders —
> that engine-wide `by_folder` rollup is filed as **BUGS #40b**.

Original acceptance (met for the prioritizer): M81/M82 rank once with a real up-window
instead of a starved companion + an `obs:null` combined slug.

### 1.3 — Structured feasibility fields in the catalog  *(BUGS #38, review §3, §5d)* ✅ **landed** (`feature/session-planner`)
> **Shipped, with a re-scope the audit justified:** no new stored fields were needed.
> The reference already **types** the oddities (M40 = `double_star`, M73 = `asterism`)
> — the type *is* the non-DSO flag — and mean **surface brightness derives** from the
> existing `magnitude` + `size` (`prioritize.surface_brightness`, anchored to published
> values: M31 22.1, M33 23.1). `feasibility_score` is a **multiplier** on the whole
> score (an infeasible target can't be rescued by urgency/goal): non-DSO → 0.05,
> SB ramp 1.0 → 0.3 across 22–25 mag/arcsec², missing data → neutral — except mag-less
> **diffuse nebulae**, which take a mild 0.8 prior (the faint-Sharpless case; Simbad
> has no V-mag to backfill for most, so a data backfill can't fix that set). Ranked
> rows carry `non_dso` + `factors.feasibility` for UI annotation.
> **Live store:** M40 → rank 145/146, M73 → 146/146; the top-10 is showpieces, not
> mag-less Sharpless.
>
> **Follow-ups filed:** the reference-mag audit (BUGS #38b — some floored targets are
> B-mag leakage: Helix listed 13.5 vs real V≈7.3); coverage gaps = 145 mags / 41 sizes.

Original acceptance (met): M40 and friends are down-ranked + flagged, not proposed as
deep targets; a surface-brightness gate exists for the ranker to consult.

---

## Phase 2 — Fix the moon model  *(BUGS #36, review §5a–b)*

The single biggest per-night driver, and today it's wrong in a way that can
greenlight broadband on a moon-up night.

### 2.1 — Correct illumination + per-slot altitude
- The 2026-07-18 plan reported **"0% lit, down at dusk (−17°)"**; truth is **~24%
  waxing crescent, +5° at dusk, setting ~23:00**. Two bugs: illumination formula/
  instant is wrong, and the moon is described by a single dusk snapshot with a wrong
  altitude (timezone / eval-instant smell).
- Evaluate the moon **per slot** across the dark window, not once in a global header.
- **Acceptance:** planner moon figures match `scripts/sky.py` for the same date/site
  within tolerance; add a regression test pinning a known night.

### 2.2 — Gate `Moon°` on moon altitude + make impact filter-aware
- Only show separation when the moon is **up**; when it's down show "— / moon down".
- "Moon impact" = *illumination × moon-altitude × separation × filter* — LP
  narrowband reads near-immune. This is the correctness half of the "explain moon
  impact" ask.
- **Acceptance:** a moon-down night shows no spurious separations; a bright-moon
  night flags broadband targets and lets LP targets through.

---

## Phase 3 — Apply device + tonight constraints to slot selection  *(BUGS #37, review §5c)*

The ranker knows a target is up; the planner must pick a **startable** time.

### 3.1 — Start-altitude ceiling (~75–78°)
The Seestar app rejects captures whose target is above ~78° at the **start**
(empirically ~75° practical). The 2026-07-18 plan put 4/8 targets over the ceiling
(M29 88°, Sh2-112 84°, Sh2-115 83°, M39 82°).
- Pick a start on the rising side below ~75°, **or** after the target descends back
  through ~75°. Never propose "best time = transit" for a high-declination target.
- Logic already exists in Astronomy `scripts/sky.py` (the `^` over-ceiling flag) —
  port it; the device ceiling lives in the device profile, not hardcoded.
- **Acceptance:** no proposed start is over the ceiling; high-dec targets get a
  rising- or setting-side slot.

---

## Phase 4 — Real session sequence, not overlapping "best times"  *(Session Planner bullets)*

Turn the tonight shortlist into a schedule a user can actually run.

### 4.1 — Target-count control  *(default 4)*
- User-settable number of targets, default **4**, up to the number of visible targets.
- Replaces the current "surface everything" behavior (8 proposed on 2026-07-18).

### 4.2 — Non-overlapping sequenced schedule
Current output is a list of per-target best times that overlap (two share 22:30, two
share 03:00). Replace with a **sequence**:
- Object sessions **cannot overlap**; each start = previous start + previous duration
  (don't model slew/focus time).
- Start/end times snap to **10-minute increments** (Seestar SSC constraint).
- **Sequencing logic** (v1, from BUGS):
  1. Highest-priority object visible **right at astronomical dark** = object 1.
     Duration = astro-dark span ÷ target count, unless it reaches deep-stack status
     with a shorter duration.
  2. Highest-priority object visible at the **end of object 1** = object 2.
  3. …continue to the target count.
  4. Tie among equal-priority objects in a window → pick the one **closer to setting**;
     sequence the other after.
- **Per-target schedule row:** object name, altitude at start, start time, duration,
  filter, moon impact (with the plain-language explanation from Phase 2).
- **Acceptance:** the field guide renders a contiguous, non-overlapping,
  10-min-aligned schedule; every row respects the start-ceiling from Phase 3.

### 4.3 — Suppress contradictory season decoration
Season labels ("Aug–Oct" shown next to a Jul 18 recommendation) are decorative and
read as contradictory. Suppress or reframe next to a live recommendation.

---

## Phase 5 — Planning UI fixes  *(Session Planner bullets)*

Blocking usability bugs in the Planning pane's date picker.
- **Date selection broken:** most calendar days are labeled with ellipses; the
  selected date renders greyed-out. Fix the date picker so a date can be chosen and
  reads as selected.
- Wire the target-count control (Phase 4.1) into the "Plan a night" section.
- Surface per-slot moon (Phase 2) and startable-window (Phase 3) in the planner table
  + the `NightTimeline` chart.

---

## Phase 6 — Foundation for the LLM session-planner skill  *(Session Planner bullets)*

Deferred but explicitly called for: "this is a point where an LLM might plug in, so
lay the foundation of the session-planner skill."
- Keep the deterministic engine (`plan_night` + the sequencer) as the **source of
  truth**; the assistant *explains / tunes / narrates*, it doesn't hand-author a plan
  (mirrors ROADMAP item 1's "engine logic; the assistant layers over it").
- Port the methodology the Astronomy `astro-session-planner` skill +
  `workflows/session_planning.md` codify into an M110-native skill/seam that reads the
  joined ranked view (Phase 1) and calls the engine.
- **Not required for the release cut** — land Phases 1–5 first; this is the follow-on.

---

## Suggested landing order (review §6, adjusted)

1. **Phase 1** (join + type + rollup + feasibility fields) — unblocks everything.
2. **Phase 2** (moon model) — correctness + safety.
3. **Phase 3** (start ceiling) — slot validity.
4. **Phase 4** (sequence + count) — the actual deliverable users see.
5. **Phase 5** (UI date-picker + wiring) — can proceed in parallel with 3–4.
6. **Phase 6** (LLM skill foundation) — post-release-cut follow-on.

**Release gate:** Phases 1–5 green (with regression tests pinning a known night's
moon + a startable-window sequence), field guide renders a correct non-overlapping
schedule for 2026-07-18 that matches a hand/`sky.py` check.

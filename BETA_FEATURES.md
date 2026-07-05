# M110 — Beta Feature Punchlist

A **static** snapshot (2026-07-05) of which *features* — shipped-but-rough,
partially implemented, or on the roadmap — need to be online for a successful
public beta. Companion to **[`BETA.md`](BETA.md)** (which covers *shippability*:
packaging, QE, distribution, docs). ROADMAP.md and BUGS.md are the *dynamic*
tracking docs; this is the frozen beta cut so scope doesn't drift.

**Scope discipline is the whole point of this list.** The beta persona's value
prop — *organize a growing Seestar library + a north-star goal to stay motivated*
— is **already shipped** (v0.1 Library, catalog/goal tracking, ingest,
processing-prep, journal). A good beta **polishes the shipped core so a stranger
can succeed with it** and fixes the few places the code is secretly hardcoded to
Mike's habits. It is **not** where the two biggest unbuilt arcs land.

Tiers: **T1** = must be online for beta · **T2** = strongly wanted, acceptable
fast-follow · **T3** = explicitly deferred *past* beta (recorded here so the cut
is deliberate, not forgotten).

---

## Execution order

The tiers above are grouped by **ship-priority**, not build order. Build in this
sequence — it groups work by subsystem (avoid thrashing between ingest and
dashboard code) and front-loads the one long-lead dependency that's outside your
control. Runs **in parallel with** BETA.md's packaging/QE stream (different kind
of work).

- **Phase 0 — start now, runs alongside everything (not a build task).** Recruit
  2–3 Seestar owners (varied models: S30 / S50) + 1 Dwarf owner and collect real
  **sample capture dumps**. This is the critical-path long pole — it gates #5
  (multi-model), Dwarf (T2), *and* BETA.md §3 ingest QE, and it's slow for reasons
  you don't control. Get it in flight day one; slot the model-specific work in as
  dumps land, not on a fixed date. (Invisible in the tier lists because it's
  recruitment, not code — don't let it fall off the radar.)
- **Phase 1 — Import / ingest hardening** *(one code cluster: `ingest.py` /
  `ingest_dialog.py` / holding area).* #6 surface-skipped-files → #4 holding-area
  discard + reveal → **#5 multi-Seestar-model** *(as Phase-0 dumps arrive)*. Highest-
  traffic path a new user hits; #5 is the biggest unknown, so front-load it.
- **Phase 2 — #17 finished-hint generalization** *(processing/curation cluster;
  independent of Phase 1, can run in parallel).* A silent-misclassification
  landmine — derisk it before relying on strangers' output looking right.
- **Phase 3 — Manual Pin/Mute priorities (#3).** Self-contained (prefs file +
  inline row controls + dashboard); slots anywhere.
- **Phase 4 — Onboarding / first-run (#1), LAST.** Split it: the **data-folder
  prompt** is independent and may land early, but the **empty-state + guided-first-
  import** copy must be finalized *after* Phases 1–3, since it narrates flows those
  phases are still changing. Building the guided tour first guarantees rework.
- **Then T2 fast-follows** (they already mirror T1 dependencies): #17 gallery —
  with the ⚠️ hero-cache fix, **only** when set-hero ships → #26 aids → Dwarf (when
  its dump is ready) → #25.

> **Note:** onboarding is listed *first* in T1 (it's the highest-value gap) but
> executes *last* — priority ≠ sequence. And Phase 0 recruitment has no line item
> in the tiers, yet it's the schedule driver.

---

## T1 — Must be online for the beta

- [ ] **Onboarding / first-run experience** *(the #1 gap — not previously on the
  feature list).* A stranger installs and lands in an empty Library with no
  orientation. Needs: **first-launch data-folder prompt** (BUGS UI-niceties);
  **empty-state guidance** ("Import from your Seestar to get started"); a **guided
  first import** happy path. Overlaps [`BETA.md`](BETA.md) §4 — that's the
  shippability angle; this is the feature work.
- [ ] **#17 finished/intermediate hinting — generalization** *(ROADMAP 7 / BUGS
  #17).* The finished-vs-intermediate classification is built on Mike's filename
  habits (ROADMAP: "probably not generalizable"). A stranger's files **will**
  misclassify. **Beta-blocking piece:** a preference-driven, user-editable hint set
  seeded from sensible defaults (replaces the hardcoded `_classify` patterns).
  *(The gallery promote/demote/set-hero UI in #17 is a T2 nicety on top.)*
- [ ] **Priority Targets view — degrade gracefully without the scorer.** The
  dashboard section reads a hand/LLM-edited `priorities.toml`; for a fresh user
  that's empty/confusing. **Pull *only* the manual Pin / Mute overrides forward**
  (the self-contained "manual overrides" sub-item of ROADMAP item 1 — a stable
  prefs file, inline on Library/Goals/Summary rows). Gives the view a reason to
  exist **without** building the scoring engine. Alternatively: a clear empty
  state. *(This is the surgical slice of item 1 that ships; the rest is T3.)*
- [ ] **Holding-area: discard + reveal** *(BUGS #26, partial).* Strangers' messy
  imports *will* land in the 6c holding area, which today offers no way to dismiss
  junk. Ship: **discard-a-held-file with confirmation** + **reveal in Finder /
  open containing folder**. *(The FITS-header inspector / thumbnail / suggested-
  identity aids are T2.)*
- [ ] **Multi-Seestar-model + newer capture modes** *(ingest robustness; overlaps
  [`BETA.md`](BETA.md) §3).* Validated on one telescope/firmware/layout only.
  Confirm/degrade for **S30 / S50** folder layouts and newer output modes
  (**mosaic / framing / EQ-mode** captures produce different files). A rock-solid
  **manual "choose folder"** fallback covers what auto-detection misses.
- [ ] **Surface skipped files after import** *(BUGS UI-niceties).* "N already
  present, skipped." Copies are already skip-if-present; this is just reporting —
  avoids "did it actually work?" confusion for a first-timer.

## T2 — Strongly wanted; acceptable fast-follow

- [ ] **#17 finished/unfinished gallery** — right-click promote / demote / set-hero
  in the object view (the curation UI atop the T1 hint-set). ⚠️ Ships with the
  **hero-render cache fix** (invalidate on source *identity*, not mtime — BUGS #17
  note), else picking an older image as hero leaves a stale hero + row thumbnails.
- [ ] **#26 holding-area identification aids** — FITS-header inspector
  (OBJECT/IMAGETYP/FILTER/RA/DEC via `frame_info`), thumbnail preview, suggested
  identity from RA/DEC (reuse #12 pointing). Most of the plumbing already exists.
- [ ] **DwarfLab (Dwarf II / 3) import** *(ROADMAP item 12).* Reach multiplier
  beyond Seestar; additive `LAYOUTS` entry + classifier, no store-version bump.
  Ship-in-beta vs. fast-follow is gated on getting one real Dwarf capture dump
  (see ROADMAP 12 / [`BETA.md`](BETA.md) §3).
- [ ] **#25 optional per-sub `.jpg` preview import** — cheap (default off); decide
  destination + gallery interaction. Low priority.

## T3 — Deferred past the beta (deliberate cuts)

*Recorded so the decision is explicit. These are real roadmap value — just not
what a "organize my library + track a goal" beta needs, and each is large or
dependency-heavy.*

- [ ] **Session planning + light-pollution + location profiles** *(ROADMAP item 1,
  checkpoint B + its foundation).* The single largest remaining arc: site
  profiles, the GeoNames glow-map, horizon masks, the whole planning UI + plan-file
  emit. **Not needed for beta** — the north-star motivation is already delivered by
  goal/catalog progress (tracking ≠ tonight-planning). Build it *after* the beta,
  informed by real users. *(The Qt-free engine foundation — `planning.py` /
  `horizon.py` / `planning_config.py` — is already built and can sit unsurfaced.)*
- [ ] **Auto-prioritization / target scoring** *(ROADMAP item 1, checkpoint A;
  BUGS #21).* **Not separable from the item above** — checkpoint A requires the
  same site-profile + light-dome foundation, so "just the prioritizer" still drags
  in most of the planning arc. Scoring weights are still TBD-with-user. **Defer the
  auto-scorer**; ship only the manual Pin/Mute slice (see T1). This is the biggest
  scope cut from the original punchlist proposal.
- [ ] **Full import triage toolkit / plate-solving** *(ROADMAP item 9).* Explicitly
  deferred; pulls in a plate-solver dependency; "only worth it once real-world
  messy imports demand more than manual assign." The T1 holding-area discard +
  reveal covers the beta need.
- [ ] **Publishing deploy targets** *(ROADMAP item 8 / BUGS #27).* 8a **local
  static-site export already ships** — that's the beta-relevant slice. GitHub Pages
  / Netlify / S3 / CMS deploy targets, per-list publish flags, auto-publish are all
  post-beta.
- [ ] **#18 advanced/custom processing workspaces** — mosaics, multi-object/multi-
  source Siril dirs. Power-user feature; not a first-beta need.
- [ ] **#19 Open In… / Process in…** — OS-level launch into Siril/PixInsight/viewer.
  Nice guide feature; cross-platform launch risk; post-beta.
- [ ] **#16 6d lazy device-under-target** — the `Images/<target>/<device>/` path
  level + store-version bump. Stays flat for beta (defer until a real 2nd device;
  Dwarf support ships flat/per-session, not per-path).

---

## Verdict on the original 5-item proposal

| Proposed | Verdict |
|---|---|
| 1. Current open BUGS items | **Triage, don't bulk-include.** The onboarding/empty-state + #17 generalization + #26 discard are T1; #18/#19/#27/6d are T3. |
| 2. Auto-prioritization | **T3 (cut) — except** the manual Pin/Mute slice (T1). Not separable from #3's foundation; weights still TBD. |
| 3. Session planning + light pollution + location profiles | **T3 (cut).** Largest unbuilt arc; not needed for the beta value prop. |
| 4. Import ROADMAP items | **Narrow.** 6a–6c shipped; keep #26 discard/reveal (T1) + aids (T2); 6d + item-9 triage are T3. |
| 5. ROADMAP 7 / 8 / 9 | **Split.** 7 = #17 hint-set (T1) + gallery/#18/#19 (T2/T3); 8 = already-shipped export, follow-ups T3; 9 = T3. |

**Net:** the beta feature work is much smaller than the proposal implied — mostly
**onboarding**, **#17 generalization**, **manual priorities**, and **import/holding
polish**. The two heaviest items (session planning, auto-prioritization) are one
arc and belong *after* the beta, so real users shape the scoring.

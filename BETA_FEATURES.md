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
	  * Mike says: I am in contact with a Dwarf 3 owner, an S30 owner and an S30 Pro owner, discussing collecting some sample dumps from them. I will continue trying to recruit others as well.
- **Phase 1 — Import / ingest hardening** *(one code cluster: `ingest.py` /
  `ingest_dialog.py` / holding area).* #6 surface-skipped-files → #4 holding-area
  discard + reveal → **#5 multi-Seestar-model** *(as Phase-0 dumps arrive)*. Highest-
  traffic path a new user hits; #5 is the biggest unknown, so front-load it.
- **Phase 2 — #17 finished-hint generalization** *(processing/curation cluster;
  independent of Phase 1, can run in parallel).* A silent-misclassification
  landmine — derisk it before relying on strangers' output looking right.
- **Phase 3 — Manual Pin/Mute priorities (#3).** ✅ Done (`feature/manual-pins`).
  Self-contained (per-store `pins.toml` + right-click row controls on Library/Goals +
  Summary Priority-targets surfacing + empty-state).
- **Phase 4 — Onboarding / first-run (#1), LAST.** ✅ Done (`feature/onboarding`),
  after Phases 1–3 settled the flows its copy narrates. Data-folder prompt +
  Summary welcome/empty-state + Library empty hint + emptied seed priorities.
- **Then T2 fast-follows** (they already mirror T1 dependencies): #17 gallery —
  with the ⚠️ hero-cache fix, **only** when set-hero ships → #26 aids → Dwarf (when
  its dump is ready) → #25.

> **Note:** onboarding is listed *first* in T1 (it's the highest-value gap) but
> executes *last* — priority ≠ sequence. And Phase 0 recruitment has no line item
> in the tiers, yet it's the schedule driver.

---

## T1 — Must be online for the beta

- [x] **Onboarding / first-run experience** *(the #1 gap).* ✅ Done
  (`feature/onboarding`). Shipped: a **first-launch data-folder prompt**
  (`FirstRunDialog` + `config.is_first_run()`; persisted, no re-prompt); **empty-state
  guidance** — a Summary **welcome card + "Import images…" CTA** (`go_to_import` → the
  Import page) when nothing's captured, plus a Library "empty — Import or add an object"
  hint; and the **guided first import** happy path (CTA lands on the existing Import
  page). Also emptied the seed `priorities.toml` so a stranger doesn't inherit
  hand-authored targets. Overlaps [`BETA.md`](BETA.md) §4 (shippability angle).
- [x] **#17 finished/intermediate hinting — generalization** *(ROADMAP 7 / BUGS
  #17).* ✅ Done (`feature/finished-hints`). The finished-vs-intermediate
  classification was built on Mike's filename habits (ROADMAP: "probably not
  generalizable") — a stranger's files **would** misclassify. Now a
  preference-driven, user-editable keyword hint set (`m110/hints.py`, edited in
  Preferences → "Finished-image hints"), seeded from sensible defaults, replaces the
  hardcoded `_classify` patterns; all three consumers draw from it.
  *(The gallery promote/demote/set-hero UI in #17 is a T2 nicety on top — still open.)*
- [x] **Priority Targets view — degrade gracefully without the scorer.** ✅ Done
  (`feature/manual-pins`). The dashboard section read a hand/LLM-edited
  `priorities.toml` — empty/confusing for a fresh user. Now the manual **Pin / Mute**
  overrides are pulled forward (the self-contained "manual overrides" sub-item of
  ROADMAP item 1): a stable per-store `pins.toml` (`m110/pins.py`), right-click
  Pin/Mute on **Library** & **Goals** rows with a ▲/▼ marker, and **Summary** surfaces
  pinned objects (mutes excluded) **plus a clear empty state**. Gives the view a
  reason to exist **without** the scoring engine (T3).
- [x] **Holding-area: discard + reveal** *(BUGS #26, partial).* ✅ Done
  (`feature/holding-discard-reveal`). Strangers' messy imports *will* land in the 6c
  holding area, which offered no way to dismiss junk. Shipped: per-row **Discard**
  (confirmation modal → `ingest.discard_holding`, Inbox-scoped + prunes emptied
  folders) + **Reveal** (opens the group's `Inbox/<folder>` in the OS file manager).
  *(The FITS-header inspector / thumbnail / suggested-identity aids are T2.)*
- [ ] **Multi-Seestar-model + newer capture modes** *(ingest robustness; overlaps
  [`BETA.md`](BETA.md) §3).* Validated on one telescope/firmware/layout only.
  Confirm/degrade for **S30 / S50** folder layouts and newer output modes
  (**mosaic / framing / EQ-mode** captures produce different files). A rock-solid
  **manual "choose folder"** fallback covers what auto-detection misses.
- [ ] **Surface skipped files after import** *(BUGS UI-niceties).* "N already
  present, skipped." Copies are already skip-if-present; this is just reporting —
  avoids "did it actually work?" confusion for a first-timer.

## T2 — Strongly wanted; acceptable fast-follow

- [x] **#17 finished/unfinished gallery** — ✅ Done (`feature/finished-gallery`).
  The object view splits into **Finished / Working files** groups with right-click
  **promote / demote / set-hero** (curation persisted in journal frontmatter, atop the
  T1 hint-set). Shipped **with** the ⚠️ **hero-render cache fix** — hero now invalidates
  on source *identity* (a `.src` sidecar), not mtime, so picking an older image as hero
  re-renders instead of leaving a stale hero + row thumbnails.
- [x] **#26 holding-area identification aids** — ✅ Done (`feature/holding-aids`).
  `ingest.annotate_holding` pre-fills the Object/Kind pickers with a suggested identity
  (OBJECT header → slug, else nearest catalog object by RA/Dec) + kind (IMAGETYP);
  double-click a held row → `HoldingInspectDialog` with the FITS-header facts
  (OBJECT/IMAGETYP/FILTER/RA·Dec via `frame_info`) + a thumbnail preview.
- [ ] **DwarfLab (Dwarf II / 3) import** *(ROADMAP item 12).* Reach multiplier
  beyond Seestar; additive `LAYOUTS` entry + classifier, no store-version bump.
  Ship-in-beta vs. fast-follow is gated on getting one real Dwarf capture dump
  (see ROADMAP 12 / [`BETA.md`](BETA.md) §3).
- [x] **#25 optional per-sub `.jpg` preview import** — ✅ Done (`feature/sub-previews`).
  Preference (default off, Preferences → Import) imports the Seestar's per-sub previews
  into a dedicated `Images/<target>/previews/` archive; **decided** to keep them out of
  `lights/` and out of the gallery (avoids flooding it with per-sub previews).

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

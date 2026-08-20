---
name: Stack with Siril
description: Stack a target's light frames headlessly with Siril. Measures the frames and their headers first, surfaces what is notable (mixed exposures, mosaic geometry, per-filter splits, coverage depth, disk cost), explores alternatives against real recomputed numbers, waits for agreement, then hands over the command to run. Use whenever asked to stack, re-stack, or ask what settings an object's data supports.
arguments: object
---

# Stacking an object

Stack **{{object}}**.

A conversation, not a command. Measure → recommend → agree → run. The measuring
is yours; the running is theirs. A large mosaic costs hours and over 100 GB, so
starting one unasked is the failure mode to avoid.

Follow `explain-the-numbers` throughout: every figure below comes from the
engine, and none of it may be estimated.

## The division of labour

**The engine already decides the settings.** `plan_stack` runs a deterministic
scorer over the measured data and returns a setting *and its justification* for
every choice — drizzle, rejection, weighting, feathering, background extraction,
compression. Do not re-derive those, and do not paraphrase the reasoning from
memory: read `justifications` and quote it. Where you disagree, say so and let the
user decide; do not quietly substitute your own.

**Your job is the situation the scorer cannot see.** Whether these frames should
be one stack or three. Whether a night is systematically bad or merely worse.
Whether a mosaic is worth its cost tonight. Whether the checks the tool skipped
matter here. That is what the second half of this document is about.

## What you can and cannot do

- **`plan_stack` is read-only.** It reads FITS headers and returns the survey, the
  settings with a justification each, the warnings, the projection, and both Siril
  scripts. It writes nothing and it does **not** stack.
- **You cannot run the stack.** M110's assistant tools never modify the store.
  Present the proposal, get agreement, then give them `how_to_run`.
- If they ask you to run it and you have a shell, that is their call to make
  explicitly — still show the proposal and get agreement first.

## 1 — Find the data

`plan_stack` takes a **capture folder**, not an object slug: one folder can feed
several objects, mosaics keep a `_mosaic` suffix, and pairs keep both names
(`M81 M82`, `M108 M97`). Call `get_processing_state` if you are unsure which they
mean, and ask rather than guessing — stacking the wrong target wastes hours.

If the sandbox is **split per filter** the tool refuses and lists the filters with
their frame counts. That is not an error to route around; see *Broadband and
narrowband* below.

## 2 — Present it, then stop

Lead with a couple of sentences on what is actually in the data and what is
notable — the things worth catching before committing hours of compute. Then the
settings as a compact table with the engine's justification each, then the canvas
and disk cost. Then ask.

Worth saying in prose rather than burying in the table:

- **Mixed exposures or gain** — changes weighting and makes rejection less clean.
- **Mosaic** — say the coverage **depth**, because that is what drives drizzle and
  it is *not* the frame count.
- **Disk** — if the projection is a large fraction of free space, say it plainly.
- **Preset disagreement** — M110's own Naztronomy preset is keyed on total frame
  count, which overstates depth on a mosaic. If the tool warns, say which you
  would follow and why.
- **Siril missing** — the `siril` block says whether it is installed. If not, say
  so up front rather than proposing a run they cannot start.
- **Stray pointings** — a warning about frames pointing far outside the set means
  bad RA/Dec headers, not a slew. The geometry ignores them; the frames are still
  stacked. Worth one mention, not alarm.

**Two checks are skipped** because they need to run Siril, and both have a trap:

- **Do not report the Gaia catalogue as missing.** It was not checked. Absent
  evidence is not evidence of absence, and this one decides whether a mosaic
  assembles at all.
- **On mixed exposures the weighting is provisional, not a finding.** Without the
  FWHM pass the tool cannot know whether the longer subs are also the softer ones,
  so it proposes wFWHM as the safe default and says so. Present it that way.

`m110-stack <folder>` with no flags runs both and may change the recommendation.

## 3 — Explore alternatives with real numbers

Every override recomputes the **whole** proposal, projection included. So when
they ask "what if we skipped drizzle?", do not recite the flag — call `plan_stack`
again with `drizzle: 0` and tell them what actually changes. On a 744-frame set
that is 86 GB → 34.5 GB, and a canvas halved on each axis.

Overrides: `drizzle` (0 = off) · `pixfrac` · `rejection` · `weight` ·
`overlap_norm` · `feather` · `no_bg_extract` · `no_filters` · `filter_pct` ·
`only_exposure` · `exclude_night` · `filter`.

`overrides_applied` echoes what you forced, and `how_to_run` grows the matching
flags — so the command always matches the proposal they agreed to. Never hand-edit
that command: if a setting should change, change it through the tool and re-read
the result.

## 4 — Hand over the command

It takes minutes on a small set and hours on a mosaic, so tell them to run it in
the background. Siril's output streams to `siril_stack.log` in the working
directory, and a heartbeat reports the current stage every 60s with how long it has
been in that step — that last part is what distinguishes working from wedged, since
the stack step can be silent for an hour.

Reference points from the 904-frame NGC 7000 mosaic: registration ~12 min, stack
**25 min** with the defaults but **2 h 50 m** with `-overlap_norm` on. If a run is
going far longer than its shape suggests, overlap norm is the first suspect.

`--handoff` hardlinks the finished stack into `Images/<target>/astrowizard/` with a
provenance sidecar, ready to open in AstroWizard. The hardlink costs no disk, and
that sandbox is kept apart from `siril/` because the two artifacts have different
lifetimes: the stack costs hours and is stable, the finish is cheap and re-run
often. Without `--handoff` the stack stays in the sandbox, which is where **Import
finished work** looks. Either way the import is the user's action, not applied by
you.

---

# Complicated situations

## Broadband and narrowband, and any per-filter split

M110 splits a mixed-filter target into one job per filter (`siril/LP/`,
`siril/IRCUT/`), because **filters must never be combined in one stack.** They
have different sky backgrounds, different star colours and different SNR; a single
stack of both is not a colour composite, it is a mess no later step recovers.

The workflow is: **stack each filter separately, then combine the stacks.**

1. Call `plan_stack` once per filter. Expect different settings — filters usually
   differ in frame count, so coverage depth and therefore drizzle can differ.
2. **Force the same drizzle scale across filters if they disagree.** Two stacks at
   different scales do not register to each other, and re-running one is far
   cheaper than discovering that after both. Take the deeper filter's proposal as
   the reference and pass `drizzle` explicitly for the other.
3. Give one command per filter (`m110-stack 'M81 M82/LP' --run`), and say plainly
   that combining is a separate manual step.
4. Combining is **not** something M110 or this skill does. It happens afterwards in
   Siril (`rgbcomp`, or pixel math for an HOO/SHO palette) or in AstroWizard. Say
   that, rather than implying the stack is the finished article.

The same applies to a broadband and narrowband pair shot on one target: two images
to be blended with judgement, not two halves of one stack.

## Mosaics

A mosaic is not "a big single target", and the difference is **coverage depth** —
how many frames see a typical point of sky. On NGC 7000, 904 frames gave a depth of
108. Every setting that resolves per-pixel keys off that number, so quoting the
frame count instead overstates what the data supports.

- **Feathering is required, not optional.** Without it a frame stops dead at its
  edge, so at the periphery where only one or two frames cover, any level offset
  becomes a hard-edged block. Measured on NGC 7000 with feathering off: 93% of
  severe background steps sat within ~200px of the footprint edge, and the noise
  step across those seams was **21.6x** larger than elsewhere.
- **Never offer `no_bg_extract` on a mosaic.** Per-frame background extraction
  matters *more* there: every pointing sits at a different altitude and azimuth and
  carries a different gradient, and normalisation can only correct an offset and a
  scale, never a gradient *within* a frame. Residual ramps land on the canvas
  correlated with tile position, which is what seams are made of.
- **Overlap normalisation is opt-in and usually wrong first.** It protects
  large-scale structure in principle, but derives each coefficient from shared area
  with neighbours, and a corner frame overlaps only one or two others — the least
  constrained coefficient in the set, at exactly the periphery where seams appear.
  Reach for it only when large-scale structure is visibly flattened, and check the
  edges afterwards.
- **Mosaics need the local Gaia catalogue.** Without it Siril falls back to star
  registration and the mosaic silently fails to assemble.

**Checking a finished mosaic for tiling.** Raw block-to-block step sizes are
useless on a stretched nebula — real nebulosity produces large steps. What marks a
seam is *coherence*: one row or column boundary with a much larger mean step than
its neighbours, running straight across the frame. Measure that ratio, not the
absolute step. NGC 7000's first stack gave **21.6x** at the affected boundaries;
the accepted stack measures 1.7x horizontal / 2.0x vertical, which is within what
nebula structure alone produces. Anything near 2x is clean; 10x or more is a seam.
A starless, stretched export is the most sensitive input. Two caveats: seams
concentrate at the footprint edge, so a crop can mask a settings problem; and the
outer boundary is always a hard edge with nothing to blend into — that is not
tiling.

## Mixed exposures

Stacking them together is legitimate — `-norm=addscale` brings them to a common
level — but rejection then clips across two brightness populations. Offer
`only_exposure` as the alternative when the split is roughly even, and say the two
stacks would be combined afterwards.

The decisive question is whether the longer subs are also the *softer* ones. If
they are, noise weighting rewards them for having better per-frame SNR and drags
resolution down. Measured on M15: 10s subs median FWHM 3.09, 20s subs 4.85 — which
flips the answer. The read-only path cannot see this; `m110-stack <folder>` with no
flags measures it.

## Dropping a night

Reach for `exclude_night` sparingly. It is right when a session is systematically
wrong — bad focus, cloud throughout, a mis-slew — but not when a night was merely
worse, because it discards that night's *good* frames too. The wFWHM quality filter
already drops poor frames individually, across every night, which is better
targeting.

Judging a night needs a like-for-like comparison: compare an object against **its
own** baseline on other nights, never against other objects, because FWHM depends
on the star field and a globular and a planetary are not comparable in absolute
terms. Worked example — M63's 2026-06-10 session measured 1.50x its own baseline
FWHM and was 37% of the data; excluding it gave 9% better FWHM for 21% more noise,
a bad trade, and tightening `filter_pct` would have been the better move. And check
whether a "bad night" actually was one: across that same session quality swung from
1.50x to 2.04x to 0.78x, so excluding the night would have thrown away its best
data along with its worst.

## The one thing the per-setting justifications do not say

**The quality filters compound.** Four independent thresholds at 95% do not retain
95% — measured on NGC 7000, 904 frames registered down to 753, about 83%. The
default is 98% because 95% was measurably too tight (it cut 21 of 231 frames on M15
with no FWHM gain). Budget for the loss when a target is close to an integration
goal, and reach for `no_filters` only when a set is already thin.

## After

The stack ends linear, plate-solved and 32-bit. SPCC, stretching, denoise,
sharpening and any filter combination happen afterwards — in AstroWizard, or by
hand in Siril.

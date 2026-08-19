---
name: Stack with Siril
description: Stack a target's light frames headlessly with Siril. Measures the frames and their headers first, surfaces what is notable (mixed exposures, mosaic geometry, coverage depth, disk cost), recommends settings with reasons, waits for agreement, then hands over the command to run. Use whenever asked to stack, re-stack, or ask what settings an object's data supports.
arguments: object
---

# Stacking an object

Stack **{{object}}**.

A conversation, not a command. Measure → recommend → agree → run. The measuring
is yours; the running is theirs. A large mosaic costs hours and over 100 GB, so
starting one unasked is the failure mode to avoid.

Follow `explain-the-numbers` throughout: every figure below comes from the
engine, and none of it may be estimated.

## What you can and cannot do

- **`plan_stack` is read-only.** It reads every frame's FITS header and returns
  the survey, the proposed settings with a justification each, the warnings, the
  disk projection and the exact Siril script those settings produce. It writes
  nothing and it does **not** stack.
- **You cannot run the stack.** M110's assistant tools never modify the store.
  Present the proposal, get agreement, then give the user the `m110-stack …
  --run` command from the tool's `how_to_run` field to run themselves.
- If they ask you to run it and you have a shell available, that is their call to
  make explicitly — still show the proposal and get agreement first.

## 1 — Find the data

Call `get_processing_state` first if you are not sure which capture folder they
mean. Folder names are as captured, so mosaics carry a `_mosaic` suffix and pairs
keep both names (`M81 M82`, `M108 M97`). If the name is ambiguous, ask rather
than guessing — stacking the wrong target wastes hours.

`plan_stack` resolves the folder to M110's `siril/` sandbox itself. The sandbox is
where the lights are hardlinked (no extra disk) and where **Import finished work**
expects the result back.

## 2 — Present it, then stop

Lead with a couple of sentences on what is actually in the data and what is
notable about it — the things worth catching before committing hours of compute.
Then the settings as a compact table with a short justification each (the tool
returns one per setting), then the disk and canvas cost. Then ask.

Worth calling out in prose rather than burying in the table:

- **Mixed exposures or gain** — changes weighting and makes rejection less clean.
- **Mosaic** — say so, and say the coverage *depth*, because that is the number
  driving the drizzle call and it is **not** the frame count.
- **Disk** — if the projection is a large fraction of free space, say it plainly.
- **Preset disagreement** — M110's own Naztronomy preset is keyed on total frame
  count, which overstates depth on a mosaic. If the tool warns they disagree, say
  which you would follow and why.
- **Siril missing** — the `siril` block says whether it is installed. If not, say
  so up front rather than proposing a run they cannot start.

Two checks are **skipped** in the read-only path because they need to run Siril:
whether the local Gaia catalogue is present, and the per-exposure FWHM
comparison. The tool says so in its warnings. Do not report the catalogue as
missing — it was not checked. `m110-stack <dir>` with no flags runs both.

Then wait. If they want changes, say what the flag would be and re-run
`plan_stack` where the tool supports the override, so they see the revised cost
before committing.

## 3 — Hand over the command

The tool returns `how_to_run`. Add overrides they agreed to:

`--only-exposure SEC` · `--exclude-night YYYY-MM-DD` · `--drizzle SCALE` ·
`--no-drizzle` · `--rejection "l 5 5"` · `--weight noise|wfwhm|nbstars|none` ·
`--overlap-norm` · `--no-bg-extract` · `--no-filters` · `--feather PX` ·
`--restack` / `--keep-process` · `--handoff` (see below).

It takes minutes on a small set and hours on a mosaic, so tell them to run it in
the background. Siril's output streams to `siril_stack.log` in the working
directory, and a heartbeat prints the current stage every 60s with how long it has
been in that step — that last part is what distinguishes working from wedged,
since the stack step can be silent for an hour.

Reference points from a 904-frame mosaic: registration ~12 min, stack **25 min**
with the defaults but **2 h 50 m** with `-overlap_norm` on. If a run is going far
longer than its shape suggests, overlap norm is the first thing to suspect.

## What it decides, and why

**Coverage depth, not frame count.** How many frames actually cover a typical
point of sky. For a single target that is every frame; for a mosaic it is far
fewer. It drives both drizzle and rejection, because both resolve against the
frames that saw a given pixel.

| depth | drizzle | rejection |
|---|---|---|
| < 100 | off | Winsorized 3 3 (percentile below ~10) |
| 100–300 | 1.5x / 1.0 | Winsorized 3 3 |
| 300–500 | 1.5x / 0.75 | Winsorized 3 3 |
| > 500 | 2.0x / 0.5 | Winsorized 3 3 |

Points worth knowing when explaining a choice:

- **The quality filters compound.** Four independent thresholds at 95% do not
  retain 95% — measured, 904 frames registered down to 753, about 83%. The
  default is 98%, because 95% was measurably too tight. Budget for the loss when a
  target is close to an integration goal.
- **Feathering on mosaics is required, not optional.** Without it a frame stops
  dead at its edge, so at the periphery where only one or two frames cover, any
  level offset becomes a hard-edged block. Measured with feathering off: 93% of
  severe background steps sat within ~200px of the footprint edge, and the noise
  step across those seams was 21.6x larger than elsewhere.
- **Overlap normalisation is opt-in.** It protects large-scale structure in
  principle, but derives each coefficient from shared area with neighbours, and a
  frame at a mosaic corner overlaps only one or two others — the least constrained
  coefficient in the set, at exactly the periphery where seams appear. It is also
  the prime suspect for a very slow stack.
- **Noise weighting when exposures are mixed**, because wFWHM would weight a sharp
  20s frame the same as a sharp 30s one. It is incompatible with overlap
  normalisation — Siril drops it silently — so the engine reconciles the two up
  front rather than letting that happen.
- **Debayering is bound to drizzle, and is derived, not a preference.** Drizzle
  needs raw CFA and demosaics as it resamples, so debayering first forecloses it;
  with drizzle off nothing else touches the CFA and the stack comes out
  **monochrome**. If a stack ever returns mono, this is why.
- **Mosaics need the local Gaia catalogue.** Without it Siril falls back to star
  registration and the mosaic silently fails to assemble.
- **Reach for `--exclude-night` sparingly.** It is right when a session is
  systematically wrong — bad focus, cloud throughout, a mis-slew — but it discards
  that night's *good* frames too. The wFWHM filter already drops poor frames
  individually, across every night, which is better targeting. Judge a night
  against that object's *own* baseline on other nights, never against other
  objects: FWHM depends on the star field, so a globular and a planetary are not
  comparable in absolute terms.

## After the stack — handing on to AstroWizard

`m110-stack … --run --handoff` hardlinks the finished stack into
`Images/<target>/astrowizard/` with a provenance sidecar, ready to open in
AstroWizard. The hardlink costs no disk, and the sandbox is kept separate from
`siril/` because the two artifacts have different lifetimes: the stack costs
hours and is stable, the finish is cheap and re-run often.

Without `--handoff` the stack simply stays in the sandbox, which is where M110's
**Import finished work** looks for it. Either way the app-side import is the
user's action, not applied by you.

The stack itself ends linear, plate-solved and 32-bit. SPCC, stretching, denoise
and sharpening happen after — in AstroWizard, or by hand in Siril.

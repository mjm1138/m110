---
name: Stack with Stackhammer
description: Stack a target's light frames with Stackhammer, the faster stacking engine for Siril on Apple silicon that adds local normalization. Asks Stackhammer what it would do with the frames, explains every setting with the engine's own reason, explores alternatives, waits for agreement, then hands over the command or stages a preset for the Stackhammer window in Siril. Use when asked to stack with Stackhammer, to compare it with the Siril stacker, or to change any Stackhammer setting.
arguments: object
---

# Stacking an object with Stackhammer

Stack **{{object}}** with Stackhammer.

A conversation, not a command: ask the engine → present → agree → hand over. You
cannot run the stack, and nothing here is applied until the user does it.

Follow `explain-the-numbers` throughout. Every figure below comes from
Stackhammer's own report; none may be estimated, and none may be carried over
from the Siril stacker's proposal.

## What Stackhammer is, in two sentences

Siril still calibrates and plate-solves the lights. Stackhammer then does the
expensive half — applying the registration, drizzle, normalization, rejection
and integration — on the Mac's GPU, only over the pixels each frame covers, and
adds **local normalization**, which Siril's stacker does not have.

It is **pre-alpha**, built from source, and runs only on a Mac with Apple
silicon. Say so once when it matters; do not bury it and do not labour it.

## Stackhammer or the Siril stacker?

Both are available for the same folder; `plan_stack` is the Siril one. Reach for
Stackhammer when:

- **The nights differ.** A moonlit session, a light-polluted one, or a mosaic
  whose panels were shot at different altitudes. Photometric scales put every
  frame on one brightness scale from its stars, and local normalization matches
  each frame's sky to a reference. That is the case it was built for.
- **It is a mosaic.** The canvas is mostly empty per frame, and Stackhammer only
  processes where a frame has data.
- **Time matters.** Siril's stack step is the slow part of a big set.

Prefer the Siril stacker when Stackhammer is not installed, on any other
platform, or when the user wants the long-proven path. A filter that M110 split
into several job folders (lights needing different calibration) is stacked as
one group by the Siril engine and one folder at a time by Stackhammer here; the
tool says so in `notes`.

Filters still stack **separately** and are combined afterwards, exactly as in
the Siril skill. Each filter's job folder has its own plan and its own preset.

## What you can and cannot do

- **`plan_stackhammer` is read-only.** It runs only Stackhammer's read-only
  commands, which read FITS headers. It does not stack and writes nothing.
- **You cannot run the stack.** Give `how_to_run` verbatim, or point at
  `how_to_run_in_siril`. Never shorten the command: it names `m110-stack` by its
  full path, and `stacker` says which M110 install that is.
- **`propose_stackhammer_preset` changes nothing either.** It stages a proposal
  that waits in M110; the preset file is written only when the user applies it.
- If Stackhammer is not found the tool says where M110 looked. Pass that on, and
  explain settings from this document if they still want to talk it through.

## 1 — Ask the engine

Call `plan_stackhammer` with the **capture folder** (not an object slug; use
`get_processing_state` if unsure, and ask rather than guess). A sandbox split
per filter needs `filter`; the error lists them.

Read these parts of the result:

- `lights` — count, exposures, camera.
- `calibration` — per subset of the lights: how they were captured, and the
  dark, flat and bias chosen for them with the reason, or why none.
- `siril_steps` — what Siril will run to make the plate-solved sequence.
- `settings` — **every** option: `value`, `proposed` (Stackhammer's own choice
  for these frames), `choices`, `why`, and `source` (`default`, `preset` or
  `override`).
- `solved` — only when the folder already holds a plate-solved sequence: how
  many frames each quality filter keeps, the canvas, and the coverage depth.
- `warnings` and `notes`.

**Before the plate solve, depth is unknown.** Stackhammer measures which frames
the filters keep, the canvas and the depth from Siril's plate solve, so on a
fresh folder `solved` is null and `solved_note` says why. Do not fill the gap
with the frame count or with the Siril proposal's depth. A run preprocesses
first and plans then.

## 2 — Present it, then stop

A couple of sentences on what is in the data and what is notable, then the
settings that matter as a compact table with Stackhammer's `why` for each, then
what a run will do. Quote the reasons; do not paraphrase them from memory.
Where a `value` differs from `proposed`, say who changed it (`source`).

Worth saying in prose:

- **Calibration.** Read `calibration.summary`. If frames from a Seestar's own
  app sit beside frames the same telescope took under N.I.N.A., say that the
  first get nothing and the second get real calibration, in one stack.
- **A refused dark or flat.** A subset's `notes` say what kept it out (size,
  binning, colour pattern, exposure, gain). That is a finding, not an error to
  route around.
- **Existing sequences.** `existing_sequences` means an earlier run's
  intermediates are in `process/`. A headless run clears them first unless the
  user asks to reuse them (`--restack`).
- **Siril missing**, from the `siril` block: say so before proposing a run.

## 3 — Explore alternatives

Pass `settings` with Stackhammer's own option names and call again. The report
is asked for afresh, so a filter change shows real kept-frame counts (when a
solved sequence exists) and a calibration change shows the new match and the
new Siril steps. An unknown name or value is refused with the valid ones; that
list is the installed Stackhammer's, so trust it over this document.

`overrides_applied` echoes what you forced, and `how_to_run` grows a matching
`--set` for each one the folder's preset does not already hold. Never hand-edit
the command.

## 4 — Hand over

Two routes; offer the one that fits how they work.

**Headless.** Give `how_to_run`. It preprocesses in Siril, stacks, and cleans
up, reporting the current stage on a heartbeat (`verbosity` raises it, as for
the Siril stacker). `--handoff` on the end sends the finished stack to
AstroWizard. The stack is named from its frames and lands at the top of the
folder's Siril working directory, where M110 lists it to send on for finishing.

**In Siril.** Stage the agreed settings with `propose_stackhammer_preset`, tell
the user to apply it in M110, then follow `how_to_run_in_siril`. The preset is
the **whole** file, not a patch: start from `preset.settings`, change what was
agreed, and pass the result. Only settings that differ from Stackhammer's
defaults need to be in it. A different preset already there is kept in
`presets/archive/`.

The preset serves both routes: once applied, the headless command needs no
`--set` at all. Prefer it when settings were agreed after real discussion, so
the next stack of this folder starts from them.

---

# The settings, and the judgement the reasons don't carry

Each option's `why` is Stackhammer's and cites its own measurements. What
follows is when to change one.

## Normalization

- **`normalization`**: `photometric` (frame scales from star fluxes) or
  `addscale` (Siril's, kept for parity). Leave `photometric` unless the goal is
  a like-for-like comparison with a Siril stack.
- **`local-norm`**: on by default, and only meaningful on photometric scales. It
  costs time on a large mosaic. Turning it off is reasonable for one clean night
  on a single pointing; it is the wrong economy for mixed nights or a mosaic.
- **`max-frame-residual`** (advanced): local normalization leaves out a frame
  whose sky it cannot fit. The result's `notes` say run can stack fewer frames
  than the filters keep for this reason. `0` keeps every frame. Reach for it
  when a target is short of its integration goal and the left-out frames are
  known to be sound, not as a default.
- **`local-norm-degree`** and **`local-norm-reference-noise`** (advanced): leave
  alone unless diagnosing local normalization itself.
- **`neutral-background`**: moves each colour channel's sky to one level so an
  autostretch opens neutral. It is one constant per channel, so it removes no
  gradient and does not replace colour calibration. Turn it off only when
  comparing raw channel levels.

## Background extraction (`background`)

**Off by default, deliberately**, and this is the opposite of the Siril
stacker's advice. Here each frame keeps its gradient and local normalization
matches every frame's sky to the reference; the reference's own gradient is then
removed from the finished stack. Stackhammer's reason records what per-frame
extraction did to a large galaxy's outer disc. Turn it on only if the user has a
reason the reference-stack approach does not serve, and say what they give up.
Left unset, it follows what `process/` already holds, so an earlier run made
with it stays ready to stack.

## Rejection

- **`rejection`**: `winsorized`, `sigma` or `none`; **`low`** / **`high`** are
  the thresholds in σ.
- **`rejection-noise`**: `frame` judges each value against its own frame's
  noise, which is what makes rejection safe across mixed exposures and mixed
  skies; `pixel` is the classic single-σ rule. Keep `frame` on any mixed set.
- **`rejection-signal-share`** (advanced): leave at its default.

## Weights (`weight`)

`noise-fwhm` (default), `noise`, `fwhm`, `psf` or `none`. The default trades a
little noise for narrower, rounder stars, and its `why` gives the measured
trade. Offer `noise` for a faint, diffuse target where depth matters more than
star shape, and `fwhm` when seeing varied a lot and resolution is the point.

## Quality filters

`filter-round`, `filter-fwhm`, `filter-bkg`, `filter-nbstars`: the share of
frames each **keeps**. They are computed over the whole sequence and combined,
so they compound, as in the Siril stacker. With a solved sequence the plan says
exactly how many frames each one fails; quote that rather than estimating.
Loosen one filter at a time. Note the name: on a plate-solved sequence Siril's
weighted FWHM is plain FWHM, so Stackhammer calls it `filter-fwhm`.

## Feathering (`feather`)

Pixels over which a frame fades out at its edge; `0` is off. Keep it on for a
mosaic, where a frame edge would otherwise be a step.

## Drizzle

- **`drizzle`**: off for debayered frames, where it is optional. Turned on, the
  preprocessing keeps the raw colour sites instead of debayering, and the stack
  drizzles them (Bayer drizzle), so the choice changes the Siril steps too.
  Changing it on a folder with a solved sequence means preprocessing again.
- **`drizzle-scale`**, **`pixfrac`**: the output grid and the droplet size.
- **`drizzle-weights`**: `noise` (least noise) or `coverage` (Siril's; narrower
  stars for more noise). The `why` carries the measured trade.

When filters will be combined afterwards, force the same drizzle setting and
scale on each, as for the Siril stacker: stacks on different grids do not
register to each other.

## Calibration

- **`calibration`**: on. Darks, flats and biases beside the lights (M110 links
  the matched ones into each job folder) are matched by header, per subset of
  the lights. Off stacks the lights as they are.
- **A Seestar app's own subs never get any.** They are dark-subtracted and
  flat-fielded on the telescope; a library dark on top would subtract twice. The
  same telescope under N.I.N.A. saves raw frames that do need calibration. Never
  suggest forcing a dark onto app subs.
- **`cosmetic`**: with a dark, replace the hot pixels it shows. Leave on.
- **`equalize-cfa`**: level a colour camera's master flat across its colours so
  dividing by it does not tint the lights. Leave on for colour data.
- **`bias-level`**: a constant offset in ADU for flats with no biases or dark
  flats. `0` is automatic. Set it only when the user knows their camera's
  offset and the automatic value is wrong.
- **`darks`**, **`flats`**, **`biases`**, **`dark-flats`**: another folder to
  take those frames from, instead of the one beside the lights.

## Housekeeping

- **`compress`**: Rice-compress Siril's intermediates. Off is fastest; on takes
  under a third of the disk. Offer it when free space is the constraint.
- **`clean`**: delete the run's intermediates after a successful stack. The
  lights and the result always stay.

## After

The stack is linear, 32-bit and plate-solved, with a depth map, a rejection map
and a per-frame record beside it. Colour calibration, stretching, denoise and
any filter combination happen afterwards, in AstroWizard or in Siril.

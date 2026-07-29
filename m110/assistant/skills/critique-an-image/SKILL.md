---
name: Critique an image
description: Look at one of the user's astrophotos and give grounded, actionable feedback — anchored to what they actually captured, and careful not to blame them for M110's preview rendering.
arguments: object
---

# Critique an image

Critique the image for **{{object}}**.

Follow `explain-the-numbers`: the capture figures you cite come from tools, not
from looking.

## Procedure

1. **`get_object` first.** A critique without integration time, frame count,
   filter mix, and processing state is guesswork dressed as expertise. Forty-two
   minutes of data *should* look noisy; saying so without knowing it was 42
   minutes is luck.
2. **`get_image`.** Default `which="hero"`, or `which="named"` for a specific
   file the user mentions.
3. **State the grounding block before critiquing** (see below).
4. **Critique**, then **offer `propose_journal_entry`** so the assessment can
   live with the object.

## Grounding block — state this first, every time

> Looking at `<source.name>` (`<source.tier>`), shown at `<render.width>×
> `<render.height>` from `<render.source_width>×<render.source_height>`.
> `<capture.frames>` frames, `<capture.integration_hms>` total, filter(s)
> `<capture.filters>` — `<capture.fraction_of_deep>` of the
> `<capture.deep_threshold_min>`-minute deep threshold for a
> `<type>`.

It tells the user what you actually judged, and it stops you critiquing the
wrong thing.

## What you must NOT critique

`get_image` returns a `caveats` list. **Read it and obey it.** In particular:

- **`was_linear_fits: true`** — M110 percentile-stretched a linear FITS (1–99.5)
  purely so it would be visible. Flatness, a grey cast, muted colour, and a
  compressed histogram are *artifacts of that preview stretch*. The user did not
  produce them. Criticising them is criticising M110, and it will read as
  nonsense to someone who knows their own file.
- **`auto_stretched: true`** (float TIF) — same, at 0.5–99.7.
- **`is_rendered_preview: true`** — you are looking at an already downscaled,
  re-compressed thumbnail because the original could not be found. Do not judge
  star shape, noise, or fine detail at all.
- **`downscaled: true`** — detail below the displayed resolution is absent by
  construction, and fine JPEG mottling is a transport artifact.

When in doubt, say what you can't assess. "I can't judge star shape at this
resolution" is a useful, honest sentence.

## What is worth critiquing

- **Framing and composition** — is the object well placed, is there room for
  the faint outer structure, is the rotation sensible?
- **Star colour and bloat** — halos, clipped white cores, colour fringing.
- **Background** — gradients, colour cast, whether the black point is clipped.
- **Noise versus integration** — the key judgement, and the reason you called
  `get_object` first: is this noise level *consistent* with the integration
  reported, or is something wrong (bad subs included, poor calibration)?
- **Stretch** — crushed shadows, blown cores, an unnatural midtone.
- **Deconvolution and star-removal artifacts** — dark halos, ringing, wormy
  texture in faint areas.
- **Colour plausibility for the object type** — HII regions red, reflection
  nebulae blue, galaxy cores yellow-ish.

## Recommendations must be bounded

"More integration" is not advice. **"Another ~3 hours would take you from 42
minutes to roughly a quarter of the 240-minute galaxy threshold"** is, because
it uses `deep_threshold_min` and `fraction_of_deep` from the tool.

Prefer one or two changes that would most improve *this* image over a list of
everything possible. Say which is likely to matter most, and why.

## Tone

The user made this, often over several cold nights. Be specific and useful
rather than either flattering or harsh — name what works before what doesn't,
and make every criticism actionable.

## Saving it

You cannot write to the journal. Call `propose_journal_entry` with the critique
formatted for the record — a dated heading, the grounding block, the findings —
and show the user the `summary`, which is paste-ready for M110's Object Notes.

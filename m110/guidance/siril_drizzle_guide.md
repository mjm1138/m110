# Drizzle in Siril — How It Works and How to Use It

A practical guide to drizzle for the Seestar S50 workflow. Covers the
mechanics, the two-parameter interaction (drizzle scale × pixel fraction),
when drizzle helps vs. doesn't, and a decision tree for picking settings
per target.

---

## What drizzle is

Drizzle ("Variable Pixel Linear Reconstruction") was invented for the
Hubble Space Telescope to recover sub-pixel detail from undersampled
imagery. The core trick: when you have many exposures of the same scene,
each with slightly different *sub-pixel* alignment offsets (from imperfect
tracking, intentional dithering, or both), you can reconstruct a
higher-resolution image from the collection than any single exposure
provides.

The math: each input pixel gets shrunk to a smaller footprint, then
"dropped" (hence "drizzle") onto a finer-grid output canvas at the
appropriate sub-pixel position. Where many input drops overlap on the
output grid, you get a confident signal estimate. Where coverage is
sparse, the algorithm interpolates.

**Drizzle is not just upscaling.** Upscaling adds output pixels but
invents no new information. Drizzle extracts genuine sub-pixel
information that was hidden by sampling — but only if the conditions are
right (many frames, real sub-pixel offsets between them, undersampling
in the originals).

---

## The two parameters

### Drizzle amount (scale factor)

How much finer the output grid is than the input.

- **1.0×** — no scaling. Output grid same resolution as input. Drizzle
  still operates (proper weighted combination), just no resolution gain.
- **1.5×** — output grid 1.5× finer in each dimension. 2.25× the pixel count.
- **2.0×** — output grid 2× finer. 4× the pixel count.
- **3.0×** — output grid 3× finer. 9× the pixel count. Rarely useful.

The scale you can usefully apply is bounded by your seeing relative to
your native pixel scale. If a star image already spans many pixels
(oversampled), increasing scale just gives you bigger blurry stars. If a
star spans 1–2 pixels (undersampled), drizzle can pull genuine structure
from the multi-frame data.

### Pixel fraction (drop size)

How big each input pixel's footprint is *relative to its original size*
when dropped on the output grid.

- **1.0** — input pixels keep their original footprint. Each input fully
  covers some area of the output grid.
- **0.7** — input pixels shrunk to 70% of original size.
- **0.5** — input pixels shrunk to half size.
- **0.3** — very small drops. Sharpest but most fragile.

Smaller drops = sharper output (less blurring from finite pixel size)
but require more frames to cover all output pixels and produce noisier
individual estimates.

---

## How the two parameters interact

This is the part most explanations skip. There's a natural "matched"
relationship:

> **`pixel_fraction ≈ 1 / drizzle_scale`** is the geometric sweet spot
> where each input pixel maps to roughly one output pixel.

| Drizzle scale | Matched pixel fraction | What it means |
|---|---|---|
| 1.0× | 1.0 | Each input → one output pixel. Normal stacking. |
| 1.5× | ~0.67 | Each input → one output cell (in the finer grid) |
| 2.0× | 0.5 | Same logic for 2× grid |
| 3.0× | 0.33 | Same logic for 3× grid |

- **Pixel fraction *above* matched** (e.g., 1.0 at scale 1.5×) — each
  input covers *multiple* output pixels. You get smoother results with
  more coverage but minimal sharpness gain from drizzle. Behaves a lot
  like weighted upscaling.
- **Pixel fraction *at* matched** — each input maps to one output cell.
  You get the cleanest resolution gain, assuming sub-pixel dithering is
  present.
- **Pixel fraction *below* matched** (e.g., 0.3 at scale 1.5×) — each
  input covers *less than* one output pixel. You get the sharpest detail
  but the output has gaps that must be filled by frames at different
  sub-pixel positions. Risky with low frame counts.

---

## What this means for the Seestar S50 specifically

### The Seestar's native sampling

- Pixel size: 1.92µm
- Focal length: ~250mm
- Plate scale: 206265 × (1.92e-3 / 250) ≈ **1.6 arcsec/pixel**

### Typical Boulder seeing

2–3 arcsec FWHM on a decent night.

Star FWHM in pixels = seeing / plate_scale ≈ 1.5–2 pixels native. That
puts the Seestar in the **borderline-undersampled** regime — drizzle can
recover *some* detail under good seeing, but you're not in
deeply-undersampled HST territory.

### Drizzle scale recommendations for the Seestar

| Scale | When it helps | When it doesn't |
|---|---|---|
| 1.0× | Always safe; cleanest combination of frames; no resolution gain | — |
| 1.5× | Good seeing (≤2.5") + 100+ frames + real dithering | Poor seeing or low frame count |
| 2.0× | Excellent seeing (≤2") + 500+ frames + good dithering | Most Boulder nights |
| 3.0× | Almost never on the Seestar | — |

### Naztronomy default = pixel fraction 1.0

(Per CLAUDE.md notes.) Conservative. With 1.5× drizzle and 1.0 fraction,
you're getting weighted-upscaled output with very small actual sharpness
gain — but also no artifacts and full coverage. That's the safe choice
and probably right as a default.

If you want to *actually exploit* drizzle's sharpness benefit:

| Setting combo | Behavior | Risk |
|---|---|---|
| 1.5× / pixel 1.0 (default) | "Smooth upsampler"; minimal resolution gain | Low risk, low reward |
| 1.5× / pixel 0.7 (matched) | Modest sharpness gain | Needs ~200+ frames with real dithering |
| 1.5× / pixel 0.5 | Sharper but more pixel noise | Need ~400+ frames |
| 2.0× / pixel 0.5 (matched) | Aggressive sharpness gain | Need ~500+ frames + good seeing + good guiding |
| 2.0× / pixel 1.0 | Just upscaling, no benefit over 1.5× | — |

---

## When drizzle definitely doesn't help

1. **Low frame counts (<100 frames).** Drizzle needs many sub-pixel views
   of each output cell to converge. Single frame or <100 frames: skip
   drizzle, just stack at 1.0×.

2. **Heavily oversampled data.** Big scope + small pixels = native data
   already resolves finer than seeing allows. Drizzle = pointless.

3. **No real sub-pixel dithering.** If all frames are aligned to within a
   fraction of a pixel (perfect tracking, no dither), drizzle has no
   extra info to extract. The Seestar's slight tracking imperfections
   and EQ-mode movement provide *some* natural dithering, but it's
   modest.

4. **Bad seeing.** If the seeing disc is 3+ arcseconds = ~2 pixels,
   you're already sampling at the seeing limit. Drizzle can't make the
   atmosphere stop blurring.

---

## Practical decision tree

For the Seestar workflow:

```
How many usable frames? (after Siril rejection — see stack_meta on the site)
├── < 100: drizzle 1.0× (no scaling); just stack
├── 100–300: drizzle 1.5× + pixel fraction 1.0 (current default — safe)
├── 300–500: drizzle 1.5× + pixel fraction 0.7 (matched — actual sharpness gain)
└── > 500 AND good seeing AND target benefits:
        drizzle 2.0× + pixel fraction 0.5 (matched — aggressive)
```

For a specific target, look at the stack FITS header's `STACKCNT`
(now surfaced on the site under each object's processing row) to know
your usable frame count.

### Examples

- **M101 (977 frames, 26% rejected from 1327)** — eligible for 1.5×
  with pixel fraction 0.7. Currently using 1.5× / 1.0 — could try the
  matched version for sharper detail.
- **M81/M82 (~3200 frames at 20% reject ≈ 2500 usable)** — eligible
  for 2.0× / 0.5 if seeing was decent across those sessions.
- **M37 (16 frames)** — drizzle pointless. Just stack 1.0×.
- **M57 (39 frames so far)** — too few for drizzle. Stack 1.0× until
  you have 100+.

---

## One more nuance — dithering source quality

The Seestar's *intrinsic* sub-pixel dithering quality varies with mount
mode and EQ alignment:

- **EQ mode + good polar alignment**: smooth, slow drift across frames.
  Great for drizzle (slow, varied sub-pixel positions across many
  frames).
- **Alt-Az mode**: field rotation creates artificial dithering but
  distorts the geometry. Worse for drizzle.
- **EQ mode + bad polar alignment**: lots of dithering, but also star
  trailing within each frame. Frames get rejected at Siril's quality
  filter step before they reach drizzle anyway.

The same rejection rate (`stack_meta.stack_rejection_pct` on the site)
is a useful proxy for "is drizzle viable for this target?":

- **Low rejection (5–15%)**: good frames, good drizzle candidate
- **Moderate rejection (15–30%)**: workable but be conservative on scale
- **High rejection (>30%)**: atmospheric / tracking issues, drizzle
  won't rescue what's broken

---

## Bottom line

For 90% of routine work, **stick with the Naztronomy default of 1.5×
scale + 1.0 pixel fraction** — safe, predictable, modest benefit. The
cost of experimenting with sharper settings is a re-stack; the benefit
(when conditions are right) is genuinely sharper detail in finished
images.

Worth experimenting on your most-frame-rich targets (M81/M82, M51, M94)
with 1.5× / 0.7 first to see if you can tell the difference, then push
to 2.0× / 0.5 only if frame counts and seeing genuinely support it.

---

## Quick reference card

```
Drizzle scale × pixel fraction = matched →  geometric sweet spot
                                          (1.0 / scale)

For Seestar S50 (1.6"/pixel, 2-3" seeing in Boulder):

  Frame count        Recommended drizzle settings
  ─────────────      ────────────────────────────────────
  < 100              1.0× (skip drizzle)
  100–300            1.5× / 1.0  (safe default)
  300–500            1.5× / 0.7  (matched, more sharpness)
  > 500 + good       2.0× / 0.5  (matched, aggressive)

Always check stack_meta rejection rate first.
High rejection (>30%) means stack-quality issues that drizzle won't fix.
```

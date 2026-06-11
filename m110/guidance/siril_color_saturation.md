# Color & saturation workflow — galaxies and stars

How to get rich, believable color out of Seestar S50 OSC data in Siril,
covering the two problems that are hardest in practice: making galaxy
color (especially faint emission like M82's red outflow) *pop*, and
giving stars magnitude-appropriate color through luminance-weighted
masking. Companion to `siril_processing_workflow.md` and
`siril_psf_guide.md`.

---

## The core concept: luminance–chrominance separation

Every brightness stretch — histogram, GHS, asinh — **desaturates as it
brightens.** As a pixel approaches white it loses its color ratios. So
stretching a galaxy hard enough to reveal structure simultaneously
bleaches color out of exactly the bright regions you care about. A
global saturation slider at the end is fighting the stretch.

The fix is to stop stretching luminance and color together:

1. Stretch a **luminance** copy hard for detail and contrast.
2. Process the **color (chrominance)** separately — saturate it
   aggressively, even to where it looks garish on its own. Color noise
   becomes invisible once married back to a sharp luminance layer.
3. **Recombine.**

This is the OSC equivalent of the LRGB workflow, and it's the single
biggest lever on galaxy color. Even when you don't do a full
luminance/color split, *thinking* in these terms explains why the order
of operations below matters.

---

## Galaxy color

### 1. Get color balance right before you saturate

Saturating an uncalibrated image just amplifies a cast. Always:
**RBF background extraction → SPCC** (Seestar S50 selectable as sensor)
*before* any saturation pass. A neutral background is a precondition —
saturation on a non-neutral background amplifies color blotches in the
sky.

### 2. Stretch with color preservation

- **Asinh Transformation** (Image Processing → Stretching → Asinh)
  preserves color ratios far better than a histogram drag. Easiest
  upstream win.
- **VeraLux HMS** is built for OSC color preservation — lean on it
  rather than finishing with a histogram stretch that bleaches the
  brights.
- Avoid finishing the stretch with a hard histogram shadows-drag; that's
  where color dies.

### 3. Saturate starless

Do all galaxy saturation on the **starless** layer (you already separate
stars). Star cores can't blow out, and you can push the galaxy far
harder than you could with stars present.

### 4. Use hue-selective saturation, not global

Siril's Saturation tool (and the `satu` command) is hue-aware. This is
the key under-used native tool.

```
satu amount [background_factor [hue_range_index]]
```

- **amount** — saturation increase, e.g. `0.2`. Positive boosts.
- **background_factor** — protects dark areas; saturation is applied
  only above background-median × factor. Default `1.0`. Raise it to keep
  faint background from getting saturated noise.
- **hue_range_index** — selects one band of the color wheel (`0`–`6`).
  The GUI Saturation dialog shows the bands by name in a dropdown
  ("Global", "Pink-Red to Red", "Red to Orange", etc.) — confirm the
  band there. The **red/magenta band** is the one for Hα emission.

For a galaxy with both a blue disk and red HII / outflow regions, run
**two passes**: one restricted to the red/magenta band to push the
emission, a separate gentler pass on the blue band for the disk. Global
saturation can't do this — it lifts everything proportionally and the
faint red never catches up to the bright continuum.

GUI path: Image Processing → Color Saturation. Set amount, raise the
background factor to taste, pick the hue band.

### 5. The M82 case — synthetic Hα boost via PixelMath

M82's red is **Hα emission** from the starburst superwind. On an OSC
sensor it lands almost entirely in the red channel, showing up as
regions where red meaningfully exceeds green. Global saturation won't
isolate it; a hue-banded pass helps; the strongest tool is a synthetic
emission layer in PixelMath (Image Processing → PixelMath):

```
new_red = R + k * max(0, R - G)
```

Start `k` around `0.3` and increase. This selectively amplifies
red-dominant pixels (the Hα filaments) while leaving neutral continuum
alone — the OSC equivalent of extracting an Hα signal.

> **Note:** you have ~21 h on the M81/M82 field, so the Hα is in the
> data — this is a recovery-in-processing problem, not acquisition.

### 6. The M82 acquisition exception

The standard rule is "galaxies = LP filter OFF (IRCUT)." M82 is the
principled exception. Its outflow is genuine Hα *emission*, and the
Seestar's dual-narrowband LP filter **passes Hα**. A dedicated pass on
M82 with the **LP filter ON** suppresses the broadband continuum and
skyglow while passing the Hα — yielding a high-contrast red-emission
layer to blend in as the red, and it works under moonlight. Worth one
experimental session.

### 7. Local contrast on the emission

Once the red is there, a **CLAHE** pass (galaxies-only) on the luminance
increases local contrast in the filaments so the red reads as structure
rather than a wash.

### Where Siril hits a ceiling

Siril's hue-selective saturation is good but coarse. If galaxy color
becomes a priority: PixInsight's **ColorSaturation** (fully editable
saturation-vs-hue curve) and **CurvesTransformation** saturation curve
are materially more capable; free **GIMP** gives Hue/Saturation with
per-hue control plus luminosity masks. But asinh + starless +
hue-banded `satu` + the PixelMath Hα trick gets ~80% of the way with
tools you already own.

---

## Star color via luminance-weighted masks

### The goal

Apply saturation **proportional to star brightness** — bright stars get
rich color, faint stars fall toward white. Real star fields look this
way; uniform star color across all magnitudes is the #1 tell of
artificial processing.

### Stretch the stars FIRST (workflow change)

**Saturation is only meaningful on stretched data.** On a linear star
layer almost all signal is compressed near zero, so saturation has
nothing to act on, and the magnitude-weighting below can't work because
the bright/faint differences only exist after stretching.

If your combine step (e.g. VeraLux StarComposer) stretches the star
layer *at combine time*, the stars never pass through a state where you
can color them. Change the order:

1. Process the **starless** layer to completion (stretch, color, decon,
   optional star-size-independent work).
2. **Separately** stretch the **star** layer, then saturate it (below),
   optionally reduce star size.
3. Recombine with a **purely additive screen blend that does not
   re-stretch**:
   - StarComposer with its own stretch disabled, *or*
   - PixelMath screen blend: `1 - (1 - starless) * (1 - stars)`

> **Matching caveat:** when you take over the star stretch, match the
> star layer's black point and brightness to the starless layer by eye,
> or stars will sit too heavy / too faint relative to the galaxy. That
> matching is the service an auto-stretch combine was doing for you.

### The mask: the star layer is its own luminance mask

A luminance-weighted mask is any selection whose strength tracks
brightness. Your **star-only layer already is one** — bright stars are
bright pixels, faint stars are dark. You don't build a mask from
scratch; you let the star image govern its own saturation.

#### Easiest path — native Siril `background_factor`

Work on the stretched star-only layer and use the **background factor**
in the Saturation tool / `satu`:

```
satu 0.4 2.0
```

The background factor sets a brightness threshold below which saturation
isn't applied. Raise it and only brighter stars get saturated; the faint
field stays white. Push the **amount** higher than you'd dare globally,
because the background factor is protecting the faint stars. It's a
poor-man's luminance weighting with zero mask-building.

#### Finer control — an actual luminance mask (PixInsight / GIMP)

1. Take the stretched star-only image. Make a grayscale luminance copy —
   that copy *is* the mask (bright = full effect, faint = little).
2. Optionally curve the mask to shape falloff (lift midtones to let
   medium stars keep some color; steepen to restrict color to the
   brightest few).
3. Apply the mask and run saturation / ColorSaturation through it.

GIMP: duplicate star layer → desaturate copy → use as layer mask on a
Hue/Saturation adjustment. PixInsight: star image as mask → ColorSaturation.

### Two refinements

- **Clipped cores.** The brightest stars often have white, clipped cores
  with color only in the halo. A pure luminance mask dumps max
  saturation onto a core with no color to amplify. If you see faint
  colored rings or no effect, use a **range mask** that excludes the top
  few percent (clipped cores) *and* the faint floor, landing saturation
  on the mid-bright halos where the color lives.
- **Watch SCNR.** Over-aggressive green-noise removal strips star color
  (and galaxy HII color), leaving everything neutral/magenta. If stars
  are weak on color before you even saturate, suspect an upstream SCNR
  pass.

---

## Combined recipe (order of operations)

```
SHARED
  1. RBF background extraction (neutralize sky)
  2. SPCC color calibration (Seestar S50 sensor)
  3. Star separation (StarNet++ / StarXTerminator)

STARLESS (galaxy) LAYER
  4. Asinh / VeraLux HMS stretch (color-preserving)
  5. Deconvolution / CLAHE on luminance (detail)
  6. Hue-banded satu: red/magenta pass + blue pass
  7. (M82 etc.) PixelMath synthetic Hα: R + k*max(0, R-G)

STAR LAYER
  8. Stretch the star layer (you control it, match black point)
  9. satu with high background_factor (magnitude-weighted),
     or luminance/range mask elsewhere; exclude clipped cores
 10. Optional light star-size reduction

RECOMBINE
 11. Screen blend, NO re-stretch:
     1 - (1 - starless) * (1 - stars)
```

Do the shared steps and the galaxy color (4–7) first and reassess — they
carry most of the visual payoff. Star color (8–10) is the polish that
separates good from great.

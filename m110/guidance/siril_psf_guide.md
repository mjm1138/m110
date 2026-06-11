# PSF size for deconvolution — what it is and how to pick a value

A practical guide to the "PSF size" parameter that every deconvolution
tool asks for. Covers what it represents, how to measure it on your own
Seestar data, and targeted advice for the three deconvolution paths in
this workflow: Siril's built-in Richardson-Lucy, GraXpert, and the
VeraLux script suite.

---

## What PSF actually represents

PSF stands for **Point Spread Function** — the shape that a true
mathematical point of light (a star) gets smeared into by the time it
lands on your sensor. A perfect optical system imaging a perfect point
source would record a single pixel lit up. In reality every star image
is a small blob, because the light got blurred by:

1. **Atmospheric seeing** — turbulence in the air column. Dominant for
   ground-based scopes. In Boulder this contributes 2–3 arcsec FWHM on a
   typical night.
2. **Optical aberrations** — focus, diffraction at the aperture, optical
   element flaws. Small but nonzero for the Seestar's f/5 doublet.
3. **Tracking error** — sub-pixel drift during the exposure smears the
   point into a tiny streak. EQ mode with decent polar alignment keeps
   this minimal at ≤30s subs.
4. **Pixel sampling** — the sensor integrates light over the area of
   each pixel, which is its own form of blur.

Stacked, these produce the characteristic round (or nearly round) blob
shape every star has. **That blob shape is the PSF.** Deconvolution's
job is to reverse the blurring: if the original was a point and the
result was this blob, what mathematical operation produced the blob? Now
apply the inverse to everything in the image.

---

## Why deconvolution needs a PSF size

The deconvolution algorithm needs to know *how big* the blur was so it
knows how aggressively to sharpen.

- **Tell it the PSF is too small** → underwhelming results; you barely
  sharpened anything.
- **Tell it the PSF is right** → genuine recovery of detail that was
  smeared by the blur.
- **Tell it the PSF is too big** → over-sharpening artifacts: dark rings
  around stars ("haloing"), ringing along bright edges, amplified noise,
  and a "crunchy" texture in nebulosity.

---

## How PSF size is measured

PSF size is usually expressed in **pixels of FWHM** (Full Width at Half
Maximum). Picture the brightness profile of a star — a bell curve. FWHM
is the width of that bell curve at half its peak height. For a typical
Seestar star on a decent night, that's roughly 2–4 pixels.

Some tools express it as a **sigma** (Gaussian standard deviation) or
**radius** instead. Conversions:

- `FWHM ≈ 2.355 × sigma`
- `FWHM ≈ 2 × radius` (when "radius" means half-width at half-max)

If a tool's slider just says "PSF size" without units, it's almost
always FWHM in pixels. If you're unsure, the tooltip usually clarifies —
or you can experimentally bracket a known-measured value and see which
unit matches.

---

## How to measure your own PSF

The most reliable approach when a tool doesn't auto-compute. Several
paths:

### Method 1: Siril's Dynamic PSF tool (easiest)

1. Load your stacked image in Siril.
2. **Tools → Image Analysis → Dynamic PSF** (or shortcut Ctrl+F6 / Cmd+F6).
3. Click on several stars across the frame (avoid saturated ones — the
   brightness profile clips and skews the fit).
4. Read the **FWHMx** and **FWHMy** values reported for each.
5. Average the FWHM values, or take a typical mid-frame star — corners
   are often slightly worse from optical aberration.

For the Seestar at native resolution this typically gives **FWHM ≈
2.5–4 pixels** depending on seeing.

### Method 2: Read the FITS header

Siril's quality filters during stacking compute per-frame FWHM. After
stacking, the average often sits in the header (look for `FWHM` or
similar), or in the Siril console output ("Mean FWHM: 3.2 pixels"). Same
value, no clicking required.

### Method 3: Multiply seeing by plate scale

A rough sanity-check estimate:

```
FWHM (pixels) ≈ seeing (arcsec) / plate_scale (arcsec/pixel)
```

For Seestar at 1.6"/pixel and Boulder seeing 2–3":

```
FWHM ≈ 2.5 / 1.6 ≈ 1.6 pixels   (good night)
FWHM ≈ 3.0 / 1.6 ≈ 1.9 pixels   (typical night)
```

These numbers will read *lower* than what Siril measures because focus,
tracking, optical aberrations, and pixel sampling all add quadratically
on top of seeing. **Measured FWHM is always ≥ seeing-based estimate.**
Use this as a floor.

### Method 4: After drizzle, scale up

If you drizzled at 1.5× or 2×, your output is on a finer grid, so the
PSF is **larger in pixels** even though it represents the same
arcseconds:

```
post-drizzle FWHM (pixels) ≈ native FWHM (pixels) × drizzle_scale
```

A 3-pixel native PSF becomes a **4.5-pixel** PSF after 1.5× drizzle, or
a **6-pixel** PSF after 2× drizzle. Pick your slider value to match the
*image you're actually deconvolving*, not the native sensor scale.

---

## Practical starting values for the Seestar

| Situation | PSF size (FWHM, pixels) |
|---|---|
| Native 1.0× stack, good seeing | **2.5** |
| Native 1.0× stack, typical seeing | **3.0–3.5** |
| Native 1.0× stack, poor seeing | **4.0–5.0** |
| 1.5× drizzled stack, typical seeing | **4.5–5.0** |
| 2.0× drizzled stack, typical seeing | **6.0–7.0** |

These are starting points. **Always measure with Dynamic PSF before
committing** on a target you care about — a single Siril click takes 10
seconds and removes all the guesswork.

---

## Tool-specific guidance

### Siril built-in: Richardson-Lucy deconvolution

**Menu path:** Image Processing → Filters → Deconvolution → Richardson-Lucy
(per CLAUDE.md, R-L is preferred over Wiener in 1.4.2; Wiener over-sharpens
at defaults).

Siril's dialog has three main controls relevant to PSF:

- **PSF type**: Gaussian, Moffat, or "from stars". Use **Gaussian** for
  Seestar data — the Moffat profile fits refractor diffraction patterns
  better but isn't a meaningful improvement here. The "from stars"
  option auto-fits a PSF from detected stars in the image; this is the
  best choice when you can use it because it removes the guessing.
- **PSF FWHM** (when Gaussian or Moffat is selected): the slider this
  guide is about. Units are **pixels of FWHM**.
- **Iterations**: how many passes Richardson-Lucy makes. 10–20 is a
  typical sweet spot. More iterations = sharper but more prone to
  ringing and noise amplification. Start at 10.

**Recommended workflow:**

1. Try **PSF type = "from stars"** first. If it produces a clean result,
   you're done — no manual PSF size needed.
2. If "from stars" fails (low star count, saturated cores, scattered
   results) or you want explicit control, switch to **Gaussian** and use
   the measured FWHM from Dynamic PSF.
3. Start at **10 iterations**, moderate regularization. Apply.
4. Inspect bright stars at 100% zoom. Adjust PSF FWHM by 0.5 pixel
   increments if you see under- or over-sharpening artifacts.

Siril treats the value as **literal FWHM in pixels** — no conversion
needed from a Dynamic PSF measurement.

### GraXpert

GraXpert (primarily known for background extraction and AI denoise)
added a deconvolution module in late 2024, with separate **Stars** and
**Object** flavors targeting star tightening and nebula/galaxy detail
respectively. Both expose two key sliders:

- **PSF size** — the value this guide is about. Units are **pixels of
  FWHM**, same convention as Siril.
- **Strength** — how aggressively to apply the deconvolution. Start
  around 0.3–0.5 and adjust.

GraXpert does *not* auto-detect the PSF for you. You set the size
explicitly, so the measurement workflow above carries over directly:

1. Open your stack in Siril, run **Image → PSF → Dynamic PSF**, click
   5–10 mid-frame stars, average the FWHM values.
2. Enter that value as GraXpert's **PSF size**.
3. Apply at low strength (~0.3), inspect, increase if subtle.

Same Seestar starting values apply: ~3.0–3.5 pixels for a native stack
under typical Boulder seeing, scaled up by the drizzle factor for
drizzled stacks (see the table above). Same failure modes too — dark
rings around stars mean PSF too large; no visible change means too
small.

If you don't want to switch back to Siril to measure, GraXpert's
preview is good enough to bracket the value by eye: start at the table
estimate and move ±0.5 pixels until star cores tighten cleanly without
ringing.

### VeraLux scripts

The VeraLux script family for Siril (HyperMetric Stretch, Revela,
Curves — see CLAUDE.md's Siril Processing section) is focused on
stretching, sharpening, and tonal work — **not deconvolution per se**.
At the time of writing there is no VeraLux *deconvolution* script that
parallels HMS or Revela.

The relevant VeraLux script for sharpening-style work is **Revela**,
which is a post-stretch sharpening script (unsharp-mask family rather
than true deconvolution). Revela's parameters aren't a literal PSF
size — they're sharpening kernel parameters. Pick them empirically by
preview rather than from a Dynamic PSF measurement.

If a VeraLux deconvolution script appears in a future release, it would
most likely accept the same FWHM-in-pixels convention as Siril's
built-in tool (since both run in the same Siril context). The
measurement workflow above would carry over directly. Until then, do
true deconvolution in Siril's R-L (or GraXpert's AI flavor) and use
Revela only for the *post-stretch sharpening* step that follows.

---

## Tuning when you can't measure

If you're stuck with a slider and no measurement readout (rare with the
above tools, but possible in generic image editors):

1. **Start at the table value** for your stack's drizzle scale.
2. **Apply with low strength** (e.g., 5–10 iterations).
3. **Look at bright stars** at 100% zoom. The failure modes are visually
   distinct:
   - **PSF too small**: image looks almost unchanged. Stars still soft.
   - **PSF too large**: dark rings appear around bright stars; nebula
     edges show ringing; backgrounds get crunchy noise.
4. Adjust by ~0.5 pixel increments and re-apply.

---

## Other parameters that interact with PSF size

- **Iterations / strength**: how aggressively to apply the inverse. More
  iterations = sharper but more artifacts. R-L at 10–20 iterations is
  the typical Seestar sweet spot.
- **Regularization / noise model**: how the algorithm decides what's
  signal vs. noise. Higher regularization = gentler, less prone to
  amplifying noise but less sharp.
- **PSF shape (Gaussian vs. Moffat)**: Gaussian fits Seestar stars well.
  Moffat is better for some refractors with prominent diffraction
  patterns; not worth pursuing for the Seestar.

The PSF *size* matters more than these other knobs in practice. Get
size right first, then tune strength.

---

## Bottom line

**Best path (when available): auto-PSF from stars.** Siril R-L's "from
stars" mode estimates PSF internally. Use this whenever your frame has
enough unsaturated stars.

**Fallback: measure with Dynamic PSF.** Three clicks in Siril gives you
a real number. Use that value (FWHM in pixels) as the PSF size in any
tool that asks — including GraXpert, which requires you to set it
explicitly.

**Last resort: estimate from the table.** Native unstacked stack +
typical Boulder seeing → start at 3.0 pixels. Multiply by drizzle scale
if applicable.

**Don't deconvolve in tools that need a PSF size if you have no way to
measure or estimate.** A bad PSF guess hurts the image more than not
deconvolving at all.

---

## Quick reference card

```
Default approach by tool:

  Siril R-L         →  PSF type = "from stars" (auto)
                       Fallback: Gaussian + measured FWHM
  GraXpert AI       →  Manual PSF size (FWHM px) + strength
  VeraLux Revela    →  Not deconvolution; tune sharpness empirically

Measured FWHM by Seestar stack type (Boulder typical seeing):

  Native 1.0× stack       →  3.0–3.5 px
  1.5× drizzled stack     →  4.5–5.0 px
  2.0× drizzled stack     →  6.0–7.0 px

Failure modes when manually tuning:

  Image barely changes   →  PSF size too small, bump up 0.5 px
  Dark rings on stars    →  PSF size too large, drop 0.5 px
  Crunchy noise          →  Reduce iterations or increase regularization
```

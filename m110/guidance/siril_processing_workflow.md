# Siril 1.4.2 Processing Workflow — ZWO Seestar S50
**Observer:** Mike | **Boulder, CO** | **Sensor:** Sony IMX462 (OSC/Bayer)

---

## Overview

Two-phase workflow: the Naztronomy script handles all preprocessing (calibration, registration, stacking) and produces a linear stack. Everything after that is done manually in Siril's GUI. The order of post-processing steps matters — follow the sequence below.

---

## Phase 1 — Preprocessing with Naztronomy-Smart_Telescope_PP.py

The script is available via **Scripts → Get Scripts** in Siril, or directly from [GitHub](https://github.com/naztronaut/siril-scripts). Run it via **Scripts → Run Script** after setting your working directory to the object folder (e.g. `Images/FITS/M94/`).

### Script Settings for S50

**Telescope:** Select `ZWO Seestar S50`. The script reads the `TELESCOP` FITS header from your light frames and may auto-detect it — verify before running.

**Drizzle:** Use `1.5x`, Pixel Fraction `1.00`. The S50 is slightly undersampled at f/5 (250mm FL, 2.9µm pixels → ~2.4"/px), so drizzle recovers detail and improves sampling. Avoid 2x — it roughly quadruples processing time and memory for diminishing returns at this focal length.

**Feathering:** Leave **off**. The script enables it automatically if batching kicks in.

**Stack Weighting:** Off is fine for typical use. Consider enabling for future multi-session deep stacks where conditions varied noticeably between nights — it down-weights frames from poorer sessions.

**Batch size:** Leave at default (Mac/Linux max is 25,000 — you won't hit it).

**Filters:** Turn on **Roundness** at `75%` and **FWHM** at `80%`. These percentages are the keep-best-N% thresholds — frames with the worst star roundness (bottom 25% rejected) and the worst FWHM (bottom 20% rejected) are dropped before stacking. Empirically these settings produce noticeably better stacks than running unfiltered: tighter stars, lower noise floor, and better deep-sky detail in the final result. The S50 occasionally drops a frame mid-capture (wind, mount glitch, satellite trail) and the filters cleanly catch those without the manual frame-by-frame inspection an unfiltered run would otherwise require. The intersection of the two filters discards frames with bad shape *or* bad sharpness — for most S50 sessions this rejects 30–40% of subs, leaving the cleanest 60–70% to stack.

**All other options:** Leave at defaults (no post-stacking options).

**Stacking rejection:** The script uses Winsorized Sigma Clipping by default, which is appropriate for the frame counts you're working with (100–1400 frames). No need to change this.

**Output:** The script produces a calibrated, debayered, registered, and stacked linear `.fit` file in the working directory. This is your starting point for Phase 2.

### Notes on Calibration Frames
The S50 performs automatic dark optimization during capture. With **Save Subframes ON**, the raw subframes already have sensor-level dark calibration baked in by the scope's firmware. The `darks/`, `biases/`, and `flats/` folders exist for your own collected frames — if you have them, the script will use them; if not, it proceeds without and results are still good given the S50's internal calibration.

---

## Phase 2 — Post-Processing in Siril GUI

Open the stacked `.fit` output from Phase 1. Work through these steps in order. **Everything through Stretching must be done while the image is still linear** (before any stretch is applied), except where noted.

### 1. Inspect and Crop (pre-stretch, linear)
Zoom to the edges of the stacked frame. Siril's stacking leaves uneven border coverage — crop away any vignetting or registration dropout around the edges before doing anything else. Use **Image Processing → Crop**.

### 2. Green Channel Equalization (pre-stretch, linear)
**Image Processing → Remove Green Noise**

OSC/Bayer sensors often carry a slightly dominant green channel from the Bayer matrix. Select protection method `Average Neutral` — note that with this method the amount is fixed at 1.0 and not adjustable, which is fine. This is subtle but prevents a green cast from compounding through the rest of the pipeline.

### 3. Background Extraction (pre-stretch, linear)
**Image Processing → Background Extraction**

In Siril 1.4.2 the options are **RBF** (Radial Basis Function) or **Polynomial**. Use **RBF** — it handles complex, non-uniform gradients better than polynomial and is generally the superior choice. Place 15–25 sample points on empty sky, avoiding stars, nebulosity, and galaxy halos. Subtract (not divide) the background model.

For Bortle 5–6 skies with EQ mode (minimal field rotation), gradients are usually modest and RBF handles them cleanly in one pass.

### 4. Color Calibration — SPCC (pre-stretch, linear)
**Image Processing → Color Calibration → Spectrophotometric Color Calibration**

SPCC uses star spectra from the Gaia catalog rather than assumptions about average sky color — it's the right tool for OSC data.

**Sensor:** `ZWO Seestar S50` is directly selectable as the sensor type.

**Filter settings by target type:**

| Target | Filter setting in SPCC |
|--------|------------------------|
| Galaxies (IRCUT) | `Broadband (no filter)` or `IRCUT` |
| Emission/planetary nebulae (LP) | Select the S50's dual narrowband LP filter — choose `ZWO Duo-Narrowband` or the closest narrowband option available. The LP filter heavily biases color; getting this right is critical for nebula hues. |

SPCC will query the Gaia catalog — ensure Siril has internet access or the catalog downloaded locally. After SPCC, stars should appear white-ish and the background neutral.

### 5. Deconvolution (pre-stretch, linear) — optional but worthwhile
**Image Processing → Filters → Deconvolution**

Deconvolution must happen on the linear image, before stretching. Use **Richardson-Lucy** — Wiener tends to over-sharpen and produce ringing at the default settings in 1.4.2 without iteration control. With R-L, start with a low iteration count and increase gradually while watching the stars; stop as soon as you see any ringing or noise amplification begin.

Skip this step for short integrations or single sessions where SNR is low. It pays off most on deep stacks (M81/M82, M94) where there's enough signal to support it.

### 6. Stretch — VeraLux HyperMetric Stretch (HMS)
**Scripts → VeraLux HyperMetric Stretch**

VeraLux HMS is the preferred stretching tool for S50 OSC data. Standard stretches (including GHS) can cause hue shifts in the color channels during aggressive stretching — VeraLux is specifically designed to preserve the photometric/color relationships between channels throughout the stretch. The interface is also considerably simpler than GHS.

For VeraLux HMS these seem to be good defaults:
* Ready-to-Use Processing Mode
* Sensor Calibration set to ZWO Seestar S50
* Target Bg set to 0.12-0.14 with Adaptive Anchor selected
* Use “Auto-Calc Log D” and adjust slider to taste
* Color Strategy at default

**GHS** (Image Processing → Histogram Transformation → Generalized Hyperbolic Stretch) remains a valid alternative if you want more granular manual control, but requires more care to avoid color shifts on OSC data. Start with D ~1–2, B ~1, and apply in two gentle passes rather than one aggressive one.

For emission nebulae (LP filter data), a more aggressive stretch is generally safe since the signal is narrowband — there's less risk of blowing out a broadband continuum.

After stretching the image is no longer linear. All remaining steps work on the stretched (non-linear) image.

### 7. Star Separation — Starnet++ (post-stretch, non-linear) — nebulae and galaxies

**Requires:** Starnet++ v2 binary installed separately ([starnetastro.com](https://www.starnetastro.com/) — macOS build). Set the executable path in **Siril → Preferences → Miscellaneous → Starnet path** before first use.

**When to use:**

| Target type | Use? |
|---|---|
| Emission / planetary nebulae (LP filter) | Yes — high value |
| Galaxies (IRCUT) | Yes — moderate value |
| Globular clusters | No — the object *is* stars |
| Open clusters | No |

**Workflow — this step branches the pipeline:**

1. **Save** the stretched image as `<object>_stretched.fit` before doing anything else. This is both a safety copy and the source for the stars layer.
2. **Run Starnet:** `Image Processing → Stars → Starnet`. Siril replaces the current image with the starless result.
3. **Save** as `<object>_starless.fit`.
4. **Compute the stars layer:** reopen `<object>_stretched.fit`, then `Image Processing → Image Arithmetic` → Subtract → select `<object>_starless.fit`. Save the result as `<object>_stars.fit`. This is the layer you'll add back at the end.
5. **Reopen** `<object>_starless.fit` and continue with all remaining steps (GraXpert through Color Adjust) on the starless image.
6. After all processing is done, **recombine:** `Image Processing → Image Arithmetic` → Add → select `<object>_stars.fit`. The original unprocessed stars are added back onto the finished nebula/galaxy.

**Why GraXpert goes after this step:** Stars and their halos interfere with AI noise reduction — the model can misidentify halo edges as signal and introduce ringing. A starless image has more uniform noise that GraXpert handles cleanly, and you can push the strength further without side effects. The same logic applies to Revela sharpening and CLAHE.

**Caveat for galaxies:** Starnet can occasionally remove galaxy flux in a dense, diffuse nucleus (M81, M94) that it mistakes for stars. Check the core in the starless output before committing to the recombination. If the nucleus looks eaten, skip recombination for that object and process stars-in.

### 8. Noise Reduction (post-stretch, non-linear)
**Scripts → GraXpert** (via Siril's GraXpert integration)

Use **GraXpert** for noise reduction — the built-in Siril denoiser is too aggressive for S50 OSC data and kills fine detail. GraXpert handles the non-Gaussian noise character that results from Bayer demosaicing more gracefully.

For **deep stacks** (M81/M82, M94 — 3+ hours): medium strength is appropriate.
For **initial captures** (single sessions, <1 hour): light touch only — heavy denoising on low-SNR data smears detail. More frames is a better solution than more denoising.

Apply **cosmetic correction** (hot/cold pixel removal) before denoising if you haven't already — salt-and-pepper noise confuses the denoiser.

### 9. Sharpening / Detail Enhancement (post-stretch, non-linear)
Siril 1.4.2 does not have a dedicated Sharpening submenu. The recommended approach for post-stretch detail enhancement is **VeraLux Revela** (available in the VeraLux script suite), which is designed specifically for bringing out fine structure in stretched data without over-sharpening stars.

For galaxies: Revela works well for spiral arm detail and dust lane definition. For nebulae at S50's focal length (250mm), sharpening is usually counterproductive — the structures are diffuse enough that sharpening adds noise more than detail.

If you need access to unsharp mask directly, it is available via the Siril command line: `unsharp sigma amount` (e.g. `unsharp 1.0 0.7`).

### 10. CLAHE — Local Contrast (post-stretch, non-linear) — galaxies only
**Image Processing → Filters → Contrast Limited Adaptive Histogram Equalization**

CLAHE is effective for bringing out internal galaxy structure — dust lanes, bars, faint outer arms. Use a small clip limit (1–2) and tile size 8–16. Apply it conservatively; it's easy to overshoot and make the result look processed. Not useful for nebulae or clusters.

### 11. Curves — VeraLux Curves (post-stretch, non-linear)
**Scripts → VeraLux Curves**

VeraLux Curves is a tonal mapping refinement tool — use it after stretching and CLAHE as a final contrast adjustment. A gentle S-curve (slightly compress highlights, lift midtones) works well for galaxies. This is the right place for it in the workflow — it's not a stretch tool and should not be used before step 6.

### 12. Final Color Adjustments (post-stretch, non-linear)
**Image Processing → Color Saturation** and **Hue/Saturation/Lightness**

Boost saturation slightly for galaxies — the IMX462 produces somewhat muted colors compared to cooled dedicated astro cameras, so a moderate lift helps bring out star colors and galaxy hues. For LP-filter nebula data, the narrowband signal renders pinkish/red (Hα) and blue-green (OIII); hue can be shifted to taste since SPCC handled the overall color balance.

---

## Save Strategy

Keep intermediate saves at key stages:
- `<object>_stack_linear.fit` — the raw Phase 1 output (always keep this)
- `<object>_postSPCC_linear.fit` — after background extraction + SPCC, before stretch (useful if you want to reprocess the non-linear steps)
- `<object>_stretched.fit` — immediately after HMS stretch, before Starnet (required if doing star separation; also the source for computing the stars layer)
- `<object>_starless.fit` — Starnet output; the image you process through steps 8–12
- `<object>_stars.fit` — stars-only layer (`_stretched` minus `_starless`); kept for recombination
- `<object>_final.fit` and `<object>_final.tif` — the finished result after recombination (TIFF for sharing/printing)

For targets where you skip star separation (globulars, open clusters), the `_stretched`, `_starless`, and `_stars` saves are unnecessary — go straight from stretch to GraXpert and save only `_final`.

Use the naming convention already established in your FITS folders.

---

## Quick Reference — Step Order

**Nebulae and galaxies (with star separation):**
```
[LINEAR]     Crop → Green Noise → RBF Background → SPCC → Deconvolution (R-L) → VeraLux HMS Stretch
             ↓ save _stretched.fit
[NON-LINEAR] Starnet (→ save _starless.fit, compute _stars.fit)
             ↓ work on starless image
             GraXpert Denoise → VeraLux Revela → CLAHE (galaxies) → VeraLux Curves → Color Adjust
             ↓ Image Arithmetic: add _stars.fit
             Save _final.fit / .tif
```

**Globulars and open clusters (no star separation):**
```
[LINEAR]     Crop → Green Noise → RBF Background → SPCC → Deconvolution (R-L) → VeraLux HMS Stretch
[NON-LINEAR] GraXpert Denoise → VeraLux Revela → VeraLux Curves → Color Adjust → Save _final.fit / .tif
```

---

## Siril 1.4.x Known Issues (already encountered)
- `preprocess` command removed → use `calibrate light -debayer`
- `mapfile` not available on macOS bash 3.2 → use `while IFS= read -r` loop
- "Solve whole sequence" in plate solver only appears when a sequence is loaded, not a single image
- No dedicated Sharpening submenu — use VeraLux Revela (scripts) or command line `unsharp sigma amount`
- Wiener deconvolution over-sharpens at defaults — use Richardson-Lucy instead

---

## What's working for me in Siril right now:

Some written up notes for the workflow that’s giving me some good results right now.

1. Stack using the Naztronomy Smart Telescope script. The author has great Youtube videos explaining the config options. I get a lot of benefit from using the filters, weighted stacking and background extraction, and maybe some benefit from drizzling. Feathering is essential for mosaic images
2. Crop. Take out all the bad noise around the edges or it will mess up the rest of the workflow - save a version here
3. Plate solve and spectrophotometric color calibration
4. GraXpert deconvolution (stellar every time, object depending on the target)
5. Optional: Star separation. I'm just starting to experiment here and don't have much to say. I have a lot to learn.
6. Veralux Hypermetric Stretch: Auto-Calc Log D, Target Bg 0.10-0.12 (maybe more or less depending on the image) - save a version here
7. GraXpert denoise: I find you can crank up the intensity pretty high without losing any object detail (scientists would probably disagree with me here)
8. Veralux curves: I might iterate on curves a few times or return to it after subsequent steps, it's really just continuing the stretch process with a bit of a blunter instrument. The goal here for me is pure aesthetics
9. Veralux revela
10. unsharp 1.0 0.8 (I can't find an unsharp mask menu option so I do this on the command line)
11. Veralux star composer if I did step 5
12. maybe adjust color saturation (I usually tone it down a bit) - save a version here
13. save as a .png or .tif depending on what I'm going to do with it
14. From there I might take it in to Photomator for some final tweaks if needed, but mostly I'm pretty happy with the output from Siril.

---

## Sources & References

### Naztronomy Preprocessing Script
- [Naztronomy-Smart_Telescope_PP.py — GitHub](https://github.com/naztronaut/siril-scripts/blob/main/Naztronomy-Smart_Telescope_PP.py)
- [Siril Python Script For Smart Telescope Preprocessing — Naztronomy](https://www.naztronomy.com/post/siril-python-script-for-smart-telescope-preprocessing)
- [Smart Telescope Script Update — Officially In Siril! — Naztronomy](https://www.naztronomy.com/post/smart-telescope-script-update-officially-in-siril)
- [Siril Smart Telescope PreProcessing Script — Cloudy Nights](https://www.cloudynights.com/forums/topic/965935-siril-smart-telescope-preprocessing-script-python/)

### VeraLux Scripts
- [VeraLux HyperMetric Stretch: What Is Behind the New Stretching Method? — martinkaessler.com](https://www.martinkaessler.com/veralux-hms-revolutionary-stretching-method/)
- [VeraLux HyperMetric Stretch — Open Discussion — AstroBin](https://app.astrobin.com/forum/topic/206981/veralux-hypermetric-stretch-an-open-discussion)
- [New Stretching Script in Siril: Veralux — Cloudy Nights](https://www.cloudynights.com/forums/topic/987003-new-stretching-script-in-siril-veralux/)
- [VeraLux Scripts — GitLab (Siril official)](https://gitlab.com/free-astro/siril-scripts/-/tree/main/VeraLux)

### Siril Documentation
- [Siril 1.4.2 Documentation — Overview](https://siril.readthedocs.io/en/stable/Workflow.html)
- [Siril 1.4.2 — Noise Reduction](https://siril.readthedocs.io/en/stable/processing/denoising.html)
- [Siril 1.4.2 — Filters](https://siril.readthedocs.io/en/stable/processing/filters.html)
- [Siril 1.4.2 — SPCC](https://siril.readthedocs.io/en/stable/processing/color-calibration/spcc.html)
- [Siril 1.4.2 — Commands Reference](https://siril.readthedocs.io/en/stable/Commands.html)

### General Workflow References
- [Siril Workflow with GraXpert and VeraLux Scripts — UnderSouthWestSkies](https://undersouthwestskies.blogspot.com/2025/12/beginner-tutorial-workflow-for-using.html)
- [Siril Full Image Processing Tutorial — siril.org](https://siril.org/tutorials/tuto-scripts/)

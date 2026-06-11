# S50 Lunar & Solar Video Stacking Workflow — Siril 1.4.2
**Observer:** Mike | **Boulder, CO** | **Sensor:** Sony IMX462 (OSC/Bayer)

---

## Overview

The Seestar S50 saves raw video as `.avi` only — SER is not available as an output format. The raw AVI is RAW8 (8-bit Bayer), which must be debayered before stacking. This workflow converts, debayers, registers, stacks, and sharpens in Siril 1.4.2.

The Seestar also produces in-app video stacks (`Video_Stacked_*.fit`) automatically. Those are convenient but use no frame selection. External stacking picks only the sharpest frames (lucky imaging), producing noticeably cleaner results on nights with variable seeing.

---

## Bayer Pattern Note

The `.avi.txt` sidecar file reports `Bayer = GR` (suggesting GRBG), but in practice **BGGR** is the pattern that produces a correct debayered image in Siril. Use BGGR.

Set this once in **Siril Preferences → File formats → FITS/SER debayer → Bayer pattern: BGGR**, and also uncheck **"Bayer information from file's header if available"** so Preferences always takes precedence over any header metadata.

---

## Step-by-Step Workflow

### 1. Transfer Files

Run `scripts/scan_staging.py --move` to move files from "From the scope" staging into `Images/Lunar_video/` (or `Solar_video/` etc.). The RAW `.avi` files and `.avi.txt` sidecars will be moved together.

### 2. Convert AVI to FITS Sequence

In Siril, set your working directory to a temp folder for this object/session.

**File → Conversion**

- Add your `.avi` file
- Output format: **FITS sequence**
- **Leave debayer OFF** at this stage — debayer in the next step for better control
- Click Convert

This produces a numbered FITS sequence (e.g. `lunar_00001.fit`, `lunar_00002.fit`, …).

### 3. Debayer the Sequence

With the FITS sequence loaded:

**Calibration tab → Output sequence section → check "Debayer before saving" → Go**

- Pattern: **BGGR** (set in Preferences as above)
- No calibration frames needed (no darks/flats for video)
- Output sequence gets a `pp_` prefix (e.g. `pp_lunar_`)

Alternatively via command line:
```
calibrate lunar -debayer -prefix=pp_
```

### 4. Register

**Registration tab**

- Sequence: select your `pp_lunar_` sequence
- Method: **KOMBAT** — specifically designed for planetary/lunar translation alignment. Fast, no star detection needed.
- Click Go

### 5. Review and Select Frames

**Sequences tab → Open Frame List** (or Frame Selector)

Scan through the registered frames and manually exclude obviously bad ones — motion blur, cloud, atmospheric distortion spikes. For the Moon at 50mm you can usually afford to keep 50–70% of frames; aggressive selection (10–20%) is more appropriate for larger apertures where seeing is the limiting factor.

If you prefer automated selection, use **Weighted FWHM** as the quality criterion in the Stacking tab — it's more reliable than the generic "Quality" metric in 1.4.2.

### 6. Stack

**Stacking tab**

- Method: **Sum** — recommended for 8-bit source data; retains dynamic range rather than averaging it away
- Normalization: **None** (Sum stacking doesn't use normalization)
- Frame selection: manual (from step 5), or Weighted FWHM with a percentage cutoff
- Click Go

Output: a single stacked FITS file.

---

## Post-Stack Sharpening — À Trous Wavelets

**Image Processing → Filters → À Trous Wavelets Transform**

Wavelets decompose the image into frequency layers. Layer 1 holds the finest detail; higher layers hold progressively coarser structure and noise. Boosting a layer (value > 1.0) enhances that scale of detail; reducing it (< 1.0) suppresses it.

**Settings:**
- Algorithm: **BSpline** (type 2) — higher quality than Linear
- Layers: 4–6

**Starting values for lunar:**

| Layer | Controls | Starting value |
|-------|----------|---------------|
| 1 | Finest surface detail (craters, rilles) | 50–75 |
| 2 | Medium detail (crater walls, terminator) | 5–15 |
| 3 | Coarse structure | 1.0 (default) |
| 4+ | Noise / large-scale gradient | 0.5–1.0 (suppress or leave) |

Use the real-time preview. Stop before ringing or a "wormy" texture appears around high-contrast edges — that's the signal that sharpening has gone too far for your SNR.

**Command-line equivalent** (useful for scripting or repeating a known-good set of values):
```
wavelet 6 2
wrecons 65 10 1 1 1 1
```

Adjust the first two coefficients to taste; the rest can stay at 1.

**Reference:** [Siril À Trous Wavelets documentation](https://siril.readthedocs.io/en/stable/processing/atrouwavelets.html) | [Planetary processing with Siril (video tutorial)](https://www.youtube.com/watch?v=pyBP8H9Gi3w)

---

## Save

Save the sharpened result as TIFF for sharing/printing and keep the pre-sharpened stack FITS as the archival master:

- `lunar_YYYYMMDD_stack.fit` — stacked, unsharpened (reprocess from here)
- `lunar_YYYYMMDD_final.tif` — sharpened output

---

## Quick Reference

```
[CONVERT]   File → Conversion: AVI → FITS, debayer OFF
[DEBAYER]   Calibration tab: Debayer before saving, BGGR → pp_ sequence
[REGISTER]  KOMBAT registration
[SELECT]    Frame Selector: exclude bad frames manually
[STACK]     Sum stacking, no normalization
[SHARPEN]   À Trous Wavelets: BSpline, Layer 1 ~65, Layer 2 ~10, rest default
[SAVE]      _stack.fit (master) + _final.tif (output)
```

---

## Known Issues / Notes

- **AVI only:** The S50 does not offer SER output. SER would carry Bayer metadata in the header; AVI does not, which is why the manual BGGR setting in Preferences is required.
- **RAW8 bit depth:** 8-bit limits dynamic range. Sum stacking (rather than averaging) partially compensates. 16-bit capture is not available on the S50.
- **Seestar in-app stacks:** `Video_Stacked_*.fit` files produced by the app are usable for quick review but include all frames with no quality selection. External stacking is worth the extra steps for keeper images.
- **Solar imaging:** Same workflow applies. Ensure the S50's solar filter is in place. Solar has higher contrast than lunar so wavelets can be pushed slightly harder on Layer 1 before ringing appears.

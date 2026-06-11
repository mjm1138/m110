# LP / narrowband Hα blend onto a broadband galaxy (Siril 1.4.2)

**Worked example:** M81/M82 — ~90 min of dual-band **LP** data blended onto a
~12 h **broadband (IRCUT)** base to put a real red Hα core/outflow on M82, with
clean star separation and proper galaxy color. First run: June 2026.

This is the procedure for combining a **separate LP/narrowband session** with an
existing broadband galaxy stack on the Seestar S50 (OSC). Use it whenever a
galaxy has genuine emission worth isolating — M82's starburst outflow is the
classic case; M51, M101, M106, M33 HII regions are candidates too.

It assumes you already know the base pipeline in
[`siril_processing_workflow.md`](siril_processing_workflow.md) and the colour
work in [`siril_color_saturation.md`](siril_color_saturation.md); this doc only
covers the **two-filter blend** that sits on top of them, and documents the
PixelMath steps in full because the dialog is unintuitive.

---

## The mental model (read this first)

You are **not co-stacking** the LP subs into the broadband stack. Different
filters capture different signal, so they are **stacked separately, then
blended:**

- The **IRCUT broadband master stays the RGB base.** It carries the galaxies'
  true colour and the bulk of the luminance. Unchanged foundation.
- The **LP stack is a narrowband layer.** The Seestar LP filter is **dual-band
  Hα (656 nm) + OIII (500 nm)**. On an OSC sensor **Hα lands in the red
  channel**, OIII in green/blue. For M82 the prize is the Hα. We isolate it,
  remove its continuum and stars, and **add only the emission into the broadband
  red.**
- **Star separation happens on the broadband** (we keep its stars). The LP layer
  is used **starless** — we want its nebulosity, not a second star field.

The single most important technique is **continuum subtraction** (red − green):
the raw LP red channel is Hα *plus* red continuum (galaxy cores + stars), and the
continuum dominates so badly that the cores blow out the instant you stretch.
Subtracting a scaled green cancels the neutral continuum and leaves the emission.

**Realistic expectation:** ~90 min of LP yields a *tasteful red accent* on M82's
core and inner region plus the brightest HII knots — **not** the bold extended
bipolar filaments of a 10 h Hα image. The technique is what's proven here; drama
needs more LP hours. Don't judge the result until after saturation (the colour
finish is what makes it pop, not the blend itself).

---

## Folder organisation

The LP subs arrive in the *same* `lights/` folder as the IRCUT subs (the Seestar
mixes them). They must be stacked separately, so split the working folders. No
separate calibration frames are needed — the Naztronomy/Seestar workflow
calibrates without them, so each working folder only needs a `lights/` subdir.

```
M81 M82/
├── broadband/lights/   ← IRCUT subs        (working dir for the broadband re-stack)
├── LP/lights/          ← *_LP_* subs       (working dir for the LP stack)
├── blend/              ← registration + blend workspace (masters land here)
├── stacks/  presets/  process/             (existing, untouched)
└── lights/             ← left EMPTY during processing; restore at the very end
```

Separate by the **`_LP_` filename token**. Moving subs on one filesystem is a
near-instant metadata operation even for thousands of files.

> **Do not run `rebuild.sh` mid-process.** While the subs live in subfolders,
> `M81 M82/lights/` is empty, so the object drops out of the tracker. Restore the
> canonical `lights/` at the very end and rebuild then (which also finally counts
> the LP integration).

---

## Phase 1 — Stack the two filters separately

Run the **Naztronomy Smart-Telescope PP** twice, once per working dir.

**Stack A — Broadband (aggressive; cleanest possible).** Working dir
`broadband/`. With many hours in hand, frame *count* isn't the constraint —
sharpness is. Tighten the quality filters well below the usual 75/80: keep
roughly the **best half to two-thirds** (e.g. Roundness ~70 / FWHM ~75 /
star-count ~80, Weighted-FWHM stacking). Even best-50% leaves plenty of
integration; you lose nothing to averaging noise and gain per-frame sharpness.
**Drizzle 1.5×, pixel fraction 0.75** (the "matched" value at 1.5× — slightly
sharper than 1.0; see [`siril_drizzle_guide.md`](siril_drizzle_guide.md)).

**Stack B — LP / narrowband (gentle; preserve faint signal).** Working dir
`LP/`. This is faint Hα — every photon counts. Keep standard 75/80 or looser;
don't throw away signal chasing sharpness. **Drizzle 1.5×, pixel fraction 0.75 —
must match Stack A.** Identical drizzle scale puts both masters on the same pixel
*scale*, so registration later is a rigid align, not a resample.

> The two masters will likely come out **different pixel dimensions** even at the
> same drizzle scale — the canvas depends on how much each session's dithering
> spread (a multi-night broadband spans a wider area than a one-night LP). That's
> fine; same *scale* is what matters, and we crop to the common overlap.

**Go/no-go check:** auto-stretch (STF) the LP master. If the **red filaments
around M82's core are visibly there** even faintly, the whole plan is viable.

---

## Phase 2 — Register the LP master to the broadband master

Done on the **linear, uncropped** stacks (the ideal state for registration — crop
*after*). Put both masters in `blend/`, named so the broadband sorts first:
`1_broadband_ircut.fit`, `2_lp.fit`.

1. Set Siril's working dir to `blend/`.
2. Console: `convert reg` → makes a 2-frame sequence (`reg_00001` = broadband,
   `reg_00002` = LP).
3. **Sequences tab** → load the `reg` sequence → right-click image **1 (broadband)
   → Set as reference** (you don't want the broadband resampled).
4. **Set Transformation → Similarity** (this matters — see below).
5. **Pass 1 — Global Star Alignment.** Registration method **Global Star
   Alignment**, click **Register**. Watch the log for the matched-star count.
   Narrowband has few stars, so if it matches very few or fails, open the
   registration settings (gear) and raise the detected-star count / lower the
   threshold, then re-run. This pass only stores transforms.
6. **Pass 2 — Apply Existing Registration.** Switch method to **Apply Existing
   Registration** — now a **Framing** combo appears. Set **Framing → Minimum**
   (outputs the *intersection* of the two frames — aligned, same-dimension, no
   black borders, and it does the overlap-crop for free). Interpolation
   **Lanczos-4**, clamping on. **Estimate → Go register.**
7. Output: `r_reg_00001.fit` (broadband, reference) and `r_reg_00002.fit` (LP,
   aligned to the broadband grid).

**Verify:** blink the two `r_reg` frames — a bright star should sit on the same
pixel in both, and both should be the same dimensions.

> **Why Similarity, not Homography.** Homography is an 8-DOF projective transform
> that needs many well-distributed star matches; fed the *sparse* star field of a
> narrowband frame it can warp the LP to "fit" noise. **Similarity** (translation
> + rotation + uniform scale, 4 DOF) is exactly right for two stacks of the same
> target at the same pixel scale — it locks down with a handful of stars and can't
> introduce projective distortion.

> If **Minimum** framing ever looks wrong, fall back to **Maximum** + a manual
> crop. ~230 matched stars is plenty for a clean lock.

---

## Phase 3 — Crop + colour-calibrate the broadband

### Step 1 — crop both frames to an identical rectangle

Black borders wreck both background modelling and SPCC photometry, so crop first
— and **both frames must get the identical box** to stay pixel-aligned.

1. `load r_reg_00001` (broadband). Draw a generous selection rectangle **inside
   the clean signal on both frames** (avoid any edge that's black on either).
2. Console: type **`boxselect`** with **no arguments** — Siril echoes the current
   selection as `x y width height`. Note those four numbers.
3. `crop` then `save broadband_crop`
4. `load r_reg_00002` (LP). Set the *same* box: `boxselect X Y W H` (your noted
   numbers), then `crop`, then `save lp_crop`

Now `broadband_crop.fit` and `lp_crop.fit` are identical-dimension, aligned,
border-free, still **linear**.

### Step 2 — SPCC the broadband

This locks in *true* galaxy colour — the foundation for the saturation work
(saturating an uncalibrated image just amplifies a cast).

1. `load broadband_crop`
2. Image Processing → Color Calibration → **Spectrophotometric Color Calibration**
3. Sensor **ZWO Seestar S50**; filter = broadband / no-filter option.
4. If it doesn't auto-solve, give it: M81 coords **09h55m33s +69d04m**, focal
   length **252 mm**, and **pixel size = sensor px ÷ drizzle**. For the S50 at
   1.5× drizzle that's **1.93 µm ÷ 1.5 ≈ 1.29 µm** — the bit people forget; the
   raw 2.9 µm or un-divided value throws the plate scale off.
5. Apply. Expect M81 to read warm/golden core, cooler bluish arms.

### Step 3 — background, only if needed

The Naztronomy preset usually runs a background extraction already, so the crop
is probably flat. If a gradient remains, do a **gentle RBF** (Background
Extraction → RBF) with sample points placed *off* the galaxies. Leave `lp_crop`
alone — we flatten it as part of the Hα prep. Both frames stay **linear**; no
stretching yet.

---

## Phase 4 — Build the Hα layer (continuum-subtracted)

Work on the LP; **leave `broadband_crop` untouched** (it stays linear/calibrated
for Phase 5). Continuum subtraction **must be done in linear space** to cancel
cleanly.

1. **Split the LP into mono channels.** `load lp_crop`, then `split ha_r ha_g
   ha_b`. `ha_r` is your Hα-plus-continuum; you'll subtract `ha_g`.
2. **Continuum-subtract in PixelMath** — see the click-by-click below. Expression:
   ```
   max(ha_r - ha_g, 0)
   ```
   `max(…,0)` clips negatives to black. Save as **`ha_pure`**.
3. **Tune the subtraction.** Inspect `ha_pure`: if bright **leftover star dots**
   remain, the green wasn't scaled enough — bump it: `max(ha_r - 1.2*ha_g, 0)`.
   If stars became **dark pits** (over-subtracted), back off: `max(ha_r -
   0.85*ha_g, 0)`. Tune the coefficient **~0.85–1.3** until stars roughly vanish.
   M81 will also largely disappear — correct, it's a normal spiral with little Hα;
   **M82's emission is what should remain.**
4. **Background-extract** `ha_pure` (RBF, gentle) to flatten any residual red
   wash.
5. **Stretch it — now it's easy.** With the bright cores gone, console
   `autostretch` as a one-shot usually pops the emission with nothing blowing out.
   A gentle GHS on top is fine if needed.
6. **Denoise.** ~90 min of stretched narrowband is grainy; this is a colour/
   emission mask, not a detail layer, so a firm **GraXpert denoise** is fine and
   desirable.
7. **Crush the black point** so only confident emission survives: Histogram
   Transformation → drag the **shadows (left) slider right** until the background
   speckle goes pure black, leaving M82's core/inner emission and the brightest
   M81 knot. (Optional small Gaussian blur — colour accents can be soft.)
8. **Remove residual stars.** If star points remain *brighter than the emission*
   (so a black-point crush can't isolate them), run **StarNet++** on the layer to
   strip them as stars. Save the final emission layer as **`ha_clean`**.

End state: **`ha_clean.fit`** — M82's Hα on a black background, no stars, already
aligned/cropped to the broadband grid (no re-registration needed).

---

## Phase 5 — Stretch + star-separate the broadband

This gives the good galaxy colour and the stars you keep. Use **VeraLux HMS**,
not manual GHS (HMS protects cores and preserves OSC colour). We separate stars
**on the linear data** with **StarNet++** (Siril's integrated remover; note
**StarXTerminator is *not* a Siril feature** — it only runs in PixInsight/
Photoshop/Affinity, so don't go looking for it in Siril).

Linear (pre-stretch) separation is preferred here: stars are still tight (smaller,
cleaner holes) and — the real win — you can then **stretch the galaxy and the
stars independently**.

1. `load broadband_crop` (linear, SPCC'd, background-extracted — **don't
   stretch**).
2. **Run StarNet++** with the **"generate star mask" option on**, so it outputs
   *both* a starless image and a star-only layer in one pass. You'll get
   `starless_…` and `starmask_…` files. (If you only get the starless, derive the
   stars in PixelMath: `broadband_crop - starless_bb` — see the recombine note on
   modes.)
3. **Stretch the galaxy:** `load` the starless → **VeraLux HMS**. Moderate,
   colour-preserving, cores protected, and **leave the background a dark *neutral
   gray*, not crushed black** — around 0.08–0.12 (≈20–30/255). This is the M106
   lesson: clipping shadows to zero kills the faint outer halos. Save as
   **`starless_bb_stretch`**.
4. **Stretch the stars *gently* and separately:** `load` the star mask → light
   HMS or asinh. Its only job is to carry star *colour*; avoid bloating. **Don't
   over-stretch** — if faint galaxy ghosts start surfacing in the mask, that's
   your cue to back off (the galaxy residual is buried in the linear mask and only
   appears when over-amplified). Keep this linear-ish mask around for Phase 8.
5. **Kill any green cast** on the starless: Color → **Remove Green Noise (SCNR)**,
   mode **Average Neutral**, preserve-lightness on. `save starless_bb_stretch`
   (overwrite).

---

## Phase 6 — Blend Hα into M82's red (the payoff)

Here we add `ha_clean` into **only** the red (and a touch of blue) of the
starless galaxy. This needs the **compose-from-mono** PixelMath mode, so we split
the starless to mono first.

1. `load starless_bb_stretch`, then split it to mono:
   ```
   split sb_r sb_g sb_b
   ```
2. Open **PixelMath**. **Leave "Use single RGB/K expression" UNCHECKED**
   (compose-from-mono mode — see the rule below). Add four variables with `+`:
   **`sb_r`, `sb_g`, `sb_b`, `ha_clean`** (all mono → compatible).
3. Fill the three boxes:
   - **R:** `min(sb_r + 0.4*ha_clean, 1)`
   - **G:** `sb_g`
   - **B:** `min(sb_b + 0.1*ha_clean, 1)`
4. **Apply** → it composes a colour image, adding Hα into red and a touch into
   blue (so the emission reads as a natural **pink-red HII glow**, not a neon
   stripe) while green passes through. `min(…,1)` prevents clipping. `save
   blended`.

**Tune the `0.4`** (blend strength): timid red → push to 0.5–0.6; fake-red blob →
pull back to 0.2–0.3. Keep the **blue coefficient ≈ ¼ of the red**. If background
red speckle appears, it's residual in `ha_clean` — go back and crush its black
point harder *before* you saturate (Phase 7 will amplify it otherwise).

---

## Phase 7 — Saturation (the step that makes it pop)

This is where the muted post-stretch image becomes a real astrophoto — it's the
recovery of the SPCC colour the stretch compressed. **Don't be timid.** Full
detail in [`siril_color_saturation.md`](siril_color_saturation.md); the short
version applied here:

1. `load blended` → Image Processing → Color → **Color Saturation**.
2. **Amount ≈ 0.5**, raise the **Background factor** so the dark sky doesn't
   saturate (keeps noise/speckle from colouring up). Apply and **repeat 2–3
   passes** — each compounds — until M81's core reads clearly golden, its arms
   show blue, and M82 looks dusty-red rather than gray. Muted is the failure mode,
   not too colourful.
3. **Hue-target** for the finish: one pass limited to the **blue band** (M81's
   arms light up), one on the **red/orange band** (cores + M82's emission deepen).
   This lets the galaxies out-colour the background instead of lifting everything.
4. **CLAHE** (Filters → CLAHE, low clip limit) for local contrast — spiral arms
   and M82's dust read three-dimensionally, and contrast makes colour *feel*
   richer.

**Watch-point:** if M81's core drifts toward neon magenta, ease the red/orange
pass. (A subsequent GraXpert gradient/denoise pass also gently pulls an
over-hot core back into a pleasing golden-pink.)

**Gradient cleanup.** Pushing saturation + contrast often surfaces a faint
gradient. A starless image is ideal for fixing it: **RBF background extraction**,
sample points spread across the background (delete any on the galaxies/halos),
correction **Subtraction**, **smoothing high** (a light-pollution ramp is broad
and smooth). GraXpert's background mode is a good second option. Save as
**`starless_final`**.

---

## Phase 8 — Prep the star layer

Work from the **linear** star mask (`starmask_broadband_crop`) — not the stretched
one, whose ghosts were just amplification.

1. `load starmask_broadband_crop`.
2. **Stretch gently** (asinh or light HMS): stars clearly visible with colour,
   background dark. **Don't over-stretch** — if galaxy shapes surface, back off.
3. **SCNR green** (Average Neutral) to keep stars neutral-to-natural.
4. **Magnitude-weighted saturation:** Color Saturation with a **high Background
   factor** so only the *bright* stars take colour while faint stars stay white —
   that reads as a real star field instead of uniformly-tinted dots. Modest
   amount. Save as **`stars_final`**. (Technique detail in
   [`siril_color_saturation.md`](siril_color_saturation.md).)

---

## Phase 9 — Recombine + export

1. **PixelMath**, **"Use single RGB/K expression" CHECKED** (this mode accepts
   *colour* inputs). Add `starless_final` and `stars_final`. **Screen blend** so
   stars add light over the galaxies without darkening them:
   ```
   ~(~starless_final*~stars_final)
   ```
   (`~` is Siril's invert, so this is `1−(1−galaxy)(1−stars)` — the screen
   formula.) **Apply**, inspect, `save final_combined`.
2. If the stars come out too heavy/bright, redo Phase 8 step 2 with a gentler
   stretch and re-blend — that's the one balance knob.

> **PixelMath screen blend vs VeraLux StarComposer:** StarComposer applies its
> *own* stretch to the star layer during the combine, overriding the controlled,
> magnitude-weighted star stretch you built in Phase 8 (it produces a fuller,
> brighter star field). The PixelMath screen blend **honours your star
> treatment** — preferred for the galaxy-as-hero look. StarComposer's fuller field
> is a legitimate taste choice, just know it's re-stretching on top of your work.

3. **Export** a 16-bit **TIFF** (archive) and a **PNG/JPG** (sharing) into
   `Images/Finished Images/M81 M82/`.
4. **Set the hero:** in `data/objects/m81.md` and `m82.md` frontmatter add
   `hero: <display name>` (or just dropping the render in `Finished Images/` lets
   auto-discovery pick it up).
5. **Housekeeping:** move the subs back from `broadband/lights/` and `LP/lights/`
   into the canonical `lights/`, delete the `blend/ broadband/ LP/` working dirs,
   then `scripts/rebuild.sh --run` so the tracker counts the LP session and the
   new render appears on the site.

---

## PixelMath — the dialog, in detail

The PixelMath UI is unintuitive; this is the part that trips everyone up.

### Loading inputs (you don't type filenames)

1. Click the **`+`** button at the top-right of the window (next to `−`). A file
   picker opens → select a `.fit`. It appears in the **Images** table.
2. Repeat `+` for each input image.
3. Look at the **Variable** column — that's the name to use in expressions
   (usually the filename stem, e.g. `ha_r`). Use whatever it actually shows. An
   "unknown variable" error almost always means a name typo vs. that column.

### The one rule that matters: the "Use single RGB/K expression" checkbox

| Checkbox | Boxes | Accepts | Produces | Use it for |
|---|---|---|---|---|
| **CHECKED** | one expression | **colour** *or* mono inputs (applied per-channel) | matches input | operating on a whole colour image; the **screen-blend recombine** (Phase 9); a **mono** op like the continuum subtraction (Phase 4) |
| **UNCHECKED** | separate R/G/B | **mono inputs only** (rejects colour) | a **colour** image composed from the three expressions | **composing colour from mono** — the **Hα-into-red blend** (Phase 6) |

The asymmetry is the trap:
- Feeding a **colour** image to the **unchecked** (R/G/B) mode →
  *"3 channel images are incompatible…"*. Fix: split the colour image to mono
  (`split r g b`) and feed the mono channels (Phase 6), **or** switch to the
  checked single-expression mode if you don't need per-channel control.
- A **channel-count mismatch** (e.g. mono `ha_clean` with a colour image in the
  *checked* mode) → *"size is different… number of channels"*. Fix: either
  replicate the mono to 3 channels — console `rgbcomp ha_clean ha_clean ha_clean
  -out=ha_clean_rgb` — **or** (better for a differential channel blend) split the
  colour image to mono and use the unchecked compose mode, which is the Phase 6
  method.

### The expressions used in this workflow

| Purpose | Mode | Expression(s) |
|---|---|---|
| Continuum-subtract Hα (Phase 4) | single (mono in/out) | `max(ha_r - ha_g, 0)` (tune coeff 0.85–1.3 on `ha_g`) |
| Derive stars if no mask (Phase 5) | unchecked, mono | put `broadband_crop - starless_bb` in R, G, B |
| Blend Hα → red (Phase 6) | unchecked (compose) | R `min(sb_r+0.4*ha_clean,1)` · G `sb_g` · B `min(sb_b+0.1*ha_clean,1)` |
| Screen-blend stars over galaxy (Phase 9) | **checked** (colour) | `~(~starless_final*~stars_final)` |

Operators/notes: `max(a,b)` is the per-pixel two-argument max (clips negatives
when `b=0`); `min(x,1)` prevents overflow/clipping; `~x` = `1−x` (invert);
multiplication is per-pixel. Ignore the function/operator palettes on the right —
just type the expression.

---

## Gotchas & lessons (quick reference)

- **Continuum subtraction must be linear.** Subtract `ha_r − k·ha_g` *before* any
  stretch, or the neutral continuum won't cancel.
- **Match drizzle scale across both stacks** (1.5×/0.75 here) so registration is a
  rigid align, not a resample.
- **Use Similarity, not Homography**, for two stacks of one target — narrowband's
  sparse stars make Homography warp to noise.
- **SPCC pixel size = sensor px ÷ drizzle** (1.93 µm ÷ 1.5 ≈ 1.29 µm). Forgetting
  the division breaks the solve/plate scale.
- **StarXTerminator is not in Siril** — use the integrated **StarNet++**.
- **Separate stars on linear data** so you can stretch galaxy and stars
  independently (and get smaller, cleaner star holes).
- **Don't crush the background to black** — leave a dark neutral gray (~0.08–0.12)
  to keep faint halos (the M106 lesson).
- **Judge after saturation, not before.** The stretch desaturates; the blend looks
  flat until the colour finish recovers the SPCC colour.
- **Screen-blend, don't StarComposer**, if you want your controlled star stretch
  honoured at recombine.
- **Don't run `rebuild.sh` until `lights/` is restored** at the end.
- **Data honesty:** ~90 min LP = a tasteful red accent, not bold filaments. More
  LP hours is the only path to dramatic outflow structure.
```


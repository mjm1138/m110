# Your telescopes — the Devices page

← [Back to the guide](README.md)

The **Devices** page (the last entry on the rail, Ctrl+6) has one entry for every
telescope you've imported from. M110 learns a telescope from the `TELESCOP` card in
its FITS headers, so there's nothing to register: import from it once and it
appears here. Two units of the same model are two entries (each has its own serial),
but they count together toward an object's
[integration goal](library.md#integration-goals-how-deep-is-deep-enough).

The list is ordered by most recent capture. Pick a telescope to see its details on
the right.

## Identity

- **Nickname** — call it what you call it ("Backyard S50", "Travel S30"). The
  nickname is used everywhere the telescope is named: the session tables, Planning's
  Telescope picker, field guides. **Save** / **Revert** light up once you've changed
  something.
- **Model** — M110 recognises Seestar and DwarfLab telescopes from their headers and
  says so. For anything else, tell it the model here so it gets the right planning
  limits and goal scaling.
- **Retired** — hides a telescope you no longer use from the list and from the
  pickers. Its captures stay in your Library. **Show retired** brings it back into
  the list.

## Planning limits

**Use for planning** makes this the telescope the **[Planning](planning.md)** page
plans for. You can also switch telescopes there. Each model comes with its own limits,
which you can adjust per telescope:

- **Start ceiling** — the highest altitude a capture may *start* at. A Seestar
  refuses to start near the zenith, so its ceiling is **hard**; a Dwarf's is softer.
- **Low-altitude floor**, **Longest exposure**, **Default exposure**, **Gain**.

**Save limits** keeps your changes; **Model defaults** puts the model's values back.

## Optics

Aperture, focal length, f-ratio and pixel size, and what they mean for your goals:
"Integration goals here are ×0.73 the S50's" for a faster telescope, for example.
A recognised model shows its published specs, read-only. For a telescope M110
doesn't recognise you can enter them yourself (**Save optics**); until you do, its
goals use the S50's numbers.

## What it captured

- **Objects** — every object this telescope has shot, with its integration time and
  last capture. Right-click → **Open object** jumps to it in the Library.
- **Captures** — every capture session with its sensor temperature and the
  **Dark** it used (see below).
- **Sensor health** — two charts built from its darks: the dark level (median ADU)
  and the hot-pixel count, each against sensor temperature.

## The dark library (Seestar)

A Seestar keeps its own master darks and subtracts one from every sub before saving
it. When you import from the telescope, M110 copies those masters into
`Calibration/<telescope>/darks/` (see **[Ingest](ingest.md)**) and lists them here,
each with a preview, its median level and hot-pixel count. A dark is named by when the
telescope made it and at what temperature ("Oct 15 21:52 · 13.9 °C"). It's named the
same way everywhere in M110.

M110 never applies these darks again: that would subtract the dark twice. They're
here so you can see **which dark each capture got**:

- Select a capture and the dark(s) it used highlight; select a dark and right-click
  → **Select the captures it served**.
- The **Dark** column shows how far the sensor drifted from that dark
  ("24.9 °C · Δ10.5 ⚠"). Past about 3 °C, hot pixels come out over- or
  under-subtracted; `m110-stack --max-dark-gap 3` leaves those frames out (see
  **[Processing](processing.md#stacking-without-opening-siril)**).
- The Seestar switches to a better-matched dark mid-capture once the sensor has
  moved about 2.5 °C. A capture that switched shows each dark it used
  ("24.9→23.2→13.9 °C").
- The Seestar doesn't record which dark it used, so M110 works it out from when each
  dark was made and the sensor temperature. It says whether a link is confirmed or
  inferred.

Right-click a dark → **Reveal in Finder** (**Reveal in file manager** on Windows and
Linux) to see the file; right-click a capture to reveal the dark it used.

Next: **[Processing prep & hardlinks →](processing.md)**

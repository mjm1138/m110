# On the roadmap

← [Back to the guide](README.md)

M110 is in public beta. A few capabilities are **partially built** — you'll see them
referenced in the app before they're fully finished. This page explains what works
today versus what's coming, so nothing feels broken.

## Session planning

**What works now.** The whole planning flow shipped — see
**[Session planning](planning.md)**: site profiles with horizon and light-dome
layers, the automatic target ranking with strategy/weight tuning, the night
scheduler with its altitude timeline, and saved field guides.

**What's coming.** **Device-ready schedule export** — writing a plan straight into a
format your telescope's automation can run (such as an SSC file for
`seestar_alp`-style schedulers) instead of a human-readable guide only. And the
telescope constraints for the Seestar **S30 / S30 Pro** are currently assumed to
match the S50 — if your S30 accepts or refuses high starts differently, we'd love
the report.

## Publishing & sharing

**What works now.** **Library → Publish / share** exports a selective static website
of your collection to a local folder — pick which sections and objects to include,
keep journals private, and open the result in your browser.

**What's coming.** One-click deploy targets (GitHub Pages, Netlify, and similar) so
publishing goes straight to the web instead of a local folder. These appear in the
Publish dialog marked *"(soon)"*.

## Other processing tools

M110 prepares for **Siril** today. Other tools (PixInsight and friends) appear in
Preferences marked *"(soon)"* — the prepare-and-guide framework is built to add them,
but only Siril is wired up for now.

---

*This list tracks the user-visible gaps only. The full, living roadmap lives in the
project's [`ROADMAP.md`](../ROADMAP.md).*

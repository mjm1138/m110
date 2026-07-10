# On the roadmap

← [Back to the guide](README.md)

M110 is in public beta. A few capabilities are **partially built** — you'll see them
referenced in the app before they're fully finished. This page explains what works
today versus what's coming, so nothing feels broken.

## Priority targets

**What works now.** On the **Summary** page, the *Priority targets* list shows objects
you've flagged. You flag them manually: right-click any object in the Library, Goals,
or the priority list and choose **Pin as priority** (▲) or **Deprioritize** (▼).
Pinned objects always show; deprioritized ones are hidden. These choices are saved
with your library and survive refreshes.

**What's coming.** An **automatic prioritizer** that *scores* and ranks your targets
for you — weighing things like how close an object is to leaving the season, how much
integration it still needs, and tonight's observability — so the list becomes a
smart "what should I shoot next" rather than a purely manual one. Your manual pins
will always compose over the automatic ranking.

## Session planning

**What exists now.** M110 already includes the astronomical engine for planning —
twilight windows, moon interference, an object's altitude and transit, and a
seasonal/tonight observability gate — plus per-site profiles (your latitude,
longitude, horizon obstructions, and light-pollution level).

**What's coming.** A **planning view** that surfaces this: tonight's best targets for
your site, when each is highest, and how many clear nights remain before an object
sets for the season. Until that page ships, the planning engine mainly feeds the
prioritizer work above.

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

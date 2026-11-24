# M110 public beta: announce drafts

Two versions: a Reddit post for r/seestar and a shorter one for the Smart Telescope
Underworld Discord. Both are in your voice. Lines in [brackets] are for you to fill in
or delete.

Before posting:
- Check each venue's self-promotion rules (r/seestar's sidebar; the Discord's
  #rules or a #showcase / #software channel). Both drafts say up front that you built it.
- Reddit: an image post with 3 shots in a gallery usually beats a text post. Use
  `site/assets/shot-overview.jpg`, `shot-detail.jpg` and `shot-night.jpg`, and put the
  text below as the body or as your first comment.
- Both drafts link to m110.space, not GitHub. The site's Download buttons go to
  `/releases/latest`, which has no stable release yet, so they land on the list of
  releases with the beta at the top. That works, but it's one extra click.

---

## Reddit — r/seestar

**Title options**

1. I built a free, open-source photo library for Seestar captures: M110 public beta (Mac / Windows / Linux)
2. M110: free "Lightroom for smart telescopes" that tracks your Messier progress. Public beta is out
3. My Seestar folder got out of hand, so I built an app for it. M110 public beta, free and open source

M110 update: my free smart telescope library manager has reached 1.0 public beta

**Body**

Background: Just a couple months after I got my S50, I had thousands of subs across 
dozens of folders, and no easy answer to "which Messier objects do I still need?" or "is 
M81 worth another night?" So I built **M110**, a free desktop app that turns a pile of 
Seestar captures into an organized deep-sky library. Today it's reached 1.0 public beta.

**What it does**

- **Imports straight from a Seestar.** Plug it in or point it at a folder. M110 sorts
  subs, stacks and finished images by object, and shows you the plan before it writes
  anything. It also reads DwarfLab captures and N.I.N.A./PINS sessions.
- **Tracks every object you've shot.** Sessions, frames, filters and total integration
  come from the FITS headers, so it knows what you've actually captured.
- **Gives you a goal to chase.** The Overview opens on a board of all 110 Messier
  objects (or Caldwell, or your own list). Each one moves from Initial to In progress to
  Deep as you add time, with goals per telescope available.
- **Stacks for you.** One click stacks a target in Siril, or sets up a Siril folder with
  your lights linked and a preset ready. Hand the result to AstroWizard or
  StackingWizard, and your finished images come back into the library.
- **Gets calibration right.** Seestar app subs are already dark-subtracted on the scope,
  so M110 never darks them twice. A Devices page shows which dark each night actually
  got. But if you have uncalibrated frames, M110 will match the best darks from your 
  device's dark library when setting up the Siril processing directory
- **Plans your nights.** It shows what's up tonight ranked by your goals, a moon-aware
  schedule with an altitude timeline, and a printable field guide. Night Vision turns
  the whole app red for use at the scope.
- **Maps your sky.** It plots your collection on a star chart, with the objects you
  haven't captured in grey.
- **Backs up your library** to a local drive and/or an S3-compatible cloud bucket.

It's local-first: your files stay in plain folders on your disk, with no account and no
cloud service. It's free and open source (Apache-2.0), with no subscription and no
licence key.

**Download:** https://m110.space (macOS signed and notarized for Apple Silicon; Windows
installer; Linux AppImage)

**It's a beta, so:**

- The Windows installer isn't code-signed yet. SmartScreen will warn you; click **More
  info → Run anyway**.
- I've used it most on a Mac with an S50. Windows and Linux have had much less real use,
  and I'd especially like reports from S30 / S30 Pro / S50 Pro owners and Dwarf users.
- Bug reports and feature requests: https://github.com/mjm1138/m110/issues, or just
  reply here.

I'd love to hear what you think, especially what's confusing in your first ten minutes.

*Not affiliated with or endorsed by ZWO or DwarfLab.*

---

## Discord — Smart Telescope Underworld

**M110 public beta: a free photo library for smart-telescope captures** 🔭

I've been building a desktop app for organizing Seestar (and Dwarf and N.I.N.A.) captures,
and the public beta is out today.

- Imports from the scope or any folder and files everything by object, with a preview
  before it writes anything
- A board of all 110 Messiers (or Caldwell, or your own list) that fills in as you add
  integration time
- One-click Siril stacking, plus hand-offs to AstroWizard / StackingWizard
- Seestar-aware calibration (never darks on-device-darked subs twice)
- Night planning with a moon-aware schedule, field guides, and a red Night Vision mode
- Local-first, free, open source (Apache-2.0)

Mac (signed and notarized), Windows (unsigned beta: More info → Run anyway) and Linux
(AppImage): <https://m110.space>

It's a beta, so feedback is gold, especially from S30 / S30 Pro and Dwarf owners and
anyone on Windows. Issues: <https://github.com/mjm1138/m110/issues>, or ping me here.

*Not affiliated with ZWO or DwarfLab.*

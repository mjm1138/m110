# M110 — Public Beta Readiness Checklist

What has to be true before we invite strangers to run M110. The persona we're
inviting: **someone who recently got a Seestar, is enjoying the hobby, and wants
structure for a growing library plus a north-star goal** — *not* necessarily a
developer who can set up a venv.

**Decided (2026-07-04):**
- **Reach:** Seestar hobbyists in public forums — **r/seestar** (Reddit) and the
  **Smart Telescope Underworld** Discord — with a secondary hope of attracting
  developers. So the bar is "a hobbyist feels it's accessible," not "an
  open-source dev can build from source."
- **Platform priority: macOS first, Linux a close second, Windows supported.**
  M110 is a **Mac-first app designed to be compatible with Linux and Windows** —
  matching the maintainer's own platforms (Mac, then Linux). Windows is genuinely
  supported and a plurality of forum users likely run it, but it is *not* the lead
  platform, and the Reddit-Windows-majority perception doesn't generalize to all
  Seestar owners — Mac and Linux matter just as much.
- **Apple Developer ID: in hand.** macOS notarization is *work, not a budget
  decision* — and macOS ships **signed + notarized** from day one.
- **Windows signing: deferred.** The beta ships **unsigned Windows releases** with
  clear "click More info → Run anyway" instructions. Revisit code-signing certs /
  licenses **only if the app gets uptake** — don't buy a cert on spec.

ROADMAP.md and BUGS.md track **features**. This file tracks **shippability** —
the gap between "feature-complete for me" and "usable by a stranger on their own
machine." Most of it is *not* in those files.

Legend: 🔴 blocker (no beta without it) · 🟡 strongly wanted · 🟢 nice-to-have
`[ ]` open · `[~]` partial

---

## 0. The headline gap

macOS is the strong platform (where dev happens). **Linux is smoke-confirmed** —
runs from source on a Raspberry Pi 5 (`skywalker.local`, ARM64), UI looks fine,
Seestar import works — but only shallowly, on ARM, not the packaged x86_64
AppImage most desktop users would run. **Windows has never been run at all.**
Every risk below flows from that. The two make-or-break tracks are **(1) a real
installer a non-developer can double-click — macOS signed/notarized first, then a
Linux AppImage, then an (unsigned) Windows build** and **(2) proving the Seestar
ingest + cross-platform basics hold up on Windows and on real x86_64 Linux
desktops, not just Mike's Mac + Pi.** Everything else is supporting.

---

## 1. Packaging & distribution 🔴

*Today the only way to run M110 is `pip install -e ".[dev]"`. That disqualifies
the target persona outright. Nothing here is in ROADMAP/BUGS beyond a one-line
"future" note.*

*Build order follows priority: **macOS → Linux → Windows** — but all three ship
for the beta (Windows just ships unsigned).*

- [ ] 🔴 **macOS `.app` bundle** *(lead platform)* — PyInstaller or Briefcase; the
  durable fix for the app/dock name (CLAUDE.md already flags the NSBundle patch as
  a stopgap).
- [ ] 🔴 **macOS notarization + Developer-ID signing** — Dev ID in hand, so this
  is a scripting/CI task (codesign → notarytool → staple), not a decision. macOS
  ships signed from day one.
- [ ] 🔴 **`.dmg` installer** (drag-to-Applications).
- [ ] 🔴 **Linux package** *(close second)* — **AppImage** (single-file,
  double-click, no install — best fit for a mixed-distro audience) as the primary;
  Flatpak as a follow-on. PySide6 + system Qt can be fiddly; test on Ubuntu LTS +
  one other.
- [ ] 🔴 **Windows build + installer** — PyInstaller `.exe` + Inno Setup (or MSI).
  Ships for the beta, but as a supported-not-lead platform.
- [ ] 🟡 **Windows unsigned-launch docs** — unsigned binaries trip **SmartScreen**
  ("Windows protected your PC"). For the beta this is **accepted**: ship unsigned
  and document the "click More info → Run anyway" step prominently on the download
  page / in the announce post. **Revisit an OV/EV code-signing cert only on
  uptake** — don't buy one on spec. (EV clears SmartScreen instantly but is pricey
  + hardware-token; OV builds reputation over time — a later decision.)
- [ ] 🟢 **Homebrew cask** (`brew install --cask m110`) / **winget** manifest —
  nice for the dev-y tail; not a substitute for the double-click installers.
- [ ] 🔴 **Real version number + scheme** — still `0.0.1` in pyproject. Pick
  `0.1.0-beta.1` (or similar) and wire `importlib.metadata` (About dialog already
  reads it).
- [ ] 🟡 **Update story** — at minimum a "check for updates / you're on vN"
  pointer to a releases page so beta users don't run stale builds. Auto-update is
  a bonus, not required.

## 2. Cross-platform QE 🔴

*Developed + exercised on macOS. **Linux is smoke-confirmed** (Pi 5 / ARM64, from
source — runs, UI fine, Seestar import works, shallow only). **Windows untested.***

- [~] 🟡 **Linux deeper pass on x86_64 desktop** — the Pi 5 run proves the code is
  Linux-clean, but confirm on a mainstream **x86_64** distro (Ubuntu LTS) with a
  desktop session (X11 *and* Wayland) and exercise the full flow: first-run,
  ingest, refresh, processing-prep, backup, publish, Media "Open." Then confirm the
  **packaged AppImage** (§1) runs, not just the from-source path.
- [ ] 🔴 **Actually run on Windows** — full smoke. Watch path handling, file
  dialogs, and the **Seestar SMB mount detection** (`find_seestar_myworks` — drive
  letters vs. `/Volumes`).
- [ ] 🟡 **Media "Open" launch** cross-platform (`pages/media.py` shells out to an
  OS player — verify on all three; this is exactly the cross-platform-launch risk
  ROADMAP #19 flags).
- [ ] 🟡 **Fresh-machine install test** — install the *packaged* build on a clean
  VM with no Python/dev tools and confirm it runs. This is the real acceptance
  test for §1.

## 3. Seestar ingest robustness 🔴

*This is THE core flow for the target audience, and it's been validated against
exactly one telescope + one firmware + one folder layout.*

- [ ] 🔴 **Other Seestar models** — S30 / S50 (and the newer bodies) folder
  structures, naming, and `MyWorks` layout. Confirm or gracefully degrade.
- [ ] 🔴 **Firmware / app-version variation** — folder names and per-sub `.jpg`
  layout have changed across ZWO app releases; make the scanner tolerant.
- [ ] 🟡 **Connection modes** — SMB share vs. USB/SD-card copy vs. the ZWO
  companion-app export folder. Which do we support, which do we document?
- [ ] 🟡 **"My Seestar isn't detected"** path — a clear manual "choose folder"
  fallback when auto-detection misses (many users won't have it SMB-mounted).
- [ ] 🟢 Beta-test the ingest against a couple of *other people's* Seestar dumps
  before wide release (recruit 2–3 friendly testers first).

### Reach expansion — DwarfLab (Dwarf II / Dwarf 3) support 🟡

*Scoped as **ROADMAP item 12**. Not a Seestar-beta blocker, but a strong reach
multiplier: DwarfLab is the #2 smart-telescope community and multi-device support
is a stronger pitch than Seestar-only. The public docs are sufficient to build a
first-pass layout (additive `LAYOUTS` entry + classifier; no store-version bump).*

- [ ] 🟡 **Decide whether Dwarf support ships *in* the first beta or as a fast
  follow-on.** Seestar-only is a clean beta; Dwarf-included widens the announce
  audience on day one. Gated on the sample dump below.
- [ ] 🟡 **Recruit a Dwarf II/3 owner** (same forums) to share a real `Astronomy/`
  capture dump — needed to confirm the two open bits (exact raw-sub
  filename/extension; whether subs carry RA/DEC/OBJECT headers or only the stack).
- [ ] 🟢 **Bug-report template asks which telescope** (Seestar model / Dwarf model)
  so multi-device issues are triageable from day one (ties into §7 templates).

## 4. First-run & onboarding 🟡

*A stranger's first 10 minutes decide whether they stay. Today they land in an
empty/all-uncaptured Library with no orientation. (Partly in BUGS "UI niceties.")*

- [ ] 🟡 **First-launch data-folder prompt** (BUGS backlog) — one-time "where
  should M110 keep your library?" instead of silently defaulting.
- [ ] 🟡 **Empty-state guidance** (BUGS backlog) — "Import from your Seestar to
  get started" when the Library is all-uncaptured.
- [ ] 🟡 **Guided first import** — the happy path (point at Seestar → preview →
  confirm → see your first object) should be obvious without reading docs.
- [ ] 🟢 **Sample/demo data** or a "tour" so someone can see the payoff before
  they've captured anything.
- [ ] 🟡 **Siril-not-installed guidance** — processing-prep assumes Siril exists.
  A first-timer needs "install Siril, then…" hand-holding (detect + link to the
  playbook), or the Processing page looks broken.

## 5. Stability, errors & feedback 🔴

*There's a `crash_dumps/` directory in the repo — crashes happen. A beta needs
graceful failure and a way to hear about it.*

- [x] 🔴 **Global exception handling** *(done — `feature/stability-errors`).*
  `error_report.install_excepthook` (wired in `main()`) replaces PySide6's
  abort-on-uncaught-slot-error with an "M110 hit a problem" dialog carrying a
  copyable report; the app **keeps running** (Continue) instead of hard-crashing.
  Worker-thread exceptions marshal to the GUI thread; re-entrancy-guarded.
- [x] 🔴 **In-app "Report a problem / feedback"** *(done).* **Help → "Report a
  problem…"** opens the same report dialog (version + OS + Qt + log tail),
  pre-filled, with a **Copy report** button and a **prefilled GitHub new-issue**
  (`issue_url`; `REPO_URL` constant — repoint when the public repo name is settled).
- [x] 🟡 **Log file** *(done).* `m110/logsetup.py` — rotating log at
  `~/.m110/logs/m110.log`, surfaced in the report path (`read_log_tail`).
- [x] 🟡 **Loud "back up your library" nudge** *(done).* `_maybe_backup_nudge`
  prompts **once ever**, only once the user has captures worth losing
  (`backup_nudge_seen` setting), pointing at the existing Back up dialog.
- [ ] 🟢 **Opt-in anonymous telemetry** (crash counts / which OS) — decide yes/no;
  if yes it needs disclosure + consent. Defensible to skip for beta.

## 6. Public presence & distribution channel 🔴

*You can't run a public beta with a private repo and no download page. Mostly
tracked only as a one-line "external presence" note in ROADMAP's decisions table.*

- [ ] 🔴 **Public GitHub repo** — under a real org (ROADMAP notes `m110` is taken →
  `m110app`/`messier110`); make the repo public, pick the license display, add
  Releases. **Before flipping it public, land the contribution-readiness items in
  §7** (branch protection, CONTRIBUTING, issue/PR templates, contribution-license
  stance) — a public repo will start receiving issues and PRs immediately, and it's
  easier to have the guardrails in place than to retrofit them mid-flood.
- [ ] 🔴 **Landing page / website** — `m110.app` (ROADMAP flags "verify at
  registrar"). Even a one-pager: what it is, screenshots, download links, "how to
  give feedback." The Features.md / Why M110.md copy is written — it needs a home.
- [ ] 🔴 **Download/Releases page** with the signed artifacts from §1 and clear
  per-OS install steps.
- [ ] 🟡 **Screenshots / a short demo GIF or video** — the app is image-forward;
  show it. Needed on both the site and the repo README.
- [ ] 🔴 **Feedback venue** — the audience already lives on **Discord (Smart
  Telescope Underworld)** and **r/seestar**, so meet them there: a pinned beta
  thread / dedicated Discord channel is lower-friction for a hobbyist than filing
  a GitHub issue. Back it with GitHub Issues (templates below) for developers and
  durable tracking; the in-app "report a problem" (§5) should point at whichever
  is primary.
- [ ] 🟡 **Announcement plan** — post in **r/seestar** and the **Smart Telescope
  Underworld** Discord (the two named targets); secondary: Cloudy Nights,
  Seestar Facebook groups, ZWO forums. Draft the post + lead with a screenshot/GIF
  and the "never touches your originals" promise.

## 7. Repo hygiene / accepting contributions 🟡

*Standard "this is a real open-source project" table stakes **plus** being ready to
receive pull requests and (eventually) onboard other contributors. None present
today. A public repo receives issues/PRs from strangers on day one, so these are
gating on §6's "make the repo public," not follow-up polish.*

- [~] 🟡 **CI** — `.github/workflows/ci.yml` runs `pytest -q` on **ubuntu-latest**
  across Python 3.11 (the `requires-python` floor) + 3.14 (dev target), for every
  push to `main` and every PR. Installs the system libs PySide6's offscreen plugin
  needs (`libegl1 libgl1 libxkbcommon0 libdbus-1-3`); `QT_QPA_PLATFORM=offscreen`
  is already forced in `tests/conftest.py`. **Its first run immediately earned its
  keep** — caught a Linux-only `SIGABRT` double-free where the launch-time backup
  auto-nudge popped a modal from a headless (never-shown) window; fixed by gating
  the automatic modals on `self.isVisible()` in `_on_refresh_done`. *Still open:*
  the macOS/Windows legs of the matrix (started ubuntu-only), and building packaged
  artifacts. This is the status check that branch protection (below) requires on
  every PR.
- [x] 🟡 **CONTRIBUTING.md** — setup (`pip install -e ".[dev]"`), tests
  (`pytest -q`, offscreen note + the Linux Qt libs), the **branch/roadmap discipline
  from CLAUDE.md** (feature branch per unit; close out by updating
  ROADMAP/BUGS/DATA_MODEL/TESTING), the PR flow, and the DCO sign-off. Points
  newcomers at the **architecture map** — CLAUDE.md (module map), DATA_MODEL.md, and
  DONE.md (how/why each subsystem shipped).
- [x] 🟡 **Issue + PR templates** — `.github/ISSUE_TEMPLATE/` bug form (asks OS /
  version / **telescope model** — Seestar S30/S50, Dwarf — feeding §3/§5) + feature
  form + chooser `config.yml` (Discord/Reddit contact links stubbed for when §6
  lands); `PULL_REQUEST_TEMPLATE.md` checklist (tests pass, engine stays Qt-free,
  preview-then-confirm, docs updated, DCO sign-off).
- [x] 🟡 **Branch protection on `main`** — live: PRs required (no direct pushes) +
  both CI checks (`test (3.11)` / `test (3.14)`) must pass before merge. Reviews set
  to **0** for now (a solo maintainer can't approve their own PR — bump to 1 when
  other contributors arrive) and `enforce_admins` **off** (owner can bypass in a
  pinch); `strict` off (no forced rebase-before-merge). Matches the "never commit
  feature work directly to `main`" rule and keeps an outside PR from landing red.
- [x] 🟡 **Contribution-license stance** — decided: **inbound = outbound (Apache-2.0)
  + DCO**. CONTRIBUTING states contributions are under the project license and
  documents the `git commit -s` `Signed-off-by` flow (full DCO 1.1 text included);
  the PR template has a sign-off checkbox. No CLA. *Follow-on when public:* add a DCO
  check bot to enforce sign-off on PRs.
- [x] 🟡 **CODE_OF_CONDUCT.md** — Contributor Covenant 2.1, enforcement contact
  `mjm1138@gmail.com`.
- [ ] 🟢 **Contributor onboarding depth** *(matures as contributors actually
  arrive)* — a few `good-first-issue`-labeled issues, a stated review-turnaround
  expectation, and a note on how forked-PR CI runs. Nice-to-have for the beta
  itself; important once someone offers to help.
- [x] 🟢 **SECURITY.md** — private reporting (GitHub advisory or email), scoped to
  the small local-app surface + the optional Simbad network use.
- [x] 🟢 **CHANGELOG.md** — Keep a Changelog format, `Unreleased` seeded; points at
  DONE.md for pre-`0.1.0` engineering history.
- [ ] 🟢 **User-facing README rewrite** — today's README is developer-oriented
  (venv/pytest). The public repo needs a *user* README (what it is, screenshots,
  download link) with the dev instructions moved down or into CONTRIBUTING.

## 8. User documentation 🟡

*README + CLAUDE.md are for contributors. The persona needs task docs.*

- [ ] 🟡 **Getting-started guide** — install → connect Seestar → first import →
  set a goal → process your first object. With screenshots.
- [ ] 🟢 **Processing-prep walkthrough** — the Siril hand-off is the least
  self-evident feature; a short "what M110 does vs. what you do in Siril" doc.
- [ ] 🟢 **FAQ / troubleshooting** — "Seestar not detected," "where's my data,"
  "is it safe / will it touch my originals" (answer: no — lead with that).

## 9. Legal / licensing / privacy 🟡

- [~] 🟡 **Bundled-asset attribution complete** — JetBrains Mono (OFL) is noted;
  confirm NOTICE covers the logo, any icons, and GeoNames/other data *before* it
  ships (glow-map data is item-1 future, so not a beta blocker yet).
- [ ] 🟡 **Network-use disclosure** — the online Simbad lookups reach the internet;
  say so plainly (and it's optional/off by default — good story, just state it).
- [ ] 🟢 **Trademark care** — "Seestar" is ZWO's; the naming already avoids it in
  the product name. Keep marketing copy to "works with Seestar," not implying
  endorsement.

## 10. Data-safety guarantees (mostly done — verify) 🟡

*The persona's captures are irreplaceable. The architecture is already careful;
this is a verification pass, not new work.*

- [~] 🟡 **"Never touches your originals"** — true by design (ingest is
  preview-then-confirm, copy-not-move from Seestar). **Verify and then say it
  loudly** in onboarding — it's a top adoption objection.
- [~] 🟡 **Migration safety across beta builds** — `migrate.py` is idempotent /
  never-destructive on the store layout. Confirm the upgrade path holds when a
  beta user updates from build N to N+1 with real data.
- [ ] 🟢 **Store-version forward-compat** — decide what happens if an *older* M110
  opens a *newer* store (user downgrades): warn, don't corrupt.

---

## Suggested beta gate (minimum viable)

A defensible "invite strangers" bar is the 🔴 items only:

1. **§1** a notarized macOS `.dmg` + a Linux **AppImage** + an **unsigned** Windows
   installer (with Run-anyway docs) + a real version. All three ship; macOS leads.
2. **§2** a **Windows** smoke pass (never run) + a **deeper x86_64 Linux** pass on
   the packaged AppImage (only ARM/Pi-from-source confirmed so far).
3. **§3** Seestar ingest confirmed on at least the common S30/S50 layouts (or a
   rock-solid manual-folder fallback + 2–3 real tester dumps).
4. **§5** global error handling + an in-app feedback/report path.
5. **§6** public repo + a landing/download page + the Discord/Reddit feedback
   venue wired up. Flipping the repo public pulls in the **§7 contribution
   guardrails** (branch protection, CONTRIBUTING, issue/PR templates, the
   contribution-license stance) — tagged 🟡 but effectively gating on *this* step,
   since a public repo takes issues and PRs from day one.

🟡 items make the beta *good* (onboarding, docs, CI) — except the §7
contribution-readiness ones noted above, which ride along with going public; 🟢
items can trail the first invites. Realistically **§1 + §2 for Windows is the long pole** — it's the
one platform never run, so packaging *and* first-time QE land together there.
Linux is de-risked (Pi-5/ARM smoke pass), leaving mainly the x86_64 AppImage
confirmation. Windows signing is explicitly **out of scope for the beta**
(unsigned + docs; revisit on uptake), so it's no longer an open decision.

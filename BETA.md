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

macOS is the strong platform (where dev happens) and is now **fully shipped** — a
signed, notarized `.dmg` that installs Gatekeeper-clean on a fresh VM. Track **(1) a
real double-click installer** is largely closed: the macOS DMG ships, and the Linux
**AppImage** + unsigned **Windows** installer are scaffolded and build automatically
in CI (`release.yml`) on the first version tag. That leaves track **(2)** as the real
remaining gap: **Linux is only smoke-confirmed** (from source on a Raspberry Pi 5,
ARM64 — UI fine, Seestar import works, shallow), and **Windows has never been run at
all**. So the open risk is no longer packaging but **first-run QE on real x86_64
Linux + Windows, and Seestar ingest on models beyond Mike's own** — best surfaced by
the packaged builds (once tagged) and the first testers.

---

## 1. Packaging & distribution 🔴

*Today the only way to run M110 is `pip install -e ".[dev]"`. That disqualifies
the target persona outright. Nothing here is in ROADMAP/BUGS beyond a one-line
"future" note.*

*Build order follows priority: **macOS → Linux → Windows** — but all three ship
for the beta (Windows just ships unsigned).*

- [x] 🔴 **macOS `.app` bundle** *(lead platform)* — **PyInstaller** pipeline in
  `packaging/macos/` (spec + entry shim + `.icns` gen + build script). Bundle id
  **`space.m110.M110`**, `Info.plist` with `CFBundleName=M110` (the durable fix for
  the NSBundle app/dock-name stopgap) + dark-mode + version from
  `importlib.metadata`. Builds + launches; local astropy hook override needed
  (contrib hook's blanket `collect_submodules` chokes on matplotlib-requiring
  `wcsaxes`).
- [x] 🔴 **macOS notarization + Developer-ID signing** — **done, produced a real
  signed+notarized build.** `sign_notarize.sh` does inside-out Developer-ID signing
  (not `--deep`), hardened runtime + `entitlements.plist`, `notarytool` submit,
  staple. Two gotchas hit + fixed: (1) needs a **Developer ID Application** cert
  under the *paid* team (`8N7DP84NGU`), not the free-tier **Apple Development** cert;
  (2) `entitlements.plist` must be **comment-free** — codesign's AMFI parser rejects
  XML comments (`AMFIUnserializeXML: syntax error`). One-time setup (cert +
  `notarytool store-credentials`) in `packaging/macos/README.md`.
- [x] 🔴 **`.dmg` installer** (drag-to-Applications) — `make_dmg.sh` (hdiutil,
  `/Applications` symlink, version-stamped name). **Produced `M110-0.1.0.dmg`; it
  installs and runs.** *(Still worth the §2 fresh-machine test on a Mac without the
  dev cert/tools — notarization should make Gatekeeper pass anywhere, but confirm.)*
- [~] 🔴 **Linux package** *(close second)* — **AppImage** scaffold in
  `packaging/linux/` (onedir PyInstaller spec + `build_appimage.sh`: onedir →
  AppDir with AppRun/`.desktop`/icon → `appimagetool`). Shares the entry shim +
  astropy hook via `packaging/common/`. **Build pending a Linux host** — PyInstaller
  can't cross-compile, so it must run on x86_64 Linux (build on Ubuntu 22.04 LTS for
  a low glibc floor); that packaged-AppImage run is also the §2 acceptance test.
  Flatpak still a follow-on. Watch: `libfuse2` on the user's box, `libxcb-cursor0`
  on newer distros.
- [~] 🔴 **Windows build + installer** — scaffold in `packaging/windows/`:
  onedir PyInstaller spec + `make_ico.py` (Pillow → `M110.ico`) + Inno Setup
  `M110.iss` (per-user install, stable AppId, Start-Menu/desktop shortcuts) +
  `build_windows.ps1` orchestrator. Shares `packaging/common/`. **Build pending a
  Windows host** — PyInstaller can't cross-compile + Inno Setup is Windows-only;
  needs Inno Setup 6.3+. Ships unsigned (supported-not-lead platform).
- [~] 🟡 **Windows unsigned-launch docs** — the SmartScreen "More info → Run
  anyway" flow is documented in `packaging/windows/README.md`; still needs to land
  on the **download page / announce post** (§6). Unsigned binaries trip
  **SmartScreen** ("Windows protected your PC"); for the beta this is **accepted**.
  **Revisit an OV/EV code-signing cert only on uptake** — don't buy one on spec.
  (EV clears SmartScreen instantly but is pricey + hardware-token; OV builds
  reputation over time — a later decision.)
- [ ] 🟢 **Homebrew cask** (`brew install --cask m110`) / **winget** manifest —
  nice for the dev-y tail; not a substitute for the double-click installers.
- [x] 🔴 **Real version number + scheme** — bumped to **`0.1.0b1`** (PEP 440
  canonical spelling of `0.1.0-beta.1`; setuptools normalizes the hyphenated form to
  this anyway, so the source string matches what the About dialog shows) in both
  `pyproject.toml` and `m110/__init__.py`. `about_dialog.app_version()` reads it via
  `importlib.metadata`. Bump both on each release; cut the `CHANGELOG.md`
  `[Unreleased]` section to a dated version when tagging a release.
- [~] 🟡 **Update story** — the GitHub **Releases page** (cut by `release.yml` on
  each tag) + the landing page's download buttons pointing at `releases/latest` give
  beta users a canonical "latest build" pointer. An in-app "you're on vN / check for
  updates" nudge is still a nice-to-have; auto-update is a bonus, not required.

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
- [~] 🟡 **Fresh-machine install test** — **macOS confirmed**: the notarized `.dmg`
  installed and ran on a clean macOS VM with no dev tools, Gatekeeper-clean
  (`spctl` → `source=Notarized Developer ID`, verified with the quarantine flag set).
  Linux AppImage + Windows installer still need the same clean-machine pass once the
  first tag builds them.

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

- [ ] 🔴 **Public GitHub repo** — **the last gating step; doing it at launch.** All
  the §7 contribution guardrails it depends on (branch protection, CONTRIBUTING,
  issue/PR templates, contribution-license stance, COC/SECURITY) are **already in
  place**, so flipping `mjm1138/m110` public is now safe to do on launch day. (ROADMAP
  notes the `m110` org name is taken → `m110app`/`messier110` if a rename is wanted;
  not required to launch under the personal account.)
- [x] 🔴 **Landing page / website** — **live at [m110.space](https://m110.space)**
  (`m110.app` was taken by an unrelated betting site). A self-contained, theme-aware
  one-pager in `site/` (hero, "never touches your originals" promise, feature grid,
  real dark-mode screenshots, per-OS download cards, ZWO disclaimer) hosted on
  **Cloudflare Pages** (Registrar + DNS + Pages all in Cloudflare; auto-HTTPS,
  www→apex redirect, HSTS, TLS 1.2 floor; auto-deploys from `main`). Bundle id
  `space.m110.M110` assumes keeping this domain long-term.
- [~] 🔴 **Download/Releases page** — the landing page's per-OS download buttons
  point at `releases/latest`; they light up once the repo is public + the first tag
  cuts a Release. `release.yml` (see §1) builds the Linux/Windows artifacts and
  creates the prerelease Release on tag; the notarized macOS DMG is uploaded by hand.
- [~] 🟡 **Screenshots / a short demo GIF or video** — **three real dark-mode
  screenshots** (Library grid, object detail with the Orion mosaic + notes, Summary
  dashboard) are live on the landing page, rendered offscreen straight from the app.
  A short demo GIF/video is still a nice-to-have; the README hero shot is a small
  follow-on.
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

- [x] 🟡 **CI** — two workflows. **`ci.yml`** runs `pytest -q` on **ubuntu-latest**
  across Python 3.11 (floor) + 3.14 (dev target) for every push to `main` and every
  PR (installs the Qt libs the offscreen plugin needs; `QT_QPA_PLATFORM=offscreen`
  forced in `tests/conftest.py`) — it's the check branch protection requires. Its
  first run earned its keep: caught a Linux-only `SIGABRT` double-free (launch-time
  backup nudge popping a modal from a headless window), fixed by gating the automatic
  modals on `self.isVisible()`. **`release.yml`** builds the Linux AppImage +
  Windows installer on GitHub's free x86_64 runners on a version tag and attaches
  them to a prerelease Release (no secrets — both ship unsigned). *Later:* a macOS-in-CI
  job (needs the Developer ID cert + notary creds as secrets); the test matrix is
  ubuntu-only for now.
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
- [x] 🟢 **User-facing README rewrite** — done: leads for the user (what it is →
  download links to m110.space + Releases → features → the "never touches your
  originals" promise → per-OS notes), dev setup condensed and pointed at
  CONTRIBUTING.md, "Lightroom" dropped from the public copy, ZWO disclaimer added.
  *(A README hero screenshot is a small follow-on.)*

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
- [x] 🟢 **Trademark care** — the landing page + README carry a ZWO/"Seestar"
  disclaimer ("works *with* your Seestar; independent, not affiliated/endorsed"), and
  the **"Lightroom" comparison was removed from all public copy** (Adobe mark; kept
  only as an internal north-star in CLAUDE.md). Marketing copy stays "works with
  Seestar," no implied endorsement.

## 10. Data-safety guarantees (mostly done — verify) 🟡

*The persona's captures are irreplaceable. The architecture is already careful;
this is a verification pass, not new work.*

- [x] 🟡 **"Never touches your originals"** — true by design (ingest is
  preview-then-confirm, copy-not-move from Seestar) and now **said loudly**: a
  dedicated promise banner on the landing page + a callout in the README. (Verified
  by the preview-then-confirm architecture; §3 real-device testing still validates it
  on other Seestar dumps.)
- [~] 🟡 **Migration safety across beta builds** — `migrate.py` is idempotent /
  never-destructive on the store layout. Confirm the upgrade path holds when a
  beta user updates from build N to N+1 with real data.
- [ ] 🟢 **Store-version forward-compat** — decide what happens if an *older* M110
  opens a *newer* store (user downgrades): warn, don't corrupt.

---

## Suggested beta gate (minimum viable)

A defensible "invite strangers" bar is the 🔴 items only. **Status as of launch-eve:**

1. **§1 — essentially done.** Notarized macOS `.dmg` **shipped**; the Linux AppImage
   + unsigned Windows installer build in CI (`release.yml`) on the first tag; real
   version (`0.1.0b1`) done. ✅ (build artifacts materialize when the tag fires)
2. **§2 — partial.** macOS clean-VM pass done. **Windows** smoke (never run) + a
   deeper **x86_64 Linux** pass still pending — they land when the first tag produces
   the installers to test.
3. **§3 — open.** Seestar ingest confirmed on at least the common S30/S50 layouts
   (or a rock-solid manual-folder fallback + 2–3 real tester dumps).
4. **§5 — done.** Global error handling + in-app report path shipped.
5. **§6 — nearly done.** Landing page live at **m110.space** with real screenshots;
   the §7 contribution guardrails are all in place. **Remaining: flip the repo
   public, tag the release (→ download page lights up), and wire the Discord feedback
   venue** — the launch-day steps.

**The remaining path to launch is short:** make the repo public → tag
`v0.1.0-beta.1` (fires `release.yml`, cuts the Release, lights up the downloads;
upload the macOS DMG by hand) → wire the Discord venue → announce. The true
open risk is no longer packaging but **§2/§3 first-run QE on real Windows + Linux +
other Seestar models** — best surfaced by the first testers. Windows signing stays
**out of scope** (unsigned + docs; revisit on uptake).

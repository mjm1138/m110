# Changelog

All notable user-facing changes to M110 are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/) once it
reaches 1.0. Until then (pre-`0.1.0`), the detailed engineering history of how and
why each subsystem shipped lives in [`DONE.md`](DONE.md); this file summarizes the
changes a **user** would notice, per release.

## [Unreleased]

### Added
- Continuous integration: GitHub Actions runs the test suite on every push and
  pull request (Python 3.11 + 3.14), with branch protection requiring it to pass
  before merge.
- Contributor documentation: `CONTRIBUTING.md`, a Code of Conduct, a security
  policy, and issue / pull-request templates.

### Fixed
- No longer crashes on Linux when a background library sync completes while the
  main window is not visible (a stray backup-nudge dialog could abort the app).

---

<!--
Release entries look like:

## [0.1.0-beta.1] - 2026-07-XX
### Added / Changed / Fixed / Removed
- ...

Keep the newest release at the top, under [Unreleased]. Move Unreleased items
into a dated, versioned section when you cut a release.
-->

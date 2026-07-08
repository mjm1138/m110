# Contributing to M110

Thanks for your interest in M110 — a cross-platform desktop app for managing a
smart-telescope deep-sky imaging collection ("Lightroom for smart telescopes").
This guide covers how to set up, make a change, and get it merged.

M110 is **Apache-2.0** licensed. By contributing you agree your contributions are
licensed under the same terms — see [Developer Certificate of Origin](#developer-certificate-of-origin-dco)
below.

---

## Development setup

Requires **Python 3.11+** (CI runs 3.11 and 3.14).

```bash
git clone https://github.com/mjm1138/m110.git
cd m110
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"             # engine + PySide6 UI + pytest/pytest-qt
m110                                # run the app  (== python -m m110.ui.main)
```

The app owns its own data store (default `~/Documents/M110`), created and seeded
on first launch. It does **not** require any other project or external service to
run — Simbad lookups are optional (`pip install -e ".[dev,online]"`) and off by
default.

### Running the tests

```bash
pytest -q                           # the whole suite (fixture-based; safe on temp roots)
pytest -q tests/test_ingest.py      # one file
```

The UI is driven **offscreen** with `pytest-qt` (`QT_QPA_PLATFORM=offscreen` is
forced in `tests/conftest.py`), so tests run headless — no display needed, and
they never read or write your real data store. Add tests alongside any engine
change; for UI work, prefer extracting logic into the (Qt-free) engine and
testing that. Rendering has golden-image tests under `tests/goldens/` (refresh
intentionally with `M110_UPDATE_GOLDENS=1`).

On Linux, the offscreen Qt plugin needs a few system libraries (mirroring CI):

```bash
sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3
```

---

## How we work

A few conventions keep the project maintainable — they mirror the maintainer
workflow documented in [`CLAUDE.md`](CLAUDE.md):

1. **Work on a feature branch.** Branch off `main` (`feature/<short-name>`); never
   commit feature work directly to `main`. `main` is protected — changes land via
   pull request with green CI.
2. **Keep the engine Qt-free.** No `PySide6` imports in `m110/*.py` — only in
   `m110/ui/`. This keeps the engine headless and testable.
3. **Never write into the content tree without explicit confirmation.** Ingest is
   strictly preview-then-confirm: read-only `scan_*_plan()` returns a plan;
   `apply_ops()` (the only writer) runs only after the user confirms. Mirror this
   for any new write feature.
4. **Slow operations run off the UI thread** on a `QThread` worker behind a modal
   progress dialog with a working Cancel. A synchronous scan/copy freezes the
   window.
5. **Close out the change with the code.** A PR should land with `pytest -q` green
   **and** the relevant docs updated in the same change:
   - [`ROADMAP.md`](ROADMAP.md) / [`BUGS.md`](BUGS.md) — mark what landed.
   - [`DATA_MODEL.md`](DATA_MODEL.md) — **required** for any change to the on-disk
     layout, a file format, a derived-JSON shape, or `.store_version` (on-disk
     changes also bump `.store_version` and add an idempotent, never-destructive
     `migrate.py` step).
   - [`TESTING.md`](TESTING.md) — when the change touches the manual-test surface.

### Finding your way around

You can orient without a maintainer walkthrough:

- [`CLAUDE.md`](CLAUDE.md) — the module map (what every engine + UI module does)
  and the conventions above, in full.
- [`DATA_MODEL.md`](DATA_MODEL.md) — the authoritative on-disk data model.
- [`DONE.md`](DONE.md) — how and why each subsystem shipped. Skim the relevant
  entry before extending or fixing an existing subsystem; it's often the missing
  context behind "why is it built this way?"

---

## Submitting a pull request

1. Fork and branch (`feature/<short-name>`).
2. Make your change, add/adjust tests, and run `pytest -q` locally.
3. Update the docs noted above.
4. Sign your commits (`git commit -s`, see DCO below) and open a PR against `main`.
5. CI (`pytest -q` on Python 3.11 + 3.14) must pass before merge.

The [pull request template](.github/PULL_REQUEST_TEMPLATE.md) has the checklist.

---

## Developer Certificate of Origin (DCO)

M110 uses the [Developer Certificate of Origin](https://developercertificate.org/)
instead of a CLA. It's a lightweight, per-commit attestation that you wrote (or
otherwise have the right to submit) the code, and that it may be distributed under
the project's Apache-2.0 license. **Inbound contributions are under the same
license as the project (inbound = outbound).**

To attest, add a `Signed-off-by` line to each commit — `git commit -s` does this
automatically using your configured `user.name` / `user.email`:

```
Signed-off-by: Jane Developer <jane@example.com>
```

Use your real name and a valid email. That's it — no separate paperwork.

<details>
<summary>Full DCO 1.1 text</summary>

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

</details>

---

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/mjm1138/m110/issues/new/choose). For
bugs, the more of OS / M110 version / telescope model (Seestar S30/S50, etc.) you
can include, the faster it's triageable. You can also file a report from inside the
app: **Help → Report a problem…** pre-fills the environment details for you.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to uphold it.

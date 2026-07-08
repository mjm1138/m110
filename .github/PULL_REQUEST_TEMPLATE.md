<!--
Thanks for contributing to M110! Please fill in the summary and run through the
checklist. See CONTRIBUTING.md for the full workflow.
-->

## Summary

<!-- What does this change do, and why? Link any related issue (e.g. "Closes #123"). -->

## Checklist

- [ ] Branched off `main` (`feature/<short-name>`), not committing directly to `main`.
- [ ] `pytest -q` passes locally; added or updated tests for the change.
- [ ] Engine code stays **Qt-free** (no `PySide6` imports in `m110/*.py`).
- [ ] Any write into the content tree stays **preview-then-confirm**.
- [ ] Docs updated in the same change as needed:
  - [ ] `ROADMAP.md` / `BUGS.md` (what landed)
  - [ ] `DATA_MODEL.md` + `.store_version` bump + `migrate.py` step (**if** the
        on-disk layout, a file format, a derived-JSON shape, or the store version changed)
  - [ ] `TESTING.md` (if the manual-test surface changed)
  - [ ] `CHANGELOG.md` (`Unreleased`, if user-facing)
- [ ] Commits are signed off (`git commit -s` — see the DCO section in CONTRIBUTING.md).

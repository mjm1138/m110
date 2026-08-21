"""Processing-workflow registry + preference-driven auto-prep.

A *workflow* prepares a captured target for an external stacking app. Siril is
implemented (delegates to `siril.autoprep`); the others are placeholders shown
disabled in Preferences until we have their folder-layout/config specs.

Auto-prep runs automatically after ingest for the workflows the user enabled in
the "Prepare objects for processing in:" preference — so initial prep "just
happens" with no manual step. Qt-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import astrowizard, config, siril

SETTING_KEY = "processing_workflows"
DEFAULT_WORKFLOWS = ["siril", "astrowizard"]

#: Ids the workflow setting could name *before* it became a map. A legacy saved
#: list enumerated only the enabled ones, so absence meant "off" — but only for a
#: workflow that was actually on offer at the time. A workflow added later is
#: **unanswered**, not declined, and must take its default instead of silently
#: reading as switched off. (AstroWizard is the first case: a user who saved
#: `["siril"]` before it existed never chose to turn it off, and reading that as
#: a decision would make Send-to/Import vanish on upgrade.)
LEGACY_SETTING_IDS = frozenset({"siril", "pixinsight", "dss", "app"})

SETTING_ARCHIVE_KEEP = "processing_archive_keep"
#: How many archived runs to keep per working folder. 0 = keep everything.
#: Three is enough to compare against the previous couple of attempts while
#: bounding growth: measured on a real library, archived runs reached 42 GB, and
#: they only ever accumulate — nothing regenerates or replaces them.
DEFAULT_ARCHIVE_KEEP = 3


@dataclass(frozen=True)
class Workflow:
    id: str
    label: str
    available: bool                       # False → shown disabled ("soon")
    autoprep: Callable | None = None      # (targets, should_cancel=None) -> dict
    prune_rejected: Callable | None = None  # (target) -> dict
    #: The module owning this workflow's *return* leg — `scan_finished`,
    #: `apply_import`, `has_unimported_output`, `working_dirs`. Separate from
    #: `autoprep` because the two halves are independent: Siril has both, while
    #: AstroWizard has no prepare step at all (`m110-stack --handoff` is what
    #: hands work in) and exists purely to be imported back from.
    importer: object | None = None


WORKFLOWS = [
    Workflow("siril", "Siril", True, siril.autoprep, siril.prune_rejected,
             importer=siril),
    Workflow("astrowizard", "AstroWizard", True, importer=astrowizard),
    Workflow("pixinsight", "PixInsight", False),
    Workflow("dss", "DeepSkyStacker", False),
    Workflow("app", "Astro Pixel Processor", False),
]


def importers() -> list:
    """Registered workflows that can import finished work back."""
    return [w for w in WORKFLOWS if w.available and w.importer is not None]


def workflows_with_output(target: str) -> list:
    """Which workflows have finished work waiting for this capture target.

    The question the Processing page and the detail pane both need now that there
    is more than one: a single `ready_for_import` boolean cannot say *which* tool
    is holding something."""
    return [w for w in importers() if w.importer.has_unimported_output(target)]
WORKFLOWS_BY_ID = {w.id: w for w in WORKFLOWS}


def enabled_workflow_ids() -> list[str]:
    """Workflow ids the user has enabled.

    Stored as a `{id: bool}` map so an id the user has never been asked about is
    distinguishable from one they turned off — see `LEGACY_SETTING_IDS`. A legacy
    list is read forward without being rewritten, so downgrading is harmless."""
    val = config.get_setting(SETTING_KEY, None)
    if isinstance(val, dict):
        return [w.id for w in WORKFLOWS
                if val.get(w.id, w.id in DEFAULT_WORKFLOWS)]
    if isinstance(val, list):
        return [w.id for w in WORKFLOWS
                if ((w.id in val) if w.id in LEGACY_SETTING_IDS
                    else (w.id in DEFAULT_WORKFLOWS))]
    return list(DEFAULT_WORKFLOWS)


def set_enabled_workflows(ids) -> None:
    """Persist the enabled set as an explicit map over every known workflow, so
    a later-added workflow can tell 'unanswered' from 'declined'."""
    ids = set(ids)
    config.save_setting(SETTING_KEY, {w.id: (w.id in ids) for w in WORKFLOWS})


def archive_keep() -> int:
    """How many archived runs to keep per working folder (0 = keep all)."""
    val = config.get_setting(SETTING_ARCHIVE_KEEP, DEFAULT_ARCHIVE_KEEP)
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return DEFAULT_ARCHIVE_KEEP


def set_archive_keep(n: int) -> None:
    config.save_setting(SETTING_ARCHIVE_KEEP, max(0, int(n)))


def run_autoprep(targets, should_cancel=None, only_missing: bool = False) -> dict:
    """Run auto-prep for every enabled + available workflow. No-op if none.

    `only_missing=True` creates only sandboxes that don't exist yet (used by the
    refresh-time backfill — never rewrites an existing working folder)."""
    results = {}
    for wid in enabled_workflow_ids():
        w = WORKFLOWS_BY_ID.get(wid)
        if w and w.available and w.autoprep:
            results[wid] = w.autoprep(targets, should_cancel=should_cancel,
                                      only_missing=only_missing)
    return results


def _store_targets() -> list[str]:
    """Capture targets in the store that have raw light frames."""
    images = config.IMAGES_DIR
    if not images.is_dir():
        return []
    out = []
    for d in sorted(images.iterdir()):
        lights = d / "lights"
        if d.is_dir() and lights.is_dir() and any(
                f.suffix.lower() in config.FIT_EXTS for f in lights.iterdir() if f.is_file()):
            out.append(d.name)
    return out


def prepare_missing(should_cancel=None) -> dict:
    """Create working folders for store targets that lack one (per the enabled
    workflows) — the refresh-time / on-demand backfill. Missing-only, so it never
    touches an existing sandbox. Returns the per-workflow autoprep summary."""
    return run_autoprep(_store_targets(), should_cancel=should_cancel,
                        only_missing=True)


def _rejected_targets() -> list[str]:
    """Capture targets that have a ``rejected/`` tier — the only ones a prune can
    affect, so the common store (nobody has rejected anything) costs one listdir."""
    images = config.IMAGES_DIR
    if not images.is_dir():
        return []
    return sorted(d.name for d in images.iterdir()
                  if d.is_dir() and (d / "rejected").is_dir())


def reconcile_rejected(should_cancel=None) -> dict:
    """Reconcile each target's working folders with its ``rejected/`` tier (#110) —
    the refresh-time counterpart to `prepare_missing`.

    Kept *separate* from `prepare_missing` deliberately: that function's invariant is
    "missing-only, never touches an existing sandbox", and this one exists precisely
    to touch an existing sandbox (dropping the hardlinks for subs excluded after prep).
    Two functions keeps that invariant a true statement instead of one with an
    exception buried in it."""
    results = {}
    targets = _rejected_targets()
    for wid in enabled_workflow_ids():
        w = WORKFLOWS_BY_ID.get(wid)
        if not (w and w.available and w.prune_rejected):
            continue
        pruned = orphans = 0
        for target in targets:
            if should_cancel and should_cancel():
                break
            r = w.prune_rejected(target)
            pruned += r.get("pruned", 0)
            orphans += r.get("orphans", 0)
        results[wid] = {"pruned": pruned, "orphans": orphans}
    return results

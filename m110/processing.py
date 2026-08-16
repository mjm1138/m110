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

from . import config, siril

SETTING_KEY = "processing_workflows"
DEFAULT_WORKFLOWS = ["siril"]


@dataclass(frozen=True)
class Workflow:
    id: str
    label: str
    available: bool                       # False → shown disabled ("soon")
    autoprep: Callable | None = None      # (targets, should_cancel=None) -> dict
    prune_rejected: Callable | None = None  # (target) -> dict


WORKFLOWS = [
    Workflow("siril", "Siril", True, siril.autoprep, siril.prune_rejected),
    Workflow("pixinsight", "PixInsight", False),
    Workflow("dss", "DeepSkyStacker", False),
    Workflow("app", "Astro Pixel Processor", False),
]
WORKFLOWS_BY_ID = {w.id: w for w in WORKFLOWS}


def enabled_workflow_ids() -> list[str]:
    """Workflow ids the user has enabled (default: Siril)."""
    val = config.get_setting(SETTING_KEY, None)
    return list(val) if isinstance(val, list) else list(DEFAULT_WORKFLOWS)


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

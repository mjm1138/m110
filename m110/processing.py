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


WORKFLOWS = [
    Workflow("siril", "Siril", True, siril.autoprep),
    Workflow("pixinsight", "PixInsight", False),
    Workflow("dss", "DeepSkyStacker", False),
    Workflow("app", "Astro Pixel Processor", False),
]
WORKFLOWS_BY_ID = {w.id: w for w in WORKFLOWS}


def enabled_workflow_ids() -> list[str]:
    """Workflow ids the user has enabled (default: Siril)."""
    val = config.get_setting(SETTING_KEY, None)
    return list(val) if isinstance(val, list) else list(DEFAULT_WORKFLOWS)


def run_autoprep(targets, should_cancel=None) -> dict:
    """Run auto-prep for every enabled + available workflow. No-op if none."""
    results = {}
    for wid in enabled_workflow_ids():
        w = WORKFLOWS_BY_ID.get(wid)
        if w and w.available and w.autoprep:
            results[wid] = w.autoprep(targets, should_cancel=should_cancel)
    return results

"""Publish options — the user's selection of *what* and *where* to publish.

Qt-free. A `PublishOptions` is assembled by the UI (or a test) and handed to a
publisher's `render`. Section ids name the pages/features that may be included.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Section ids the user can toggle. "library" gates the full catalog table on the
# landing page (off → only captured objects); the rest gate their own page or,
# for "galleries"/"journal", a per-object-page feature.
ALL_SECTIONS = ("summary", "library", "sessions", "processing", "journal", "galleries")
DEFAULT_SECTIONS = set(ALL_SECTIONS)

DEFAULT_SITE_TITLE = "My Astrophotography"


@dataclass
class PublishOptions:
    output_dir: Path
    sections: set[str] = field(default_factory=lambda: set(DEFAULT_SECTIONS))
    exclude_journals: bool = False        # global privacy: omit all journal notes
    site_title: str = DEFAULT_SITE_TITLE
    gallery_level: str = "finished"       # "finished" | "device-stacks" | "all"
    github_repo: str = ""                 # owner/repo or git URL (github-pages target)
    github_branch: str = "gh-pages"

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        # Normalise to the known section vocabulary (ignore stray ids).
        self.sections = {s for s in self.sections if s in ALL_SECTIONS}
        from .images import GALLERY_LEVELS
        if self.gallery_level not in GALLERY_LEVELS:
            self.gallery_level = "finished"

    def has(self, section: str) -> bool:
        return section in self.sections

"""Selection / privacy filtering — the testable core of *what* gets published.

Default-publish, opt-out: every Library object is published unless its entry
carries `publish = false`. Journals (notes) are additionally gated by a global
`exclude_journals` switch and a per-object `private` journal frontmatter flag.
Qt-free; no rendering or I/O of its own beyond reading the journal frontmatter.
"""
from __future__ import annotations

from .. import objects


def is_publishable(entry: dict) -> bool:
    """A Library entry is published unless it opts out with `publish = false`."""
    return entry.get("publish", True) is not False


def publishable_slugs(library: dict[str, dict]) -> set[str]:
    """Slugs whose Library entry is not opted out of publishing."""
    return {slug for slug, e in library.items() if is_publishable(e)}


def journal_visible(slug: str, options, frontmatter: dict | None = None) -> bool:
    """Whether an object's journal notes should appear in the published site.

    False if journals are globally excluded, the "journal" section is off, or the
    object's journal frontmatter marks it `private: true`. `frontmatter` may be
    passed to avoid a re-read when the caller already has it.
    """
    if options.exclude_journals or not options.has("journal"):
        return False
    fm = frontmatter if frontmatter is not None else objects.read_journal(slug)[0]
    private = str(fm.get("private", "")).strip().lower()
    return private not in ("true", "1", "yes")


def filter_sessions(sessions: list[dict], slugs: set[str]) -> list[dict]:
    """Keep only sessions touching at least one publishable slug."""
    return [s for s in sessions if any(sl in slugs for sl in s.get("slugs", []))]


def filter_processing(processing: dict, slugs: set[str]) -> dict:
    """Restrict the processing rollup to folders feeding a publishable slug,
    recomputing the status counts so nothing excluded leaks into the totals."""
    folders = {f: v for f, v in processing.get("folders", {}).items()
               if any(sl in slugs for sl in v.get("slugs", []))}
    queue = [q for q in processing.get("queue", [])
             if any(sl in slugs for sl in q.get("slugs", []))]
    counts = {st: sum(1 for v in folders.values() if v.get("status") == st)
              for st in ("out_of_date", "not_processed", "up_to_date", "dismissed")}
    out = dict(processing)
    out["folders"], out["queue"], out["counts"] = folders, queue, counts
    return out

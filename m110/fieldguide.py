"""Session-plan **field guide** — render tonight's plan to a printable Markdown
document, and manage the saved guides under the store's ``Plans/`` axis (Qt-free).

A field guide is a human-readable observing plan: the night's dark window + moon,
then the ordered target list (best time = transit, altitude, the up-window, moon
separation, filter, and any notes). It's plain Markdown so the app renders it with
``QTextBrowser.setMarkdown`` (Qt-native — no dependency) and it prints/shares.

Device-automation formats (SSC / NINA) are deferred; this is the universal,
telescope-agnostic slice.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from . import catalog, config, prioritize


def _hm(t) -> str:
    return t.strftime("%H:%M") if isinstance(t, datetime) else "—"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "plan"


def moon_headline(moon: dict) -> str:
    """One-line moon summary from ``plan_night``'s per-slot moon dict — phase plus
    what it *does* across the night ("sets 23:05"), not a single dusk snapshot
    (BUGS #36). Shared by the field guide and the Planning page."""
    illum = moon.get("illum")
    lit = f"{round(illum * 100)}% lit" if illum is not None else "—"
    alt, set_t, rise_t = moon.get("alt"), moon.get("set_time"), moon.get("rise_time")
    if alt is None:
        return lit
    if alt > 0:
        state = f"up at dusk (+{alt:.0f}°)"
        state += f" · sets {_hm(set_t)}" if set_t else " · up all night"
    else:
        state = "down at dusk"
        state += f" · rises {_hm(rise_t)}" if rise_t else " · down all night"
    return f"{lit} · {state}"


def start_cells(entry: dict) -> tuple[str, str]:
    """``(time, altitude)`` strings for the proposed **start** slot — the startable
    pick under the device ceiling (Phase 3 / #37), falling back to transit for plan
    dicts that predate it. A hard-ceiling target with no startable moment reads
    "—"; a soft-ceiling over-ceiling start is flagged ``^`` (the sky.py notation)."""
    if "start_time" not in entry:                     # pre-Phase-3 plan dict
        return _hm(entry.get("transit_time")), f"{entry.get('transit_alt', 0):.0f}°"
    t, alt = entry.get("start_time"), entry.get("start_alt")
    if t is None:
        return "—", "—"                               # device would refuse every start
    flag = "^" if entry.get("over_ceiling") else ""
    return _hm(t), f"{alt:.0f}°{flag}"


def moon_cell(entry: dict) -> str:
    """The per-target Moon column: separation + impact when the moon is **up** at
    that target's best time, else "—" (separation from a set moon means nothing).
    Degrades to the bare separation for plans that predate the annotation."""
    alt = entry.get("moon_alt_at_best")
    if alt is None:                                   # old plan dict — no gating info
        sep = entry.get("moon_sep_deg")
        return f"{sep:.0f}°" if sep is not None else "—"
    if alt <= 0:
        return "—"
    impact = entry.get("moon_impact")
    sep = entry.get("moon_sep_deg", 0.0)
    return f"{sep:.0f}° · {impact}" if impact else f"{sep:.0f}°"


def render_markdown(site, day: date, plan: dict, *, title: str | None = None) -> str:
    """Render ``plan`` (from ``planning.plan_night``) to a Markdown field guide."""
    try:
        lib = catalog.load_library()
    except Exception:
        lib = {}
    ref = catalog.load_reference()
    dusk, dawn = plan.get("window", (None, None))
    moon = plan.get("moon", {}) or {}
    entries = plan.get("entries", [])

    heading = title or f"Observing plan — {day.isoformat()}"
    lines = [f"# {heading}", ""]
    lines.append(f"**Site:** {site.name}  ")
    if dusk and dawn:
        lines.append(f"**Astro dark:** {_hm(dusk)} – {_hm(dawn)}  ")
    illum = moon.get("illum")
    if illum is not None:
        lines.append(f"**Moon:** {moon_headline(moon)}  ")
    lines.append("")

    schedule = plan.get("schedule") or []
    if not entries and not schedule:
        lines.append("_No targets are up tonight from this site._")
        return "\n".join(lines) + "\n"

    def obj_name(slug):
        entry = lib.get(slug) or ref.get(slug) or {}
        return catalog.object_label(catalog.object_identifiers(slug, entry)) or slug

    if schedule:
        # The sequenced schedule (Phase 4 / #40–41): contiguous, non-overlapping,
        # 10-min-aligned slots — object N+1 starts when object N ends.
        lines.append(f"## Schedule ({len(schedule)} targets)")
        lines.append("")
        lines.append("| # | Object | Start | Duration | Alt | Filter | Moon |")
        lines.append("|---|--------|-------|----------|-----|--------|------|")
        for i, s in enumerate(schedule, 1):
            flag = "^" if s.get("over_ceiling") else ""
            filt = s.get("filter") or prioritize.filter_for_type(
                (lib.get(s["slug"]) or ref.get(s["slug"]) or {}).get("type", ""))
            lines.append(f"| {i} | {obj_name(s['slug'])} | {_hm(s['start'])} | "
                         f"{s['duration_min']} min | {s['alt_start']:.0f}°{flag} | "
                         f"{filt} | {moon_cell(s)} |")
        lines.append("")
        seq_entries = [e for e in entries
                       if e["slug"] in {s["slug"] for s in schedule}] or entries
    else:
        lines.append(f"## Targets ({len(entries)}) — in shooting order")
        lines.append("")
        lines.append("| # | Object | Start | Alt | Up-window | Moon | Filter |")
        lines.append("|---|--------|-------|-----|-----------|------|--------|")
        for i, e in enumerate(entries, 1):
            filt = prioritize.filter_for_type(
                (lib.get(e["slug"]) or ref.get(e["slug"]) or {}).get("type", ""))
            win = f"{_hm(e['up_start'])}–{_hm(e['up_end'])}"
            st, sa = start_cells(e)
            lines.append(f"| {i} | {obj_name(e['slug'])} | {st} | {sa} | {win} | "
                         f"{moon_cell(e)} | {filt} |")
        lines.append("")
        seq_entries = entries
    rows = schedule or entries
    notes = []
    if any((r.get("moon_alt_at_best") or 0) > 0 for r in rows):
        notes.append("**Moon** = separation from the moon at the target's start, "
                     "with its impact (illumination × proximity; narrowband LP is "
                     "largely immune); \"—\" = the moon is below the horizon then — "
                     "no impact.")
    notes.append("**Start** = the best startable time under the device's "
                 "start-altitude ceiling (a capture may climb past it once running).")
    if any(r.get("over_ceiling") for r in rows):
        notes.append("**^** = starts above the ceiling (no lower slot was clear) — "
                     "expect field rotation near the zenith.")
    lines.append(f"<sub>{' '.join(notes)}</sub>")
    lines.append("")

    # Per-target remarks (the library `notes` field), when present. Season labels
    # are intentionally NOT shown here — a season window printed beside a concrete
    # dated recommendation reads as contradictory (review §5e / Phase 4.3).
    detail = []
    for e in seq_entries:
        slug = e["slug"]
        entry = lib.get(slug) or ref.get(slug) or {}
        note = (entry.get("notes") or "").strip()
        if note:
            detail.append(f"- **{obj_name(slug)}** — {note}")
    if detail:
        lines.append("## Notes")
        lines.append("")
        lines.extend(detail)
        lines.append("")

    lines.append(f"<sub>Generated by M110 · {day.isoformat()}</sub>")
    return "\n".join(lines) + "\n"


# ── saved guides under Plans/ ─────────────────────────────────────────────────

def _plans_dir() -> Path:
    d = Path(config.PLANS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(day: date, title: str, markdown: str) -> Path:
    """Write a field guide to ``Plans/<YYYY-MM-DD>_<slug>.md`` (disambiguated if the
    name already exists) and return its path."""
    d = _plans_dir()
    stem = f"{day.isoformat()}_{_slugify(title)}"
    path = d / f"{stem}.md"
    i = 1
    while path.exists():
        path = d / f"{stem}_{i}.md"
        i += 1
    path.write_text(markdown, encoding="utf-8")
    return path


_TITLE_RE = re.compile(r"^#\s+(.*)")


def _title_of(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _TITLE_RE.match(line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return path.stem


def list_guides() -> list[dict]:
    """Saved field guides, newest first: ``[{path, name, date, title}]``. ``date``
    is parsed from the filename prefix when present, else the file mtime date."""
    d = Path(config.PLANS_DIR)
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.md"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", p.name)
        dt = m.group(1) if m else date.fromtimestamp(p.stat().st_mtime).isoformat()
        out.append({"path": p, "name": p.name, "date": dt, "title": _title_of(p)})
    out.sort(key=lambda g: (g["date"], g["name"]), reverse=True)
    return out


def read(path) -> str:
    return Path(path).read_text(encoding="utf-8")

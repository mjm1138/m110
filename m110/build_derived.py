#!/usr/bin/env python3
"""Join catalog + sessions + priorities into derived rollups.

Outputs (under the hidden internal store, config.DERIVED_DIR):
  totals.json     — per-object integration totals & status
  priorities.json — priority list with current progress
  summary.json    — category roll-ups for the dashboard
  processing.json — per-target processing status / queue
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Ported into the M110 engine.
from . import config  # noqa: E402

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Paths resolve dynamically from config (so a changed data root / test
# monkeypatch takes effect without re-import).

DEEP_STACK_MIN = 60  # threshold per CLAUDE.md
PROCESSED_EXTS = (".fit", ".fits", ".tif", ".tiff")
# Hand-finished renders (finished/) are raster exports, not FITS stacks — but
# they're still processed output. An imported library (e.g. the Astronomy
# sibling) often carries only a finished render with no raw Siril stack, and
# must not read as "not processed".
FINISHED_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".fit", ".fits")
SKIP_DIRS = {"M42 copy", "M81 M82 orig", "Template"}


def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_sessions() -> list[dict]:
    sessions = config.SESSIONS_JSONL
    if not sessions.exists():
        return []
    rows = []
    with sessions.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fmt_hm(minutes: float) -> str:
    h = int(minutes // 60)
    m = int(round(minutes - h * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h}:{m:02d}"


def slug_to_priority_id(slug: str, catalog: dict) -> str:
    """Display id for a slug — prefer catalog id, else uppercase slug."""
    return catalog.get(slug, {}).get("id", slug.upper())


def build_totals(catalog: dict, sessions: list[dict]) -> dict:
    """For each captured slug, aggregate sessions and compute status.

    A "captured slug" is any catalog slug that appears in at least one
    session's `slugs` list.
    """
    by_slug: dict[str, dict] = defaultdict(lambda: {
        "frames": 0,
        "integration_min": 0.0,
        "session_count": 0,
        "session_dates": set(),
        "filters": set(),
        "exposures": set(),
        "first_capture": None,
        "last_capture": None,
        "has_pre_new_start": False,
        "session_refs": [],   # indices into sessions list
    })

    # Also track per-object-folder totals (composite frames like M81/M82
    # count once per shared session, but the slug version doubles them).
    folder_totals: dict[str, dict] = defaultdict(lambda: {
        "frames": 0,
        "integration_min": 0.0,
        "session_dates": set(),
        "filters": set(),
        "exposures": set(),
        "slugs": set(),
        "has_pre_new_start": False,
    })

    for i, s in enumerate(sessions):
        for slug in s.get("slugs", []):
            t = by_slug[slug]
            t["frames"] += s["frames"]
            t["integration_min"] += s["integration_min"]
            t["session_dates"].add(s["date"])
            t["filters"].add(s["filter"])
            t["exposures"].add(s["exposure_s"])
            if s.get("pre_new_start"):
                t["has_pre_new_start"] = True
            t["session_refs"].append(i)

        f = folder_totals[s["object_dir"]]
        f["frames"] += s["frames"]
        f["integration_min"] += s["integration_min"]
        f["session_dates"].add(s["date"])
        f["filters"].add(s["filter"])
        f["exposures"].add(s["exposure_s"])
        f["slugs"].update(s.get("slugs", []))
        if s.get("pre_new_start"):
            f["has_pre_new_start"] = True

    # Targets captured *only* as Seestar in-app stacks have no raw light frames, so
    # they produce no sessions and are absent from the loop above — yet they're real
    # captures (and `add_captured_objects` promotes them on exactly this signal). Add
    # a zero-integration folder/slug entry so they show up in the gallery / status /
    # `targets_for_slug` like any other capture (no subs → 0 min, status "initial").
    from . import scan_sessions
    slugset = set(catalog)
    images = config.IMAGES_DIR
    if images.is_dir():
        for d in sorted(p for p in images.iterdir() if p.is_dir()):
            if d.name in folder_totals or not (d / "seestar-stacks").is_dir():
                continue
            slugs = (scan_sessions.folder_to_slugs(d.name, slugset)
                     or [scan_sessions.slugify(d.name)])
            folder_totals[d.name]["slugs"].update(slugs)
            for slug in slugs:
                by_slug[slug]                    # touch → default zero entry

    # Finalise — convert sets, compute derived fields, attach status.
    out = {}
    for slug, t in by_slug.items():
        dates = sorted(t["session_dates"])
        out[slug] = {
            "id": slug_to_priority_id(slug, catalog),
            "frames": t["frames"],
            "integration_min": round(t["integration_min"], 2),
            "integration_hms": fmt_hm(t["integration_min"]),
            "session_count": len(dates),
            "session_dates": dates,
            "first_capture": dates[0] if dates else None,
            "last_capture": dates[-1] if dates else None,
            "filters": sorted(t["filters"]),
            "exposures": sorted(t["exposures"]),
            "has_pre_new_start": t["has_pre_new_start"],
            "status": ("deep_stack" if t["integration_min"] >= DEEP_STACK_MIN
                       else "initial"),
        }

    folders = {}
    for fname, f in folder_totals.items():
        dates = sorted(f["session_dates"])
        folders[fname] = {
            "frames": f["frames"],
            "integration_min": round(f["integration_min"], 2),
            "integration_hms": fmt_hm(f["integration_min"]),
            "session_count": len(dates),
            "first_capture": dates[0] if dates else None,
            "last_capture": dates[-1] if dates else None,
            "filters": sorted(f["filters"]),
            "exposures": sorted(f["exposures"]),
            "slugs": sorted(f["slugs"]),
            "has_pre_new_start": f["has_pre_new_start"],
            "status": ("deep_stack" if f["integration_min"] >= DEEP_STACK_MIN
                       else "initial"),
        }

    return {"by_slug": out, "by_folder": folders}


def build_priorities(priorities: list[dict], totals: dict, catalog: dict) -> list[dict]:
    """Attach current integration progress to each priority entry."""
    by_slug = totals["by_slug"]
    by_folder = totals["by_folder"]

    def slug_for_id(pid: str) -> str | None:
        # Try simple slug
        s = pid.lower().replace(" ", "-").replace("/", "-")
        if s in catalog:
            return s
        # M81/M82 etc — match folder
        for fname in by_folder:
            fslug = fname.lower().replace(" ", "-").replace("/", "-")
            if fslug == s:
                return fname  # use folder name as the lookup key
        return None

    import re as _re
    out = []
    for p in priorities:
        pid = p["id"]
        # Strip parenthesised qualifiers ("Markarian's Chain (mosaic)" →
        # "Markarian's Chain") for matching purposes; keep them in the id
        # for display. Lower-case + slash/space normalised.
        def norm(s: str) -> str:
            s = _re.sub(r"\s*\(.*?\)\s*", "", s).strip().lower()
            return s.replace("/", " ")
        pid_norm = norm(pid)

        # `track = false` marks a campaign / reminder entry (multi-object or
        # multi-filter) whose id doesn't map to a single capture folder — skip
        # auto-progress matching so it renders without a misleading bar.
        tracked = p.get("track", True)

        folder_match = None
        if tracked:
            for fname in by_folder:
                if norm(fname) == pid_norm:
                    folder_match = fname
                    break

        progress = None
        if folder_match:
            t = by_folder[folder_match]
            progress = {
                "source": "folder",
                "key": folder_match,
                "integration_min": t["integration_min"],
                "integration_hms": t["integration_hms"],
                "frames": t["frames"],
                "session_count": t["session_count"],
                "status": t["status"],
            }
        elif tracked:
            # Try slug match (also strip parenthesised qualifiers).
            base = _re.sub(r"\s*\(.*?\)\s*", "", pid).strip()
            slug = base.lower().replace(" ", "-").replace("/", "-")
            if slug in by_slug:
                t = by_slug[slug]
                progress = {
                    "source": "slug",
                    "key": slug,
                    "integration_min": t["integration_min"],
                    "integration_hms": t["integration_hms"],
                    "frames": t["frames"],
                    "session_count": t["session_count"],
                    "status": t["status"],
                }

        target_min = p.get("target_integration_min")
        pct = None
        if progress and target_min:
            pct = round(100 * progress["integration_min"] / target_min, 1)
            pct = min(pct, 999.9)  # cap display at 999.9% for absurd cases

        out.append({
            **p,
            "track": tracked,
            "progress": progress,
            "percent_complete": pct,
        })
    return out


# ── stack metadata from FITS headers ─────────────────────────────────────
#
# Siril writes STACKCNT (frames used), LIVETIME (total integration in
# seconds), and EXPTIME (per-frame exposure) into the FITS header of any
# stacked output. We read these to surface the *actual* integration time
# present in the latest stacked image — which is typically less than the
# raw-light total because Siril's roundness/FWHM filters reject 20-40%
# of frames depending on conditions.
#
# This complements the existing raw-integration tracker:
#   - Raw integration  = total light frames × exposure (effort captured)
#   - Stack integration = STACKCNT × EXPTIME (signal in the actual image)
#
# Rejection rate = (raw_frames - stack_frames) / raw_frames is a useful
# data-quality diagnostic.


def read_latest_stack_metadata(folder: Path) -> dict | None:
    """Read STACKCNT / LIVETIME / EXPTIME from the most recent .fit/.fits
    stack file in `folder` (root) or `folder/stacks/` (post-migration).

    Returns a dict with stack_frames, stack_integration_min,
    stack_integration_hms, stack_exposure_s, stack_file, and stacked_at,
    or None if no eligible file found (no .fit/.fits with STACKCNT header).
    """
    try:
        from astropy.io import fits
    except ImportError:
        return None

    candidates = []
    for d in [folder, folder / "stacks"]:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".fit", ".fits"):
                continue
            candidates.append(f)
    candidates.sort(key=lambda p: -p.stat().st_mtime)

    for f in candidates:
        try:
            with fits.open(f) as hdul:
                hdr = hdul[0].header
                cnt = hdr.get("STACKCNT")
                live = hdr.get("LIVETIME")
                if cnt and live:
                    return {
                        "stack_file": f.name,
                        "stack_frames": int(cnt),
                        "stack_integration_min": round(float(live) / 60, 1),
                        "stack_integration_hms": fmt_hm(float(live) / 60),
                        "stack_exposure_s": float(hdr.get("EXPTIME", 0)),
                        "stacked_at": hdr.get("DATE"),
                    }
        except Exception:
            continue
    return None


# ── star-removal recommendation ──────────────────────────────────────────
#
# Star removal (e.g. via StarNet++ or StarXTerminator) benefits extended-
# surface-brightness targets — large galaxies, nebulae — where the star
# field competes with delicate detail. Small/distant galaxies, point-source
# clusters (globular, open) don't benefit. Threshold below picks the
# inflection point empirically: catches M51-class and larger; skips small
# Virgo Cluster galaxies and tiny planetaries.

STAR_REMOVAL_MIN_ARCMIN = 8.0   # default size threshold (longer axis)

_SIZE_RE = re.compile(r"([\d.]+)\s*([°'])")


def parse_size_arcmin(size_str: str) -> float:
    """Extract the longest dimension from a catalog size string in arcminutes.

    Accepts forms like "11'×7'", "3°×1°", "8'×6'". Degrees are converted to
    arcminutes (×60). Returns 0 if no dimensions found.
    """
    if not size_str:
        return 0.0
    dims = []
    for num, unit in _SIZE_RE.findall(size_str):
        val = float(num)
        if unit == "°":
            val *= 60.0
        dims.append(val)
    return max(dims) if dims else 0.0


def default_star_removal_recommended(catalog_entry: dict) -> bool:
    """True if this object's type and size suggest star removal is worthwhile.

    Default rule:
      - Type is one of the extended-surface-brightness classes (galaxy,
        nebula in any flavor: planetary, emission, reflection, supernova
        remnant, etc.)
      - AND longest dimension >= STAR_REMOVAL_MIN_ARCMIN arcmin

    Catalog type strings observed: galaxy, galaxy_group, globular,
    open_cluster, emission, emission_snr, planetary, reflection. The first
    set wants star removal; the cluster types don't.
    """
    t = (catalog_entry.get("type") or "").lower()
    # Match keywords that indicate an extended-surface-brightness object.
    # Excludes "globular" and "open_cluster" by virtue of not matching.
    extended_keywords = (
        "galaxy", "nebula", "planetary", "emission", "reflection",
        "snr", "remnant",
    )
    if not any(k in t for k in extended_keywords):
        return False
    return parse_size_arcmin(catalog_entry.get("size", "")) >= STAR_REMOVAL_MIN_ARCMIN


def recommend_star_removal_for_folder(slugs: list[str],
                                      catalog: dict,
                                      override) -> bool:
    """Per-folder recommendation. Override (if not None) wins.

    For multi-slug folders (M81 M82), recommend if ANY of the contained
    objects qualifies — the capture image will contain all of them and
    the most demanding one drives the decision.
    """
    if override is not None:
        return bool(override)
    return any(default_star_removal_recommended(catalog.get(s, {})) for s in slugs)


def build_processing(totals: dict, overrides: dict | None,
                     catalog: dict | None = None,
                     sessions: list[dict] | None = None) -> dict:
    """For each captured FITS folder, derive processing status.

    Statuses:
      not_processed — no processed output (stack or finished render) yet
      out_of_date   — frames were captured after the latest stack (unintegrated)
      up_to_date    — the latest stack already includes everything captured
      dismissed     — explicitly dismissed in overrides

    Freshness is judged by **capture date vs. the stack's FITS `DATE`** — the
    frames shot after the stack was made are the unintegrated ones. Capture
    dates come from the FITS headers (via `scan_sessions`), so this is reliable
    even when file mtimes were flattened by a bulk import (e.g. the Astronomy
    port copied lights + renders with fresh/clustered mtimes, which defeated the
    older mtime comparison). When no stack `DATE` is available (finished-render-
    only objects, or a stack whose header lacks DATE) it falls back to the
    newest-light-vs-newest-processed mtime comparison.
    """
    overrides = (overrides or {}).get("folder", {}) if isinstance(overrides, dict) else {}
    by_folder = totals["by_folder"]
    now_iso = datetime.now().isoformat(timespec="seconds")
    out: dict[str, dict] = {}

    # Per-folder capture (date, frames) from sessions — the basis for splitting
    # frames into "present when stacked" vs. "captured since".
    sess_by_folder: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for s in (sessions or []):
        sess_by_folder[s["object_dir"]].append((s["date"], s["frames"]))

    if not config.IMAGES_DIR.is_dir():
        return {"folders": {}, "queue": [], "generated_at": now_iso}

    for fname, t in by_folder.items():
        folder = config.target_dir(fname)
        if not folder.is_dir():
            continue

        lights = folder / "lights"
        light_files = []
        if lights.is_dir():
            light_files = [f for f in lights.iterdir()
                           if f.is_file() and f.suffix.lower() in config.FIT_EXTS]
        newest_light_mtime = (max(f.stat().st_mtime for f in light_files)
                              if light_files else 0.0)

        # Processed output = .fit / .tif / .tiff in the folder root OR in the
        # stacks/ subdir (newer location — see migrate_to_stacks.py), PLUS any
        # hand-finished render in finished/ (raster or FITS). Excludes anything
        # inside lights/, darks/, biases/, flats/, process/, seestar-stacks/.
        processed = []
        search_dirs = [(folder, PROCESSED_EXTS)]
        stacks_subdir = folder / "stacks"
        if stacks_subdir.is_dir():
            search_dirs.append((stacks_subdir, PROCESSED_EXTS))
        finished_subdir = folder / "finished"
        if finished_subdir.is_dir():
            search_dirs.append((finished_subdir, FINISHED_EXTS))
        for d, exts in search_dirs:
            for f in d.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in exts:
                    continue
                m = f.stat().st_mtime
                processed.append({
                    "name": f.name,
                    "mtime": m,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                })
        processed.sort(key=lambda p: -p["mtime"])
        newest_processed_mtime = processed[0]["mtime"] if processed else 0.0

        # Read STACKCNT / LIVETIME / DATE from the most recent stack file's
        # FITS header (post-Siril). DATE = when the stack was made; the frames
        # captured after it are the unintegrated ones.
        stack_meta = read_latest_stack_metadata(folder) if processed else None
        stack_date = (stack_meta.get("stacked_at") or "")[:10] if stack_meta else ""

        # Split captured frames by the stack's DATE. `frames_before` = frames
        # available when the stack was made (the rejection denominator);
        # `frames_after` = frames captured since (the unintegrated backlog).
        frames_before = frames_after = 0
        have_date_signal = bool(stack_date) and bool(sess_by_folder.get(fname))
        if have_date_signal:
            for date, fr in sess_by_folder[fname]:
                if date <= stack_date:
                    frames_before += fr
                else:
                    frames_after += fr

        # Determine status
        ov = overrides.get(fname, {})
        if ov.get("dismissed"):
            status = "dismissed"
        elif not processed:
            status = "not_processed"
        elif have_date_signal:
            # Authoritative: any frames shot after the latest stack are unintegrated.
            status = "out_of_date" if frames_after > 0 else "up_to_date"
        elif newest_light_mtime > newest_processed_mtime:
            status = "out_of_date"       # fallback: no stack DATE to compare against
        else:
            status = "up_to_date"

        # "New lights since last stack": prefer the capture-date frame count
        # (frames shot after the stack); else the mtime-based light-file count.
        if have_date_signal:
            new_lights = frames_after
        else:
            new_lights = (
                sum(1 for f in light_files
                    if f.stat().st_mtime > newest_processed_mtime)
                if processed else len(light_files)
            )

        # Format helpers
        def fmt_mtime(m):
            if not m:
                return None
            return datetime.fromtimestamp(m).strftime("%Y-%m-%d")

        # Rejection% = frames dropped by Siril's quality filters, measured
        # against the frames available *when the stack was made* (frames_before)
        # — NOT the running capture total, which would miscount later,
        # unintegrated frames as "rejected" (the ~/Astronomy bug).
        if stack_meta:
            denom = frames_before if (have_date_signal and frames_before > 0) else t["frames"]
            if denom > 0:
                rejection_pct = round((1 - stack_meta["stack_frames"] / denom) * 100)
                # Clip to [0, 100] in case of weird inputs (multi-session stacks
                # where STACKCNT exceeds the denominator, etc.).
                rejection_pct = max(0, min(100, rejection_pct))
                stack_meta = {**stack_meta,
                              "stack_rejection_pct": rejection_pct,
                              "frames_at_stack": denom}

        out[fname] = {
            "folder": fname,
            "status": status,
            "integration_min": t["integration_min"],
            "integration_hms": t["integration_hms"],
            "frames": t["frames"],
            "session_count": t["session_count"],
            "last_capture": t.get("last_capture"),
            "latest_processed": (processed[0]["name"]
                                 if processed else None),
            "latest_processed_at": fmt_mtime(newest_processed_mtime),
            "latest_light_at": fmt_mtime(newest_light_mtime),
            "new_lights_since_stack": new_lights,
            "processed_files": processed[:6],   # cap for display
            "processed_count": len(processed),
            "stack_meta": stack_meta,    # None if no FITS stack found
            "star_removal": recommend_star_removal_for_folder(
                t.get("slugs", []), catalog or {}, ov.get("star_removal")),
            "note": ov.get("note"),
            "priority": ov.get("priority"),
            "slugs": t.get("slugs", []),
        }

    # Build a queue ordered by what most needs attention.
    priority_score = {
        "out_of_date":   0,
        "not_processed": 1,
        "up_to_date":    2,
        "dismissed":     3,
    }
    queue = sorted(
        out.values(),
        key=lambda f: (priority_score.get(f["status"], 9),
                       -f["new_lights_since_stack"],
                       -f["integration_min"]),
    )
    return {
        "folders": out,
        "queue": queue,
        "counts": {
            "out_of_date":   sum(1 for f in out.values() if f["status"] == "out_of_date"),
            "not_processed": sum(1 for f in out.values() if f["status"] == "not_processed"),
            "up_to_date":    sum(1 for f in out.values() if f["status"] == "up_to_date"),
            "dismissed":     sum(1 for f in out.values() if f["status"] == "dismissed"),
        },
        "generated_at": now_iso,
    }


def build_summary(catalog: dict, totals: dict) -> dict:
    """Roll up by category for the dashboard."""
    by_slug = totals["by_slug"]
    cats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "captured": 0, "deep_stack": 0,
        "captured_ids": [], "deep_ids": [],
    })

    for slug, entry in catalog.items():
        cat = entry.get("type", "unknown")
        cats[cat]["total"] += 1
        if slug in by_slug:
            cats[cat]["captured"] += 1
            cats[cat]["captured_ids"].append(entry["id"])
            if by_slug[slug]["status"] == "deep_stack":
                cats[cat]["deep_stack"] += 1
                cats[cat]["deep_ids"].append(entry["id"])

    # Totals roll-up
    grand = {
        "total":      sum(c["total"]      for c in cats.values()),
        "captured":   sum(c["captured"]   for c in cats.values()),
        "deep_stack": sum(c["deep_stack"] for c in cats.values()),
    }
    return {"by_category": dict(cats), "grand": grand}


def build_goals(totals: dict, active_ids: list[str]) -> list[dict]:
    """Per active goal (bundled catalog *or* custom list), progress over its
    members: {id, name, total, captured, deep, percent, in_progress}.
    Captured/deep come from the object-level rollup (by_slug). `in_progress` is
    the short list of members captured but still below the deep-stack target —
    {slug, name} — for the "in-progress captures" view."""
    from . import catalog, goals as goals_mod
    by_slug = totals["by_slug"]
    ref = catalog.load_reference()
    out = []
    for gid in active_ids:
        members = goals_mod.goal_members(gid)
        if not members:
            continue
        name = goals_mod.goal_name(gid)
        captured = [s for s in members if s in by_slug]
        deep = [s for s in captured if by_slug[s].get("status") == "deep_stack"]
        in_progress = [
            {"slug": s, "name": (ref.get(s, {}).get("name") or members[s] or s)}
            for s in captured if by_slug[s].get("status") != "deep_stack"
        ]
        total = len(members)
        out.append({
            "id": gid, "name": name, "total": total,
            "captured": len(captured), "deep": len(deep),
            "percent": round(100 * len(captured) / total, 1) if total else 0.0,
            "in_progress": in_progress,
        })
    return out


def main():
    overrides_path = config.OVERRIDES_TOML
    catalog = load_toml(config.LIBRARY_TOML)["catalog"]
    priorities = load_toml(config.PRIORITIES_TOML).get("priority", [])
    sessions = load_sessions()
    overrides = load_toml(overrides_path) if overrides_path.exists() else None

    from . import goals as goals_mod
    totals = build_totals(catalog, sessions)
    priority_progress = build_priorities(priorities, totals, catalog)
    summary = build_summary(catalog, totals)
    processing = build_processing(totals, overrides, catalog, sessions)
    goals = build_goals(totals, goals_mod.active_goal_ids())

    out_dir = config.DERIVED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "totals.json").write_text(
        json.dumps(totals, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "priorities.json").write_text(
        json.dumps(priority_progress, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "processing.json").write_text(
        json.dumps(processing, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "goals.json").write_text(
        json.dumps(goals, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  totals:     {len(totals['by_slug'])} slugs, "
          f"{len(totals['by_folder'])} folders")
    print(f"  priorities: {len(priority_progress)} entries")
    print(f"  summary:    {summary['grand']['captured']}/"
          f"{summary['grand']['total']} captured "
          f"({summary['grand']['deep_stack']} deep stack)")
    pc = processing["counts"]
    print(f"  processing: {pc['out_of_date']} out-of-date, "
          f"{pc['not_processed']} not processed, "
          f"{pc['up_to_date']} up-to-date"
          + (f", {pc['dismissed']} dismissed" if pc['dismissed'] else ""))


if __name__ == "__main__":
    main()

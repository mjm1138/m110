#!/usr/bin/env python3
"""Join catalog + sessions + priorities into derived rollups.

Outputs:
  data/derived/totals.json     — per-object integration totals & status
  data/derived/priorities.json — priority list with current progress
  data/derived/summary.json    — category roll-ups for the dashboard
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Ported into the Astronamigo engine.
from .display_names import display_name_for_name  # noqa: E402
from . import config  # noqa: E402

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

REPO = config.DATA_ROOT  # live Astronomy data store (parallel-run)
CATALOG = REPO / "data" / "catalog.toml"
PRIORITIES = REPO / "data" / "priorities.toml"
SESSIONS = REPO / "data" / "sessions.jsonl"
OVERRIDES = REPO / "data" / "processing_overrides.toml"
FITS_DIR = REPO / "Images" / "FITS"
OUT_DIR = REPO / "data" / "derived"

DEEP_STACK_MIN = 60  # threshold per CLAUDE.md
PROCESSED_EXTS = (".fit", ".tif", ".tiff")
SKIP_DIRS = {"M42 copy", "M81 M82 orig", "Template"}


def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_sessions() -> list[dict]:
    if not SESSIONS.exists():
        return []
    rows = []
    with SESSIONS.open() as f:
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
                     catalog: dict | None = None) -> dict:
    """For each captured FITS folder, derive processing status by comparing
    the newest processed-file mtime against the newest light-frame mtime.

    Statuses:
      not_processed — no .tif/.fit in folder root
      out_of_date   — newest light is newer than newest processed file
      up_to_date    — newest processed file is at least as new as newest light
      dismissed     — explicitly dismissed in overrides

    The comparison is mtime-based — same logic as
    scripts/check_processing_status.py but computed per folder and joined
    against the totals so the page can render a real queue.
    """
    overrides = (overrides or {}).get("folder", {}) if isinstance(overrides, dict) else {}
    by_folder = totals["by_folder"]
    now_iso = datetime.now().isoformat(timespec="seconds")
    out: dict[str, dict] = {}

    if not FITS_DIR.is_dir():
        return {"folders": {}, "queue": [], "generated_at": now_iso}

    for fname, t in by_folder.items():
        folder = FITS_DIR / fname
        if not folder.is_dir():
            continue

        lights = folder / "lights"
        light_files = []
        if lights.is_dir():
            light_files = [f for f in lights.iterdir()
                           if f.is_file() and f.suffix.lower() == ".fit"]
        newest_light_mtime = (max(f.stat().st_mtime for f in light_files)
                              if light_files else 0.0)

        # Processed files = .fit / .tif / .tiff in the folder root OR in
        # the stacks/ subdir (newer location — see migrate_to_stacks.py).
        # Excludes anything inside lights/, darks/, biases/, flats/, process/.
        # Number of slugs the folder feeds drives display-name format.
        n_slugs = len(t.get("slugs", [])) or 1
        processed = []
        search_dirs = [folder]
        stacks_subdir = folder / "stacks"
        if stacks_subdir.is_dir():
            search_dirs.append(stacks_subdir)
        for d in search_dirs:
            for f in d.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in PROCESSED_EXTS:
                    continue
                m = f.stat().st_mtime
                processed.append({
                    "name": f.name,
                    "display_name": display_name_for_name(f.name, m, fname, n_slugs),
                    "mtime": m,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                })
        processed.sort(key=lambda p: -p["mtime"])
        newest_processed_mtime = processed[0]["mtime"] if processed else 0.0

        # Determine status
        ov = overrides.get(fname, {})
        if ov.get("dismissed"):
            status = "dismissed"
        elif not processed:
            status = "not_processed"
        elif newest_light_mtime > newest_processed_mtime:
            status = "out_of_date"
        else:
            status = "up_to_date"

        # Estimate "new lights since last stack" — lights with mtime newer
        # than the newest processed file. For not_processed folders, this
        # equals the total light count.
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

        # Read STACKCNT / LIVETIME from the most recent stack file's
        # FITS header (post-Siril). This captures the "actual" integration
        # in the published image vs. the raw-light total.
        stack_meta = read_latest_stack_metadata(folder) if processed else None
        if stack_meta and t["frames"] > 0:
            rejection_pct = round(
                (1 - stack_meta["stack_frames"] / t["frames"]) * 100
            )
            # Clip to [0, 100] in case of weird inputs (multi-session
            # stacks where STACKCNT exceeds the raw frame count for that
            # folder, etc.). Treat negative as 0 (over-counted stack).
            rejection_pct = max(0, min(100, rejection_pct))
            stack_meta = {**stack_meta, "stack_rejection_pct": rejection_pct}

        out[fname] = {
            "folder": fname,
            "status": status,
            "integration_min": t["integration_min"],
            "integration_hms": t["integration_hms"],
            "frames": t["frames"],
            "session_count": t["session_count"],
            "last_capture": t.get("last_capture"),
            "latest_processed": (processed[0]["display_name"]
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


def main():
    catalog = load_toml(CATALOG)["catalog"]
    priorities = load_toml(PRIORITIES).get("priority", [])
    sessions = load_sessions()
    overrides = load_toml(OVERRIDES) if OVERRIDES.exists() else None

    totals = build_totals(catalog, sessions)
    priority_progress = build_priorities(priorities, totals, catalog)
    summary = build_summary(catalog, totals)
    processing = build_processing(totals, overrides, catalog)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "totals.json").write_text(
        json.dumps(totals, indent=2, ensure_ascii=False, default=str))
    (OUT_DIR / "priorities.json").write_text(
        json.dumps(priority_progress, indent=2, ensure_ascii=False))
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT_DIR / "processing.json").write_text(
        json.dumps(processing, indent=2, ensure_ascii=False))

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

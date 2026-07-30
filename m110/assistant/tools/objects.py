"""Per-object detail — one call, everything about one target.

Deliberately collapses ~8 engine reads. A model answering "tell me about M101"
would otherwise chain identifiers -> totals -> images -> journal -> curation ->
pins -> sessions -> deep threshold, and every extra round trip is a chance to
stop early and guess at the rest.
"""
from __future__ import annotations

from m110 import build_derived, catalog, derived, objects as journals, pins, prioritize
from m110.assistant.registry import ToolError, register
from m110.assistant.store import require_store


@register(
    name="get_object",
    title="Object detail",
    description=(
        "Everything M110 knows about one object: designations, catalogs, coordinates, "
        "capture totals and per-session history, the images on disk, the user's journal "
        "notes, pin state, and how its integration compares to the deep-stack threshold "
        "for its type. Call this before critiquing an image. Instant; cached data only. "
        "Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["slug"],
        "properties": {
            "slug": {"type": "string",
                     "description": "Object slug, e.g. 'm101'. Use list_objects to find it."},
            "include_journal": {"type": "boolean",
                                "description": "Include the journal body text (default true)."},
            "include_images": {"type": "boolean",
                               "description": "Include the per-image gallery list (default true)."},
        },
    },
    cost="instant",
    engine=("m110.catalog.load_library", "m110.catalog.object_identifiers",
            "m110.catalog.catalogs_for_slug", "m110.catalog.load_coords",
            "m110.derived.totals_by_slug", "m110.derived.images_for",
            "m110.derived.load_sessions", "m110.objects.read_journal",
            "m110.objects.get_curation", "m110.pins.get_state",
            "m110.build_derived.deep_threshold", "m110.prioritize.filter_for_type"),
)
def get_object(slug: str, include_journal: bool = True,
               include_images: bool = True) -> dict:
    require_store()
    slug = slug.strip().lower()
    library = catalog.load_library()
    entry = library.get(slug)
    if entry is None:
        raise ToolError(
            f"No object {slug!r} in this library. Use list_objects to search — note "
            "the Library holds only what the user tracks, not every catalogued object."
        )

    obj_type = entry.get("type") or "unknown"
    totals = (derived.totals_by_slug() if derived.derived_available() else {}).get(slug, {})
    integration = totals.get("integration_min", 0.0) or 0.0
    deep_min = build_derived.deep_threshold(obj_type)

    coords = catalog.load_coords().get(slug)
    out = {
        "slug": slug,
        "identifiers": catalog.object_identifiers(slug, entry),
        "name": entry.get("name", ""),
        "type": obj_type,
        "magnitude": entry.get("magnitude"),
        "size": entry.get("size"),
        "season": entry.get("season"),
        "notes": entry.get("notes"),
        "catalogs": [{"id": cid, "designation": desig}
                     for cid, desig in catalog.catalogs_for_slug(slug)],
        "coordinates": ({"ra_deg": coords[0], "dec_deg": coords[1]} if coords else None),
        "capture": {
            "integration_min": integration,
            "integration_hms": totals.get("integration_hms"),
            "frames": totals.get("frames", 0),
            "sessions": totals.get("session_count", 0),
            "filters": totals.get("filters", []),
            "exposures_s": totals.get("exposures", []),
            "first_capture": totals.get("first_capture"),
            "last_capture": totals.get("last_capture"),
            "status": totals.get("status", "uncaptured"),
            # Type-aware, per build_derived.DEEP_MIN_BY_TYPE — never quote one
            # global number for "deep".
            "deep_threshold_min": deep_min,
            "fraction_of_deep": (round(min(integration / deep_min, 1.0), 3)
                                 if deep_min else None),
        },
        "recommended_filter": prioritize.filter_for_type(obj_type),
        "pin_state": pins.get_state(slug),
        "sessions": [s for s in derived.load_sessions() if slug in (s.get("slugs") or [])],
    }

    if include_images:
        curation = journals.get_curation(slug)
        imgs = derived.images_for(slug) if derived.derived_available() else []
        out["images"] = [{
            "name": i.get("name"),
            "tier": i.get("label"),
            "state": journals.image_state(i.get("name", ""), i.get("label", ""), curation),
            "size_mb": i.get("size_mb"),
            "path": i.get("src"),
        } for i in imgs]

    if include_journal:
        frontmatter, body = journals.read_journal(slug)
        out["journal"] = {
            "has_notes": journals.has_notes(slug),
            "frontmatter": frontmatter,
            "body": body,
        }
    return out

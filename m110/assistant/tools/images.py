"""Vision: hand the client's own model an actual image, with the facts to judge it by.

No provider SDK is involved — the image travels as a transport-level image
block, so whichever model the user's client runs does the looking.

The metadata is not decoration. A critique of a percentile-stretched linear FITS
is a critique of M110's preview pipeline, not of the user's processing, and the
model has no way to know that unless told. `was_linear_fits` and
`is_rendered_preview` are the fields that prevent it.
"""
from __future__ import annotations

from m110 import build_derived, catalog, derived, objects as journals
from m110.assistant import vision
from m110.assistant.registry import ToolError, register
from m110.assistant.serialize import ImageBlob, ToolResult
from m110.assistant.store import require_store


@register(
    name="get_image",
    title="Get image",
    description=(
        "Return one of an object's images so you can actually look at it, together with "
        "the capture facts needed to judge it (integration, frames, filters, and how "
        "the file was rendered). Call get_object first — a critique without integration "
        "time and frame count is guesswork. IMPORTANT: FITS and float-TIF sources are "
        "percentile-stretched by M110 to be visible at all, so a flat or grey look may "
        "be this preview rendering rather than the user's processing; the metadata says "
        "which. Takes a few seconds. Read-only."
    ),
    params={
        "type": "object",
        "additionalProperties": False,
        "required": ["slug"],
        "properties": {
            "slug": {"type": "string", "description": "Object slug, e.g. 'm51'."},
            "which": {
                "type": "string", "enum": ["hero", "finished", "named"],
                "description": ("'hero' (default) shows the object's main image, "
                                "rendered from its ORIGINAL source rather than the "
                                "downscaled thumbnail; 'finished' the newest finished "
                                "render; 'named' a specific file via `name`."),
            },
            "name": {"type": "string",
                     "description": "Filename, required when which='named'. See get_object."},
            "max_long_edge": {
                "type": "integer", "minimum": 256, "maximum": vision.MAX_LONG_EDGE,
                "description": (f"Longest edge in pixels (default {vision.DEFAULT_LONG_EDGE}, "
                                "the useful ceiling for judging stars and gradients). "
                                "Larger costs tokens without adding usable detail."),
            },
        },
    },
    cost="seconds",
    returns="json+images",
    engine=("m110.build_images.hero_source_path", "m110.build_images._open_image",
            "m110.derived.images_for", "m110.objects.get_curation",
            "m110.objects.image_state", "m110.webexport.resize_long_edge",
            "m110.webexport.encode_jpeg"),
)
def get_image(slug: str, which: str = "hero", name: str | None = None,
              max_long_edge: int = vision.DEFAULT_LONG_EDGE) -> ToolResult:
    require_store()
    slug = slug.strip().lower()

    library = catalog.load_library()
    entry = library.get(slug)
    if entry is None:
        raise ToolError(f"No object {slug!r} in this library. Use list_objects to search.")

    path, source = vision.resolve_source(slug, which, name)
    rendered = vision.render(path, max_long_edge)

    obj_type = entry.get("type") or "unknown"
    totals = (derived.totals_by_slug() if derived.derived_available() else {}).get(slug, {})
    integration = totals.get("integration_min", 0.0) or 0.0
    deep_min = build_derived.deep_threshold(obj_type)

    meta = {
        "slug": slug,
        "identifiers": catalog.object_identifiers(slug, entry),
        "name": entry.get("name", ""),
        "type": obj_type,
        "source": source,
        "render": {
            "width": rendered["width"],
            "height": rendered["height"],
            "source_width": rendered["source_width"],
            "source_height": rendered["source_height"],
            "downscaled": rendered["downscaled"],
            "jpeg_quality": rendered["jpeg_quality"],
            "encoded_bytes": rendered["encoded_bytes"],
        },
        "capture": {
            "integration_min": integration,
            "integration_hms": totals.get("integration_hms"),
            "frames": totals.get("frames", 0),
            "sessions": totals.get("session_count", 0),
            "filters": totals.get("filters", []),
            "exposures_s": totals.get("exposures", []),
            "status": totals.get("status", "uncaptured"),
            "deep_threshold_min": deep_min,
            "fraction_of_deep": (round(min(integration / deep_min, 1.0), 3)
                                 if deep_min else None),
        },
        "journal": {"has_notes": journals.has_notes(slug)},
    }

    caveats = []
    if source["was_linear_fits"]:
        caveats.append(
            "This is a LINEAR FITS auto-stretched by M110 at the 1-99.5 percentile for "
            "display. Flatness, muted colour, or a grey cast are artifacts of that "
            "preview stretch, not of the user's processing. Do not critique them."
        )
    elif source["auto_stretched"]:
        caveats.append(
            "This is a float TIF auto-stretched by M110 (0.5-99.7 percentile) for "
            "display; tonal rendering is M110's, not the user's."
        )
    if source["is_rendered_preview"]:
        caveats.append(
            "The original source could not be located, so this is M110's already "
            "downscaled and re-compressed hero preview. Do not judge star shape, "
            "noise, or fine detail from it."
        )
    if rendered["downscaled"]:
        caveats.append(
            f"Downscaled from {rendered['source_width']}x{rendered['source_height']} "
            f"to {rendered['width']}x{rendered['height']}, then JPEG-encoded. Detail "
            "below that scale, and fine JPEG artifacts, are transport effects."
        )
    meta["caveats"] = caveats

    # Metadata first, image second: the grounding should be read before the look.
    return ToolResult(meta, images=(ImageBlob(base64=rendered["base64"],
                                              mime_type=rendered["mime_type"]),))

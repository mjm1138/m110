"""Sky-map chart data (ROADMAP item 12) — Qt-free.

Turns the Library into a star-atlas chart: every object the caller asks for,
plotted where it actually sits in the sky, colored by how far along its capture
is. The chart itself is drawn by **uranometria** (an optional dependency), whose
``render_svg`` returns standalone SVG documents plus each marker's position — so
the UI can paint the disc natively with ``QtSvg`` and hit-test clicks without
embedding a browser engine. See ROADMAP item 12 for why that matters.

The engine's job here is only to *build the config and interpret the results*:

    charts, warnings = skymap.render(slugs)          # one entry per hemisphere
    charts[0]["objects"][0]["x"], ["y"]              # marker centre, 0-1000 viewBox
    charts[0]["objects"][0]["uid"]                   # index into the config list

Callers pass the slugs they want charted — the Library page hands over its own
filtered selection, so search, the catalog filter and captured-only all apply to
the map for free without this module knowing they exist.

Objects with no coordinates are **skipped, not failed** (`build_config` returns
them so the caller can say so): a live Library carries capture-target entries
like ``M42_mosaic`` and off-catalog ones like ``Unknown`` that have no single
position to plot.

uranometria is optional. `available()` reports whether it is installed, and every
render path raises `SkymapDepsMissing` rather than `ImportError` — the same
degrade-gracefully contract as `publish.PublishDepsMissing` and
`catalog.OnlineLookupError`.
"""

from __future__ import annotations

from . import catalog, derived, objects

# Capture status drives marker color. These are the status strings
# `build_derived` already computes (via the type-aware `deep_threshold`, so the
# map, the status chips and the prioritizer cannot disagree), plus our own name
# for "in the Library but never shot".
STATUS_DEEP = "deep_stack"
STATUS_INITIAL = "initial"
STATUS_UNCAPTURED = "uncaptured"

# Defaults mirror the light-theme semantic roles (`ui.theme.status_color`:
# deep=green, initial=amber, everything else muted) so an unthemed render still
# reads the way the rest of the app does. The UI passes live tokens over these,
# which is what makes the chart follow light/dark.
DEFAULT_COLORS = {
    STATUS_DEEP: "#2f9e44",
    STATUS_INITIAL: "#b9770a",
    STATUS_UNCAPTURED: "#6b7077",
}


class SkymapDepsMissing(Exception):
    """The optional `skymap` extra (uranometria) isn't installed.

    Raised instead of a bare `ImportError` so the UI can show an actionable
    install hint — or hide the Map view entirely — the same way
    `publish.PublishDepsMissing` gates the static-site renderer.
    """


def available() -> bool:
    """Whether the chart library is importable."""
    try:
        import uranometria  # noqa: F401
    except ImportError:
        return False
    return True


def _uranometria():
    try:
        import uranometria
    except ImportError as err:
        raise SkymapDepsMissing(
            "The sky map needs the uranometria package "
            '(pip install "uranometria @ git+https://github.com/devonjones/uranometria")'
        ) from err
    return uranometria


def object_status(slug: str, by_slug: dict | None = None) -> str:
    """Capture status for `slug` as one of the ``STATUS_*`` constants.

    Reads `build_derived`'s own verdict rather than re-deriving it from
    integration minutes, so a threshold change lands everywhere at once.
    """
    if by_slug is None:
        by_slug = derived.totals_by_slug()
    entry = by_slug.get(slug)
    if not entry:
        return STATUS_UNCAPTURED
    return STATUS_DEEP if entry.get("status") == STATUS_DEEP else STATUS_INITIAL


def _label_for(slug: str, entry: dict) -> str:
    """Chart label for an object: its designation, without the capture-target
    decoration a folder-derived Library entry can carry (``M42_mosaic``)."""
    label = str(entry.get("id") or slug)
    return label[: -len("_mosaic")] if label.endswith("_mosaic") else label


def build_config(
    slugs=None,
    *,
    colors: dict | None = None,
    title: str | None = None,
    mirror: bool = False,
    heroes: bool = True,
) -> tuple[dict, list[str]]:
    """Build a uranometria chart config as ``(config, skipped)``.

    `slugs` selects what to chart (default: the whole Library). `skipped` lists
    the slugs left out for want of coordinates, so a caller can report them
    rather than silently drawing a shorter chart.

    Entries are **fully specified** — label plus J2000 ``ra``/``dec`` from
    `catalog.load_coords` — so uranometria never does a lookup and the render is
    offline and deterministic. That also side-steps the designations a real
    Library holds that no catalog resolves (``Unknown``, ``Markarian's Chain``).

    `heroes` attaches each object's rendered hero path as ``image``. It is never
    embedded in the SVG; it comes back on the marker so the UI can show the photo
    when one is clicked.
    """
    library = catalog.load_library()
    coords = catalog.load_coords()
    by_slug = derived.totals_by_slug()
    palette = {**DEFAULT_COLORS, **(colors or {})}

    wanted = list(library) if slugs is None else [s for s in slugs if s in library]
    entries, skipped = [], []
    for slug in wanted:
        if slug not in coords:
            skipped.append(slug)
            continue
        e = library[slug]
        ra, dec = coords[slug]
        entry = {
            "label": _label_for(slug, e),
            "name": e.get("name") or "",
            "type": e.get("type") or "",
            "ra": ra,
            "dec": dec,
            "color": palette[object_status(slug, by_slug)],
        }
        if heroes:
            hero = objects.hero_path(slug)
            if hero:
                entry["image"] = str(hero)
        entries.append(entry)

    config: dict = {"objects": entries, "mirror": mirror}
    if title:
        config["title"] = title
    return config, skipped


def render(
    slugs=None,
    *,
    colors: dict | None = None,
    palette: dict | None = None,
    font_family: str | None = None,
    title: str | None = None,
    mirror: bool = False,
) -> tuple[list, list[str]]:
    """Render the chart as ``(charts, warnings)``.

    One entry per hemisphere the selection needs, north first — a southern disc
    appears only when something is far enough south to need one, which is exactly
    when the UI should offer an N|S toggle.

    `colors` overrides the per-status marker colors; `palette` themes the chart
    itself (sky, grid, constellation lines — any subset of
    ``uranometria.chart.PALETTE``); `font_family` names a font the host has
    loaded. Slugs skipped for missing coordinates are reported as warnings, so a
    caller that ignores `build_config`'s second return value still hears about
    them.

    Raises `SkymapDepsMissing` when uranometria is not installed, and returns
    ``([], warnings)`` when the selection has nothing chartable — never an
    exception for an empty or unresolvable list.
    """
    uranometria = _uranometria()
    config, skipped = build_config(
        slugs, colors=colors, title=title, mirror=mirror
    )
    warnings = []
    if skipped:
        warnings.append(
            f"{len(skipped)} object(s) have no coordinates and are not on the chart: "
            + ", ".join(sorted(skipped)[:8])
            + (" …" if len(skipped) > 8 else "")
        )
    if not config["objects"]:
        return [], warnings
    charts, chart_warnings = uranometria.render_svg(
        config, palette=palette, font_family=font_family, allow_online=False
    )
    return charts, warnings + list(chart_warnings)

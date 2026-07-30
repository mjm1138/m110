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

uranometria is optional. `available()` reports whether it is installed *and
importable*, and every render path raises `SkymapDepsMissing` rather than letting
an `ImportError` — or any other import-time failure — escape: the same
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
    """The optional `skymap` extra (uranometria) isn't installed — or won't import.

    Raised instead of a bare `ImportError` so the UI can show an actionable
    install hint — or hide the Map view entirely — the same way
    `publish.PublishDepsMissing` gates the static-site renderer.
    """


# `import uranometria` runs real work at module scope: `uranometria.catalog` loads
# its bundled constellation JSON on import. So an *installed* uranometria can still
# fail to import — a frozen build that carried the modules but not the package data
# raised FileNotFoundError there, and because the Library renders the map while the
# window is being built, that took the whole app down at launch (0.3.0b1). Anything
# the import raises is therefore "no sky map", never a crash.
def _uranometria():
    """Import uranometria, or raise `SkymapDepsMissing` describing why not."""
    try:
        import uranometria
    except ImportError as err:
        raise SkymapDepsMissing(
            "The sky map needs the uranometria package "
            '(pip install "uranometria @ git+https://github.com/devonjones/uranometria")'
        ) from err
    except Exception as err:                    # installed, but broken/incomplete
        raise SkymapDepsMissing(
            f"The sky map couldn't load its chart library: {type(err).__name__}: {err}"
        ) from err
    return uranometria


def available() -> bool:
    """Whether the chart library is importable."""
    try:
        _uranometria()
    except SkymapDepsMissing:
        return False
    return True


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
) -> tuple[dict, list[str], list[str]]:
    """Build a uranometria chart config as ``(config, charted, skipped)``.

    `slugs` selects what to chart (default: the whole Library). `charted` is the
    slugs actually on the chart, **in config order** — a marker's ``uid`` indexes
    it, which is the only way back from a click to an object. `skipped` lists the
    slugs left out for want of coordinates, so a caller can report them rather
    than silently drawing a shorter chart.

    Entries are **fully specified** — label plus J2000 ``ra``/``dec`` from
    `catalog.load_coords` — so uranometria never does a lookup and the render is
    offline and deterministic. That also side-steps the designations a real
    Library holds that no catalog resolves (``Unknown``, ``Markarian's Chain``).

    `heroes` attaches each object's rendered hero path as ``image``. It is never
    embedded in the SVG; it comes back on the marker so the UI can show the photo
    when one is clicked.
    """
    library = catalog.load_library()
    reference = catalog.load_reference()
    coords = catalog.load_coords()
    by_slug = derived.totals_by_slug()
    palette = {**DEFAULT_COLORS, **(colors or {})}

    # A slug need not be in the Library: charting a goal's *unshot* members is
    # the point of the "not yet shot" tier, and those live only in the bundled
    # reference until you capture one.
    wanted = list(library) if slugs is None else list(slugs)
    entries, charted, skipped = [], [], []
    for slug in wanted:
        e = library.get(slug) or reference.get(slug)
        if e is None:
            continue                       # not an object we know at all
        if slug not in coords:
            skipped.append(slug)
            continue
        charted.append(slug)
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
    return config, charted, skipped


# uranometria charts an object list, so an empty one has nothing to draw. To
# still hand back the *sky* — the useful thing to show when a filter matches
# nothing — render a single marker painted in nothing at all. Verified against
# QtSvg: a transparent marker alters zero pixels, so what comes back is the bare
# chart. The dummy is stripped from the returned objects, so it can't be clicked.
_EMPTY_SKY = {"label": "", "ra": 0.0, "dec": 90.0, "color": "transparent"}


def render(
    slugs=None,
    *,
    colors: dict | None = None,
    palette: dict | None = None,
    font_family: str | None = None,
    title: str | None = None,
    mirror: bool = False,
    empty_sky: bool = True,
) -> tuple[list, list[str]]:
    """Render the chart as ``(charts, warnings)``.

    One entry per hemisphere the selection needs, north first — a southern disc
    appears only when something is far enough south to need one, which is exactly
    when the UI should offer an N|S toggle.

    Every marker gains a **`slug`** and its **`status`** alongside uranometria's
    own fields, so a click maps straight back to an object and a host can key a
    legend off what is actually on the chart. Doing the slug here rather than in
    the caller keeps the uid→slug correspondence next to the code that
    establishes it — a caller re-deriving it from its own list would be wrong the
    moment one object lacks coordinates.

    `colors` overrides the per-status marker colors; `palette` themes the chart
    itself (sky, grid, constellation lines — any subset of
    ``uranometria.chart.PALETTE``); `font_family` names a font the host has
    loaded. Slugs skipped for missing coordinates are reported as warnings, so a
    caller that ignores `build_config`'s second return value still hears about
    them.

    Raises `SkymapDepsMissing` when uranometria is not installed. A selection
    with nothing chartable is never an exception: by default it comes back as
    one **empty sky** — the chart with no objects on it, which is what a host
    wants to show when a filter matches nothing. Pass ``empty_sky=False`` for
    ``([], warnings)`` instead.
    """
    uranometria = _uranometria()
    config, charted, skipped = build_config(
        slugs, colors=colors, title=title, mirror=mirror
    )
    warnings = []
    if skipped:
        # Name them the way the user sees them in the Library — a slug is an
        # internal key, and "markarians-chain" in a message is a leak, not a label.
        library = catalog.load_library()
        names = sorted(str(library.get(s, {}).get("id") or s) for s in skipped)
        shown = ", ".join(names[:8]) + (" …" if len(names) > 8 else "")
        warnings.append(
            f"{len(skipped)} object{'s' if len(skipped) != 1 else ''} "
            f"{'have' if len(skipped) != 1 else 'has'} no coordinates, so "
            f"{'they aren' if len(skipped) != 1 else 'it isn'}'t on the chart: {shown}"
        )
    empty = not config["objects"]
    if empty:
        if not empty_sky:
            return [], warnings
        config["objects"] = [dict(_EMPTY_SKY)]
    charts, chart_warnings = uranometria.render_svg(
        config, palette=palette, font_family=font_family, allow_online=False
    )
    by_slug = derived.totals_by_slug()
    for chart in charts:
        chart["objects"] = [] if empty else [
            {**m, "slug": charted[m["uid"]],
             "status": object_status(charted[m["uid"]], by_slug)}
            for m in chart["objects"]
        ]
    return charts, warnings + list(chart_warnings)

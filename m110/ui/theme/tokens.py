"""Design tokens — the single source of truth for color, spacing, type.

Semantic **roles** (not raw colors), with a light, dark and night instance.
Everything in `m110/ui/` pulls color/spacing from here (via `theme` / QSS) rather
than hardcoding, so the app stays coherent across themes.

The 1.0 palette ("notebook-tinged pro", UI_ROADMAP → 1.0 redesign) is warm graphite
on dark, warm paper on light, and red-on-black for night vision. Surfaces climb a
**luminance ladder** — well < window < surface tier < control < hover — with at
least 5 L* between levels, so panels separate by tone rather than by 1px borders.
The **image well** sits behind grids, heroes and the viewer: near-black on dark,
a medium warm gray on light — astro images never sit on paper. The contrast test checks the
ladder and the WCAG contrast of every text/background pair numerically.

The currently-applied palette is a module global (`active()` / `set_active`) so
programmatic call sites (e.g. table-item foreground, which QSS can't reach) read the
same source the stylesheet does.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

# ── scales (plain constants; px) ──────────────────────────────────────────────
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 4, "md": 6, "lg": 10}
# The 1.0 type scale: 11 · 13 · 15 · 17 · 22 · 30. `small` is kept as an alias of
# `caption` for older call sites — the scale has no 12.
FONT_SIZE = {"caption": 11, "small": 11, "body": 13, "section": 15,
             "heading": 17, "title": 22, "display": 30}
TYPE_SCALE = (11, 13, 15, 17, 22, 30)


@dataclass(frozen=True)
class Tokens:
    name: str                 # "light" | "dark" | "night"
    # surfaces (the ladder, darkest → lightest on dark themes)
    well: str                 # image well: grids, heroes, viewer — dark in every theme
    window: str               # page background (content panels)
    chrome: str               # toolbar strip / title area
    sidebar: str              # source list
    surface: str              # cards, tables, lists
    surface_alt: str          # alternating rows / subtle fills / hover on surface
    control: str              # buttons, fields, segments
    control_hover: str
    raised: str               # menus / popups / tooltips
    # lines (used sparingly — surface steps do most of the separating)
    border: str
    divider: str
    # text
    text_primary: str
    text_secondary: str       # = muted
    text_disabled: str
    well_text: str            # text drawn on the image well
    well_muted: str
    # accent
    accent: str
    accent_text: str          # on-accent foreground (AA against `accent`)
    accent_hover: str
    # selection / focus
    selection_bg: str
    selection_text: str
    focus_ring: str
    # status (capture): Deep · n% · Initial
    status_deep: str
    status_progress: str      # captured, part-way to its integration goal
    status_initial: str
    # spare semantic set (processing states map onto these)
    ok: str
    warn: str
    danger: str
    neutral: str

    @property
    def is_dark(self) -> bool:
        return self.name != "light"


# ── the palettes ──────────────────────────────────────────────────────────────
# TO TWEAK THEME COLORS: edit the hex values below, then run
# `pytest tests/test_theme_contrast.py` — it fails if a change breaks AA contrast or
# collapses the luminance ladder. Every role is a semantic name used app-wide (via
# QSS + programmatic lookups), so one hex here recolors that role everywhere.

# Warm graphite (mock A). Ladder L*: well 6 · window 18 · surface tier 23–24 ·
# control 30 · hover 35.
DARK = Tokens(
    name="dark",
    well="#141312", window="#2d2b28", chrome="#3a3632", sidebar="#3c3833",
    surface="#3a3732", surface_alt="#403c37", control="#4a4640",
    control_hover="#57524b", raised="#403c37",
    border="#24221f", divider="#34312d",
    text_primary="#ece6da", text_secondary="#b3aa9b", text_disabled="#7a7266",
    well_text="#ece6da", well_muted="#ada495",
    accent="#d9a648", accent_text="#1f1a10", accent_hover="#e3b35c",
    selection_bg="#5b4a2b", selection_text="#ece6da", focus_ring="#d9a648",
    status_deep="#9cbf7e", status_progress="#86a8d0", status_initial="#df8f6d",
    ok="#9cbf7e", warn="#d9a648", danger="#e07a6a", neutral="#ada495",
)

# Warm paper chrome, ink text, brass-ink accent. The image well is a medium warm
# gray (L* 38) rather than near-black: a black well read as a hole punched in the
# paper, and white would wash the photographs out. L* 38 is the lightest gray that
# still carries light captions and status chips at AA (a true middle gray, L* 50,
# would need dark captions). Ladder L*: well 38 · sidebar/chrome 86 · window 92 ·
# surface 97 · control 99.
LIGHT = Tokens(
    name="light",
    well="#5c5852", window="#ece6da", chrome="#ded6c6", sidebar="#ddd5c4",
    surface="#f8f5ee", surface_alt="#f0ebe0", control="#fffdf8",
    control_hover="#f3eee4", raised="#fffdf8",
    border="#d3cbbb", divider="#e0d9ca",
    text_primary="#25221d", text_secondary="#5c5447", text_disabled="#a39a8a",
    well_text="#f4efe6", well_muted="#ddd6c9",
    accent="#8f6314", accent_text="#fffdf8", accent_hover="#7d560f",
    selection_bg="#ead9b4", selection_text="#25221d", focus_ring="#8f6314",
    status_deep="#386223", status_progress="#33598a", status_initial="#934020",
    ok="#386223", warn="#8f6314", danger="#a8392b", neutral="#5c5447",
)

# Night vision: red on black, nothing above the red channel, so it doesn't spoil
# dark adaptation at the telescope. Not user-selectable until Phase 8 wires it to
# View and Settings; it is complete and contrast-checked now so that is a drop-in.
NIGHT = Tokens(
    name="night",
    well="#000000", window="#0d0202", chrome="#120303", sidebar="#140404",
    surface="#170505", surface_alt="#1c0606", control="#240808",
    control_hover="#300b0b", raised="#240808",
    border="#2a0a0a", divider="#1c0606",
    text_primary="#ff6b5c", text_secondary="#e0503f", text_disabled="#8a2a20",
    well_text="#ff6b5c", well_muted="#e0503f",
    accent="#ff6b5c", accent_text="#0d0202", accent_hover="#ff8070",
    selection_bg="#4a1010", selection_text="#ff6b5c", focus_ring="#ff6b5c",
    status_deep="#ff8a70", status_progress="#ff6b5c", status_initial="#e0503f",
    ok="#ff8a70", warn="#ff6b5c", danger="#ff8a70", neutral="#e0503f",
)

# The themes a user can pick today. NIGHT joins in Phase 8.
THEMES = {"light": LIGHT, "dark": DARK}
ALL_THEMES = {"light": LIGHT, "dark": DARK, "night": NIGHT}

# Roles a complete Tokens must define (used by tests to catch a missing field).
ROLE_FIELDS = [f.name for f in fields(Tokens) if f.name != "name"]

_active: Tokens = LIGHT


def active() -> Tokens:
    """The currently-applied palette (defaults to LIGHT until a theme is installed)."""
    return _active


def set_active(tokens: Tokens) -> None:
    global _active
    _active = tokens


# What is drawn *on* the light theme's gray well: the dark palette, with captions
# and status hues lifted to stay AA on the lighter gray.
LIGHT_WELL = replace(
    DARK, well=LIGHT.well, surface="#67635c",
    text_primary=LIGHT.well_text, text_secondary=LIGHT.well_muted,
    well_text=LIGHT.well_text, well_muted=LIGHT.well_muted,
    status_deep="#c9e6ae", status_progress="#c6dbf5", status_initial="#fccfb9",
)


def on_well(t: Tokens | None = None) -> Tokens:
    """The palette to draw *on the image well* with — status chips, tile captions,
    the empty-thumbnail placeholder. The well is dark (dark/night) or a medium gray
    (light) whatever the panels around it are, so it gets its own hues."""
    t = t or _active
    return {"night": NIGHT, "light": LIGHT_WELL}.get(t.name, DARK)

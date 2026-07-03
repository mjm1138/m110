"""Design tokens — the single source of truth for color, spacing, type.

Semantic **roles** (not raw colors), with a light + dark instance. Everything in
`m110/ui/` pulls color/spacing from here (via `theme` / QSS) rather than hardcoding,
so the app stays coherent across themes and a future brand accent is a one-line swap.

The currently-applied palette is a module global (`active()` / `set_active`) so
programmatic call sites (e.g. table-item foreground, which QSS can't reach) read the
same source the stylesheet does.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

# ── scales (plain constants; px) ──────────────────────────────────────────────
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 4, "md": 6, "lg": 10}
FONT_SIZE = {"caption": 11, "small": 12, "body": 13, "section": 15, "title": 20}


@dataclass(frozen=True)
class Tokens:
    name: str                 # "light" | "dark"
    # surfaces
    window: str
    surface: str
    surface_alt: str          # alternating rows / subtle fills
    raised: str               # menus / popups / tooltips
    # lines
    border: str
    divider: str
    # text
    text_primary: str
    text_secondary: str       # = muted
    text_disabled: str
    # accent
    accent: str
    accent_text: str          # on-accent foreground
    accent_hover: str
    # selection / focus
    selection_bg: str
    selection_text: str
    focus_ring: str
    # status (capture)
    status_deep: str
    status_initial: str
    # spare semantic set (processing states map onto these later)
    ok: str
    warn: str
    danger: str
    neutral: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


# ── the palette ───────────────────────────────────────────────────────────────
# TO TWEAK THEME COLORS: edit the hex values in LIGHT / DARK below. Every role is a
# semantic name used app-wide (via QSS + programmatic lookups), so changing one hex
# here recolors that role everywhere — no other file needs editing. `accent` is the
# single brand swap-point. After editing, relaunch (or toggle the theme) to see it.
LIGHT = Tokens(
    name="light",
    window="#f5f6f7", surface="#ffffff", surface_alt="#f0f1f3", raised="#ffffff",
    border="#d8dbdf", divider="#e3e5e8",
    text_primary="#1c1e21", text_secondary="#6b7077", text_disabled="#a0a4a9",
    accent="#8a5a2b", accent_text="#ffffff", accent_hover="#71491f",
    selection_bg="#ece0c8", selection_text="#1c1e21", focus_ring="#8a5a2b",
    status_deep="#2f9e44", status_initial="#b9770a",
    ok="#2f9e44", warn="#b9770a", danger="#c33b3b", neutral="#6b7077",
)

DARK = Tokens(
    name="dark",
    window="#1e1f22", surface="#26282c", surface_alt="#2b2e33", raised="#303338",
    border="#3a3d42", divider="#34373c",
    text_primary="#e6e7e9", text_secondary="#9aa0a6", text_disabled="#6b7077",
    accent="#c69a6b", accent_text="#241c12", accent_hover="#d6ab7c",
    selection_bg="#4a3d2c", selection_text="#e6e7e9", focus_ring="#c69a6b",
    status_deep="#3fb950", status_initial="#d29922",
    ok="#3fb950", warn="#d29922", danger="#e5534b", neutral="#9aa0a6",
)

THEMES = {"light": LIGHT, "dark": DARK}

# Roles a complete Tokens must define (used by tests to catch a missing field).
ROLE_FIELDS = [f.name for f in fields(Tokens) if f.name != "name"]

_active: Tokens = LIGHT


def active() -> Tokens:
    """The currently-applied palette (defaults to LIGHT until a theme is installed)."""
    return _active


def set_active(tokens: Tokens) -> None:
    global _active
    _active = tokens

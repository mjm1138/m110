"""The 1.0 palettes, checked numerically: WCAG AA for every text/background pair the
app draws, and a luminance ladder with real steps between surface levels.

The critique (docs-archive/UI_CRITIQUE_2026-11.md) measured white-on-accent at 3.1:1
and four dark surfaces packed into ~9 L*; these tests keep both from coming back."""
import pytest

from m110.ui.theme import contrast, tokens

AA = 4.5          # body text
AA_LARGE = 3.0    # non-text UI (focus ring, check fill) and placeholder text

THEMES = list(tokens.ALL_THEMES.values())
TEXT_BGS = ("window", "chrome", "sidebar", "surface", "surface_alt", "raised")


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_every_role_is_a_hex_color(t):
    for role in tokens.ROLE_FIELDS:
        v = getattr(t, role)
        assert isinstance(v, str) and v.startswith("#") and len(v) == 7, (t.name, role)


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("fg", ["text_primary", "text_secondary"])
def test_text_is_aa_on_every_panel(t, fg):
    for bg in TEXT_BGS:
        r = contrast.ratio(getattr(t, fg), getattr(t, bg))
        assert r >= AA, f"{t.name}: {fg} on {bg} is {r:.2f}:1"


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_text_on_controls(t):
    assert contrast.ratio(t.text_primary, t.control) >= AA
    assert contrast.ratio(t.text_primary, t.control_hover) >= AA
    # Placeholder/secondary text inside a field: large-text/UI threshold.
    assert contrast.ratio(t.text_secondary, t.control) >= AA_LARGE


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_on_accent_text_is_aa(t):
    """The selected sidebar row and default button: today's white-on-blue was 3.1:1."""
    assert contrast.ratio(t.accent_text, t.accent) >= AA
    assert contrast.ratio(t.accent_text, t.accent_hover) >= AA


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_accent_is_visible_as_a_ui_mark(t):
    """Focus rings and check fills are non-text UI: ≥ 3:1 against the panel."""
    for bg in ("window", "surface", "control"):
        assert contrast.ratio(t.focus_ring, getattr(t, bg)) >= AA_LARGE, bg


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_selection_is_readable(t):
    assert contrast.ratio(t.selection_text, t.selection_bg) >= AA


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_status_hues_are_readable_as_text(t):
    for s in ("status_deep", "status_progress", "status_initial"):
        for bg in ("window", "surface", "sidebar"):
            r = contrast.ratio(getattr(t, s), getattr(t, bg))
            assert r >= AA, f"{t.name}: {s} on {bg} is {r:.2f}:1"


@pytest.mark.parametrize("t", THEMES, ids=lambda t: t.name)
def test_the_image_well_is_dark_with_readable_captions(t):
    """Astro images never sit on paper: the well is dark in every theme, and what's
    drawn on it (captions, status chips) uses the well palette."""
    assert contrast.lightness(t.well) <= 10
    for fg in (t.well_text, t.well_muted):
        assert contrast.ratio(fg, t.well) >= AA
    w = tokens.on_well(t)
    for s in (w.status_deep, w.status_progress, w.status_initial):
        assert contrast.ratio(s, t.well) >= AA


def test_status_hues_are_distinct_from_the_accent():
    """'In progress' must not read as 'selected' (critique §2.5)."""
    for t in (tokens.DARK, tokens.LIGHT):
        assert t.status_progress != t.accent
        assert t.status_deep != t.accent


@pytest.mark.parametrize("t", [tokens.DARK, tokens.LIGHT], ids=lambda t: t.name)
def test_luminance_ladder_has_real_steps(t):
    """≥ 5 L* between successive surface levels, so tone — not borders — separates
    panels. Dark climbs well → window → surface tier → control → hover; light puts
    the sidebar/chrome below the window and cards/controls above it."""
    L = contrast.lightness
    if t.name == "dark":
        ladder = [t.well, t.window, t.surface, t.control, t.control_hover]
    else:
        ladder = [t.well, t.sidebar, t.window, t.surface]
    steps = [L(b) - L(a) for a, b in zip(ladder, ladder[1:])]
    assert all(s >= 5 for s in steps), [round(s, 1) for s in steps]
    # The surface tier (chrome/sidebar/surface) reads as one level.
    tier = [L(t.chrome), L(t.sidebar)] + ([L(t.surface)] if t.name == "dark" else [])
    assert max(tier) - min(tier) < 5


def test_type_scale():
    assert tokens.TYPE_SCALE == (11, 13, 15, 17, 22, 30)
    assert set(tokens.FONT_SIZE.values()) <= set(tokens.TYPE_SCALE)


def test_only_light_and_dark_are_selectable_yet():
    assert set(tokens.THEMES) == {"light", "dark"}
    assert tokens.ALL_THEMES["night"] is tokens.NIGHT
    assert tokens.NIGHT.is_dark and not tokens.LIGHT.is_dark

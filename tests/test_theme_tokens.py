"""Design tokens — completeness + valid colors."""
from PySide6.QtGui import QColor

from m110.ui.theme import tokens


def test_light_and_dark_define_every_role():
    for t in (tokens.LIGHT, tokens.DARK):
        for role in tokens.ROLE_FIELDS:
            assert getattr(t, role), f"{t.name} missing {role}"


def test_all_color_values_parse():
    for t in (tokens.LIGHT, tokens.DARK):
        for role in tokens.ROLE_FIELDS:
            c = QColor(getattr(t, role))
            assert c.isValid(), f"{t.name}.{role} is not a valid color"


def test_themes_registry_and_is_dark():
    assert tokens.THEMES["light"] is tokens.LIGHT
    assert tokens.THEMES["dark"] is tokens.DARK
    assert tokens.DARK.is_dark and not tokens.LIGHT.is_dark


def test_active_defaults_and_set():
    tokens.set_active(tokens.DARK)
    assert tokens.active().name == "dark"
    tokens.set_active(tokens.LIGHT)
    assert tokens.active().name == "light"

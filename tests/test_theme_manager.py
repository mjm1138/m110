"""Theme manager — apply, switch, persist, resolve."""
from m110 import config
from m110.ui import theme
from tests._helpers import seed_root


def test_install_applies_stylesheet(qapp):
    mgr = theme.install(qapp)
    assert qapp.styleSheet().strip()
    assert mgr.mode in theme.MODES


def test_set_mode_switches_and_persists(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)        # patches SETTINGS_FILE → temp
    mgr = theme.install(qapp)
    mgr.set_mode("dark")
    assert theme.active_tokens().name == "dark"
    dark_qss = qapp.styleSheet()
    mgr.set_mode("light")
    assert theme.active_tokens().name == "light"
    assert qapp.styleSheet() != dark_qss
    assert config.get_setting(theme.SETTING_KEY) == "light"


def test_resolve_maps_modes():
    assert theme.resolve("dark") == "dark"
    assert theme.resolve("light") == "light"
    assert theme.resolve("system") in ("light", "dark")


def test_invalid_saved_mode_falls_back(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    config.save_setting(theme.SETTING_KEY, "neon")   # bogus
    mgr = theme.install(qapp)
    assert mgr.mode == "system"


def test_status_color_follows_theme(qapp):
    mgr = theme.install(qapp)
    mgr.set_mode("dark")
    assert theme.status_color("deep_stack").name() == theme.DARK.status_deep
    mgr.set_mode("light")
    assert theme.status_color("deep_stack").name() == theme.LIGHT.status_deep
    # unknown status → muted
    assert theme.status_color("???").name() == theme.muted_color().name()

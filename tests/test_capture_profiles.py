"""Capture profiles (m110/capture_profiles.py, #203): which software wrote a frame,
its device key, whether it was dark-subtracted before saving, and its object name.
The header cards here are copied from real frames: a PINS (N.I.N.A. 3.3) S50 night
over Alpaca (2026-11-06) and the same S50's own app subs."""
import pytest

from m110 import capture_profiles as cp

# A PINS light, as written (the cards these rules read).
NINA_LIGHT = {
    "IMAGETYP": "LIGHT", "OBJECT": "M 45 Panel 1", "TELESCOP": "S50 Prime",
    "INSTRUME": "Seestar S50_15e7e390 Telephoto Camera",
    "SWCREATE": "PI N Stars (N.I.N.A. 3.3.0.1058 (arm64))",
}
NINA_DARK = {k: v for k, v in NINA_LIGHT.items() if k != "OBJECT"} | {"IMAGETYP": "DARK"}
# The same telescope's own app sub.
APP_SUB = {"TELESCOP": "S50_15e7e390", "INSTRUME": "Seestar S50",
           "CREATOR": "ZWO Seestar S50", "OBJECT": "IC 434"}


def test_nina_is_recognised_by_swcreate_desktop_and_pins():
    assert cp.profile_for(NINA_LIGHT).id == "nina"
    assert cp.profile_for({"SWCREATE": "N.I.N.A. 3.1.2.9001"}).id == "nina"


def test_the_nina_s50_is_the_same_device_as_its_app_subs():
    """N.I.N.A. over Alpaca says TELESCOP='S50 Prime'; the serial is in INSTRUME."""
    assert cp.device_key(NINA_LIGHT) == "S50_15e7e390"
    assert cp.device_key(NINA_DARK) == "S50_15e7e390"
    assert cp.device_key(APP_SUB) == "S50_15e7e390"


def test_nina_with_other_gear_keys_on_telescop_then_instrume():
    rig = {"SWCREATE": "N.I.N.A. 3.1", "TELESCOP": "Esprit 100",
           "INSTRUME": "ZWO ASI2600MM Pro"}
    assert cp.device_key(rig) == "Esprit 100"
    assert cp.device_key({"SWCREATE": "N.I.N.A. 3.1",
                          "INSTRUME": "ZWO ASI2600MM Pro"}) == "ZWO ASI2600MM Pro"
    assert cp.device_key({"SWCREATE": "N.I.N.A. 3.1"}) is None


def test_darks_applied_follows_the_capture_path_not_the_model():
    """The S50's app subtracts a dark before saving; the same S50 under N.I.N.A.
    does not (hot pixels at full strength in the lights, measured 2026-11-07)."""
    assert cp.darks_applied(APP_SUB) is True
    assert cp.darks_applied(NINA_LIGHT) is False
    # a bare per-unit TELESCOP (older firmware, every pre-#203 fixture) is the app
    assert cp.darks_applied({"TELESCOP": "S50_aaaa0001"}) is True
    assert cp.darks_applied({"TELESCOP": "DWARF 3"}) is False
    assert cp.darks_applied({}) is False


@pytest.mark.parametrize("name,expected", [
    ("M 45 Panel 1", "M 45_mosaic"),
    ("M 45 Panel 12", "M 45_mosaic"),
    ("Veil Panneau 2", "Veil_mosaic"),      # N.I.N.A. localises "Panel"
    ("M31 Pannello 3", "M31_mosaic"),
    ("M 110", "M 110"),
    ("NGC 2024 IC 434", "NGC 2024 IC 434"),
    ("Panel 1", "Panel 1"),                  # nothing left once the word is gone
])
def test_nina_panels_fold_onto_the_mosaic(name, expected):
    assert cp.object_name(dict(NINA_LIGHT, OBJECT=name)) == expected


def test_object_name_is_none_without_an_object_card():
    assert cp.object_name(NINA_DARK) is None


def test_facts_bundles_the_three_answers():
    assert cp.facts(NINA_LIGHT) == {"device": "S50_15e7e390",
                                    "darks_applied": False, "capture": "nina"}
    assert cp.facts(APP_SUB)["capture"] == "seestar-app"

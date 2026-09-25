"""Telescope identity from the FITS ``TELESCOP`` card (m110.devices)."""
from m110 import devices
from m110.planning_config import DEVICE_PRESETS


def test_folder_name_is_the_trimmed_header_string():
    assert devices.folder_name("Draco") == "Draco"
    assert devices.folder_name("DWARF 3 ") == "DWARF 3"     # real names, verbatim
    assert devices.folder_name("") == "unknown"
    assert devices.folder_name(None) == "unknown"


def test_preset_key_maps_known_devices_and_every_key_exists():
    cases = {
        "Draco": "draco", "DRACO": "draco",
        "DWARF 3": "dwarf_3", "Dwarf3": "dwarf_3", "DWARF III": "dwarf_3",
        "DWARF Mini": "dwarf_mini",
        "S50_15e7e390": "seestar_s50", "Seestar S50": "seestar_s50",
        "Seestar S30": "seestar_s30", "S30 Pro": "seestar_s30_pro",
        "S30_pro_abc": "seestar_s30_pro",
    }
    for tel, key in cases.items():
        assert devices.preset_key(tel) == key, tel
        assert key in DEVICE_PRESETS
    assert devices.preset_key("ASIAIR") is None
    assert devices.preset_key("") is None
    assert devices.preset_key(None) is None

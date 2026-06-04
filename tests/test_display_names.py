# tests/test_display_names.py
import pytest
from astronamigo.display_names import (
    _filename_object_name,
    _filename_date_from_name_and_mtime,
    display_name_for_name,
)


class TestObjectName:
    # Single-object: spaces stripped, alphanumerics joined
    def test_simple_messier(self):
        assert _filename_object_name("M51", 1) == "M51"

    def test_messier_with_internal_space(self):
        assert _filename_object_name("M 51", 1) == "M51"

    def test_ngc_strips_space(self):
        assert _filename_object_name("NGC 2903", 1) == "NGC2903"

    # Apostrophes stripped
    def test_apostrophe_stripped(self):
        assert _filename_object_name("Markarian's Chain", 1) == "MarkariansChain"

    # Multi-object folders: underscore separator
    def test_two_messier_objects(self):
        assert _filename_object_name("M81 M82", 2) == "M81_M82"

    def test_two_messier_objects_with_extra_space(self):
        # Folder might have inconsistent spacing
        assert _filename_object_name("M108  M97", 2) == "M108_M97"

    # Parentheticals folded as suffix
    def test_parenthetical_suffix(self):
        assert _filename_object_name("Veil Nebula (E)", 1) == "VeilNebulaE"

    # "mosaic" keyword pulled off with underscore
    def test_mosaic_suffix(self):
        assert _filename_object_name("M42 mosaic", 1) == "M42_mosaic"

    def test_mosaic_parenthetical(self):
        assert _filename_object_name(
            "North America Nebula (mosaic)", 1
        ) == "NorthAmericaNebula_mosaic"

    def test_mosaic_with_apostrophe(self):
        assert _filename_object_name(
            "Markarian's Chain (mosaic)", 1
        ) == "MarkariansChain_mosaic"

    # Underscore in source folder (e.g. M42_mosaic)
    def test_underscore_folder(self):
        assert _filename_object_name("M42_mosaic", 1) == "M42_mosaic"


class TestDateExtraction:
    def test_seestar_embedded_date(self):
        # Seestar filenames have YYYYMMDD-HHMMSS pattern
        d = _filename_date_from_name_and_mtime(
            "Light_M 51_30.0s_IRCUT_20260514-225000.fit",
            mtime=0.0,
        )
        assert d == "20260514"

    def test_fallback_to_mtime(self):
        # Non-Seestar filename → falls back to mtime
        # mtime 1716163200 is 2024-05-20 in UTC; use a known reference
        import datetime
        mtime = datetime.datetime(2026, 5, 14, 22, 30).timestamp()
        d = _filename_date_from_name_and_mtime("processed.png", mtime=mtime)
        assert d == "20260514"


class TestDisplayName:
    def test_fits_is_stacked(self):
        name = display_name_for_name(
            "Light_M 51_30.0s_IRCUT_20260514-225000.fit",
            mtime=0.0, folder="M51", n_slugs=1,
        )
        assert name == "M51_stacked_20260514.fit"

    def test_jpg_is_processed(self):
        name = display_name_for_name(
            "whatever.jpg", mtime=0.0, folder="M51", n_slugs=1,
        )
        # mtime=0.0 → 19700101, but that's the fallback we expect
        assert name.startswith("M51_processed_")
        assert name.endswith(".jpg")

    def test_multi_object_folder(self):
        name = display_name_for_name(
            "stack.fit", mtime=0.0, folder="M81 M82", n_slugs=2,
        )
        assert name.startswith("M81_M82_stacked_")


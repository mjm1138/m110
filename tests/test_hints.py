"""Finished / intermediate filename hints (#17 generalization): the shared,
user-editable vocabulary + that the three consumers honor it."""
from pathlib import Path

import pytest

from m110 import build_images, config, hints, ingest, siril


@pytest.fixture
def clean_settings(tmp_path, monkeypatch):
    """Point settings at an empty per-test file so hints start at defaults."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


# ── the hint set itself ───────────────────────────────────────────────────────

def test_defaults_when_unset(clean_settings):
    h = hints.get_hints()
    assert h["finished"] == hints.DEFAULT_FINISHED
    assert h["intermediate"] == hints.DEFAULT_INTERMEDIATE
    assert hints.is_finished_name("M27_spcc_processed.png")
    assert not hints.is_finished_name("NGC6992.png")          # no default keyword
    assert hints.is_intermediate_name("starless_M27.tif")


def test_case_insensitive_substring(clean_settings):
    assert hints.is_finished_name("Andromeda_FINAL.jpg")
    assert hints.is_finished_name("x_Processed_y.tif")


def test_override_replaces_and_persists(clean_settings):
    hints.set_hints(["export"], ["mask"])
    h = hints.get_hints()
    assert h["finished"] == ["export"]
    assert h["intermediate"] == ["mask"]
    # replace, not merge: a removed default no longer matches
    assert not hints.is_finished_name("M27_processed.png")
    assert hints.is_finished_name("M27_export.png")


def test_set_hints_cleans_input(clean_settings):
    hints.set_hints(["  Final ", "final", "", "Export"], [])
    h = hints.get_hints()
    assert h["finished"] == ["final", "export"]               # trimmed, lowered, de-duped
    assert h["intermediate"] == []


def test_empty_intermediate_vetoes_nothing(clean_settings):
    hints.set_hints(["processed"], [])
    assert not hints.is_intermediate_name("starless.png")


# ── consumers honor a user-added keyword ──────────────────────────────────────

def test_siril_classify_honors_added_keyword(clean_settings):
    # A stranger's finished stack with no default keyword misclassifies by default…
    assert siril._classify(Path("/x/NGC6992_export.fit"), "NGC6992") is None
    # …until they add "export" to the finished hints.
    hints.set_hints(hints.DEFAULT_FINISHED + ["export"], hints.DEFAULT_INTERMEDIATE)
    kind, _dest = siril._classify(Path("/x/NGC6992_export.fit"), "NGC6992")
    assert kind == "stack"


def test_siril_classify_intermediate_veto(clean_settings):
    # A raster is normally a render, but a star-layer keyword vetoes it.
    assert siril._classify(Path("/x/M27_processed.png"), "M27")[0] == "render"
    assert siril._classify(Path("/x/starless_M27.png"), "M27") is None


def test_ingest_finished_raster_honors_hints(clean_settings):
    assert not ingest._is_finished_raster("NGC6992_export.png")
    hints.set_hints(hints.DEFAULT_FINISHED + ["export"], hints.DEFAULT_INTERMEDIATE)
    assert ingest._is_finished_raster("NGC6992_export.png")


def test_ingest_finished_raster_intermediate_veto(clean_settings):
    # New consistency: a loose star-layer raster is not claimed as finished.
    assert ingest._is_finished_raster("M27_processed.png")
    assert not ingest._is_finished_raster("starless_processed.png")


def test_build_images_final_fit_honors_hints(clean_settings):
    # _is_intermediate_fit uses the finished vocabulary as a veto.
    assert build_images._is_intermediate_fit(Path("/x/M27_crop.fit"))
    assert not build_images._is_intermediate_fit(Path("/x/M27_crop_processed.fit"))
    hints.set_hints(["export"], hints.DEFAULT_INTERMEDIATE)
    assert not build_images._is_intermediate_fit(Path("/x/M27_crop_export.fit"))

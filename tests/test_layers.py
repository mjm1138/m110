"""Multi-layer FITS (Draco "SHO": HO primary + an `SOO` image extension).

Synthetic fixtures shaped like DwarfLab's real file (firmware 1.1.0.55): a 3-plane
uint16 primary written with BZERO=32768 carrying the full header, and an extension
that repeats only FILTER / EXPTIME / STACKCNT. Temp files only.
"""
import numpy as np
import pytest
from astropy.io import fits

from m110 import layers
from tests._helpers import make_sho


def test_lists_both_layers_from_headers(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    got = layers.image_layers(path)
    assert [(l.index, l.name, l.filter, l.frames, l.exptime) for l in got] == [
        (0, "PRIMARY", "HO", 20, 6000.0), (1, "SOO", "SO", 39, 11700.0)]
    assert [l.label for l in got] == ["HO 20×", "SO 39×"]
    assert layers.is_multi_layer(path)


def test_an_ordinary_file_is_one_layer_and_junk_is_none(tmp_path):
    one = tmp_path / "one.fits"
    fits.PrimaryHDU(np.zeros((4, 4), dtype=np.float32)).writeto(one)
    assert [l.name for l in layers.image_layers(one)] == ["PRIMARY"]
    assert not layers.is_multi_layer(one)
    junk = tmp_path / "junk.fits"
    junk.write_bytes(b"not a fits file")
    assert layers.image_layers(junk) == []


def test_a_table_extension_is_not_a_layer(tmp_path):
    path = tmp_path / "t.fits"
    col = fits.Column(name="x", format="E", array=np.arange(3, dtype=np.float32))
    fits.HDUList([fits.PrimaryHDU(np.zeros((4, 4), dtype=np.float32)),
                  fits.BinTableHDU.from_columns([col])]).writeto(path)
    assert len(layers.image_layers(path)) == 1


def test_layer_header_inherits_the_primary_and_the_layer_wins(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    h = layers.read_layer_header(path, 1)
    assert (h["FILTER"], h["STACKCNT"], h["EXPTIME"]) == ("SO", 39, 11700.0)
    assert (h["OBJECT"], h["GAIN"], h["TELESCOP"]) == ("C 20", 120, "Draco")
    assert h[layers.LAYER_CARD] == "SOO"
    for structural in ("XTENSION", "EXTNAME", "NAXIS", "BITPIX", "PCOUNT"):
        assert structural not in h
    hist = [str(x) for x in h["HISTORY"]]
    assert "device stack" in hist and any("layer SOO (HDU 1)" in x for x in hist)


def test_the_primary_layer_header_carries_no_layer_stamp(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    h = layers.read_layer_header(path, 0)
    assert h["FILTER"] == "HO" and layers.LAYER_CARD not in h


@pytest.mark.parametrize("index", [0, 1])
def test_write_layer_is_pixel_exact_and_single_image(tmp_path, index):
    path, ho, so = make_sho(tmp_path / "sho.fits")
    dest = layers.write_layer(path, index, tmp_path / "out.fits")
    with fits.open(dest) as out:
        assert len(out) == 1
        assert out[0].data.dtype == np.uint16
        assert np.array_equal(out[0].data, so if index else ho)
        assert out[0].header["FILTER"] == ("SO" if index else "HO")
        assert out[0].header["OBJECT"] == "C 20"
    assert not (tmp_path / "out.fits.part").exists()


def test_write_layer_leaves_the_source_untouched(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    before = path.read_bytes()
    layers.write_layer(path, 1, tmp_path / "so.fits")
    assert path.read_bytes() == before


def test_write_layer_rejects_a_missing_hdu_and_leaves_nothing(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    with pytest.raises(IndexError):
        layers.write_layer(path, 5, tmp_path / "x.fits")
    assert not (tmp_path / "x.fits").exists()
    assert not (tmp_path / "x.fits.part").exists()


def test_tag_is_filename_safe():
    assert layers.Layer(1, "SOO", filter="S II/O III").tag == "S-II-O-III"
    assert layers.Layer(2, "SOO").tag == "SOO"


def test_describe_names_the_layers_for_a_tooltip(tmp_path):
    path, _, _ = make_sho(tmp_path / "sho.fits")
    found = layers.image_layers(path)
    want = "2 layers — HO 20 frames · SO 39 frames"
    assert layers.describe(found) == want
    assert layers.describe([lay.as_dict() for lay in found]) == want
    assert layers.describe(found[:1]) == "" and layers.describe(None) == ""

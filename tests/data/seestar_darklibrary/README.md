# Seestar S50 master darks (real, unmodified)

Five master darks exactly as a Seestar S50 wrote them to
`<volume>/darklibrary/20s/` on 2026-10-15…17 (the first nights its firmware kept
a dark library), gzipped with `gzip -9 -n` (byte-identical when unpacked).

They carry EXPTIME / GAIN / XBINNING / CCD-TEMP / STACKCNT / FILTER='dark' and **no**
IMAGETYP, DATE-OBS or TELESCOP (and a leftover WCS from whatever target was
being solved). `tools/make_test_corpus.py` unpacks them into the store's
`Calibration/` and the fake device mount's `darklibrary/`; the
`.jpg` previews the device writes beside them are regenerated, not stored.

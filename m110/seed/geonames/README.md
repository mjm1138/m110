# Bundled populated-places data (light-dome glow map)

`cities1000.tsv.gz` — a trimmed subset of **GeoNames** `cities1000` (all populated
places with population ≥ 1000, worldwide), used by `m110/glow.py` to estimate the
local light-pollution "glow" floor for session planning. Columns:
`asciiname · latitude · longitude · population · country`.

**License:** GeoNames is **CC-BY 4.0** — attribution is in the repo `NOTICE`.

**Regenerate** (build-time; needs a one-time network download):

```bash
python tools/gen_geonames.py            # download + trim + write cities1000.tsv.gz
```

Runtime stays offline — only the trimmed, gzipped file ships and is read by
`glow.load_towns()`. If the file is absent, the glow auto-map degrades gracefully
(no domes computed) and the user relies on the Bortle anchor / a hand-imported mask.

> Chosen extract is `cities1000`, **not** `cities15000`: nearby towns of a few
> thousand dominate skyglow, and a 15k floor would drop the sources that matter most
> to rural/dark-site users (and the sparser southern hemisphere). VIIRS radiance is
> the deferred v2 upgrade.

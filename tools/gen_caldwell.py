#!/usr/bin/env python3
"""Generate bundled Caldwell data (dev/build-time tool — needs astroquery + network).

From the canonical Caldwell list (designation + common name + type, transcribed
from Wikipedia's Caldwell catalogue), resolve coordinates + angular size via Simbad
and emit:
  * append ~109 entries to m110/seed/objects.toml   (the object reference dataset)
  * m110/seed/catalogs/caldwell.toml                (membership: slug → "C#")

Also rewrites m110/seed/catalogs/messier.toml into the uniform [members] table
format. Runtime stays offline — only the bundled output ships.

    python tools/gen_caldwell.py        # writes the bundled files in place
"""
from __future__ import annotations

import tomllib
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "m110" / "seed"

# caldwell #, primary designation (for Simbad), common name, Wikipedia type
_CALDWELL = """\
1|NGC 188|Polarissima Cluster|Open Cluster
2|NGC 40|Bow-Tie Nebula|Planetary Nebula
3|NGC 4236||Barred Spiral Galaxy
4|NGC 7023|Iris Nebula|Open Cluster and Nebula
5|IC 342|Hidden Galaxy|Spiral Galaxy
6|NGC 6543|Cat's Eye Nebula|Planetary Nebula
7|NGC 2403||Spiral Galaxy
8|NGC 559||Open Cluster
9|Sh2-155|Cave Nebula|Nebula
10|NGC 663||Open Cluster
11|NGC 7635|Bubble Nebula|Nebula
12|NGC 6946|Fireworks Galaxy|Spiral Galaxy
13|NGC 457|Owl Cluster|Open Cluster
14|NGC 869|Double Cluster|Open Cluster
15|NGC 6826|Blinking Planetary|Planetary Nebula
16|NGC 7243||Open Cluster
17|NGC 147||Dwarf Spheroidal Galaxy
18|NGC 185||Dwarf Spheroidal Galaxy
19|IC 5146|Cocoon Nebula|Open Cluster and Nebula
20|NGC 7000|North America Nebula|Nebula
21|NGC 4449||Irregular Galaxy
22|NGC 7662|Blue Snowball|Planetary Nebula
23|NGC 891|Silver Sliver Galaxy|Spiral Galaxy
24|NGC 1275|Perseus A|Elliptical Galaxy
25|NGC 2419||Globular Cluster
26|NGC 4244||Spiral Galaxy
27|NGC 6888|Crescent Nebula|Nebula
28|NGC 752||Open Cluster
29|NGC 5005||Spiral Galaxy
30|NGC 7331||Spiral Galaxy
31|IC 405|Flaming Star Nebula|Nebula
32|NGC 4631|Whale Galaxy|Barred Spiral Galaxy
33|NGC 6992|East Veil Nebula|Supernova Remnant
34|NGC 6960|West Veil Nebula|Supernova Remnant
35|NGC 4889|Coma B|Elliptical Galaxy
36|NGC 4559||Spiral Galaxy
37|NGC 6885||Open Cluster
38|NGC 4565|Needle Galaxy|Spiral Galaxy
39|NGC 2392|Eskimo Nebula|Planetary Nebula
40|NGC 3626||Lenticular Galaxy
41|Mel 25|Hyades|Open Cluster
42|NGC 7006||Globular Cluster
43|NGC 7814||Spiral Galaxy
44|NGC 7479|Superman Galaxy|Barred Spiral Galaxy
45|NGC 5248||Spiral Galaxy
46|NGC 2261|Hubble's Variable Nebula|Nebula
47|NGC 6934||Globular Cluster
48|NGC 2775||Spiral Galaxy
49|NGC 2237|Rosette Nebula|Nebula
50|NGC 2244|Satellite Cluster|Open Cluster
51|IC 1613||Irregular Galaxy
52|NGC 4697||Elliptical Galaxy
53|NGC 3115|Spindle Galaxy|Lenticular Galaxy
54|NGC 2506||Open Cluster
55|NGC 7009|Saturn Nebula|Planetary Nebula
56|NGC 246|Skull Nebula|Planetary Nebula
57|NGC 6822|Barnard's Galaxy|Irregular Galaxy
58|NGC 2360|Caroline's Cluster|Open Cluster
59|NGC 3242|Ghost of Jupiter|Planetary Nebula
60|NGC 4038|Antennae Galaxies|Interacting Galaxy
61|NGC 4039|Antennae Galaxies|Interacting Galaxy
62|NGC 247||Spiral Galaxy
63|NGC 7293|Helix Nebula|Planetary Nebula
64|NGC 2362|Tau Canis Majoris Cluster|Open Cluster and Nebula
65|NGC 253|Sculptor Galaxy|Spiral Galaxy
66|NGC 5694||Globular Cluster
67|NGC 1097||Barred Spiral Galaxy
68|NGC 6729|R CrA Nebula|Nebula
69|NGC 6302|Bug Nebula|Planetary Nebula
70|NGC 300|Sculptor Pinwheel Galaxy|Spiral Galaxy
71|NGC 2477||Open Cluster
72|NGC 55|String of Pearls Galaxy|Barred Spiral Galaxy
73|NGC 1851||Globular Cluster
74|NGC 3132|Eight Burst Nebula|Planetary Nebula
75|NGC 6124||Open Cluster
76|NGC 6231||Open Cluster and Nebula
77|NGC 5128|Centaurus A|Elliptical Galaxy
78|NGC 6541||Globular Cluster
79|NGC 3201||Globular Cluster
80|NGC 5139|Omega Centauri|Globular Cluster
81|NGC 6352||Globular Cluster
82|NGC 6193||Open Cluster
83|NGC 4945||Barred Spiral Galaxy
84|NGC 5286||Globular Cluster
85|IC 2391|Omicron Velorum Cluster|Open Cluster
86|NGC 6397||Globular Cluster
87|NGC 1261||Globular Cluster
88|NGC 5823||Open Cluster
89|NGC 6087|S Normae Cluster|Open Cluster
90|NGC 2867||Planetary Nebula
91|NGC 3532|Wishing Well Cluster|Open Cluster
92|NGC 3372|Eta Carinae Nebula|Nebula
93|NGC 6752|Great Peacock Globular|Globular Cluster
94|NGC 4755|Jewel Box|Open Cluster
95|NGC 6025||Open Cluster
96|NGC 2516|Southern Beehive Cluster|Open Cluster
97|NGC 3766|Pearl Cluster|Open Cluster
98|NGC 4609||Open Cluster
99|Coalsack Nebula|Coalsack Nebula|Dark Nebula
100|IC 2944|Lambda Centauri Nebula|Open Cluster and Nebula
101|NGC 6744||Spiral Galaxy
102|IC 2602|Theta Car Cluster|Open Cluster
103|NGC 2070|Tarantula Nebula|Open Cluster and Nebula
104|NGC 362||Globular Cluster
105|NGC 4833||Globular Cluster
106|NGC 104|47 Tucanae|Globular Cluster
107|NGC 6101||Globular Cluster
108|NGC 4372||Globular Cluster
109|NGC 3195||Planetary Nebula
"""


def _our_type(wiki: str) -> str:
    t = wiki.lower()
    if "galaxy" in t:
        return "galaxy"
    if "globular" in t:
        return "globular"
    if "open cluster" in t:                 # incl. "open cluster and nebula"
        return "open_cluster"
    if "planetary" in t:
        return "planetary"
    if "supernova remnant" in t:
        return "emission_snr"
    if "dark nebula" in t:
        return "dark_nebula"
    if "nebula" in t:
        return "emission"
    return "unknown"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("/", "-")


def _toml_str(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    from astroquery.simbad import Simbad
    rows = []
    for line in _CALDWELL.strip().splitlines():
        num, desig, common, wtype = line.split("|")
        rows.append({"c": f"C{num}", "id": desig, "name": common,
                     "type": _our_type(wtype)})

    # Resolve coords + size via Simbad (batch; match back by the input name).
    sim = Simbad()
    sim.add_votable_fields("V", "dim")
    names = [r["id"] for r in rows]
    res = sim.query_objects(names)
    by_name = {}
    for row in res:
        # user_specified_id is space-padded to a fixed column width — strip it.
        key = str(row["user_specified_id"]).strip() if "user_specified_id" in res.colnames else None
        by_name[key] = row

    out_objs, members, missing = [], [], []
    for i, r in enumerate(rows):
        row = by_name.get(r["id"])
        ra = dec = size = mag = None
        if row is not None:
            try:
                if row["ra"] is not None and not getattr(row["ra"], "mask", False):
                    ra = round(float(row["ra"]), 5)
                    dec = round(float(row["dec"]), 5)
            except Exception:
                pass
            try:
                maj = float(row["galdim_majaxis"]); minr = float(row["galdim_minaxis"])
                if maj == maj:                  # not NaN
                    size = f"{maj:.0f}'×{minr:.0f}'" if minr == minr else f"{maj:.0f}'"
            except Exception:
                pass
            try:
                v = float(row["V"])
                if v == v:
                    mag = round(v, 1)
            except Exception:
                pass
        if ra is None:
            missing.append(r["id"])
        slug = _slug(r["id"])
        members.append((slug, r["c"]))
        out_objs.append((slug, r["id"], r["name"], r["type"], mag, size, ra, dec))

    # --- append to objects.toml (skip slugs already present) ---
    obj_path = SEED / "objects.toml"
    existing = set(tomllib.load(open(obj_path, "rb"))["object"])
    blocks = ["", "# ── Caldwell catalogue objects (generated; coords/size via Simbad) ──"]
    added = 0
    for slug, oid, name, otype, mag, size, ra, dec in out_objs:
        if slug in existing:
            continue
        added += 1
        blocks.append(f"\n[object.{slug}]")
        blocks.append(f"id = {_toml_str(oid)}")
        if name:
            blocks.append(f"name = {_toml_str(name)}")
        blocks.append(f"type = {_toml_str(otype)}")
        if mag is not None:
            blocks.append(f"magnitude = {mag}")
        if size:
            blocks.append(f"size = {_toml_str(size)}")
        if ra is not None:
            blocks.append(f"ra_deg = {ra}")
            blocks.append(f"dec_deg = {dec}")
    with obj_path.open("a") as f:
        f.write("\n".join(blocks) + "\n")

    # --- caldwell.toml membership table ---
    cw = ['name = "Caldwell"',
          'description = "Patrick Moore\'s 109 bright deep-sky objects the Messier '
          'list omits (no Messier overlap)."', "", "[members]"]
    for slug, c in members:
        cw.append(f"{_member_key(slug)} = {_toml_str(c)}")
    (SEED / "catalogs" / "caldwell.toml").write_text("\n".join(cw) + "\n")

    # --- regenerate messier.toml into the [members] table format ---
    _rewrite_messier()

    print(f"Caldwell: {len(rows)} objects, {added} appended to objects.toml, "
          f"{len(members)} members.")
    if missing:
        print(f"  coords unresolved ({len(missing)}): {missing}")


def _member_key(slug: str) -> str:
    # bare key if it's a safe TOML bare key, else quoted
    import re
    return slug if re.fullmatch(r"[A-Za-z0-9_-]+", slug) else _toml_str(slug)


def _rewrite_messier():
    mp = SEED / "catalogs" / "messier.toml"
    data = tomllib.load(open(mp, "rb"))
    members = data["members"]                  # current list form
    obj = tomllib.load(open(SEED / "objects.toml", "rb"))["object"]
    lines = [f'name = {_toml_str(data["name"])}',
             f'description = {_toml_str(data["description"])}', "", "[members]"]
    for slug in members:
        desig = obj.get(slug, {}).get("id", slug)
        lines.append(f"{_member_key(slug)} = {_toml_str(desig)}")
    mp.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

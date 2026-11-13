"""A stand-in for the `stackhammer` binary, for tests.

It speaks the same contract M110 reads (schema 5: `settings`, `prepare`, `plan`,
`run --json`, `clean`), with shapes taken from the real binary's read-only
output, and decides everything from the folders it is pointed at — so a test
arranges files, not mocks. `tests/_helpers.install_fake_stackhammer` copies this
file to an executable named `stackhammer`.

What it records, for assertions: every invocation's argv is appended to
`FAKE_STACKHAMMER_LOG` (one JSON list per line) when that variable is set.

Knobs (environment): `FAKE_STACKHAMMER_SCHEMA` (default 5),
`FAKE_STACKHAMMER_RUN` = `ok` | `error` | `cancelled`.
"""
import json
import os
import sys

FITS = (".fit", ".fits", ".fts")
RECIPE = ("lights_", "pp_lights_", "bkg_pp_lights_")
SCHEMA = int(os.environ.get("FAKE_STACKHAMMER_SCHEMA", "5"))

RUN_SETTINGS = [
    {"option": "filter-round", "value": 95, "why": "the share of frames kept"},
    {"option": "filter-fwhm", "value": 98, "why": "the share of frames kept"},
    {"option": "filter-bkg", "value": 98, "why": "the share of frames kept"},
    {"option": "filter-nbstars", "value": 95, "why": "the share of frames kept"},
    {"option": "normalization", "value": "photometric",
     "choices": ["addscale", "photometric"], "why": "frame scales from star fluxes"},
    {"option": "local-norm", "value": True, "why": "matches each frame's background"},
    {"option": "neutral-background", "value": True, "why": "one sky level per channel"},
    {"option": "rejection", "value": "winsorized",
     "choices": ["none", "sigma", "winsorized"], "why": "Winsorized sigma clipping"},
    {"option": "rejection-noise", "value": "frame", "choices": ["pixel", "frame"],
     "why": "each value against its own frame's noise"},
    {"option": "low", "value": 3, "why": "threshold below, in sigma"},
    {"option": "high", "value": 3, "why": "threshold above, in sigma"},
    {"option": "weight", "value": "noise-fwhm",
     "choices": ["none", "noise", "fwhm", "psf", "noise-fwhm"],
     "why": "noise and star width together"},
    {"option": "feather", "value": 30, "why": "fades frames out at their edges"},
    {"option": "drizzle", "value": False, "why": "off: these frames are debayered"},
    {"option": "drizzle-scale", "value": 1.5, "why": "output pixels per input pixel"},
    {"option": "pixfrac", "value": 1, "why": "droplet size"},
    {"option": "drizzle-weights", "value": "noise", "choices": ["noise", "coverage"],
     "why": "the least noise"},
]
PREPARATION = [
    {"option": "prepare", "value": False, "why": "needs a lights folder"},
    {"option": "calibration", "value": True, "why": "applies matching frames"},
    {"option": "cosmetic", "value": True, "why": "replaces hot pixels"},
    {"option": "equalize-cfa", "value": True, "why": "levels the master flat"},
    {"option": "bias-level", "value": 0, "why": "0 is automatic"},
    {"option": "background", "value": False, "why": "off: local normalization"},
    {"option": "compress", "value": False, "why": "off: fastest to stack"},
    {"option": "clean", "value": True, "why": "deletes this run's intermediates"},
]


def fail(message, code=1):
    sys.stderr.write(f"Error: {message}\n")
    sys.exit(code)


def emit(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


def fits_in(folder):
    try:
        return sorted(n for n in os.listdir(folder) if n.lower().endswith(FITS)
                      and not n.startswith("."))
    except OSError:
        return []


def sequences(process):
    try:
        return sorted(n[:-4] for n in os.listdir(process)
                      if n.endswith(".seq") and n[:-4] in RECIPE)
    except OSError:
        return []


def cmd_settings(_args):
    emit({"schemaVersion": SCHEMA, "settings": RUN_SETTINGS, "preparation": PREPARATION})


def cmd_prepare(args):
    working = os.path.abspath(args[0])
    flags = args[1:]
    lights = os.path.join(working, "lights")
    names = fits_in(lights)
    if not names:
        fail(f"no FITS lights in {lights}")
    process = os.path.join(working, "process")
    existing = sequences(process)
    background = ("--background" in flags
                  or ("--no-background" not in flags and "bkg_pp_lights_" in existing))
    sequence = "bkg_pp_lights_" if background else "pp_lights_"
    drizzle, compress = "--drizzle" in flags, "--compress" in flags
    calibration = "--no-calibration" not in flags
    darks = fits_in(os.path.join(working, "darks"))
    use_dark = calibration and bool(darks)

    link = {"name": "link", "weight": 1, "why": "makes the lights a Siril sequence",
            "commands": [f'cd "{lights}"', "link lights -out=../process",
                         "cd ../process"]}
    if os.path.exists(os.path.join(working, ".fake_check")):
        link["check"] = {"file": "lights_conversion.txt", "names": names}
    calibrate = "calibrate lights_"
    if use_dark:
        calibrate += f' "-dark={os.path.join(working, "darks", darks[0])}"'
        if "--no-cosmetic" not in flags:
            calibrate += " -cc=dark"
    if not drizzle:
        calibrate += " -debayer"
    steps = [link]
    if compress:
        steps.append({"name": "compress", "weight": 0, "why": "Rice compression",
                      "commands": ["setcompress 1 -type=rice 16"]})
    steps.append({"name": "calibrate", "weight": 9.5, "why": "calibrates the lights",
                  "commands": [calibrate]})
    if background:
        steps.append({"name": "background", "weight": 20.5, "why": "subtracts a plane",
                      "commands": ["seqsubsky pp_lights_ 1 -samples=10 -tolerance=2.0"]})
    steps.append({"name": "plate solve", "weight": 24.7, "why": "solves every frame",
                  "commands": [f"seqplatesolve {sequence} -nocache -force "
                               "-disto=ps_distortion -order=4 -radius=2", "close"]})

    solved = bool(existing) and existing[-1] == sequence and sequence in existing
    bias = flags[flags.index("--bias-level") + 1] if "--bias-level" in flags else "0"
    emit({
        "schemaVersion": SCHEMA,
        "workingDirectory": working,
        "processDirectory": process,
        "lights": {"path": lights, "frames": len(names), "unreadable": [],
                   "exposures": [{"seconds": 20, "frames": len(names)}],
                   "liveTimeSeconds": 20 * len(names),
                   "instruments": ["Seestar S50"],
                   "sizes": [{"width": 1080, "height": 1920, "channels": 1,
                              "bitpix": 16, "bayerPattern": "GRBG",
                              "frames": len(names)}]},
        "sequence": sequence,
        "existing": existing,
        "steps": steps,
        "calibration": {
            "applied": use_dark, "applicable": True,
            "folders": ([{"kind": "darks", "path": os.path.join(working, "darks"),
                          "files": len(darks), "summary": f"{len(darks)} dark(s)",
                          "notes": [], "sets": [{"id": 1, "files": darks}]}]
                        if darks else []),
            "subsets": [{"label": f"{len(names)} lights", "capture": "nina",
                         "frames": len(names), "pass": 1, "notes": [],
                         **({"dark": {"argument": os.path.join(working, "darks", darks[0]),
                                      "built": False, "why": "matches exposure and gain"}}
                            if use_dark else {})}],
            "summary": [f"{len(names)} lights: "
                        + ("dark " + darks[0] if use_dark else "no calibration frames")],
        },
        "settings": [
            {"option": "prepare", "value": not solved,
             "why": "process already holds it" if solved else "no plate-solved sequence yet"},
            {"option": "calibration", "value": calibration, "why": "matching frames"},
            {"option": "cosmetic", "value": "--no-cosmetic" not in flags, "why": "hot pixels"},
            {"option": "equalize-cfa", "value": "--no-equalize-cfa" not in flags,
             "why": "levels the flat"},
            {"option": "bias-level", "value": float(bias), "why": "0 is automatic"},
            {"option": "background", "value": background, "why": "a plane per frame"},
            {"option": "compress", "value": compress, "why": "Rice compression"},
            {"option": "clean", "value": True, "why": "deletes intermediates"},
        ],
        "warnings": (["no dark matches their exposure and gain"]
                     if os.path.exists(os.path.join(working, ".fake_warning")) else []),
    })


def option(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def plan_object(process, args):
    seq = option(args, "--seq", "bkg_pp_lights_")
    path = os.path.join(process, f"{seq}.seq")
    if not os.path.exists(path):
        fail(f"no sequence {seq} in {process}")
    total = len([n for n in fits_in(process) if n.startswith(seq)]) or 4
    fwhm = float(option(args, "--filter-fwhm", 98))
    kept = max(0, total - (1 if fwhm < 98 else 0))
    if kept == 0:
        fail("the filters keep no frames")
    cfa = os.path.exists(os.path.join(process, ".cfa"))
    settings = [dict(s) for s in RUN_SETTINGS]
    for s in settings:
        if s["option"] == "drizzle" and cfa:
            s.update(value=True, why="required: these frames are undebayered CFA")
        if s["option"].startswith("filter-") and option(args, "--" + s["option"]):
            s["value"] = float(option(args, "--" + s["option"]))
    return {
        "schemaVersion": SCHEMA,
        "processDirectory": process,
        "sequence": {"name": seq, "path": path, "version": 6, "referenceKept": True},
        "selection": {"total": total, "included": total, "kept": list(range(1, kept + 1)),
                      "criteria": [{"criterion": "fwhm", "percent": fwhm, "pool": total,
                                    "threshold": 5.7, "keeps": "below", "passing": kept,
                                    "includedFailing": total - kept}]},
        "keptFrames": {"sizes": [], "exposures": [{"seconds": 20, "frames": kept}],
                       "liveTimeSeconds": 20 * kept, "withoutWCS": [],
                       "withoutDistortion": [1, 2], "unreadable": []},
        "framing": {"width": 1200, "height": 2000, "centerRA": 10.0, "centerDec": 41.0,
                    "arcsecPerPixel": 2.39, "coveredFraction": 0.9,
                    "medianDepth": kept, "maximumDepth": kept},
        "warnings": [],
        "notes": ["run can stack fewer: frames local normalization can't fit stay out"],
        "settings": settings,
    }


def cmd_plan(args):
    emit(plan_object(os.path.abspath(args[0]), args[1:]))


def line(obj):
    print(json.dumps(obj, sort_keys=True), flush=True)


def cmd_run(args):
    process = os.path.abspath(args[0])
    output = os.path.abspath(option(args, "--output"))
    plan = plan_object(process, args[1:])
    line({"event": "plan", "plan": plan})
    line({"event": "stages", "stages": [{"name": "geometry", "weight": 1},
                                        {"name": "integration", "weight": 9}]})
    line({"event": "stage", "stage": "geometry", "index": 0, "fraction": 0})
    mode = os.environ.get("FAKE_STACKHAMMER_RUN", "ok")
    if mode == "error":
        line({"event": "error", "message": "the GPU ran out of memory"})
        sys.exit(1)
    if mode == "cancelled":
        line({"event": "cancelled"})
        sys.exit(130)
    line({"event": "progress", "stage": "integration", "done": 1, "total": 1,
          "fraction": 0.9})
    name = "M_51_4x20sec_2026-03-20_0h01m_2026-11-12_0936_og"
    os.makedirs(os.path.join(output, "stackhammer", name), exist_ok=True)
    path = os.path.join(output, name + ".fit")
    with open(path, "w") as f:
        f.write("stack")
    line({"event": "result", "path": path, "name": name, "frames": 4,
          "width": 1200, "height": 2000, "bands": 1, "skipped": [], "leftOut": [3],
          "medianDepth": 4, "maximumDepth": 4, "seconds": [],
          "depthPath": os.path.join(output, "stackhammer", name, "depth.fits"),
          "summary": ["4 frames, 1 min 20 s"]})


def cmd_clean(args):
    working = os.path.abspath(args[0])
    process = os.path.join(working, "process")
    removed, size = [], 0
    for name in sorted(os.listdir(process)) if os.path.isdir(process) else []:
        path = os.path.join(process, name)
        if os.path.isfile(path) and name.startswith(RECIPE + ("ps_distortion",)):
            size += os.path.getsize(path)
            os.remove(path)
            removed.append(name)
    gone = os.path.isdir(process) and not os.listdir(process)
    if gone:
        os.rmdir(process)
    emit({"processDirectory": process, "removed": removed, "bytes": size,
          "kept": [], "removedDirectory": gone})


def main():
    argv = sys.argv[1:]
    log = os.environ.get("FAKE_STACKHAMMER_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps(argv) + "\n")
    if argv[:1] == ["--version"]:
        print("0.0.0")
        return
    command, rest = argv[0], [a for a in argv[1:] if a != "--json"]
    handler = {"settings": cmd_settings, "prepare": cmd_prepare, "plan": cmd_plan,
               "run": cmd_run, "clean": cmd_clean}.get(command)
    if handler is None:
        fail(f"unknown subcommand {command}", 64)
    handler(rest)


if __name__ == "__main__":
    main()

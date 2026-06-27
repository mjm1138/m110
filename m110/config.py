"""Runtime configuration for M110.

The app owns its own data store (default ``~/Documents/M110``), resolved
in order from: the ``M110_DATA_ROOT`` env var, the saved preference
(``~/.m110/settings.json``), then the default. Qt-free so the engine
stays headless — the UI Preferences dialog calls ``save_data_root()`` and
prompts a restart.
"""
from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path

APP_CONFIG_DIR = Path.home() / ".m110"
SETTINGS_FILE = APP_CONFIG_DIR / "settings.json"
DEFAULT_DATA_ROOT = Path.home() / "Documents" / "M110"
SEED_DIR = Path(__file__).resolve().parent / "seed"
GUIDANCE_DIR = Path(__file__).resolve().parent / "guidance"   # bundled playbooks

INTERNAL_DIRNAME = ".m110_internal_data"

# Directory skeleton created under a data root. Two visible axes — Objects/
# (catalog-object journals + future per-object artifacts) and Images/ (per
# capture-target content) — plus Media/, the ingest Inbox/, and the hidden
# .m110_internal_data/ holding all machine state.
_SUBDIRS = [
    "Objects", "Images", "Media", "Inbox",
    INTERNAL_DIRNAME,
    f"{INTERNAL_DIRNAME}/derived",
    f"{INTERNAL_DIRNAME}/renders/hero",
    f"{INTERNAL_DIRNAME}/profiles",
]
# Static files copied verbatim from the bundled seed if missing. (library.toml is
# generated from the object reference — see _seed_library.)
_SEED_FILES = ["priorities.toml"]

_README_TEXT = """\
M110 — internal application data
================================

This folder holds M110's machine-managed state: the object catalog, capture
session index, generated rollups, and rendered thumbnails/heroes. M110 reads
and rewrites these files automatically.

Don't edit anything in here unless you know what you're doing — hand edits can
be silently overwritten or leave the Library in an inconsistent state. Your
actual images live under Images/, and your notes under Objects/.
"""

# Canonical journal format. The reference copy is written to
# `.m110_internal_data/journal_template.md`; each object's stub is this template
# with {id}/{name} filled in. `{` braces are escaped for str.format below.
JOURNAL_TEMPLATE = """\
---
name: "{name}"
hero_caption: ""
# hero: "<filename of a gallery image to pin as the hero>"   # optional
---

# {id} — {name}

<!--
Your observing & processing notes for this object. This file is yours to edit;
M110 reads the frontmatter above (name / hero_caption / hero) for the gallery.
Everything below the frontmatter is free-form Markdown.
-->
"""


def _object_stub(obj_id: str, name: str) -> str:
    return JOURNAL_TEMPLATE.format(id=obj_id, name=name or obj_id)


# Default observing-site profile. Seeded once into
# `.m110_internal_data/profiles/default.toml` with placeholder coordinates the
# user edits. The [glow] light-pollution layer starts empty — the light-dome
# phase fills it in by looking up the location online. See m110/planning_config.py.
DEFAULT_PROFILE_TOML = """\
# M110 observing-site profile. Edit the coordinates for your location; M110's
# session planning derives twilight, transit altitude, and observability from it.
# Add more locations (e.g. a dark-site trip) as sibling <name>.toml files.

[site]
name = "Home"
latitude_deg = 40.015        # decimal degrees, +N
longitude_deg = -105.270     # decimal degrees, +E
elevation_m = 1655           # metres above sea level
timezone = "America/Denver"  # IANA timezone (DST handled automatically)

[horizon]
# Physical skyline obstruction. Point `mask` at a Stellarium/NINA .hrz file
# (e.g. exported from theo.rocks) placed alongside this profile. Empty = open.
mask = ""

[glow]
# Light-pollution layer (the city light-dome). Filled in by the light-dome
# lookup; an azimuth-dependent quality floor layered over the physical horizon.
bortle = 0                   # 0 = unset
sqm_zenith = 0.0             # mag/arcsec^2, 0 = unset
mask = ""                    # broadband glow floor (.hrz)
mask_narrowband = ""         # softer floor for ON/LP (narrowband) filters
"""


def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def save_data_root(path) -> None:
    """Persist the chosen data root (takes effect on next launch)."""
    save_setting("data_root", str(Path(path).expanduser()))


def get_setting(key: str, default=None):
    """Read a persisted app setting (``~/.m110/settings.json``)."""
    return _read_settings().get(key, default)


def save_setting(key: str, value) -> None:
    """Persist a single app setting."""
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    s = _read_settings()
    s[key] = value
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


def _resolve_data_root() -> Path:
    env = os.environ.get("M110_DATA_ROOT")
    if env:
        return Path(env).expanduser()
    saved = _read_settings().get("data_root")
    if saved:
        return Path(saved).expanduser()
    return DEFAULT_DATA_ROOT


def _apply(root: Path) -> None:
    global DATA_ROOT, IMAGES_DIR, OBJECTS_DIR, MEDIA_DIR, STAGING_DIR
    global INTERNAL_DIR, LIBRARY_TOML, PRIORITIES_TOML, SESSIONS_JSONL
    global OVERRIDES_TOML, DERIVED_DIR, RENDERS_DIR, HERO_DIR, GOALS_TOML
    global PROFILES_DIR
    DATA_ROOT = root
    # Visible content axes
    OBJECTS_DIR = root / "Objects"          # Objects/<catalog id>/journal.md
    IMAGES_DIR = root / "Images"            # Images/<target>/{lights,stacks,…}
    MEDIA_DIR = root / "Media"              # Media/<Category>_photo|_video
    STAGING_DIR = root / "Inbox"            # ingest staging
    # Hidden machine state
    INTERNAL_DIR = root / INTERNAL_DIRNAME
    LIBRARY_TOML = INTERNAL_DIR / "library.toml"   # the user's object corpus
    GOALS_TOML = INTERNAL_DIR / "goals.toml"       # per-store active goals
    PRIORITIES_TOML = INTERNAL_DIR / "priorities.toml"
    SESSIONS_JSONL = INTERNAL_DIR / "sessions.jsonl"
    OVERRIDES_TOML = INTERNAL_DIR / "processing_overrides.toml"
    DERIVED_DIR = INTERNAL_DIR / "derived"
    RENDERS_DIR = INTERNAL_DIR / "renders"  # thumbnails (+ hero/<slug>.jpg)
    HERO_DIR = RENDERS_DIR / "hero"
    PROFILES_DIR = INTERNAL_DIR / "profiles"  # observing-site / device planning profiles


# ── per-target content paths (Images/<target>/<sub>) ────────────────────────

def target_dir(name: str) -> Path:
    return IMAGES_DIR / name


def lights_dir(name: str) -> Path:
    return IMAGES_DIR / name / "lights"


def stacks_dir(name: str) -> Path:
    """Siril stacks for a capture target."""
    return IMAGES_DIR / name / "stacks"


def seestar_stacks_dir(name: str) -> Path:
    """Seestar in-app stacks for a capture target."""
    return IMAGES_DIR / name / "seestar-stacks"


def finished_dir(name: str) -> Path:
    return IMAGES_DIR / name / "finished"


def darks_dir(name: str) -> Path:
    """Dark calibration frames for a capture target."""
    return IMAGES_DIR / name / "darks"


def flats_dir(name: str) -> Path:
    """Flat calibration frames for a capture target."""
    return IMAGES_DIR / name / "flats"


def biases_dir(name: str) -> Path:
    """Bias/offset calibration frames for a capture target."""
    return IMAGES_DIR / name / "biases"


def siril_dir(name: str) -> Path:
    """Contained Siril sandbox for a capture target (processing-prep)."""
    return IMAGES_DIR / name / "siril"


def siril_job_dir(name: str, filt: str | None = None) -> Path:
    """Working dir for a Siril job. Single-filter targets use the sandbox root;
    mixed-filter targets get one job per filter under it."""
    base = siril_dir(name)
    return base if filt is None else base / filt


_apply(_resolve_data_root())


def set_data_root(path) -> None:
    """Re-point the in-process data root (tests / runtime best-effort).

    The supported *persistent* change is ``save_data_root()`` + restart, because
    a few ported modules bind their paths at import.
    """
    _apply(Path(path).expanduser())


def data_root_ok() -> bool:
    return LIBRARY_TOML.is_file()


def ensure_data_root(root=None) -> Path:
    """Create the directory skeleton and seed catalog/priorities if missing.

    Migrates an older-layout store in place first, then ensures the skeleton.
    Idempotent — safe to call on every launch.
    """
    r = Path(root).expanduser() if root else DATA_ROOT

    # Bring a pre-two-axis store up to the current layout before seeding.
    from . import migrate
    migrate.migrate_store(r)

    for sub in _SUBDIRS:
        (r / sub).mkdir(parents=True, exist_ok=True)
    internal = r / INTERNAL_DIRNAME
    for name in _SEED_FILES:
        dst = internal / name
        src = SEED_DIR / name
        if not dst.exists() and src.is_file():
            shutil.copy(src, dst)
    _seed_library(internal / "library.toml")
    readme = internal / "README.txt"
    if not readme.exists():
        readme.write_text(_README_TEXT)

    # Reference journal template + a per-object stub for every Library object
    # (idempotent — never overwrites an existing journal).
    template = internal / "journal_template.md"
    if not template.exists():
        template.write_text(JOURNAL_TEMPLATE)
    _ensure_object_stubs(r, internal)

    # A default observing-site profile for session planning (idempotent).
    profile = internal / "profiles" / "default.toml"
    if not profile.exists():
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(DEFAULT_PROFILE_TOML)

    # Stamp the store version so migrate short-circuits on the next launch.
    from . import migrate
    (internal / migrate.VERSION_FILE).write_text(str(migrate.STORE_VERSION))
    return r


def _seed_library(dst: Path) -> None:
    """Create a fresh, **empty** `library.toml`. As of Phase 5d the Library is the
    user's captured/annotated collection, not the catalog — it grows only by
    capture (`catalog.add_captured_objects`) or the Add-object flow; uncaptured
    catalog members live in the Goals view. Idempotent; never overwrites."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        "# M110 Library — your object corpus (captured + annotated objects).\n"
        "# Grows by capture / Add-object; M110 reads/writes this file.\n")


def _ensure_object_stubs(root: Path, internal: Path) -> None:
    """Create Objects/<id>/journal.md (from the template) for every Library
    object, if missing. Reads the Library directly from `internal` so it's
    correct even when `root` differs from the global DATA_ROOT."""
    cat_path = internal / "library.toml"
    if not cat_path.is_file():
        return
    try:
        with cat_path.open("rb") as f:
            catalog = tomllib.load(f).get("catalog", {})
    except (OSError, tomllib.TOMLDecodeError):
        return
    objects_dir = root / "Objects"
    for slug, entry in catalog.items():
        obj_id = (entry.get("id") or slug).replace("/", "-").strip()
        if not obj_id:
            continue
        journal = objects_dir / obj_id / "journal.md"
        if journal.exists():
            continue
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(_object_stub(obj_id, entry.get("name", "")))


# ── Seestar device detection ────────────────────────────────────────────────

def find_seestar_myworks() -> Path | None:
    """Locate the Seestar's ``MyWorks`` dir across possible mounts.

    Handles USB (``/Volumes/Seestar``) and SMB (``/Volumes/EMMC Images``, etc.)
    by scanning /Volumes for any volume containing a ``MyWorks`` directory,
    preferring obviously-named ones.
    """
    vol = Path("/Volumes")
    if not vol.is_dir():
        return None
    try:
        volumes = list(vol.iterdir())
    except (PermissionError, OSError):
        return None
    volumes.sort(key=lambda p: (0 if ("seestar" in p.name.lower()
                                      or "emmc" in p.name.lower()) else 1, p.name))
    for d in volumes:
        try:
            mw = d / "MyWorks"
            if mw.is_dir():
                return mw
        except (PermissionError, OSError):
            continue
    return None

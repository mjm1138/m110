"""The two backup slots — a local drive and the cloud — and their saved settings.

A backup used to have exactly one destination, so every setting was one flat
global key. That made the pattern the guide recommends — *everything* to a local
drive, *essentials* offsite — something the user had to re-type by hand, and the
automatic backup only ever covered whichever destination was saved last. Two
fixed slots is the smallest shape that makes "both" the default: each has its own
destination, scope, schedule and retention (the remaining half of issue #93; a
general list of N destinations is still deferred).

Stored as one dict value, ``backup_destinations = {"local": {...}, "cloud":
{...}}`` — the whole-dict pattern `prioritizer_weights` already uses. The legacy
flat keys are *read* when the dict is absent (the saved destination lands in
whichever slot its kind says) and left in place when the new shape is written, so
nothing is lost and a downgrade still finds its settings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime

from .. import config
from .destination import KIND_S3, parse_destination
from .errors import BackupDestinationError
from .options import (
    DEFAULT_INTERVAL_HOURS, DEFAULT_MIN_FREE_GB, SETTING_AUTO, SETTING_DEST,
    SETTING_FORMAT, SETTING_INTERVAL, SETTING_KEEP, SETTING_MIN_FREE, SETTING_SCOPE,
)
from .scope import SCOPE_ESSENTIALS, SCOPE_EVERYTHING, SCOPES

SLOT_LOCAL = "local"
SLOT_CLOUD = "cloud"
SLOTS = (SLOT_LOCAL, SLOT_CLOUD)
SLOT_LABELS = {SLOT_LOCAL: "Local", SLOT_CLOUD: "Cloud"}

SETTING_DESTINATIONS = "backup_destinations"

# Mirrors formats.FORMAT_*; not imported from there because formats reads the
# local slot's preference and would make this a cycle.
_MIRRORED, _POOLED = "mirrored", "pooled"


@dataclass(frozen=True)
class SlotSettings:
    destination: str = ""
    scope: str = SCOPE_EVERYTHING
    auto: bool = False
    interval_hours: float = DEFAULT_INTERVAL_HOURS
    retention_keep: int = 0              # 0 = keep every backup
    min_free_gb: float = 0               # 0 = off; meaningless for a bucket
    format: str = _MIRRORED              # only the local slot has a choice
    last_backup_at: str | None = None    # ISO time of the last successful run

    @property
    def configured(self) -> bool:
        return bool(self.destination)

    @property
    def last_backup(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.last_backup_at) \
                if self.last_backup_at else None
        except ValueError:
            return None


# Cloud defaults to Essentials — the light frames are ~99% of a library and the
# metered, slow direction is exactly where they don't belong by default — and to
# keep-every-backup: never surprise-delete an offsite copy.
DEFAULTS = {
    SLOT_LOCAL: SlotSettings(min_free_gb=DEFAULT_MIN_FREE_GB),
    SLOT_CLOUD: SlotSettings(scope=SCOPE_ESSENTIALS, format=_POOLED),
}

_FIELDS = {f.name for f in fields(SlotSettings)}


def slot_for_destination(destination: str) -> str:
    """Which slot a destination string belongs in, by its kind. A malformed
    address is treated as local — the caller's validation reports it."""
    try:
        kind = parse_destination(destination).kind
    except (BackupDestinationError, ValueError):
        return SLOT_LOCAL
    return SLOT_CLOUD if kind == KIND_S3 else SLOT_LOCAL


def check_slot_destination(slot: str, destination: str) -> str | None:
    """A user-facing reason this destination can't go in this slot, or None."""
    destination = (destination or "").strip()
    if not destination:
        return None
    wanted = slot_for_destination(destination)
    if wanted == slot:
        return None
    if slot == SLOT_LOCAL:
        return ("That's a cloud storage address — set it up on the Cloud tab "
                "instead.")
    return ("Cloud backups need an s3:// address, like s3://your-bucket/backups. "
            "For a folder or drive, use the Local drive tab.")


def _clean(slot: str, raw: dict) -> SlotSettings:
    """Coerce a stored dict into SlotSettings, falling back per field."""
    base = DEFAULTS[slot]
    vals = {k: v for k, v in (raw or {}).items() if k in _FIELDS}
    s = replace(base, **vals)
    try:
        interval = float(s.interval_hours) or DEFAULT_INTERVAL_HOURS
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_HOURS
    try:
        keep = max(0, int(s.retention_keep or 0))
    except (TypeError, ValueError):
        keep = 0
    try:
        min_free = max(0.0, float(s.min_free_gb or 0))
    except (TypeError, ValueError):
        min_free = base.min_free_gb
    return replace(
        s,
        destination=str(s.destination or "").strip(),
        scope=s.scope if s.scope in SCOPES else base.scope,
        auto=bool(s.auto),
        interval_hours=interval,
        retention_keep=keep,
        min_free_gb=min_free,
        format=s.format if s.format in (_MIRRORED, _POOLED) else base.format,
    )


def _from_legacy() -> dict[str, SlotSettings]:
    """Slots built from the flat pre-slot keys. The one saved destination goes to
    the slot its kind names, carrying its schedule, retention and scope; the
    format and free-space rule were always about a local volume, so they go to the
    local slot whichever way the destination went."""
    get = config.get_setting
    out = dict(DEFAULTS)
    dest = str(get(SETTING_DEST, "") or "").strip()
    target = slot_for_destination(dest) if dest else SLOT_LOCAL
    carried = {
        "destination": dest,
        "auto": get(SETTING_AUTO, False),
        "interval_hours": get(SETTING_INTERVAL, DEFAULT_INTERVAL_HOURS),
        "retention_keep": get(SETTING_KEEP, 0),
    }
    if get(SETTING_SCOPE) is not None:
        carried["scope"] = get(SETTING_SCOPE)
    out[target] = _clean(target, {**asdict(DEFAULTS[target]), **carried})
    local = asdict(out[SLOT_LOCAL])
    # Only an absent key gets the 100 GB default; a stored 0/null is "off".
    local["min_free_gb"] = get(SETTING_MIN_FREE, DEFAULT_MIN_FREE_GB)
    local["format"] = get(SETTING_FORMAT, _MIRRORED)
    out[SLOT_LOCAL] = _clean(SLOT_LOCAL, local)
    return out


def load_slots() -> dict[str, SlotSettings]:
    stored = config.get_setting(SETTING_DESTINATIONS)
    if not isinstance(stored, dict):
        return _from_legacy()
    return {slot: _clean(slot, stored.get(slot) or {}) for slot in SLOTS}


def load_slot(slot: str) -> SlotSettings:
    return load_slots()[slot]


def save_slot(slot: str, settings: SlotSettings) -> None:
    """Persist one slot, writing the other as currently loaded — which is also
    what migrates a legacy settings file to the new shape on its first save."""
    slots = load_slots()
    slots[slot] = _clean(slot, asdict(settings))
    config.save_setting(SETTING_DESTINATIONS,
                        {name: asdict(s) for name, s in slots.items()})


def update_slot(slot: str, **changes) -> SlotSettings:
    """Change only the named fields of one slot (read-modify-write), so a writer
    that owns some fields — the dialog, a finished run stamping its time — never
    clobbers the rest."""
    s = replace(load_slot(slot), **changes)
    save_slot(slot, s)
    return load_slot(slot)


def configured_slots() -> list[str]:
    slots = load_slots()
    return [name for name in SLOTS if slots[name].configured]


def record_backup(slot: str, when: datetime | None = None) -> None:
    update_slot(slot, last_backup_at=(when or datetime.now()).isoformat(
        timespec="seconds"))

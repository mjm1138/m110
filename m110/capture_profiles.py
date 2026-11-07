"""Which capture software wrote a frame, and what that means for importing it.

A FITS header says what was shot, but every capture program spells it its own way:
the object card, how a mosaic panel is named, which card identifies the telescope
unit, and whether the frame was already dark-subtracted before it was saved. A
**capture profile** is that knowledge as plain data, so one engine path routes them
all (#203). Profiles are matched on header cards only, never on the folder layout or
the filename: N.I.N.A.'s file pattern is a user setting, and stock N.I.N.A. puts every
target of a night in one ``<date>/LIGHT/`` folder.

The built-ins (`BUILTIN`) are checked in order; the first whose `match` holds wins,
and `generic` always does. Part 2 of #203 loads user profiles of the same shape from
the store; nothing here depends on them being built in.

The four questions every reader asks go through this module:

* `device_key` — the per-unit device key (``Calibration/<device>/``, the Devices
  page). N.I.N.A. over Alpaca reports a Seestar as ``TELESCOP='S50 Prime'`` (the
  Alpaca device name), with the serial only in
  ``INSTRUME='Seestar S50_15e7e390 Telephoto Camera'``; the Seestar app writes
  ``TELESCOP='S50_15e7e390'``. Both are the same sensor (measured 2026-11-07: equal
  dark pedestal, identical hot pixels), so both resolve to ``S50_15e7e390``.
* `darks_applied` — whether this frame was dark-subtracted before it was saved. A
  property of the **capture path**, not of the telescope model: the Seestar app
  subtracts on the device, the same S50 driven by N.I.N.A. does not. The rule,
  word for word the same in Stackhammer: *app frame = `CREATOR` starting
  `ZWO Seestar`, or a `BIAS` card present (with no `SWCREATE`); never `TELESCOP` or
  `INSTRUME` alone. A Seestar-named frame with none of `CREATOR`, `BIAS`,
  `SWCREATE` has an unknown capture path (None): calibration says so and asks.*
* `object_name` — the target name to resolve (``canonical_target``), with a mosaic
  panel folded onto ``<object>_mosaic``.
* `profile_for` — which profile matched (the Import page's layout label).

Qt-free; reads no files (callers pass a header mapping — an astropy ``Header`` or a
plain dict of card → value). **Apply it to the original lights only, never to
Siril's output:** Siril drops ``SWCREATE`` when it writes ``process/`` frames, so a
N.I.N.A. ``pp_`` frame carries none of the capture-path cards and would read as
unknown (found by Stackhammer's calibration spike, 2026-11-07).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from . import devices

# A condition is (card, regex) — the card's string value must match (re.search,
# case-insensitive) — or (card, None): the card must be absent or blank.
Condition = tuple[str, str | None]


@dataclass(frozen=True)
class CaptureProfile:
    id: str
    label: str
    # Alternatives (OR) of condition sets (AND). Empty = matches everything.
    match: tuple[tuple[Condition, ...], ...] = ()
    object_header: str = "OBJECT"
    # A mosaic panel's name: group "base" is the object. Folded to "<base>_mosaic".
    panel_re: str | None = None
    # Ordered (card, regex, template): the first card whose value matches gives the
    # device key; the template formats the match ({0} = whole value, {1}… = groups).
    device_rules: tuple[tuple[str, str, str], ...] = (("TELESCOP", r".+", "{0}"),)
    # True/False = this software's frames are/aren't dark-subtracted before saving.
    # "model" = the telescope model decides (devices.darks_applied_on_device);
    # "unknown" = False, except for a model whose own app dark-subtracts — there the
    # capture path can't be told, so the answer is None (`darks_applied`).
    darks_applied: bool | str = False
    # Where a dark/flat/bias with no object goes: the device library, or the
    # holding area for the user to place.
    uncategorized_calibration: str = "library"
    # FILTER renames, each applied when its condition holds: ((card, regex),
    # ((from, to), …)). Matching is case-insensitive on `from`.
    filter_maps: tuple = ()


# N.I.N.A. localises the panel label (its `LblPanel` resource); the framing assistant
# names each panel "<target> <LblPanel> <n>". The common translations, plus "Tile".
_PANEL_WORDS = ("Panel", "Panneau", "Pannello", "Paneel", "Painel", "Panou",
                "Панель", "Панел", "面板", "パネル", "패널", "Tile")
_NINA_PANEL_RE = (r"^(?P<base>.+?)[\s_-]+(?:" + "|".join(_PANEL_WORDS)
                  + r")[\s_-]*\d+$")
_PANEL_RE = r"^(?P<base>.+?)[\s_-]+Panel[\s_-]*\d+$"

# A Seestar unit's serial as N.I.N.A. sees it, through the ZWO Alpaca driver:
# INSTRUME = 'Seestar S50_15e7e390 Telephoto Camera' → 'S50_15e7e390', the key
# the Seestar app's own TELESCOP gives. (An S30 Pro's spelling is unverified, so it
# falls through to TELESCOP rather than being guessed.)
_SEESTAR_SERIAL_RULE = ("INSTRUME", r"\bSeestar\s+(S\d+)_([0-9A-Fa-f]+)\b", "{1}_{2}")

BUILTIN: tuple[CaptureProfile, ...] = (
    CaptureProfile(
        id="nina", label="N.I.N.A.",
        # 'N.I.N.A. 3.1.2.9001' on the desktop; 'PI N Stars (N.I.N.A. 3.3.0.1058
        # (arm64))' under PINS.
        match=((("SWCREATE", r"N\.I\.N\.A\."),),),
        panel_re=_NINA_PANEL_RE,
        device_rules=(_SEESTAR_SERIAL_RULE,
                      ("TELESCOP", r".+", "{0}"), ("INSTRUME", r".+", "{0}")),
        darks_applied=False,
        # The ZWO Alpaca driver names the S50's UV/IR-cut slot "IR"; the Seestar
        # app calls the same filter "IRCUT" (its wheel has only that, LP and Dark).
        # One name, so a target's N.I.N.A. and app subs land in one job folder.
        filter_maps=((("INSTRUME", r"\bSeestar\b"), (("IR", "IRCUT"),)),),
    ),
    CaptureProfile(
        id="seestar-app", label="Seestar app",
        # THE RULE (shared with Stackhammer, docs/design/calibration.md): a frame
        # saved by the Seestar's own app says CREATOR = 'ZWO Seestar …' and carries
        # a BIAS card (its pedestal). Every one of 1,291 app subs sampled across
        # 2026-03…10 and firmware 6.70…9.31 has both, and none has SWCREATE.
        # Never TELESCOP or INSTRUME alone: both name the Seestar under N.I.N.A.
        # too, which is how N.I.N.A.'s undarked frames were once taken as darked.
        match=((("CREATOR", r"^\s*ZWO\s+Seestar"),),
               (("BIAS", r"\S"), ("SWCREATE", None),
                ("TELESCOP", r"^\s*(?:Seestar\s+)?S\d+")),
               (("BIAS", r"\S"), ("SWCREATE", None), ("INSTRUME", r"\bSeestar\b")),),
        panel_re=_PANEL_RE,
        # the app dark-subtracts every sub it saves (S50 measured; S30s run the
        # same pipeline) — so an app frame is True whatever its TELESCOP says
        darks_applied=True,
    ),
    CaptureProfile(
        id="dwarf-app", label="DwarfLab app",
        match=((("SWCREATE", None), ("TELESCOP", r"dwarf")),),
        panel_re=_PANEL_RE,
        darks_applied=False,
    ),
    CaptureProfile(
        id="generic", label="FITS headers",
        panel_re=_PANEL_RE,
        device_rules=(("TELESCOP", r".+", "{0}"), ("INSTRUME", r".+", "{0}")),
        # A Seestar-named frame with no CREATOR, no BIAS and no SWCREATE: its
        # capture path is unknown, so "already dark-subtracted?" is None — said,
        # and asked, never guessed either way.
        darks_applied="unknown",
    ),
)
BY_ID = {p.id: p for p in BUILTIN}


def _card(hdr: Mapping | None, name: str) -> str:
    if hdr is None:
        return ""
    try:
        v = hdr.get(name)
    except Exception:
        return ""
    return "" if v is None else str(v).strip()


def _holds(hdr: Mapping | None, cond: Condition) -> bool:
    card, pat = cond
    val = _card(hdr, card)
    if pat is None:
        return not val
    return bool(val) and re.search(pat, val, re.IGNORECASE) is not None


def profile_for(hdr: Mapping | None) -> CaptureProfile:
    """The first profile whose `match` holds for this header (`generic` at worst)."""
    for p in BUILTIN:
        if not p.match or any(all(_holds(hdr, c) for c in alt) for alt in p.match):
            return p
    return BY_ID["generic"]                       # pragma: no cover - generic matches


def device_key(hdr: Mapping | None, profile: CaptureProfile | None = None) -> str | None:
    """The per-unit device key, or None when no card identifies a device."""
    p = profile or profile_for(hdr)
    for card, pat, template in p.device_rules:
        val = _card(hdr, card)
        if not val:
            continue
        m = re.search(pat, val, re.IGNORECASE)
        if m:
            key = template.format(m.group(0), *m.groups()).strip()
            if key:
                return key
    return None


def darks_applied(hdr: Mapping | None, profile: CaptureProfile | None = None) -> bool | None:
    """Was this frame dark-subtracted before it was saved? True/False, or None when
    that can't be told: a frame of a model whose app dark-subtracts (a Seestar)
    that carries none of the capture-path cards (CREATOR, BIAS, SWCREATE).
    Calibration refuses such frames with a note rather than guess."""
    p = profile or profile_for(hdr)
    if isinstance(p.darks_applied, bool):
        return p.darks_applied
    on_device = devices.darks_applied_on_device(device_key(hdr, p))
    if p.darks_applied == "model":
        return on_device
    return None if on_device else False


def filter_name(hdr: Mapping | None, profile: CaptureProfile | None = None) -> str | None:
    """The FILTER card under the profile's renames (N.I.N.A.'s Seestar ``IR`` →
    ``IRCUT``), or None when the card is blank."""
    raw = _card(hdr, "FILTER")
    if not raw:
        return None
    p = profile or profile_for(hdr)
    for cond, pairs in p.filter_maps:
        if _holds(hdr, cond):
            for frm, to in pairs:
                if raw.lower() == frm.lower():
                    return to
    return raw


def fold_panel(name: str | None, profile: CaptureProfile) -> str | None:
    """``'M 45 Panel 2'`` → ``'M 45_mosaic'`` under a profile that names panels so;
    anything else unchanged."""
    if not name or not profile.panel_re:
        return name
    m = re.match(profile.panel_re, name.strip(), re.IGNORECASE)
    if m and m.group("base").strip():
        return f"{m.group('base').strip()}_mosaic"
    return name


def object_name(hdr: Mapping | None, profile: CaptureProfile | None = None) -> str | None:
    """The target name to resolve, from the profile's object card, panel-folded."""
    p = profile or profile_for(hdr)
    raw = _card(hdr, p.object_header)
    return fold_panel(raw, p) if raw else None


def facts(hdr: Mapping | None) -> dict:
    """``{device, darks_applied, capture}`` — the three capture facts every header
    reader records next to its own (one profile lookup)."""
    p = profile_for(hdr)
    return {"device": device_key(hdr, p), "darks_applied": darks_applied(hdr, p),
            "capture": p.id}

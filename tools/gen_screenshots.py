#!/usr/bin/env python3
"""Render M110 UI screenshots for the website / docs, reproducibly.

A headless (offscreen) render of the real ``MainWindow`` against a data root —
no window management, no computer-use, and it writes **nothing** to the store.
Follows the recipe in CLAUDE.md ("Capturing UI screenshots"): build the window,
set ``_ready = False`` (neuters the launch refresh + the update-check network
thread, so rendering against the *live* store is read-only), pump the async
thumbnail/hero loaders, then render into a 2× ``QPixmap`` and save a progressive
JPEG sized for the site (1240×780 → 2480×1560 retina).

Root selection — real data for the site; a corpus for other contributors:
    default                     ~/Documents/M110  (your live library)
    --root DIR                  an explicit data root
    M110_SCREENSHOT_ROOT=DIR    env override (e.g. a generated test corpus)

Usage:
    python tools/gen_screenshots.py                       # → site/assets/shot-*.jpg
    python tools/gen_screenshots.py --root ~/Documents/M110-test
    M110_SCREENSHOT_ROOT=~/Documents/M110-test python tools/gen_screenshots.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

W, H, SCALE = 1240, 780, 2                      # site asset size + retina factor
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "site" / "assets"


def _pump(app, seconds: float):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _pump_until(app, pred, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.05)
    try:
        return bool(pred())
    except Exception:
        return False


def _shot(win, app, path: Path, settle: float = 3.0):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PIL import Image
    _pump(app, settle)                          # let hero/thumbnail loaders populate
    pm = QPixmap(W * SCALE, H * SCALE)
    pm.setDevicePixelRatio(SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    win.render(pm)
    tmp = Path(tempfile.mkdtemp()) / "shot.png"
    pm.save(str(tmp), "PNG")
    Image.open(tmp).convert("RGB").save(
        str(path), "JPEG", quality=82, optimize=True, progressive=True)
    tmp.unlink()
    print(f"  wrote {path.name}  ({path.stat().st_size // 1024} KB, {W*SCALE}×{H*SCALE})")


def _pick_detail_slug():
    """A hero-bearing object with the richest gallery — makes a full detail pane."""
    from m110 import config
    try:
        imgs = json.loads((config.DERIVED_DIR / "images.json").read_text())
    except Exception:
        return None
    best, best_n = None, -1
    for slug, items in imgs.items():
        if (config.HERO_DIR / f"{slug}.jpg").exists() and len(items or []) > best_n:
            best, best_n = slug, len(items or [])
    return best


def build(root: Path, out_dir: Path):
    from m110 import config
    os.environ["M110_DATA_ROOT"] = str(root)
    config.set_data_root(root)
    # Never touch the user's real ~/.m110/settings.json — theme + view prefs go to
    # a throwaway file, so screenshots don't change their preferences.
    config.SETTINGS_FILE = Path(tempfile.mkdtemp()) / "settings.json"

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from m110.ui import theme
    theme.install(app)
    theme.set_mode("dark")                      # the site uses dark-mode shots

    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False                          # READ-ONLY: no launch refresh / net thread
    win.resize(W, H)
    win.statusBar().hide()                      # keep the local data-root path out of frame
    win.show()
    _pump(app, 1.0)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Library — the thumbnail grid (home view)
    win.nav.setCurrentRow(win._catalog_index)
    _shot(win, app, out_dir / "shot-library.jpg")

    # 2) Object detail — a hero-bearing object with the fullest gallery
    slug = _pick_detail_slug()
    if slug:
        win.open_object(slug)
        try:
            win.catalog.splitter.setSizes([320, 900])   # favour the detail/hero pane
        except Exception:
            pass
        _shot(win, app, out_dir / "shot-detail.jpg")
    else:
        print("  (no hero-bearing object found — skipping shot-detail.jpg)")

    # 3) Overview — the dashboard
    win.nav.setCurrentRow(win._overview_index)
    _shot(win, app, out_dir / "shot-summary.jpg", settle=2.5)

    # 4) Planning — the priority ranking, plus a night plan + timeline if it computes
    win.nav.setCurrentRow(win._planning_index)
    _pump(app, 1.0)
    try:
        win.planning._render_ranking()          # from the cached prioritized.json (no write)
    except Exception as e:
        print(f"  (planning ranking not rendered: {e})")
    try:                                         # optional: tonight's plan drives the timeline
        win.planning._on_generate()
        _pump_until(app, lambda: win.planning._plan_table.rowCount() > 0, 30)
    except Exception as e:
        print(f"  (planning night-plan skipped: {e})")
    _shot(win, app, out_dir / "shot-planning.jpg", settle=2.0)

    win.close()
    _pump(app, 0.3)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.environ.get("M110_SCREENSHOT_ROOT") or str(Path.home() / "Documents" / "M110")
    ap.add_argument("--root", default=default_root,
                    help="data root to render (default: $M110_SCREENSHOT_ROOT or ~/Documents/M110)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"output dir for shot-*.jpg (default: {DEFAULT_OUT})")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        sys.exit(f"data root not found: {root}")
    print(f"Rendering screenshots from {root}  →  {args.out}")
    build(root, args.out.expanduser().resolve())
    print("Done.")


if __name__ == "__main__":
    main()

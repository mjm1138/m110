#!/usr/bin/env python3
"""Export the M110 app-icon parchment tile to PNG(s) for packaging.

Runtime doesn't need this — `theme.brand.app_icon()` renders the icon in-process for
the dock/window. This tool emits a static `m110/ui/theme/brand/app-icon.png` (and a
1024px master) so a future Developer-ID `.app` bundle / `.icns` / `.ico` build has a
source asset. Build-time only.

    QT_QPA_PLATFORM=offscreen python -m tools.gen_app_icon
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

BRAND = Path(__file__).resolve().parent.parent / "m110" / "ui" / "theme" / "brand"


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    from m110.ui.theme import brand   # needs a QApplication (QPixmap/QPainter)

    for size, name in [(1024, "app-icon@1024.png"), (256, "app-icon.png")]:
        pm = brand._icon_pixmap(size)
        out = BRAND / name
        pm.save(str(out), "PNG")
        print(f"  wrote {out.relative_to(BRAND.parent.parent.parent)} ({size}px)")


if __name__ == "__main__":
    main()

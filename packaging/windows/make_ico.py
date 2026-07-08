"""Build packaging/windows/M110.ico from the 1024px brand master.

A Windows .ico bundles several square sizes; Pillow writes them all from the one
master. Cross-platform (Pillow only), so it can run on the build host or be
regenerated anywhere. Run from the repo root:

    python packaging/windows/make_ico.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MASTER = ROOT / "m110" / "ui" / "theme" / "brand" / "app-icon@1024.png"
OUT = HERE / "M110.ico"

# Standard Windows icon sizes (Explorer, taskbar, alt-tab, jumbo view).
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    if not MASTER.exists():
        raise SystemExit(f"master icon not found: {MASTER}\n"
                         f"(regenerate it with: python tools/gen_app_icon.py)")
    img = Image.open(MASTER).convert("RGBA")
    img.save(OUT, format="ICO", sizes=SIZES)
    print(f"wrote {OUT.relative_to(ROOT)} ({', '.join(f'{w}' for w, _ in SIZES)}px)")


if __name__ == "__main__":
    main()

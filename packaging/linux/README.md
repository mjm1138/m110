# Linux packaging (AppImage)

Builds a single-file, double-click **M110-`<version>`-`<arch>`.AppImage** — the best
fit for a mixed-distro audience (no install, no root). BETA §1 "close second" after
macOS.

## TL;DR (on a Linux host)

```bash
pip install -e ".[build]"
# one-time: get appimagetool (see below)
./packaging/linux/build_appimage.sh
chmod +x dist/M110-*.AppImage && ./dist/M110-*.AppImage
```

## Pieces

| File | Role |
|---|---|
| `M110.spec` | PyInstaller **onedir** spec → `dist/M110/` (bundled Python/Qt). Reuses the shared entry shim + astropy hook in `packaging/common/`. |
| `m110.desktop` | Desktop entry (name, icon, categories) the AppImage embeds. |
| `build_appimage.sh` | onedir build → assemble `AppDir` (AppRun + .desktop + icon) → `appimagetool`. |

## Prerequisites

- **Build on Linux** — PyInstaller is not a cross-compiler. Build on the **oldest
  glibc** you want to support (Ubuntu 22.04 LTS is a good floor); the resulting
  AppImage then runs on that distro *and newer* ones, but not older.
- **appimagetool**, once (the script won't auto-download it):
  ```bash
  wget -O ~/.local/bin/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x ~/.local/bin/appimagetool
  ```
  Or pass `APPIMAGETOOL=/path/to/appimagetool` to the build script.
- **Runtime:** AppImages need **libfuse2** on the *user's* machine (many modern
  distros ship only fuse3). If missing, users can run
  `./M110-*.AppImage --appimage-extract-and-run`. Document this on the download page.

## Notes & gotchas

- **Qt platform plugins.** PyInstaller bundles PySide6's Qt, including the `xcb`
  (X11) and `wayland` platform plugins. Most desktops "just work"; if the app fails
  to start with a *"could not load the Qt platform plugin"* error, the host is
  missing a base library the bundled plugin links against (commonly
  `libxcb-cursor0` on newer distros). Note it on the download page rather than
  bloating the AppImage.
- **Test on x86_64 + a desktop session**, X11 *and* Wayland (BETA §2). The Pi-5
  smoke pass proved the code is Linux-clean, but the *packaged* AppImage on a
  mainstream x86_64 distro is the real acceptance test.
- **Architecture.** The AppImage is named for `uname -m` (`x86_64` on a PC,
  `aarch64` on a Pi). Build once per arch you want to ship.
- **First launch** writes the data store to `~/Documents/M110` (or `$M110_DATA_ROOT`),
  same as every platform.

## CI (later)

Scripted so a `ubuntu-22.04` GitHub Actions job can build the AppImage on tag.
Deferred until the local flow is proven on a real x86_64 desktop.

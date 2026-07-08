# Windows packaging

Builds an **M110-`<version>`-setup.exe** (PyInstaller `.exe` + Inno Setup installer).
Supported-but-not-lead platform (BETA §1); ships **unsigned** for the beta.

## TL;DR (on a Windows host)

```powershell
pip install -e ".[build]"
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
```

Produces `dist\M110-<version>-setup.exe`.

## Pieces

| File | Role |
|---|---|
| `M110.spec` | PyInstaller **onedir** spec → `dist\M110\` (M110.exe + bundled Python/Qt). Reuses `packaging\common\` (entry shim + astropy hook). |
| `make_ico.py` | `app-icon@1024.png` → `M110.ico` (Pillow; embedded in the .exe + used as the setup icon). |
| `M110.iss` | Inno Setup script — per-user install, Start-Menu + optional desktop shortcut, uninstaller. |
| `build_windows.ps1` | Orchestrates icon → PyInstaller → Inno Setup. |

## Prerequisites

- **Build on Windows** — PyInstaller can't cross-compile; Inno Setup is Windows-only.
- **Inno Setup 6.3+** — install from <https://jrsoftware.org/isdl.php>. The script
  finds `ISCC.exe` on `PATH` or at `C:\Program Files (x86)\Inno Setup 6\`.
- **Python 3.11+** with `pip install -e ".[build]"`.

## Unsigned build — SmartScreen

The beta ships **unsigned** (code-signing certs deferred until there's uptake — see
BETA.md §1). On first run of an unsigned installer, Windows SmartScreen shows
**"Windows protected your PC."** Users clear it by:

> **More info → Run anyway**

Document this prominently on the download page and in the announce post — it's the
single biggest first-run friction on Windows. (An EV cert clears SmartScreen
instantly but is pricey + hardware-token; an OV cert builds reputation over time.
Revisit only on uptake.)

## Notes & gotchas

- **Per-user install, no admin.** `M110.iss` sets `PrivilegesRequired=lowest`, so a
  hobbyist installs without a UAC prompt (into `%LOCALAPPDATA%\Programs\M110`). The
  dialog still lets advanced users pick all-users.
- **AppId is stable** (`{254AD386-…}`) so future versions upgrade in place rather
  than installing side-by-side. Don't change it.
- **Watch on first real run** (BETA §2/§3): path handling (backslashes / spaces /
  OneDrive-redirected `Documents`), native file dialogs, and **Seestar detection**
  (`find_seestar_myworks` — drive letters + UNC paths vs. `/Volumes`).
- **First launch** writes the data store to `%USERPROFILE%\Documents\M110` (or
  `%M110_DATA_ROOT%`).
- The `.exe` version resource (CompanyName/ProductVersion in file properties) is not
  set yet — a later polish item (PyInstaller `version_file`).

## CI (later)

Scripted so a `windows-latest` GitHub Actions job can build the installer on tag.
Deferred until the local flow is proven on a real Windows machine.

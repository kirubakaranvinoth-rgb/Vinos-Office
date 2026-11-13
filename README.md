# Vino's Office

A branded office suite installer: LibreOffice + Vino's Office branding + the Sheets Home add-on, in one setup `.exe`.

## Build

```
python build.py
```

This writes `../Installers/VinosOffice-<version>-Setup.exe` (about 360 MB, works offline).

Requirements:
- `vendor/LibreOffice_<ver>_Win_x86-64.msi` from https://www.libreoffice.org/download/. It's kept out of git because of its size.
- Pillow, used to draw the brand images.
- NSIS, from the Tauri toolchain at `%LOCALAPPDATA%\tauri\NSIS`.
- `../libreoffice-sheets-home`, for the Sheets Home add-on.

Bump `VERSION` in `build.py` for each release. To move to a newer LibreOffice, download its MSI and update `LO_VERSION` and `LO_PRODUCTCODE` in `build.py`. You can read the product code from the MSI's Property table.

## What setup does

- **PC without LibreOffice:** it installs LibreOffice silently into `C:\Program Files\Vinos Office` and hides LibreOffice's own Apps & Features entry, so only "Vino's Office" is listed. It doesn't register Office file types and doesn't install the online-update feature.
- **PC with LibreOffice:** it brands that existing installation. Uninstalling puts the original look back.
- **Running a newer setup over an existing Vino's Office:** it updates the branding and add-ons.

In every case, setup then:
- replaces the splash screen, Start Center and About logos (originals are kept as `*.vinos-orig`);
- installs the add-ons for all users:
  - `VinosOfficeBranding.oxt`, which renames the product to "Vino's Office" in window titles and menus and turns off the Donate, Get Involved and What's New bars and the tip of the day;
  - `SheetsHome.oxt`;
- creates the Start menu entries (Vino's Office, Calc, Writer, Impress) and the desktop shortcuts.

## Layout

- `brand/make_assets.py` draws the splash, logos, icon and installer images from the Vino logo and art.
- `branding-ext/` holds the configuration add-on (product name, popups).
- `installer/installer.nsi` is the setup script, and `installer/notice.txt` is the LibreOffice / MPL-2.0 notice shown during setup.

## Theme switching

LibreOffice applies a Light/Dark change only partly until it restarts, so with Windows in dark mode, choosing Light looks broken (pale icons and an unreadable menu bar). The branding add-on adds **View > Vino's Office Theme > Light / Dark / Same as Windows** (`branding-ext/vinos_theme.py`). It also watches the Appearance setting, including changes made in Tools > Options, and offers to restart straight away so the new theme applies fully. The prompt is a native Windows box, because LibreOffice's own dialogs are half-themed at that moment.

## Modern look (1.0.6)

- **Ribbon:** `branding-ext/vinos_ui.py` switches Calc, Writer, Impress and Draw to LibreOffice's Tabbed ribbon (`notebookbar.ui`) the first time each opens, once per user. It records this in `<profile>/config/vinosoffice-ui.json`, so anyone who switches back keeps their choice. Startup windows may not accept the command yet, so it retries for up to 10 s.
- **Colours:** `branding-ext/VinoTheme.xcu` defines the VINO_LIGHT and VINO_DARK colour schemes. Note that they belong to component `org.openoffice.Office` / `UI`, node `ColorScheme`. `Common.xcu` turns them on (`LibreOfficeTheme=1`), and `vinos_theme.py` selects the scheme that matches Light / Dark / Same as Windows.
- **Ribbon buttons:** the ribbon Extension tab gets the theme buttons (`ThemeMenu.xcu`) and Sheets Home / Contents (`Addons.xcu` in Sheets Home), all through `OfficeNotebookBar`.

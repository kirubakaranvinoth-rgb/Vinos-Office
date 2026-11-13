# Sheets Home for LibreOffice Calc

CellLite's **Sheets Home**, as a LibreOffice extension (`.oxt`). Handy for workbooks with lots of sheets.

## What it does

Press **Ctrl+Shift+H**, choose **Sheet ▸ Sheets Home…**, or click the four-tile toolbar button:

- **Every sheet in one list**, showing its number, name, used range, row count and notes (Current, Hidden, Pivot, charts, Index).
- **Search as you type**, ranked like CellLite: an exact match first, then names that start with your text, then word matches, then names that contain it. Use ↑ ↓ to pick a sheet and Enter to open it, so it also works as a quick sheet finder.
- **Sort** by workbook order, name A→Z or Z→A (`Sheet2` comes before `Sheet10`), or most data first.
- **Recent** buttons for the sheets you used last in that document.
- **Hidden sheets** can be shown or hidden in the list. Opening a hidden sheet asks before unhiding it.
- **Preview** of the first cells of the selected sheet.
- **Rename…, Hide / Unhide, + New sheet** buttons.
- **Create index sheet**, also available as Sheet ▸ Create Contents Index Sheet. It adds or refreshes a `Contents` sheet at the front with a link to every sheet. In Calc, Ctrl+click a link to follow it. The links still work after saving as .xlsx and opening in Excel or WPS. You can undo it in one step.

## Install

Double-click `SheetsHome-<version>.oxt`, or use LibreOffice **Tools ▸ Extensions ▸ Add**, then restart LibreOffice.

## Build

```
python build.py
```

This needs Pillow to draw the icons. It writes `dist/SheetsHome-<version>.oxt` and copies it to `../Installers`. Bump `<version>` in `src/description.xml` for each release.

## Files

- `src/sheets_home.py` holds the code: the command handler, the Sheets Home dialog, the index sheet, and recent-sheet tracking.
- `src/Addons.xcu` adds the Sheet menu items and the toolbar button.
- `src/Accelerators.xcu` binds Ctrl+Shift+H in Calc only. Calc's own Ctrl+Shift+F (Repeat Search) is unchanged.
- `src/ProtocolHandler.xcu` registers the `org.celllite.sheetshome:` commands.
- `src/Jobs.xcu` starts recent-sheet tracking whenever a document opens.

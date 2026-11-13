"""Build the Vino's Office setup .exe.

    python build.py

1. draws the brand images                     (brand/make_assets.py)
2. packages the branding add-on               (branding-ext/ -> build/VinosOfficeBranding.oxt)
3. builds Sheets Home                         (../libreoffice-sheets-home)
4. compiles the installer with NSIS           -> ../Installers/VinosOffice-<version>-Setup.exe

Bump VERSION for every release. To move to a newer LibreOffice, put its .msi in vendor/ and set LO_MSI.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.0.5"
LO_VERSION = "26.8.3"
LO_MSI = f"vendor/LibreOffice_{LO_VERSION}_Win_x86-64.msi"
LO_PRODUCTCODE = "{2E138BFE-5DFE-4CCB-B34D-56308CCE5097}"

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
INSTALLERS = ROOT.parent / "Installers"
SHEETS_HOME = ROOT.parent / "libreoffice-sheets-home"
MAKENSIS = Path(os.environ["LOCALAPPDATA"]) / "tauri" / "NSIS" / "makensis.exe"


def zip_dir(src: Path, out: Path):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src).as_posix())


def main():
    BUILD.mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "brand" / "make_assets.py")], check=True)
    zip_dir(ROOT / "branding-ext", BUILD / "VinosOfficeBranding.oxt")

    subprocess.run([sys.executable, str(SHEETS_HOME / "build.py")], check=True, cwd=SHEETS_HOME)
    newest = max((SHEETS_HOME / "dist").glob("SheetsHome-*.oxt"), key=lambda p: p.stat().st_mtime)
    shutil.copy2(newest, BUILD / "SheetsHome.oxt")

    msi = ROOT / LO_MSI
    if not msi.exists():
        sys.exit(f"Missing {msi} - download it from https://www.libreoffice.org/download/")
    INSTALLERS.mkdir(exist_ok=True)
    out = INSTALLERS / f"VinosOffice-{VERSION}-Setup.exe"
    subprocess.run([str(MAKENSIS), "/V2",
                    f"/DVERSION={VERSION}", f"/DLO_VERSION={LO_VERSION}", f"/DLO_MSI={msi}",
                    f"/DLO_PRODUCTCODE={LO_PRODUCTCODE}", f"/DOUTFILE={out}",
                    "installer.nsi"], check=True, cwd=ROOT / "installer")
    print(f"built {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

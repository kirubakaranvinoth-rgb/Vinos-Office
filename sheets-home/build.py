"""Build SheetsHome.oxt and copy it to ../Installers.

    python build.py

Draws the toolbar icons (needs Pillow), zips src/ into dist/SheetsHome-<version>.oxt,
and copies it next to the CellLite installers.
"""
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
INSTALLERS = ROOT.parent.parent / "Installers"  # next to the vinos-office folder (same place as the setup)
GREEN = (30, 142, 62, 255)


def icon(size: int) -> Image.Image:
    """Four rounded tiles, like CellLite's Sheets button."""
    s = 8  # draw large, then shrink for smooth edges
    img = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, gap = size * s * 0.08, size * s * 0.1
    tile = (size * s - 2 * pad - gap) / 2
    for r in range(2):
        for c in range(2):
            x, y = pad + c * (tile + gap), pad + r * (tile + gap)
            d.rounded_rectangle((x, y, x + tile, y + tile), radius=tile * 0.2, fill=GREEN)
    return img.resize((size, size), Image.LANCZOS)


def index_icon(size: int) -> Image.Image:
    """A contents list: green bullets with grey lines."""
    s = 8
    S = size * s
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(3):
        y = S * (0.22 + i * 0.28)
        d.rounded_rectangle((S * 0.08, y, S * 0.26, y + S * 0.16), radius=S * 0.04, fill=GREEN)
        d.rounded_rectangle((S * 0.36, y + S * 0.03, S * 0.92, y + S * 0.13), radius=S * 0.04, fill=(84, 118, 150, 255))
    return img.resize((size, size), Image.LANCZOS)


def main():
    (SRC / "icons").mkdir(exist_ok=True)
    for n in (16, 26, 42):
        icon(n).save(SRC / "icons" / f"home_{n}.png")
    for n in (16, 26):
        index_icon(n).save(SRC / "icons" / f"index_{n}.png")

    version = re.search(r'<version value="([^"]+)"', (SRC / "description.xml").read_text(encoding="utf-8")).group(1)
    DIST.mkdir(exist_ok=True)
    out = DIST / f"SheetsHome-{version}.oxt"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(SRC).as_posix())
    print("built", out)

    INSTALLERS.mkdir(exist_ok=True)
    shutil.copy2(out, INSTALLERS / out.name)
    print("copied to", INSTALLERS / out.name)


if __name__ == "__main__":
    main()

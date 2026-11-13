"""Draws every Vino's Office brand image from the Vino logo + art.

    python brand/make_assets.py

Outputs (brand/out/):
  program/intro.png, program/intro-highres.png      splash screen
  program/shell/logo*.svg, about.svg               Start Center + About dialog
  vinos-office.ico                                 shortcuts / Add-Remove Programs
  installer-side.bmp, installer-header.bmp         setup wizard images
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
SPLASH_SRC = HERE.parents[1] / "celllite" / "public" / "splash"
OUT = HERE / "out"
NAME = "Vino's Office"
TAGLINE = "Spreadsheets · Documents · Presentations"
BG = (6, 16, 28)
ACCENT = (64, 196, 214)  # teal, matches the logo's glow
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT = "C:/Windows/Fonts/segoeui.ttf"

logo_src = Image.open(SPLASH_SRC / "vino-logo.jpg").convert("RGB")
art_src = Image.open(SPLASH_SRC / "vino-art.jpg").convert("RGB")


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def logo(size, radius_frac=0.18):
    return rounded(logo_src.resize((size, size), Image.LANCZOS), int(size * radius_frac))


def art_strip(w, h):
    """Centre of the art (rock + moon), cropped to w×h, fading into the background on the left."""
    src_ratio = art_src.width / art_src.height
    if w / h > src_ratio:
        a = art_src.resize((w, int(w / src_ratio)), Image.LANCZOS)
    else:
        a = art_src.resize((int(h * src_ratio), h), Image.LANCZOS)
    left, top = (a.width - w) // 2, max(0, int((a.height - h) * 0.25))
    a = a.crop((left, top, left + w, top + h)).convert("RGBA")
    fade = Image.new("L", (w, h))
    px = fade.load()
    for x in range(w):
        v = int(255 * min(1, (x / (w * 0.55)) ** 1.6))
        for y in range(h):
            px[x, y] = v
    a.putalpha(fade)
    return a


def splash(w, h):
    s = h / 199  # layout designed at 644×199
    img = Image.new("RGBA", (w, h), BG + (255,))
    art = art_strip(int(w * 0.46), h)
    img.alpha_composite(art, (w - art.width, 0))
    lg = logo(int(132 * s))
    img.alpha_composite(lg, (int(24 * s), (h - lg.height) // 2 - int(6 * s)))
    d = ImageDraw.Draw(img)
    x = int(24 * s) + lg.width + int(22 * s)
    d.text((x, int(42 * s)), NAME, font=font(int(38 * s), True), fill=(255, 255, 255))
    d.text((x + int(2 * s), int(94 * s)), TAGLINE, font=font(int(13 * s)), fill=(150, 175, 196))
    return img.convert("RGB")


def wordmark(text_rgb, h=200):
    """Logo tile + name, transparent background (Start Center / About)."""
    f = font(int(h * 0.42), True)
    tw = ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(NAME, font=f)
    w = int(h + h * 0.18 + tw + h * 0.05)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.alpha_composite(logo(h, 0.2), (0, 0))
    ImageDraw.Draw(img).text((int(h * 1.18), int(h * 0.18)), NAME, font=f, fill=text_rgb)
    return img


def svg_of(img, width_px=None):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode()
    w, h = img.size
    dw = width_px or w
    dh = round(h * dw / w, 2)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2" '
            f'width="{dw}" height="{dh}" viewBox="0 0 {w} {h}">'
            f'<image width="{w}" height="{h}" xlink:href="data:image/png;base64,{data}" href="data:image/png;base64,{data}"/></svg>')


def theme_icon(kind, size):
    """Ribbon icons for the theme buttons: sun (Light), moon (Dark), half circle (Same as Windows)."""
    s = 8
    S = size * s
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    teal, navy = (14, 143, 163, 255), (84, 118, 150, 255)  # "navy" is a mid slate so it shows on light and dark ribbons
    c, r = S / 2, S * 0.22
    if kind == "light":
        for i in range(8):
            import math
            a = i * math.pi / 4
            x1, y1 = c + math.cos(a) * r * 1.45, c + math.sin(a) * r * 1.45
            x2, y2 = c + math.cos(a) * r * 2.0, c + math.sin(a) * r * 2.0
            d.line((x1, y1, x2, y2), fill=teal, width=int(S * 0.08))
        d.ellipse((c - r, c - r, c + r, c + r), fill=teal)
    elif kind == "dark":
        R = S * 0.36
        d.ellipse((c - R, c - R, c + R, c + R), fill=navy)
        d.ellipse((c - R + S * 0.2, c - R - S * 0.08, c + R + S * 0.2, c + R - S * 0.08), fill=(0, 0, 0, 0))
    else:  # auto: half light, half dark
        R = S * 0.38
        d.ellipse((c - R, c - R, c + R, c + R), outline=navy, width=int(S * 0.07))
        d.pieslice((c - R, c - R, c + R, c + R), 90, 270, fill=navy)
    return img.resize((size, size), Image.LANCZOS)


def main():
    icons = HERE.parent / "branding-ext" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for kind in ("light", "dark", "auto"):
        for n in (16, 26):
            theme_icon(kind, n).save(icons / f"theme_{kind}_{n}.png")
    (OUT / "program" / "shell").mkdir(parents=True, exist_ok=True)
    splash(644, 199).save(OUT / "program" / "intro.png")
    splash(990, 306).save(OUT / "program" / "intro-highres.png")

    dark_text, light_text = (20, 30, 40), (255, 255, 255)
    shell = OUT / "program" / "shell"
    for name, rgb in (("logo.svg", dark_text), ("logo_inverted.svg", light_text),
                      ("logo-sc.svg", dark_text), ("logo-sc_inverted.svg", light_text)):
        (shell / name).write_text(svg_of(wordmark(rgb), 346), encoding="utf-8")
    about = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    about.alpha_composite(logo(600, 0.12))
    (shell / "about.svg").write_text(svg_of(about, 372), encoding="utf-8")

    ico = logo(256, 0.2)
    ico.save(OUT / "vinos-office.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # NSIS wizard: side panel 164×314, header 150×57 (24-bit BMP)
    side = Image.new("RGBA", (164, 314), BG + (255,))
    strip = art_strip(164, 150)
    side.alpha_composite(strip.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_LEFT_RIGHT), (0, 164))
    side.alpha_composite(logo(116), (24, 26))
    d = ImageDraw.Draw(side)
    d.text((82, 150), NAME, font=font(17, True), fill=(255, 255, 255), anchor="mm")
    side.convert("RGB").save(OUT / "installer-side.bmp")
    head = Image.new("RGBA", (150, 57), (255, 255, 255, 255))
    head.alpha_composite(logo(45), (100, 6))
    head.convert("RGB").save(OUT / "installer-header.bmp")
    print("assets written to", OUT)


if __name__ == "__main__":
    main()

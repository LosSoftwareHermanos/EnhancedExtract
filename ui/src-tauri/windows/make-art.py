"""Draw the installer bitmaps from the brand assets: python ui/src-tauri/windows/make-art.py

NSIS stretches each bitmap to its control, so they are drawn at twice the 96-DPI size
and look sharp on 125-200 % displays. Output is 24-bit BMP, the only kind NSIS loads.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LOGO = ROOT / "site/assets/media/logo.png"
DISPLAY = HERE / "fonts/oxanium-700.ttf"
TEXT = HERE / "fonts/bai-jamjuree-600.ttf"

GROUND = (11, 12, 18)
SURFACE = (19, 20, 28)
LINE = (38, 39, 51)
INK = (236, 234, 220)
MUTED = (108, 108, 122)
YELLOW = (252, 238, 10)
CYAN = (0, 229, 240)

S = 2  # supersampling: drawn at 2x the 96-DPI control size


def grid(draw, w, h, step, color):
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=color, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=color, width=1)


def brackets(draw, box, arm, width, color):
    x0, y0, x1, y1 = box
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line([(x, y), (x + dx * arm, y)], fill=color, width=width)
        draw.line([(x, y), (x, y + dy * arm)], fill=color, width=width)


def logo(size):
    img = Image.open(LOGO).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


def sidebar(path):
    """Left art of the Welcome and Finish pages: 109x193 dialog units = 164x314 px at 96 DPI."""
    w, h = 164 * S, 314 * S
    img = Image.new("RGB", (w, h), GROUND)
    d = ImageDraw.Draw(img)

    # Perspective floor grid, like the app's backdrop.
    horizon = int(h * 0.80)
    vx = w // 2
    for i in range(-8, 9):
        d.line([(vx, horizon), (vx + i * 70 * S, h)], fill=(24, 25, 34), width=S)
    y, gap = horizon, 6 * S
    while y < h:
        d.line([(0, y), (w, y)], fill=(24, 25, 34), width=S)
        y += gap
        gap = int(gap * 1.32)
    d.line([(0, horizon), (w, horizon)], fill=(30, 72, 84), width=S)

    # Logo tile with its corner brackets.
    size = 96 * S
    lx, ly = (w - size) // 2, 54 * S
    img.paste(logo(size), (lx, ly), logo(size))
    pad = 12 * S
    brackets(d, (lx - pad, ly - pad, lx + size + pad, ly + size + pad), 12 * S, 2 * S, YELLOW)

    # Wordmark.
    big = ImageFont.truetype(str(DISPLAY), 21 * S)
    small = ImageFont.truetype(str(TEXT), 8 * S)
    for i, word in enumerate(("ENHANCED", "EXTRACT")):
        tw = d.textlength(word, font=big)
        d.text(((w - tw) / 2, ly + size + 30 * S + i * 23 * S), word, font=big, fill=INK if i == 0 else YELLOW)

    tag = "DELETE-AS-YOU-GO EXTRACTION"
    tw = d.textlength(tag, font=small)
    d.text(((w - tw) / 2, ly + size + 82 * S), tag, font=small, fill=MUTED)

    # Footer: the same "EE ▬▬ ▪" mark the site uses.
    fy = h - 22 * S
    d.text((14 * S, fy - 5 * S), "SETUP", font=small, fill=MUTED)
    d.rectangle([w - 70 * S, fy, w - 26 * S, fy + 3 * S], fill=YELLOW)
    d.rectangle([w - 22 * S, fy, w - 14 * S, fy + 3 * S], fill=YELLOW)
    img.save(path)


def header(path):
    """Right of the page header: modern_headerbmp is 150x57 px at 96 DPI."""
    w, h = 150 * S, 57 * S
    img = Image.new("RGB", (w, h), GROUND)
    d = ImageDraw.Draw(img)
    size = 34 * S
    x, y = w - size - 18 * S, (h - size) // 2
    img.paste(logo(size), (x, y), logo(size))
    brackets(d, (x - 6 * S, y - 6 * S, x + size + 6 * S, y + size + 6 * S), 6 * S, S, YELLOW)
    img.save(path)


if __name__ == "__main__":
    out = HERE / "art"
    out.mkdir(exist_ok=True)
    sidebar(out / "sidebar.bmp")
    header(out / "header.bmp")
    print("wrote", *sorted(p.name for p in out.glob("*.bmp")))

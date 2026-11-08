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


# ---------- frameless window: title bar and buttons ----------------------------------------
# Native buttons can't have cut corners, so the installer shows these bitmaps instead (skin.nsh).
# Unlike the art above they are not stretched: one set per display scale, picked at run time.

WORDMARK = ROOT / "ui/src/assets/wordmark.png"
NEGATIVE = (255, 70, 85)
CONTROL = (61, 62, 78)
SCALES = (100, 125, 150, 200)
SS = 4  # supersampling for clean diagonal cuts and text

# label, style. Primary is the yellow action; the rest are outlined like the app's .btn.
BUTTONS = {
    "next": ("NEXT", "primary"), "install": ("INSTALL", "primary"), "finish": ("FINISH", "primary"),
    "uninstall": ("UNINSTALL", "primary"), "close": ("CLOSE", "primary"),
    "back": ("BACK", "outline"), "cancel": ("CANCEL", "outline"), "browse": ("BROWSE", "outline"),
    "exit": ("EXIT", "danger"),
}


def button(path, label, style, scale, enabled):
    k = scale / 100
    w, h, cut = (round(58 * k), round(26 * k), round(7 * k)) if style == "danger" else (round(104 * k), round(30 * k), round(8 * k))
    W, H, C = w * SS, h * SS, cut * SS
    img = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(img)
    if style == "primary":
        fill, ink = (YELLOW, GROUND) if enabled else ((58, 56, 20), (216, 210, 162))
        # Two cut corners, like .btn-primary: top left and bottom right.
        d.polygon([(C, 0), (W, 0), (W, H - C), (W - C, H), (0, H), (0, C)], fill=fill)
    else:
        line = NEGATIVE if style == "danger" else (CONTROL if enabled else LINE)
        ink = NEGATIVE if style == "danger" else (INK if enabled else MUTED)
        t = max(SS, round(k * SS))  # a 1 px line at this scale
        outer = [(0, 0), (W, 0), (W, H - C), (W - C, H), (0, H)]
        d.polygon(outer, fill=line)
        d.polygon([(t, t), (W - t, t), (W - t, H - C - t // 2), (W - C - t // 2, H - t), (t, H - t)], fill=GROUND)
    font = ImageFont.truetype(str(DISPLAY), round((12.5 if style != "danger" else 12) * k * SS))
    spacing = 0.06 * font.size
    widths = [d.textlength(ch, font=font) for ch in label]
    tw = sum(widths) + spacing * (len(label) - 1)
    x = (W - tw) / 2
    top, bottom = font.getbbox("NEXT")[1], font.getbbox("NEXT")[3]
    y = (H - (bottom - top)) / 2 - top
    for ch, cw in zip(label, widths):
        d.text((x, y), ch, font=font, fill=ink)
        x += cw + spacing
    img.resize((w, h), Image.LANCZOS).save(path)


def wordmark(path, scale):
    k = scale / 100
    mark = Image.open(WORDMARK).convert("RGBA")
    h = round(14 * k)
    w = round(mark.width * h / mark.height)
    mark = mark.resize((w, h), Image.LANCZOS)
    img = Image.new("RGB", (w, h), GROUND)
    img.paste(mark, (0, 0), mark)
    img.save(path)


def toggle(path, kind, checked, enabled, scale):
    """The app's square radio (.radio: a 2px box, a filled square inside when chosen) and its
    checkbox (input[type=checkbox]: a 1px box, yellow with a dark tick when on)."""
    k = scale / 100
    n = round((14 if kind == "radio" else 16) * k)
    N = n * SS
    img = Image.new("RGB", (N, N), GROUND)
    d = ImageDraw.Draw(img)
    if kind == "radio":
        color = (YELLOW if checked else (198, 198, 192)) if enabled else CONTROL
        t = round(2 * k * SS)
        d.rectangle([0, 0, N - 1, N - 1], fill=color)
        d.rectangle([t, t, N - 1 - t, N - 1 - t], fill=GROUND)
        if checked:
            i = round(4 * k * SS)
            d.rectangle([i, i, N - 1 - i, N - 1 - i], fill=color)
    else:
        t = max(SS, round(k * SS))
        if checked:
            d.rectangle([0, 0, N - 1, N - 1], fill=YELLOW)
            m, s = N * 0.19, N * 0.62          # the tick sits in a 10/16 box, centred
            pts = [(0.12, 0.48), (0, 0.62), (0.40, 1), (1, 0.22), (0.87, 0.09), (0.40, 0.72)]
            d.polygon([(m + x * s, m + y * s) for x, y in pts], fill=GROUND)
        else:
            d.rectangle([0, 0, N - 1, N - 1], fill=CONTROL if enabled else LINE)
            d.rectangle([t, t, N - 1 - t, N - 1 - t], fill=GROUND)
    img.resize((n, n), Image.LANCZOS).save(path)


def chrome(out):
    out.mkdir(exist_ok=True)
    for scale in SCALES:
        for kind in ("radio", "check"):
            for checked in (True, False):
                toggle(out / f"{kind}_{'on' if checked else 'off'}_{scale}.bmp", kind, checked, True, scale)
        toggle(out / f"radio_dis_{scale}.bmp", "radio", False, False, scale)
        wordmark(out / f"wordmark_{scale}.bmp", scale)
        for key, (label, style) in BUTTONS.items():
            for enabled in (True, False):
                if style == "danger" and not enabled:
                    continue
                button(out / f"{key}_{'on' if enabled else 'off'}_{scale}.bmp", label, style, scale, enabled)


if __name__ == "__main__":
    out = HERE / "art"
    out.mkdir(exist_ok=True)
    sidebar(out / "sidebar.bmp")
    header(out / "header.bmp")
    chrome(out / "chrome")
    print("wrote", *sorted(p.name for p in out.glob("*.bmp")), f"and {len(list((out / 'chrome').glob('*.bmp')))} chrome bitmaps")

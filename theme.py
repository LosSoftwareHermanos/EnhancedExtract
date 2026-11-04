"""Cyberpunk look for the app: colours, font loading, ttk styles and the custom widgets
ttk can't draw (buttons and panels with cut corners)."""
import ctypes
import os
import random
import tkinter as tk
from tkinter import font as tkfont, ttk

import sounds

BG = "#0B0C12"
FIELD = "#171822"
LINE = "#3D3E4E"
TEXT = "#ECEADC"
MUTED = "#A0A0AE"
DIM = "#6C6C7A"
YELLOW = "#FCEE0A"
YELLOW_HOVER = "#FFF75E"
CYAN = "#00E5F0"
RED = "#FF4655"

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FR_PRIVATE = 0x10
CUT = 9     # size of a cut corner, in pixels

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# The title art may sit next to the app or in the EE assets folder.
TITLE_PNG_PLACES = (os.path.join(_APP_DIR, "title", "title2.png"),
                    os.path.join(_APP_DIR, "EE", "title", "title2.png"))
TITLE_HEIGHT = 36          # height of the title art in the header, in pixels
GLITCH_SHIFT = 6            # furthest a slice of the title moves sideways, in pixels
GLITCH_GHOST = 2            # furthest the cyan/red copies sit from the title, in pixels
GLITCH_GAP_MS = (2000, 5000)    # calm time between bursts
GLITCH_FRAMES = (3, 4)      # frames in one burst
GLITCH_FRAME_MS = (30, 50)  # how long each burst frame stays up
GLITCH_VARIANTS = 16        # different glitch frames prepared at startup


def _load_font_files():
    """Make the bundled fonts available to this process only (nothing is installed)."""
    if not os.path.isdir(FONT_DIR):
        return
    for name in os.listdir(FONT_DIR):
        if name.lower().endswith(".ttf"):
            try:
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(FONT_DIR, name), FR_PRIVATE, 0)
            except OSError:
                pass


def pick_family(root):
    families = set(tkfont.families(root))
    for family in ("Rajdhani Medium", "Rajdhani", "Bahnschrift", "Segoe UI"):
        if family in families:
            return family
    return "TkDefaultFont"


def title_family(root):
    return "Rajdhani" if "Rajdhani" in tkfont.families(root) else pick_family(root)


def dark_title_bar(root):
    """Ask Windows for a dark title bar. Older Windows ignores this, which is fine."""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except (OSError, AttributeError):
        pass


def apply(root):
    _load_font_files()
    family = pick_family(root)
    for name, size in (("TkDefaultFont", 11), ("TkTextFont", 11), ("TkHeadingFont", 11), ("TkMenuFont", 11)):
        tkfont.nametofont(name).configure(family=family, size=size)
    root.configure(bg=BG)
    root.option_add("*Text.background", FIELD)
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", YELLOW)
    root.option_add("*Text.selectBackground", YELLOW)
    root.option_add("*Text.selectForeground", BG)
    root.option_add("*Text.font", ("Consolas", 10))
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 0)
    root.option_add("*Text.padX", 8)
    root.option_add("*Text.padY", 6)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, bordercolor=LINE, lightcolor=BG, darkcolor=BG,
                troughcolor=FIELD, fieldbackground=FIELD, insertcolor=YELLOW,
                selectbackground=YELLOW, selectforeground=BG, focuscolor=CYAN)
    s.map(".", foreground=[("disabled", DIM)])
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Good.TLabel", foreground=CYAN)
    s.configure("Bad.TLabel", foreground=RED)
    s.configure("PanelTitle.TLabel", foreground=YELLOW, font=(title_family(root), 12, "bold"))

    s.configure("TEntry", padding=(6, 4), bordercolor=LINE, lightcolor=FIELD, darkcolor=FIELD)
    s.map("TEntry", bordercolor=[("focus", YELLOW)], lightcolor=[("focus", YELLOW)],
          darkcolor=[("focus", YELLOW)], fieldbackground=[("disabled", BG), ("readonly", FIELD)])
    s.configure("TSpinbox", padding=(6, 4), arrowcolor=YELLOW, arrowsize=12, background=FIELD,
                lightcolor=FIELD, darkcolor=FIELD)
    s.map("TSpinbox", bordercolor=[("focus", YELLOW)], fieldbackground=[("disabled", BG)],
          arrowcolor=[("disabled", DIM)])

    s.configure("TCheckbutton", indicatorbackground=FIELD, indicatorforeground=BG, indicatormargin=(0, 2, 8, 2),
                upperbordercolor=LINE, lowerbordercolor=LINE, padding=(0, 2))
    # Same layout as clam's but without the dotted focus ring round the text; the box
    # itself turns cyan when the checkbox has keyboard focus.
    s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Checkbutton.indicator", {"side": "left", "sticky": ""}),
        ("Checkbutton.label", {"side": "left", "sticky": "nswe"})]})])
    s.map("TCheckbutton", background=[("active", BG)], foreground=[("active", YELLOW), ("disabled", DIM)],
          indicatorbackground=[("selected", YELLOW), ("active", FIELD)],
          upperbordercolor=[("focus", CYAN), ("selected", YELLOW)],
          lowerbordercolor=[("focus", CYAN), ("selected", YELLOW)])

    s.configure("Horizontal.TProgressbar", background=CYAN, troughcolor=FIELD, bordercolor=LINE,
                lightcolor=CYAN, darkcolor=CYAN, thickness=14)
    s.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG, lightcolor=LINE,
                darkcolor=LINE, arrowcolor=TEXT, relief="flat")
    s.map("Vertical.TScrollbar", background=[("active", YELLOW), ("disabled", BG)],
          lightcolor=[("active", YELLOW)], darkcolor=[("active", YELLOW)],
          arrowcolor=[("active", BG), ("disabled", DIM)])

    s.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT, rowheight=24,
                bordercolor=LINE, lightcolor=FIELD, darkcolor=FIELD)
    s.map("Treeview", background=[("selected", YELLOW)], foreground=[("selected", BG)])
    s.configure("Treeview.Heading", background=BG, foreground=YELLOW, bordercolor=LINE, lightcolor=BG,
                darkcolor=BG, relief="flat", font=(family, 10))
    s.map("Treeview.Heading", background=[("active", FIELD)])
    dark_title_bar(root)

    # CutButton's cyan focus ring shows only while the user moves around with Tab, not when
    # a pop-up hands its button the focus or after a click.
    def focus_ring(on):
        CutButton.show_focus = on
        try:
            w = root.focus_get()
        except KeyError:        # focus is in a widget tkinter doesn't know (a dropdown list)
            return
        if isinstance(w, CutButton):
            w._draw()
    for move in ("<<NextWindow>>", "<<PrevWindow>>"):     # Tab and Shift+Tab
        root.bind_all(move, lambda e: root.after_idle(focus_ring, True), add="+")
    root.bind_all("<ButtonPress>", lambda e: focus_ring(False), add="+")


class CutButton(tk.Canvas):
    """A button with a cut bottom-right corner. Variants: primary (solid yellow, the main
    action), ghost (outline) and danger (red outline, for destructive actions)."""

    show_focus = False      # draw the focus ring; on while the user is moving with Tab (see apply)

    def __init__(self, master, text, command=None, variant="ghost", state="normal", padx=20, height=34, font=None,
                 sound="button"):
        super().__init__(master, height=height, bg=BG, highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self._text, self._command, self._variant, self._state = text, command, variant, state
        self._sound = sound     # name in sounds.FILES, or None when the command plays its own
        self._hover = self._pressed = self._focus = False
        self._font = font or tkfont.Font(root=self, family=title_family(self), size=11, weight="bold")
        self._h = height
        tk.Canvas.configure(self, width=self._font_measure(text) + 2 * padx)
        for seq, fn in (("<Enter>", lambda e: self._set(_hover=True)),
                        ("<Leave>", lambda e: self._set(_hover=False, _pressed=False)),
                        ("<ButtonPress-1>", lambda e: self._set(_pressed=True)),
                        ("<ButtonRelease-1>", self._release),
                        ("<FocusIn>", lambda e: self._set(_focus=True)),
                        ("<FocusOut>", lambda e: self._set(_focus=False)),
                        ("<space>", lambda e: self.invoke()),
                        ("<Return>", lambda e: self.invoke()),
                        ("<Configure>", lambda e: self._draw())):
            self.bind(seq, fn)
        self._draw()

    def _font_measure(self, text):
        if isinstance(self._font, tkfont.Font):
            return self._font.measure(text)
        return tkfont.Font(root=self, font=self._font).measure(text)

    def _set(self, **flags):
        for name, value in flags.items():
            setattr(self, name, value)
        self._draw()

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        was_pressed = self._pressed
        self._set(_pressed=False)
        if was_pressed and inside:
            self.invoke()

    def invoke(self):
        if self._state != "disabled" and self._command:
            if self._sound:
                sounds.play(self._sound)
            self._command()

    def set_variant(self, variant):
        self._variant = variant
        self._draw()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            tk.Canvas.configure(self, cursor="arrow" if self._state == "disabled" else "hand2",
                                takefocus=0 if self._state == "disabled" else 1)
        if "text" in kw:
            self._text = kw.pop("text")
        if cnf or kw:
            tk.Canvas.configure(self, cnf, **kw)
        self._draw()

    config = configure

    def _colors(self):
        """(fill, outline, text) for the current state."""
        if self._state == "disabled":
            return BG, LINE, DIM
        if self._variant == "primary":
            fill = YELLOW_HOVER if self._hover else YELLOW
            return fill, fill, BG
        accent = RED if self._variant == "danger" else YELLOW
        if self._pressed:
            return accent, accent, BG
        if self._hover:
            return BG, accent, accent
        return BG, RED if self._variant == "danger" else LINE, RED if self._variant == "danger" else TEXT

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), int(tk.Canvas.cget(self, "width")))
        h = self._h
        fill, outline, text = self._colors()
        ring = self._focus and CutButton.show_focus and self._state != "disabled"
        if ring:
            outline = CYAN
        points = [1, 1, w - 2, 1, w - 2, h - 2 - CUT, w - 2 - CUT, h - 2, 1, h - 2]
        self.create_polygon(points, fill=fill, outline=outline, width=2 if ring else 1)
        self.create_text(w // 2, h // 2, text=self._text, fill=text, font=self._font)


class CheckBox(ttk.Checkbutton):
    """ttk.Checkbutton that plays the on / off sound when it's ticked or unticked."""

    def __init__(self, master, command=None, **kw):
        self._user_command = command
        super().__init__(master, command=self._toggled, **kw)

    def _toggled(self):
        sounds.play("check_on" if self.instate(["selected"]) else "check_off")
        if self._user_command:
            self._user_command()


class Panel(tk.Frame):
    """A titled outline box with a cut bottom-right corner. Put children in .body."""

    def __init__(self, master, title=None, padding=10):
        super().__init__(master, bg=BG)
        if title:
            ttk.Label(self, text=title, style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 3))
        box = tk.Frame(self, bg=BG, highlightthickness=1, highlightbackground=LINE)
        box.pack(fill="both", expand=True)
        self.body = ttk.Frame(box, padding=padding)
        self.body.pack(fill="both", expand=True)
        size = CUT + 3
        notch = tk.Canvas(box, width=size, height=size, bg=BG, highlightthickness=0, bd=0)
        notch.create_polygon(size, 0, size, size, 0, size, fill=BG, outline="")
        notch.create_line(0, size - 1, size - 1, 0, fill=LINE)
        notch.place(relx=1, rely=1, anchor="se", x=1, y=1)


def _title_frames(master):
    """Build the title art: returns (clean frame, list of glitch frames). The PNG only
    supplies the letter shapes; its empty space is cropped and the colour comes from the theme."""
    from PIL import Image, ImageChops, ImageTk

    path = next((p for p in TITLE_PNG_PLACES if os.path.exists(p)), TITLE_PNG_PLACES[0])
    alpha = Image.open(path).convert("RGBA").getchannel("A")
    alpha = alpha.crop(alpha.getbbox())
    width = round(alpha.width * TITLE_HEIGHT / alpha.height)
    letters = alpha.resize((width, TITLE_HEIGHT), Image.LANCZOS)
    margin = GLITCH_SHIFT + GLITCH_GHOST    # room for the glitch to move without clipping
    mask = Image.new("L", (width + 2 * margin, TITLE_HEIGHT))
    mask.paste(letters, (margin, 0))

    def frame(ghost=0):
        img = Image.new("RGB", mask.size, BG)
        if ghost:
            img.paste(CYAN, None, ImageChops.offset(mask, ghost, 0))
            img.paste(RED, None, ImageChops.offset(mask, -ghost, 0))
        img.paste(YELLOW, None, mask)
        return img

    def glitched():
        img = frame(random.randint(1, GLITCH_GHOST))
        for _ in range(random.randint(2, 4)):
            top = random.randint(0, TITLE_HEIGHT - 2)
            band = (0, top, img.width, min(top + random.randint(2, 6), TITLE_HEIGHT))
            shift = random.choice((-1, 1)) * random.randint(2, GLITCH_SHIFT)
            img.paste(ImageChops.offset(img.crop(band), shift, 0), band)
        return img

    return (ImageTk.PhotoImage(frame(), master=master),
            [ImageTk.PhotoImage(glitched(), master=master) for _ in range(GLITCH_VARIANTS)])


class Header(tk.Canvas):
    """App name as title art with short glitch bursts, the one loud thing on screen. Falls
    back to plain text if the art or Pillow is missing."""

    def __init__(self, master, text):
        super().__init__(master, height=58, bg=BG, highlightthickness=0, bd=0)
        try:
            self._clean, self._glitches = _title_frames(self)
        except (ImportError, OSError):
            font = (title_family(self), 30, "bold")
            self.create_text(18, 31, text=text, anchor="w", font=font, fill=CYAN)
            self.create_text(15, 28, text=text, anchor="w", font=font, fill=YELLOW)
            return
        # The frames carry a margin on the left; pull it back so the letters line up with the tabs.
        self._image = self.create_image(14 - GLITCH_SHIFT - GLITCH_GHOST, 29, anchor="w", image=self._clean)
        self._wait_for_burst()

    def _wait_for_burst(self):
        self.after(random.randint(*GLITCH_GAP_MS), self._burst, random.randint(*GLITCH_FRAMES))

    def _burst(self, frames_left):
        if frames_left:
            self.itemconfigure(self._image, image=random.choice(self._glitches))
            self.after(random.randint(*GLITCH_FRAME_MS), self._burst, frames_left - 1)
        else:
            self.itemconfigure(self._image, image=self._clean)
            self._wait_for_burst()

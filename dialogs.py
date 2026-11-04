"""Pop-ups in the app's look. Same call style as tkinter.messagebox, so the rest of the app
just imports this module as messagebox.

Like messagebox, every function blocks until the pop-up is closed. Closing it with Esc
counts as No / Cancel. On a warning question No has the keyboard focus, so pressing
Enter by accident never confirms something risky."""
import tkinter as tk
from tkinter import ttk

import chrome
import sounds
import theme
from theme import CutButton

WRAP = 460      # message width, in pixels


class _Dialog(tk.Toplevel):
    def __init__(self, parent, title, message, accent):
        parent = parent.winfo_toplevel() if parent else tk._default_root
        # No Windows title bar: the pop-up draws its own border and title, and is moved by
        # dragging the title. Esc and the buttons close it.
        super().__init__(parent, bg=theme.BG, highlightthickness=1, highlightbackground=theme.LINE)
        self.withdraw()
        self.title(title)
        self.result = None
        self.owner = parent
        tk.Frame(self, bg=accent, width=4).pack(side="left", fill="y")
        self.body = ttk.Frame(self, padding=(18, 14, 18, 14))
        self.body.pack(side="left", fill="both", expand=True)
        heading = ttk.Label(self.body, text=title.upper(), foreground=accent, cursor="fleur",
                            font=(theme.title_family(self), 14, "bold"))
        heading.pack(anchor="w", pady=(0, 8))
        chrome.make_draggable(self, heading)
        ttk.Label(self.body, text=message, wraplength=WRAP, justify="left").pack(anchor="w")
        self.buttons = ttk.Frame(self.body)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

    def add_buttons(self, *specs):
        """specs: (text, result, variant), left to right."""
        self.buttons.pack(anchor="e", pady=(16, 0))
        made = []
        for text, result, variant in specs:
            b = CutButton(self.buttons, text, command=lambda r=result: self.close(r), variant=variant, padx=26)
            b.pack(side="left", padx=(8, 0))
            made.append(b)
        return made

    def close(self, result=None):
        self.result = result
        self.grab_release()
        self.destroy()

    def run(self, focus):
        """Show centred on the app, hold input until closed, return the result."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if self.owner.winfo_viewable():
            self.transient(self.owner)
            x = self.owner.winfo_rootx() + (self.owner.winfo_width() - w) // 2
            y = self.owner.winfo_rooty() + (self.owner.winfo_height() - h) // 2
        else:
            x, y = (self.winfo_screenwidth() - w) // 2, (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        sounds.play("popup")
        self.deiconify()
        self.wait_visibility()
        chrome.hide_title_bar(self)
        self.grab_set()
        self.lift()
        focus.focus_force()
        self.wait_window()
        return self.result


def _notice(title, message, accent, parent):
    d = _Dialog(parent, title, message, accent)
    ok, = d.add_buttons(("OK", True, "primary"))
    d.run(ok)


def showinfo(title, message, parent=None, **_):
    _notice(title, message, theme.CYAN, parent)


def showwarning(title, message, parent=None, **_):
    _notice(title, message, theme.YELLOW, parent)


def showerror(title, message, parent=None, **_):
    _notice(title, message, theme.RED, parent)


def askyesno(title, message, icon=None, parent=None, **_):
    risky = icon == "warning"
    d = _Dialog(parent, title, message, theme.RED if risky else theme.YELLOW)
    no, yes = d.add_buttons(("NO", False, "ghost"), ("YES", True, "danger" if risky else "primary"))
    return bool(d.run(no if risky else yes))


def askstring(title, message, show=None, parent=None, **_):
    """The typed text, or None if cancelled."""
    d = _Dialog(parent, title, message, theme.YELLOW)
    value = tk.StringVar()
    entry = ttk.Entry(d.body, textvariable=value, show=show or "", width=44)
    entry.pack(fill="x", pady=(12, 0))
    entry.bind("<Return>", lambda e: d.close(value.get()))
    d.add_buttons(("CANCEL", None, "ghost"))
    ok = CutButton(d.buttons, "OK", command=lambda: d.close(value.get()), variant="primary", padx=26)
    ok.pack(side="left", padx=(8, 0))
    return d.run(entry)

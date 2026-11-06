"""What the app needs from the PC, and the SYSTEM CHECK pop-up shown when it opens.

- WinFsp: driver for tab 2's virtual drive. Has to be installed in Windows; the app
  carries its installer, so INSTALL works without a download.
- UnRAR: for tab 1. WinRAR's copy is used if WinRAR is installed, else the copy that
  ships with the app, so normally nothing is missing. If both are gone, the pop-up
  links to the official WinRAR site (WinRAR's own installer may not be bundled)."""
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import settings
import theme
from dialogs import _Dialog
from extractor import rar_tool
from isocore import install_winfsp, winfsp_installed
from theme import CheckBox, CutButton

WINRAR_SITE = "https://www.win-rar.com/download.html"
HIDE_KEY = "hide_system_check"      # setting: "Don't show this again" was ticked


class SystemCheck(_Dialog):
    def __init__(self, parent):
        super().__init__(parent, "System check", "What this app needs on this PC:", theme.CYAN)
        self.busy = False
        self.error_label = None
        rows = ttk.Frame(self.body)
        rows.pack(fill="x", pady=(10, 0))
        self.winfsp = self._row(rows, 0, "WinFsp", "virtual drive for tab 2 (install from ISO)")
        self.rar = self._row(rows, 1, "RAR extractor", "for tab 1 (extract RAR)")
        rows.columnconfigure(1, weight=1)
        self.hide_var = tk.BooleanVar(value=bool(settings.get(HIDE_KEY, False)))
        CheckBox(self.body, text="Don't show this again", variable=self.hide_var).pack(anchor="w", pady=(14, 0))
        self.later = self.add_buttons(("LATER", None, "ghost"))[0]
        self.refresh()

    def _row(self, rows, r, name, what):
        ttk.Label(rows, text=name, font=(theme.title_family(self), 12, "bold")).grid(
            row=r, column=0, sticky="w", padx=(0, 14), pady=4)
        ttk.Label(rows, text=what, style="Muted.TLabel").grid(row=r, column=1, sticky="w", pady=4)
        status = ttk.Label(rows, width=24)
        status.grid(row=r, column=2, sticky="w", padx=(14, 0), pady=4)
        slot = ttk.Frame(rows, width=120, height=34)       # holds the row's button, if any
        slot.grid(row=r, column=3, sticky="e", padx=(10, 0), pady=4)
        slot.grid_propagate(False)
        return {"status": status, "slot": slot, "button": None}

    def _set(self, row, ok, text, button=None):
        row["status"].configure(text=("✓  " if ok else "✗  ") + text, style="Good.TLabel" if ok else "Bad.TLabel")
        if row["button"]:
            row["button"].destroy()
            row["button"] = None
        if button:
            label, command = button
            row["button"] = CutButton(row["slot"], label, command=command, variant="primary", padx=14)
            row["button"].place(relx=1, rely=0.5, anchor="e")

    def refresh(self):
        """Check both again; if nothing is missing, LATER becomes ALL SET."""
        fsp = winfsp_installed()
        if fsp:
            self._set(self.winfsp, True, "installed")
        else:
            self._set(self.winfsp, False, "not installed", ("INSTALL", self._install))
        tool = rar_tool()
        if tool:
            self._set(self.rar, True, tool[0])
        else:
            self._set(self.rar, False, "missing", ("GET WINRAR", lambda: webbrowser.open(WINRAR_SITE)))
        if fsp and tool:
            self.later.configure(text="ALL SET")
            self.later.set_variant("primary")

    def _install(self):
        self.busy = True
        self.winfsp["button"].configure(state="disabled", text="WAIT")
        self.winfsp["status"].configure(text="…  installing", style="TLabel")
        self.later.configure(state="disabled")

        def run():
            error = install_winfsp()
            self.after(0, done, error)

        def done(error):
            self.busy = False
            self.later.configure(state="normal")
            self.refresh()
            if error:
                self.winfsp["status"].configure(text="✗  install failed")
                if not self.error_label:
                    self.error_label = ttk.Label(self.body, style="Bad.TLabel", wraplength=520)
                    self.error_label.pack(anchor="w", pady=(8, 0), before=self.buttons)
                self.error_label.configure(text=f"WinFsp install failed ({error}). "
                                                "Try again, or get it from winfsp.dev.")

        threading.Thread(target=run, daemon=True).start()

    def close(self, result=None):
        if self.busy:       # an install is running; its result still has to land here
            return
        settings.put(HIDE_KEY, self.hide_var.get())
        super().close(result)


def check(parent):
    """Show the SYSTEM CHECK pop-up until the user closes it."""
    d = SystemCheck(parent)
    d.run(d.later)


def check_at_start(parent):
    """The pop-up shown when the app opens. "Don't show this again" skips it, but only while
    nothing is missing."""
    if settings.get(HIDE_KEY, False) and winfsp_installed() and rar_tool():
        return
    check(parent)

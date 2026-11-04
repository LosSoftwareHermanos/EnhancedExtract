"""EnhancedExtract - extract RAR sets and install games from ISOs while freeing space as you go.

Tab 1: extract multi-part RAR sets, deleting each part as it is used.
Tab 2: serve an ISO as a virtual drive and free ISO space behind setup.exe.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk

import chrome
import dialogs as messagebox
import extractor as ex
import paths
import requirements
import theme
from install_tab import InstallTab
import sounds
from theme import CheckBox, CutButton, Panel


class RarTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.events = queue.Queue()
        self.info = None
        self.runner = None
        self.worker = None

        self.archive_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.verify_var = tk.BooleanVar(value=True)
        self.delete_var = tk.BooleanVar(value=True)
        self.password_var = tk.StringVar()
        self.show_pw_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Pick the first part of a RAR set.")
        self.space_var = tk.StringVar(value="")

        self._build()
        self.delete_var.trace_add("write", lambda *_: self._refresh_space())
        self.dest_var.trace_add("write", lambda *_: self._refresh_space())
        self.after(100, self._pump)

    # ---------- layout ----------
    def _build(self):
        pad = {"padx": 4, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=14, pady=(10, 12))
        frm.columnconfigure(0, weight=1)

        source = Panel(frm, "// ARCHIVE")
        source.grid(row=0, column=0, sticky="ew")
        src = source.body
        src.columnconfigure(1, weight=1)
        ttk.Label(src, text="Archive (part 1)").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(src, textvariable=self.archive_var, state="readonly").grid(row=0, column=1, sticky="ew", **pad)
        self.btn_archive = CutButton(src, "BROWSE", command=self._pick_archive)
        self.btn_archive.grid(row=0, column=2, **pad)

        ttk.Label(src, text="Extract to").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(src, textvariable=self.dest_var).grid(row=1, column=1, sticky="ew", **pad)
        self.btn_dest = CutButton(src, "BROWSE", command=self._pick_dest)
        self.btn_dest.grid(row=1, column=2, **pad)

        ttk.Label(src, text="Password").grid(row=2, column=0, sticky="w", **pad)
        pw = ttk.Frame(src)
        pw.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        self.pw_entry = ttk.Entry(pw, textvariable=self.password_var, show="*", width=30)
        self.pw_entry.pack(side="left", padx=(0, 10))
        CheckBox(pw, text="Show", variable=self.show_pw_var,
                        command=lambda: self.pw_entry.configure(show="" if self.show_pw_var.get() else "*")
                        ).pack(side="left")
        ttk.Label(pw, text="Leave empty if there is none", style="Muted.TLabel").pack(side="left", padx=(14, 0))

        opts = ttk.Frame(src)
        opts.grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 0))
        CheckBox(opts, text="Verify all parts before extracting (recommended)",
                        variable=self.verify_var).pack(anchor="w")
        CheckBox(opts, text="Delete each part as soon as it has been extracted",
                        variable=self.delete_var).pack(anchor="w")

        progress = Panel(frm, "// PROGRESS")
        progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        prog = progress.body
        prog.columnconfigure(0, weight=1)
        self.space_label = ttk.Label(prog, textvariable=self.space_var, justify="left")
        self.space_label.grid(row=0, column=0, sticky="w", **pad)
        self.bar = ttk.Progressbar(prog, maximum=100)
        self.bar.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(prog, textvariable=self.status_var, style="Good.TLabel").grid(row=2, column=0, sticky="w", **pad)

        log = Panel(frm, "// LOG", padding=0)
        log.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        frm.rowconfigure(2, weight=1)
        self.log_box = tk.Text(log.body, height=6, wrap="word", state="disabled")
        self.log_box.tag_configure("error", foreground=theme.RED)
        sb = ttk.Scrollbar(log.body, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, sticky="e", pady=(12, 0))
        self.btn_verify = CutButton(btns, "VERIFY ONLY", command=lambda: self._start(verify_only=True))
        self.btn_verify.pack(side="left", padx=(0, 8))
        self.btn_stop = CutButton(btns, "STOP", command=self._stop, variant="danger", state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))
        self.btn_start = CutButton(btns, "START", command=self._start, variant="primary", padx=34, height=38)
        self.btn_start.pack(side="left")

    # ---------- inputs ----------
    def _pick_archive(self):
        path = filedialog.askopenfilename(title="Pick the first part",
                                          filetypes=[("RAR archives", "*.rar"), ("All files", "*.*")])
        if not path:
            return
        path = os.path.normpath(path)
        while True:
            try:
                self.info = ex.inspect(path, self.password_var.get() or None)
                break
            except ex.PasswordError as e:
                self.info = None
                if not self._ask_password(str(e)):
                    return
            except ex.ExtractError as e:
                self.info = None
                messagebox.showerror("EnhancedExtract", str(e))
                return
        self.archive_var.set(path)
        if not self.dest_var.get():
            base = os.path.basename(path)
            for suffix in (".rar",):
                base = base[: -len(suffix)] if base.lower().endswith(suffix) else base
            base = base.rsplit(".part", 1)[0]
            self.dest_var.set(os.path.join(os.path.dirname(path), base))
        self._log(f"Loaded {len(self.info.volumes)} parts, {self.info.files} files, "
                  f"{ex.human(self.info.packed)} packed -> {ex.human(self.info.unpacked)} unpacked.")
        self._refresh_space()

    def _ask_password(self, reason):
        pw = messagebox.askstring("Password needed", reason + "\n\nEnter the archive password:",
                                    show="*", parent=self)
        if pw:
            self.password_var.set(pw)
            return True
        return False

    def _pick_dest(self):
        path = filedialog.askdirectory(title="Extract to")
        if path:
            self.dest_var.set(os.path.normpath(path))

    def _refresh_space(self):
        if not self.info or not self.dest_var.get():
            self.space_var.set("")
            return
        need = ex.space_needed(self.info, self.dest_var.get(), self.delete_var.get())
        free = ex.free_space(self.dest_var.get())
        ok = free >= need
        self.space_label.configure(style="TLabel" if ok else "Bad.TLabel")
        self.space_var.set(
            f"Parts: {len(self.info.volumes)} ({ex.human(self.info.packed)})    "
            f"Unpacked: {ex.human(self.info.unpacked)}\n"
            f"Free on destination: {ex.human(free)}    Needed: {ex.human(need)}  "
            + ("OK" if ok else f"NOT ENOUGH - {ex.human(need - free)} short"))

    # ---------- running ----------
    def _start(self, verify_only=False):
        if not self.info:
            messagebox.showwarning("EnhancedExtract", "Pick an archive first.")
            return
        dest = self.dest_var.get().strip()
        delete = self.delete_var.get() and not verify_only
        verify = self.verify_var.get() or verify_only
        if not verify_only:
            if not dest:
                messagebox.showwarning("EnhancedExtract", "Pick a destination folder.")
                return
            need = ex.space_needed(self.info, dest, delete)
            free = ex.free_space(dest)
            if free < need and not messagebox.askyesno(
                    "Not enough space",
                    f"Needed about {ex.human(need)}, free {ex.human(free)}.\n"
                    "Extraction will probably fail. Start anyway?", icon="warning"):
                return
            if delete:
                msg = ("Parts will be DELETED as they are extracted.\n\n"
                       "If extraction fails or is stopped midway, the deleted parts are gone "
                       "and you will have to download them again.\n\n")
                if not verify:
                    msg += "Verification is OFF - a corrupt part would only be found after earlier parts are deleted.\n\n"
                if not messagebox.askyesno("Confirm delete mode", msg + "Continue?", icon="warning"):
                    return

        self._set_running(True)
        self.bar["value"] = 0
        self.last_verify_only = verify_only
        self.runner = ex.Runner(log=lambda t: self.events.put(("log", t)),
                                progress=lambda p, i, n: self.events.put(("progress", (p, i, n))),
                                password=self.password_var.get() or None)
        self.phase = "Verifying" if verify else "Extracting"
        self.worker = threading.Thread(target=self._work, args=(dest, verify, verify_only, delete), daemon=True)
        self.worker.start()

    def _work(self, dest, verify, verify_only, delete):
        try:
            if verify:
                self.events.put(("phase", "Verifying"))
                self.runner.verify(self.info)
            if not verify_only:
                self.events.put(("phase", "Extracting"))
                self.runner.extract(self.info, dest, delete)
            self.events.put(("done", None))
        except ex.PasswordError as e:
            self.events.put(("password", str(e)))
        except ex.ExtractError as e:
            self.events.put(("error", str(e)))
        except Exception as e:  # unexpected; keep the GUI alive
            self.events.put(("error", f"Unexpected error: {e!r}"))

    def _stop(self):
        if self.runner and messagebox.askyesno("Stop", "Stop now? Any parts already deleted cannot be recovered.",
                                                 icon="warning"):
            self.runner.stop()

    def _pump(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "phase":
                    self.phase = data
                    self.bar["value"] = 0
                elif kind == "progress":
                    pct, part, total = data
                    if pct is not None:
                        self.bar["value"] = pct
                    self.status_var.set(f"{self.phase}: part {min(part, total)} of {total}"
                                        + (f" - {pct}%" if pct is not None else ""))
                elif kind == "done":
                    self.bar["value"] = 100
                    self.status_var.set("Done.")
                    self._finish()
                    messagebox.showinfo("EnhancedExtract", "Finished successfully.")
                elif kind == "password":
                    self._log("ERROR: " + data)
                    self.status_var.set("Password needed.")
                    self._finish()
                    if self._ask_password(data):
                        self._start(verify_only=self.last_verify_only)
                elif kind == "error":
                    self._log("ERROR: " + data)
                    left = ex.remaining_parts(self.info) if self.info else []
                    self.status_var.set("Failed.")
                    self._finish()
                    messagebox.showerror("EnhancedExtract", data + f"\n\nParts still on disk: {len(left)} of "
                                         f"{len(self.info.volumes) if self.info else 0}.")
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _finish(self):
        self._set_running(False)
        self._refresh_space()

    def _set_running(self, running):
        state = "disabled" if running else "normal"
        for b in (self.btn_start, self.btn_verify, self.btn_archive, self.btn_dest, self.pw_entry):
            b.configure(state=state)
        self.btn_stop.configure(state="normal" if running else "disabled")
        sounds.start_progress() if running else sounds.stop_progress()

    def _log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n", "error" if text.startswith("ERROR") else ())
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def busy(self):
        return bool(self.worker and self.worker.is_alive())

    def shutdown(self):
        if self.busy():
            self.runner.stop()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # Invisible until the title bar is gone and the UI is drawn, so the plain Windows
        # frame never flashes up first. _go_borderless shows it.
        self.attributes("-alpha", 0.0)
        self.title("EnhancedExtract")
        chrome.set_app_icon(self)
        # Tab 2 needs about 880 pixels to show everything; stay on screen on smaller displays.
        width, height = 860, min(880, self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}")
        theme.apply(self)
        sounds.preload()
        sounds.install_typing_sound(self)
        self.configure(highlightthickness=1, highlightbackground=theme.LINE, highlightcolor=theme.LINE)
        header = theme.Header(self, "ENHANCEDEXTRACT")
        header.pack(fill="x")
        controls = tk.Frame(header, bg=theme.BG)
        controls.place(relx=1, x=-14, y=12, anchor="ne")
        self._make_mute_button(controls).pack(side="left", padx=(0, 6))
        CutButton(controls, "—", command=self.iconify, padx=14, height=30, sound="minimize"
                  ).pack(side="left", padx=(0, 6))
        CutButton(controls, "EXIT", command=self._on_close, variant="danger", padx=16, height=30, sound="exit"
                  ).pack(side="left")

        tabs = tk.Frame(self, bg=theme.BG)
        tabs.pack(fill="x", padx=14)
        self.tab_buttons = []
        for i, label in enumerate(("1  EXTRACT RAR", "2  INSTALL FROM ISO")):
            b = CutButton(tabs, label, command=lambda i=i: self._show_tab(i), sound=None)
            b.pack(side="left", padx=(0, 6))
            self.tab_buttons.append(b)
        tk.Frame(self, bg=theme.YELLOW, height=2).pack(fill="x", padx=14)

        pages = tk.Frame(self, bg=theme.BG)
        pages.pack(fill="both", expand=True)
        pages.rowconfigure(0, weight=1)
        pages.columnconfigure(0, weight=1)
        self.rar_tab = RarTab(pages)
        self.install_tab = InstallTab(pages)
        self.pages = (self.rar_tab, self.install_tab)
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")
        self.current_tab = None
        self._show_tab(0, quiet=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)    # still used by Alt+F4 and the taskbar
        self._go_borderless(header, width, height)
        self.after(300, requirements.check_at_start, self)    # once the window is up, so it centres on it

    def _make_mute_button(self, master):
        """Speaker button: normal while sounds are on, red with a crossed speaker when muted."""
        if "Segoe MDL2 Assets" in tkfont.families(self):
            font, on_text, off_text = ("Segoe MDL2 Assets", 12), "", ""   # speaker / muted speaker
        else:
            font, on_text, off_text = None, "SFX", "SFX"
        def show():
            muted = sounds.is_muted()
            button.set_variant("danger" if muted else "ghost")
            button.configure(text=off_text if muted else on_text)

        def toggle():
            if sounds.is_muted():
                sounds.set_muted(False)
                sounds.play("sound_on")
            else:
                sounds.play("sound_off")    # still plays out: muting only blocks new sounds
                sounds.set_muted(True)
            show()

        button = CutButton(master, on_text, command=toggle, padx=12, height=30, font=font, sound=None)
        show()
        return button

    def _go_borderless(self, header, width, height):
        """Swap the Windows title bar for the app's own: drag the header to move, the
        bottom-right grip to resize, and the header buttons to minimize and exit."""
        self.update_idletasks()
        if chrome.hide_title_bar(self, keep_system_menu=True):
            x = (self.winfo_screenwidth() - width) // 2
            y = max(0, (self.winfo_screenheight() - 40 - height) // 2)
            chrome.place(self, x, y, width, height)
            chrome.make_draggable(self, header)
            chrome.ResizeGrip(self, 760, min(760, height), theme.BG, theme.DIM)
        else:
            self.minsize(760, min(760, height))   # title bar stays; Windows handles the rest
        self.update()                             # draw everything at its final size first
        self.attributes("-alpha", 1.0)

    def _show_tab(self, index, quiet=False):
        if index != self.current_tab and not quiet:
            sounds.play(("tab_rar", "tab_iso")[index])
        self.current_tab = index
        self.pages[index].tkraise()
        for i, b in enumerate(self.tab_buttons):
            b.set_variant("primary" if i == index else "ghost")

    def _on_close(self):
        if self.rar_tab.busy() or self.install_tab.busy():
            if not messagebox.askyesno("Quit", "A job is running or a virtual drive is mounted.\n"
                                       "Stop it / unmount and quit?", icon="warning"):
                return
        self.rar_tab.shutdown()
        self.install_tab.shutdown()
        sounds.stop_progress()
        # Hide now, close a moment later so the exit sound isn't cut off.
        self.withdraw()
        self.after(sounds.length_ms("exit") + 150, self.destroy)


def is_admin():
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin():
    """Restart this app elevated. Game setups relaunch themselves as admin, and an admin
    program can't see a drive mounted by a normal one, so the virtual drive must be
    mounted from an admin app. Returns True if the elevated copy was started."""
    import ctypes
    if paths.FROZEN:
        return False    # the exe's manifest already makes Windows ask for admin
    script = os.path.abspath(__file__)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"',
                                             os.path.dirname(script), 1)
    return rc > 32


if __name__ == "__main__":
    if sys.argv[1:2] == ["--vdrive"]:      # the exe started again as the virtual drive process
        del sys.argv[1]
        import vdrive
        vdrive.main()
        sys.exit(0)
    if not is_admin() and "--no-admin" not in sys.argv and relaunch_as_admin():
        sys.exit(0)
    App().mainloop()

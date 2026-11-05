"""Tab 2: serve an ISO as a virtual drive (vdrive.py) so setup.exe can install from it,
freeing ISO space behind setup as it reads.

A safety buffer of ISO data behind setup is always kept. Pages are only freed once
setup is a whole buffer past them; if setup goes back further than half the buffer,
freeing stops for good and setup simply continues as a normal install.
"""
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

import dialogs as messagebox
import requirements
import theme
import udf
import sounds
from isocore import (DEFAULT_BUFFER_GB, EXTRA_NEEDED_GB, GB, LOG_DIR, MB, MIN_BUFFER_GB, VDrive,
                     delete_iso, drive_free, free_drive_letter, human, is_admin, iso_attached, setup_result,
                     space_needed, was_freed)
from theme import CheckBox, CutButton, Panel

UNMOUNT_TIMEOUT_MS = 10000


SHCNE_DRIVEREMOVED = 0x00000080
SHCNE_DRIVEADD = 0x00000100


def announce_drive(letter, event=SHCNE_DRIVEADD):
    """Tell Explorer a drive appeared or went away so open windows update without reopening."""
    import ctypes
    SHCNF_PATHW = 0x0005
    try:
        ctypes.windll.shell32.SHChangeNotify(event, SHCNF_PATHW, ctypes.c_wchar_p(letter + "\\"), None)
    except OSError:
        pass


class InstallTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.events = queue.Queue()
        self.drive = None
        self.letter = None
        self.files = []
        self.warned = set()

        self.iso_var = tk.StringVar()
        self.install_var = tk.StringVar()
        self.buffer_var = tk.StringVar(value=str(DEFAULT_BUFFER_GB))
        self.install_size_var = tk.StringVar()
        self.auto_delete_var = tk.BooleanVar(value=True)
        self.pending_delete = False
        self.last_status = None
        self.space_var = tk.StringVar()
        self.info_var = tk.StringVar(value="Pick a game ISO (one that contains setup.exe + .bin files).")
        self.min_free = None
        self._build()
        self.buffer_var.trace_add("write", lambda *_: self._update_space())
        self.install_size_var.trace_add("write", lambda *_: self._update_space())
        self.after(200, self._pump)
        self.after(2000, self._refresh_space_periodically)

    # ---------- layout ----------
    def _build(self):
        pad = {"padx": 4, "pady": 3}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=14, pady=(10, 12))

        # The buttons are packed first so a short window squeezes the log, never them.
        btns = ttk.Frame(frm)
        btns.pack(side="bottom", fill="x", pady=(10, 0))

        source = Panel(frm, "// GAME ISO")
        source.pack(fill="x")
        src = source.body
        src.columnconfigure(1, weight=1)
        ttk.Label(src, text="Game ISO").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(src, textvariable=self.iso_var, state="readonly").grid(row=0, column=1, sticky="ew", **pad)
        self.btn_iso = CutButton(src, "BROWSE", command=self._pick_iso)
        self.btn_iso.grid(row=0, column=2, **pad)

        treef = ttk.Frame(src)
        treef.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(6, 0))
        self.tree = ttk.Treeview(treef, columns=("size", "read", "freed"), height=4)
        self.tree.heading("#0", text="File in ISO", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("read", text="Read by setup", anchor="e")
        self.tree.heading("freed", text="Freed", anchor="e")
        self.tree.column("#0", width=260)
        for c in ("size", "read", "freed"):
            self.tree.column(c, width=110, anchor="e")
        tree_sb = ttk.Scrollbar(treef, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_sb.set)
        self.tree.pack(side="left", fill="x", expand=True)
        tree_sb.pack(side="right", fill="y")

        target = Panel(frm, "// INSTALL")
        target.pack(fill="x", pady=(8, 0))
        tgt = target.body
        tgt.columnconfigure(1, weight=1)
        ttk.Label(tgt, text="Install folder").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(tgt, textvariable=self.install_var).grid(row=0, column=1, sticky="ew", **pad)
        self.btn_install = CutButton(tgt, "BROWSE", command=self._pick_install)
        self.btn_install.grid(row=0, column=2, **pad)
        ttk.Label(tgt, style="Muted.TLabel", text="Must be the same folder you choose in setup."
                  ).grid(row=1, column=1, columnspan=2, sticky="w", padx=4)

        ttk.Label(tgt, text="Safety buffer").grid(row=2, column=0, sticky="w", **pad)
        buf = ttk.Frame(tgt)
        buf.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        self.buffer_spin = ttk.Spinbox(buf, from_=MIN_BUFFER_GB, to=100, increment=1, width=5,
                                       textvariable=self.buffer_var)
        # Arrow clicks and the Up/Down keys send these just before the value changes.
        self.buffer_spin.bind("<<Increment>>", lambda e: self._buffer_step(+1), add="+")
        self.buffer_spin.bind("<<Decrement>>", lambda e: self._buffer_step(-1), add="+")
        self.buffer_spin.pack(side="left", padx=(0, 8))
        ttk.Label(buf, style="Muted.TLabel",
                  text=f"GB of ISO kept behind setup in case it goes back ({DEFAULT_BUFFER_GB} recommended)"
                  ).pack(side="left")

        ttk.Label(tgt, text="Install size").grid(row=3, column=0, sticky="w", **pad)
        size = ttk.Frame(tgt)
        size.grid(row=3, column=1, columnspan=2, sticky="w", **pad)
        self.size_entry = ttk.Entry(size, textvariable=self.install_size_var, width=12)
        self.size_entry.pack(side="left", padx=(0, 8))
        ttk.Label(size, style="Muted.TLabel",
                  text="MB, from setup's 'At least ... MB of free disk space is required'").pack(side="left")
        self.auto_delete_check = CheckBox(
            tgt, variable=self.auto_delete_var,
            text="Delete the ISO automatically when setup finishes successfully")
        self.auto_delete_check.grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 0))

        status = Panel(frm, "// STATUS")
        status.pack(fill="x", pady=(8, 0))
        self.space_label = ttk.Label(status.body, textvariable=self.space_var, justify="left")
        self.space_label.pack(anchor="w", padx=4)
        self.info_label = ttk.Label(status.body, textvariable=self.info_var, justify="left", style="Good.TLabel")
        self.info_label.pack(anchor="w", padx=4, pady=(2, 0))

        log = Panel(frm, "// LOG", padding=0)
        log.pack(fill="both", expand=True, pady=(8, 0))
        self.log_box = tk.Text(log.body, height=3, wrap="word", state="disabled")
        self.log_box.tag_configure("error", foreground=theme.RED)
        sb = ttk.Scrollbar(log.body, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Delete sits apart from the buttons used during an install so it's never hit by mistake.
        self.btn_delete = CutButton(btns, "DELETE ISO", command=self._delete_iso, variant="danger")
        self.btn_delete.pack(side="left")
        self.btn_setup = CutButton(btns, "RUN SETUP.EXE", command=self._run_setup, height=38)
        self.btn_setup.pack(side="right")
        self.btn_mount = CutButton(btns, "MOUNT", command=self._mount, height=38, padx=30)
        self.btn_mount.pack(side="right", padx=8)
        self.btn_unmount = CutButton(btns, "UNMOUNT", command=self._unmount)
        self.btn_unmount.pack(side="right")
        self._refresh_buttons()

    # ---------- inputs ----------
    def _pick_iso(self):
        path = filedialog.askopenfilename(title="Pick the game ISO",
                                          filetypes=[("Disc images", "*.iso"), ("All files", "*.*")])
        if not path:
            return
        path = os.path.normpath(path)
        try:
            img = udf.UDFImage(path)
            self.files = img.files()
            img.close()
        except (OSError, udf.UDFError) as e:
            messagebox.showerror("EnhancedExtract", f"Cannot read this ISO:\n{e}")
            return
        self.iso_var.set(path)
        self.tree.delete(*self.tree.get_children())
        for e in self.files:
            self.tree.insert("", "end", iid=e.path, text=e.path.lstrip("/"), values=(human(e.size), "-", "-"))
        total = sum(e.size for e in self.files)
        self._log(f"Loaded {os.path.basename(path)}: {len(self.files)} files, {human(total)}.")
        if not any(e.path.lower() == "/setup.exe" for e in self.files):
            self._log("Note: no setup.exe in the ISO root.")
        if was_freed(path):
            self._log("WARNING: this ISO was already partly freed in an earlier run. Freed parts are gone.")
        self._update_space()
        self._update_info()
        self._refresh_buttons()

    def _pick_install(self):
        path = filedialog.askdirectory(title="Install folder (same as in setup)")
        if path:
            self.install_var.set(os.path.normpath(path))

    def _buffer_step(self, direction):
        """Up or down sound, unless the buffer is already at that end of its range."""
        if str(self.buffer_spin.cget("state")) == "disabled":
            return
        value = self._buffer_gb()
        if value is None or (direction > 0 and value < 100) or (direction < 0 and value > MIN_BUFFER_GB):
            sounds.play("buffer_up" if direction > 0 else "buffer_down")

    def _buffer_gb(self):
        try:
            return float(self.buffer_var.get())
        except ValueError:
            return None

    def _install_size(self):
        """Install size typed from setup, in bytes (setup's MB are 1024*1024 bytes)."""
        text = self.install_size_var.get().strip().replace(",", "").replace(" ", "")
        try:
            mb = float(text)
        except ValueError:
            return None
        return int(mb * MB) if mb > 0 else None

    def _space_needed(self):
        """(needed bytes, growth bytes) before mounting, or None if inputs are missing."""
        buf = self._buffer_gb()
        size = self._install_size()
        if buf is None or buf < MIN_BUFFER_GB or size is None:
            return None
        return space_needed(buf, size, self.files)

    def _refresh_space_periodically(self):
        # While mounted, status messages refresh the line; before that, free space can change
        # because the user is clearing room, so poll it.
        if not self.drive:
            self._update_space()
        self.after(2000, self._refresh_space_periodically)

    def _update_space(self):
        iso = self.iso_var.get()
        self.space_label.configure(style="TLabel")
        if not iso:
            self.space_var.set("")
            return
        free = drive_free(iso)
        drive = os.path.splitdrive(iso)[0]
        if self.drive:
            # Installing: free space is expected to drop; just report it.
            self.min_free = free if self.min_free is None else min(self.min_free, free)
            self.space_var.set(f"Free on {drive} {human(free)}    (lowest so far {human(self.min_free)})")
            if free < 0.5 * GB and "lowspace" not in self.warned:
                self.warned.add("lowspace")
                messagebox.showwarning("EnhancedExtract",
                                       f"Only {human(free)} left on {drive}.\n\n"
                                       "If it reaches 0, setup will fail with a disk-full error.")
            return
        buf = self._buffer_gb()
        if buf is None or buf < MIN_BUFFER_GB:
            self.space_var.set(f"Free on {drive} {human(free)}    Buffer must be at least {MIN_BUFFER_GB} GB.")
            return
        needed = self._space_needed()
        if needed is None:
            self.space_var.set(f"Free on {drive} {human(free)}    Enter the install size from setup "
                               "to check the space needed.")
            return
        need, growth = needed
        verdict = "OK" if free >= need else f"NOT ENOUGH - free {human(need - free)} more or lower the buffer"
        if free < need:
            self.space_label.configure(style="Bad.TLabel")
        self.space_var.set(f"Free on {drive} {human(free)}    Needed: {human(need)} "
                           f"({buf:g} GB buffer + {EXTRA_NEEDED_GB} GB margin + {human(growth)} game bigger "
                           f"than ISO)\n{verdict}")

    # ---------- mount / unmount ----------
    def _mount(self):
        iso = self.iso_var.get()
        install = self.install_var.get().strip()
        buf = self._buffer_gb()
        if not iso:
            return
        if not requirements.winfsp_installed():
            # skipped with LATER at start-up: offer the same SYSTEM CHECK install again
            requirements.check(self)
            if not requirements.winfsp_installed():
                return
            self._log("WinFsp installed.")
        if not install:
            messagebox.showwarning("EnhancedExtract", "Pick the install folder first "
                                   "(the same folder you will choose in setup).")
            return
        if buf is None or buf < MIN_BUFFER_GB:
            messagebox.showwarning("EnhancedExtract", f"Safety buffer must be at least {MIN_BUFFER_GB} GB.")
            return
        if self._install_size() is None:
            messagebox.showwarning("EnhancedExtract",
                                   "Enter the install size first.\n\n"
                                   "Start setup.exe once (e.g. from Windows' own mount of the ISO), go to the "
                                   "'Select Destination Location' page and copy the number from "
                                   "'At least ... MB of free disk space is required'. Then cancel setup.")
            return
        free = drive_free(iso)
        need, growth = self._space_needed()
        if free < need:
            messagebox.showerror("EnhancedExtract",
                                 f"Not enough free space.\n\n"
                                 f"Free: {human(free)}\nNeeded: {human(need)}\n"
                                 f"  = buffer {buf:g} GB + {EXTRA_NEEDED_GB} GB margin + {human(growth)} "
                                 "(the installed game is bigger than the ISO)\n\n"
                                 f"Free {human(need - free)} more, or lower the buffer.")
            return
        if os.path.splitdrive(install)[0].lower() != os.path.splitdrive(iso)[0].lower():
            if not messagebox.askyesno("Different drives",
                                       "The install folder is on a different drive than the ISO.\n"
                                       "Freeing the ISO will not make room on the install drive.\n"
                                       "Continue anyway?"):
                return
        if not is_admin() and not messagebox.askyesno(
                "Not running as admin",
                "The app is not running as administrator.\n\n"
                "Most game setups restart themselves as admin, and an admin program can't see this "
                "virtual drive - setup would fail with 'cannot find the path'.\n\n"
                "Close the app and reopen it with run.bat, then accept the Windows admin prompt.\n\n"
                "Mount anyway?", icon="warning"):
            return
        if iso_attached(iso):
            messagebox.showerror("EnhancedExtract", "Windows has this ISO mounted.\n\n"
                                 "Eject it first: in Explorer right-click its DVD drive -> Eject.")
            return
        msg = ("INSTALL WHILE FREEING\n\n"
               f"The app keeps the last {buf:g} GB of the ISO behind setup and frees older parts as "
               "setup installs.\n\n"
               "- The ISO can't be mounted normally afterwards.\n"
               "- If setup fails, is cancelled or the PC crashes, this ISO is lost "
               "(keep a backup copy or be ready to download again).\n"
               "- Do not cancel setup once it is installing.\n\n"
               "Continue?")
        if not messagebox.askyesno("Confirm", msg, icon="warning"):
            return
        os.makedirs(install, exist_ok=True)
        letter = free_drive_letter()
        if not letter:
            messagebox.showerror("EnhancedExtract", "No free drive letter.")
            return
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        log = os.path.join(LOG_DIR, f"{os.path.basename(iso)}-{stamp}.csv")
        self.drive = VDrive(iso, letter, "free", buf, install_dir=install, log=log)
        self.letter = letter
        self.warned.clear()
        self.min_free = None
        self.last_status = None
        self.pending_delete = False
        self._log(f"Mounting as {letter} with a {buf:g} GB safety buffer...")
        self._log(f"Read log: {log}")
        self._refresh_buttons()

    def _run_setup(self):
        if not self.letter:
            return
        exe = os.path.join(self.letter + "\\", "setup.exe")
        if not os.path.exists(exe):
            messagebox.showerror("EnhancedExtract", f"{exe} not found.")
            return
        messagebox.showinfo("EnhancedExtract",
                            "Setup will start after you click OK (Windows may ask for admin rights).\n\n"
                            f"In setup, choose this install folder:\n\n{self.install_var.get()}\n\n"
                            "Setup may warn that there isn't enough disk space - it doesn't know about "
                            "freeing. Choose to continue if it lets you.")
        os.makedirs(LOG_DIR, exist_ok=True)
        setup_log = os.path.join(LOG_DIR, f"setup-{time.strftime('%Y%m%d-%H%M%S')}.log")
        try:
            # Started directly (not via the shell) so the app can wait for it and read its exit
            # code; /LOG makes Inno Setup write its own log, which ends with a success line.
            setup = subprocess.Popen([exe, f"/LOG={setup_log}"], cwd=self.letter + "\\")
        except OSError as e:
            self._log(f"ERROR starting setup: {e}")
            messagebox.showerror("EnhancedExtract", f"Could not start setup:\n\n{e}")
            return
        self.btn_setup.configure(state="disabled")
        self._log(f"Started {exe} (setup log: {setup_log})")
        threading.Thread(target=lambda: self.events.put(("setup_done", (setup.wait(), setup_log))),
                         daemon=True).start()

    def _setup_finished(self, code, setup_log):
        """Decide whether the install succeeded; on success optionally unmount and delete the ISO."""
        self._refresh_buttons()
        problems, unread = setup_result(code, setup_log, (self.last_status or {"files": {}})["files"])
        if problems:
            self._log("Setup may not have finished: " + "; ".join(problems))
            messagebox.showwarning("EnhancedExtract",
                                   "Setup might not have finished fully:\n\n- " + "\n- ".join(problems) +
                                   "\n\nThe ISO was kept. Try the game first before deleting it.")
            return
        if unread:
            names = ", ".join(p.lstrip("/") for p in unread)
            self._log("Setup finished, but did not read to the end of: " + names)
            messagebox.showinfo("EnhancedExtract",
                                "Setup finished, but it didn't use all of these files:\n\n" + names +
                                "\n\nThat's normal for optional extras you didn't pick, like languages.\n\n"
                                "The ISO was kept. Try the game first; if it works, use Delete ISO.")
            return
        self._log("Setup finished successfully (exit code 0, log confirms, all .bin files read to the end).")
        if not self.auto_delete_var.get():
            messagebox.showinfo("EnhancedExtract", "Setup finished successfully.\n\n"
                                "Unmount, then use Delete ISO when you're ready.")
            return
        self.pending_delete = True
        self._log("Unmounting and deleting the ISO automatically...")
        self._unmount(ask=False)

    def _unmount(self, ask=True):
        if not self.drive:
            return
        if ask and not messagebox.askyesno("Unmount", "Make sure setup has FINISHED (or was closed).\n\nUnmount now?"):
            return
        # Don't wait here: that would freeze the window. The drive reports "ended" when it
        # is gone; if it hasn't gone after a while, it is killed.
        drive = self.drive
        drive.quit()
        self.after(UNMOUNT_TIMEOUT_MS, drive.kill)

    def _delete_iso(self, confirm=True):
        iso = self.iso_var.get()
        if not iso or self.drive:
            return
        if confirm and not messagebox.askyesno("Delete ISO", f"Delete this ISO permanently?\n\n{iso}\n\n"
                                               "Only do this after the game is installed and launches.",
                                               icon="warning"):
            return
        try:
            on_disk = delete_iso(iso)
        except OSError as e:
            messagebox.showerror("EnhancedExtract", f"Could not delete: {e}")
            return
        self._log(f"Deleted {iso} ({human(on_disk)} given back to the drive)")
        if not confirm:
            messagebox.showinfo("EnhancedExtract", "Done!\n\nThe game is installed and the ISO was deleted "
                                f"({human(on_disk)} given back).")
        self.iso_var.set("")
        self.files = []
        self.tree.delete(*self.tree.get_children())
        self._update_space()
        self._update_info()
        self._refresh_buttons()

    # ---------- status ----------
    def _pump(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "setup_done":
                    self._setup_finished(*data)
        except queue.Empty:
            pass
        for msg in self.drive.poll() if self.drive else []:
            t = msg.get("type")
            if t == "ended":
                self._drive_ended()
                break
            if t == "status":
                self._apply_status(msg)
            elif t == "event":
                self._log(msg["msg"])
                self._maybe_alert(msg["msg"])
            elif t == "fatal":
                self._log("ERROR: " + msg["msg"])
                messagebox.showerror("EnhancedExtract", msg["msg"])
            elif t == "mounted":
                self._wait_for_drive(self.letter, time.time() + 20)
        self.after(200, self._pump)

    def _drive_ended(self):
        if self.letter:
            announce_drive(self.letter, SHCNE_DRIVEREMOVED)
        self._log(f"Virtual drive {self.letter} unmounted.")
        self.drive = None
        self.letter = None
        self._refresh_buttons()
        self._update_space()
        if self.pending_delete:
            self.pending_delete = False
            self._delete_iso(confirm=False)

    def _wait_for_drive(self, letter, deadline):
        """The drive appears a moment after vdrive starts; open it in Explorer once it does."""
        if letter != self.letter:
            return
        if os.path.exists(letter + "\\"):
            if is_admin():
                # Explorer runs as the normal user and can't see a drive mounted by an admin app.
                self._log(f"Mounted as {letter}. Click 'Run setup.exe' when ready. "
                          "(The drive won't show in Explorer - only admin programs like setup can see it.)")
            else:
                announce_drive(letter)
                os.startfile(letter + "\\")
                self._log(f"Mounted as {letter} and opened in Explorer. Click 'Run setup.exe' when ready.")
        elif time.time() < deadline:
            self.after(250, self._wait_for_drive, letter, deadline)
        else:
            self._log(f"Drive {letter} did not appear within 20 seconds.")

    def _apply_status(self, st):
        self.last_status = st
        for path, f in st["files"].items():
            if self.tree.exists(path):
                read = f"{100 * f['hwm'] / f['size']:.0f}%" if f["size"] else "-"
                freed = human(f["freed"]) if f["freed"] else ("-" if f["eligible"] else "kept")
                self.tree.item(path, values=(human(f["size"]), read, freed))
        self._update_space()
        self._update_info(st)

    def _update_info(self, st=None):
        self.info_label.configure(style="Bad.TLabel" if st and (st["violations"] or st["paused"]) else "Good.TLabel")
        if not self.iso_var.get():
            self.info_var.set("Pick a game ISO (one that contains setup.exe + .bin files).")
            return
        if not st:
            self.info_var.set(f"Mounted as {self.letter}" if self.letter else "Not mounted.")
            return
        freed = sum(f["freed"] for f in st["files"].values())
        lines = [f"Mounted as {self.letter}    Read by setup: {human(st['bytes_read'])}    "
                 f"Freed: {human(freed)}    Installed so far: {human(st['installed'])}"]
        if st["max_back"] == 0:
            back = "Setup went back: never"
        elif st["max_back"] <= st["buffer"] // 2:
            back = f"Setup went back: max {human(st['max_back'])} (inside the buffer, OK)"
        else:
            back = f"Setup went back: max {human(st['max_back'])} - BEYOND half the buffer"
        lines.append(back)
        if st["violations"]:
            lines.append(f"BLOCKED reads of freed data: {st['violations']}")
        if st["paused"]:
            lines.append("FREEING STOPPED - setup continues as a normal install")
        self.info_var.set("\n".join(lines))

    def _maybe_alert(self, msg):
        for key, title in (("BLOCKED", "Setup asked for freed data"), ("STOPPED", "Freeing stopped")):
            if key in msg and key not in self.warned:
                self.warned.add(key)
                messagebox.showwarning("EnhancedExtract", f"{title}:\n\n{msg}")

    def _refresh_buttons(self):
        mounted = self.drive is not None
        has_iso = bool(self.iso_var.get())
        self.btn_mount.configure(state="normal" if has_iso and not mounted else "disabled")
        self.btn_setup.configure(state="normal" if mounted else "disabled")
        self.btn_unmount.configure(state="normal" if mounted else "disabled")
        self.btn_delete.configure(state="normal" if has_iso and not mounted else "disabled")
        # Yellow marks the next step.
        self.btn_mount.set_variant("ghost" if mounted else "primary")
        self.btn_setup.set_variant("primary" if mounted else "ghost")
        for w in (self.btn_iso, self.btn_install, self.buffer_spin, self.size_entry):
            w.configure(state="disabled" if mounted else "normal")

    def _log(self, text):
        self.log_box.configure(state="normal")
        bad = text.startswith(("ERROR", "WARNING", "BLOCKED", "Freeing STOPPED"))
        self.log_box.insert("end", time.strftime("%H:%M:%S ") + text + "\n", "error" if bad else ())
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def busy(self):
        return self.drive is not None

    def shutdown(self):
        self._unmount(ask=False)

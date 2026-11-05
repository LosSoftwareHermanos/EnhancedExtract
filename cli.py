"""EnhancedExtract for the terminal: the same jobs as the window, driven by flags, so
scripts and AI agents can run them end to end without prompts.

Run `python cli.py` to see the commands, and `python cli.py <group> <command> --help` for
each one's flags and examples. See AGENTS.md for the JSON contract.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

import extractor as ex
import isocore as iso
import paths
import udf

VERSION = "1.2"
SCHEMA = 1          # bumped when JSON event fields change incompatibly

EXIT = {
    0: "success (or already done)",
    1: "the job failed",
    2: "bad arguments or input",
    3: "password needed or wrong",
    4: "not enough free space",
    5: "something the PC needs is missing (UnRAR, WinFsp, fusepy, admin rights)",
    6: "a destructive step needs --yes",
    130: "stopped with Ctrl+C",
}
SETUP_SILENT = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
DONE_MARKER = ".enhancedextract-done.json"      # left in the destination by `rar extract --delete`
PROG = "EnhancedExtract.exe --cli" if paths.FROZEN else "python cli.py"

# Text mode: these event types are the command's data and go to stdout; everything else
# (progress, logs, warnings, errors) goes to stderr so stdout can be piped.
DATA_TYPES = {"archive", "space", "iso", "file", "check", "plan"}
CHATTY_TYPES = {"log", "progress", "status", "event"}      # hidden by --quiet


class Stop(Exception):
    """Ends the command with an exit code. `fix` is a command that would get past it."""

    def __init__(self, code, msg, fix=None, **extra):
        super().__init__(msg)
        self.code, self.msg, self.fix, self.extra = code, msg, fix, extra


class Out:
    """Writes events as JSON lines (--json) or as plain text."""

    def __init__(self, as_json=False, quiet=False):
        self.as_json = as_json
        self.quiet = quiet
        self.lock = threading.Lock()

    def __call__(self, type, msg=None, **fields):
        with self.lock:
            if self.as_json:
                obj = {"type": type, "ts": round(time.time(), 3)}
                if msg is not None:
                    obj["msg"] = msg
                obj.update(fields)
                print(json.dumps(obj, ensure_ascii=False), flush=True)
                return
            if msg is None or (self.quiet and type in CHATTY_TYPES):
                return
            prefix = {"error": "Error: ", "warning": "Warning: ", "hint": "Hint: "}.get(type, "")
            print(prefix + msg, file=sys.stdout if type in DATA_TYPES else sys.stderr, flush=True)

    def result(self, code, fields):
        if self.as_json:
            self("result", None, exit_code=code, schema=SCHEMA, **fields)
            return
        # Plain "key: value" lines on stdout, easy to read and to grep.
        for key, value in fields.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            print(f"{key}: {value}")


def command_line(argv, *extra):
    return subprocess.list2cmdline(PROG.split() + list(argv) + list(extra))


def with_yes(args):
    """The command the user ran, with --yes added: what to rerun once they agree."""
    return command_line(args.argv, *([] if "--yes" in args.argv else ["--yes"]))


# ---------- system ----------
def fusepy_available():
    return paths.FROZEN or importlib.util.find_spec("fuse") is not None


def system_report():
    tool = ex.rar_tool()
    return {
        "unrar": {"ok": bool(tool), "source": tool[0] if tool else None, "path": tool[1] if tool else None},
        "winfsp": {"ok": iso.winfsp_installed()},
        "fusepy": {"ok": fusepy_available()},
        "admin": {"ok": iso.is_admin()},
    }


def cmd_system_check(args, out):
    report = system_report()
    for name, r in report.items():
        out("check", f"{name:7} {'OK' if r['ok'] else 'MISSING'}" + (f"  ({r['source']}: {r['path']})"
                                                                     if r.get("path") else ""),
            name=name, **r)
    hints = {
        "unrar": "Install WinRAR, or put UnRAR.exe on PATH (needed for rar commands).",
        "winfsp": f"Install the driver (as administrator): {PROG} system install-winfsp",
        "fusepy": "Install the Python package: python -m pip install fusepy",
        "admin": "Not administrator: iso install can't run setup.exe from here (setups elevate "
                 "themselves and can't see a drive mounted by a normal process).",
    }
    for name, r in report.items():
        if not r["ok"]:
            out("hint", hints[name], name=name)
    missing = [k for k, r in report.items() if not r["ok"] and k != "admin"]
    return {"ok": not missing, "missing": missing, **{k: r["ok"] for k, r in report.items()}}


def cmd_system_install_winfsp(args, out):
    if iso.winfsp_installed():
        out("event", "WinFsp is already installed.")
        return {"ok": True, "already_installed": True}
    if args.dry_run:
        out("plan", f"Would install WinFsp silently from {iso.WINFSP_MSI}.")
        return {"ok": True, "dry_run": True}
    if not iso.is_admin():
        raise Stop(5, "Installing WinFsp needs administrator rights.",
                   fix=f"Run from an administrator terminal: {command_line(args.argv)}")
    out("event", "Installing WinFsp (about 30 seconds)...")
    error = iso.install_winfsp()
    if error:
        raise Stop(5, f"WinFsp install failed: {error}", fix="Get it from https://winfsp.dev and install it.")
    out("event", "WinFsp installed.")
    return {"ok": True, "already_installed": False}


# ---------- rar ----------
def read_password(args):
    if getattr(args, "password_stdin", False):
        return sys.stdin.readline().rstrip("\r\n") or None
    return args.password or os.environ.get("EE_PASSWORD") or None


def archive_dest(args, first):
    return os.path.abspath(args.dest) if getattr(args, "dest", None) else ex.default_dest(first)


def load_archive(args):
    path = os.path.abspath(args.archive)
    if not os.path.isfile(path):
        raise Stop(2, f"Archive not found: {path}",
                   fix=f"Pass the first part of the set: {PROG} {args.group} {args.cmd} \"D:\\Games\\Game.part1.rar\"")
    try:
        return ex.inspect(path, args.pw)
    except ex.PasswordError as e:
        argv = [a for a in args.argv if a != args.archive]
        raise Stop(3, str(e), fix=f"echo <password> | {command_line(argv, args.archive, '--password-stdin')}")
    except ex.ExtractError as e:
        if "UnRAR.exe not found" in str(e):
            raise Stop(5, str(e), fix=f"{PROG} system check")
        raise Stop(1, str(e))


def space_report(info, dest, delete):
    need = ex.space_needed(info, dest, delete)
    free = ex.free_space(dest)
    return {"dest": dest, "needed": need, "free": free, "enough": free >= need}


def archive_event(out, info):
    out("archive", f"{len(info.volumes)} parts, {info.files} files, {ex.human(info.packed)} packed -> "
                   f"{ex.human(info.unpacked)} unpacked", first=info.first, volumes=info.volumes,
        files=info.files, packed=info.packed, unpacked=info.unpacked)


def cmd_rar_inspect(args, out):
    info = load_archive(args)
    dest = archive_dest(args, info.first)
    space = space_report(info, dest, args.delete)
    archive_event(out, info)
    out("space", f"Extract to {dest}: free {ex.human(space['free'])}, needed {ex.human(space['needed'])} "
                 f"({'OK' if space['enough'] else 'NOT ENOUGH'})", **space)
    return {"ok": True, "parts": len(info.volumes), "unpacked": info.unpacked, "dest": dest,
            "space_ok": space["enough"]}


class Progress:
    """Turns Runner callbacks into events without flooding: every percent in JSON mode,
    every 10 % or new part in text mode."""

    def __init__(self, out):
        self.out = out
        self.phase = ""
        self.last = None

    def __call__(self, pct, part, total):
        part = min(part, total)
        step = pct if self.out.as_json or pct is None else pct // 10 * 10
        key = (self.phase, part, step)
        if key == self.last:
            return
        self.last = key
        text = f"{self.phase}: part {part} of {total}" + (f" - {pct}%" if pct is not None else "")
        self.out("progress", text, phase=self.phase.lower(), part=part, parts=total, percent=pct)


def run_job(runner, job):
    try:
        job()
    except KeyboardInterrupt:
        runner.stop()
        raise Stop(130, "Stopped with Ctrl+C.")
    except ex.PasswordError as e:
        raise Stop(3, str(e))
    except ex.ExtractError as e:
        raise Stop(1, str(e))


def cmd_rar_verify(args, out):
    info = load_archive(args)
    progress = Progress(out)
    progress.phase = "Verifying"
    runner = ex.Runner(log=lambda t: out("log", t), progress=progress, password=args.pw)
    run_job(runner, lambda: runner.verify(info))
    return {"ok": True, "parts": len(info.volumes), "files": info.files}


def already_extracted(args):
    """An earlier `rar extract --delete` finished and removed the archive: report it as done
    instead of failing, so a retried command is safe."""
    first = os.path.abspath(args.archive)
    if os.path.exists(first):
        return None
    marker = os.path.join(archive_dest(args, first), DONE_MARKER)
    try:
        with open(marker, encoding="utf-8") as f:
            done = json.load(f)
    except (OSError, ValueError):
        return None
    return done if os.path.normcase(done.get("archive", "")) == os.path.normcase(os.path.basename(first)) else None


def cmd_rar_extract(args, out):
    done = already_extracted(args)
    if done:
        dest = archive_dest(args, os.path.abspath(args.archive))
        out("event", f"Already extracted to {dest} (the parts were deleted then).")
        return {"ok": True, "already_done": True, "dest": dest,
                **{k: done[k] for k in ("files", "unpacked") if k in done}}
    info = load_archive(args)
    dest = archive_dest(args, info.first)
    space = space_report(info, dest, args.delete)
    out("space", f"Free {ex.human(space['free'])}, needed {ex.human(space['needed'])}", **space)
    if not space["enough"] and not args.ignore_space:
        raise Stop(4, f"Not enough free space for {dest}: {ex.human(space['needed'] - space['free'])} short.",
                   fix=f"Free some space, or try anyway: {command_line(args.argv, '--ignore-space')}", **space)
    if args.dry_run:
        archive_event(out, info)
        steps = ([] if args.no_verify else ["verify every part"]) + [f"extract to {dest}"]
        if args.delete:
            steps.append(f"delete the {len(info.volumes)} parts as they are used")
        out("plan", "Would " + ", then ".join(steps) + ".", steps=steps,
            deletes=info.volumes if args.delete else [])
        return {"ok": True, "dry_run": True, "dest": dest, "needs_yes": args.delete}
    if args.delete and not args.yes:
        raise Stop(6, "--delete removes each part once it is extracted; if extraction fails midway, the "
                      "deleted parts are gone.", fix=with_yes(args))
    if args.delete and args.no_verify:
        out("warning", "Verification is off: a corrupt part would only be found after earlier parts "
                       "were deleted.")
    progress = Progress(out)
    runner = ex.Runner(log=lambda t: out("log", t), progress=progress, password=args.pw)

    def job():
        if not args.no_verify:
            progress.phase = "Verifying"
            runner.verify(info)
        progress.phase = "Extracting"
        runner.extract(info, dest, args.delete)

    try:
        run_job(runner, job)
    except Stop as e:
        e.extra.update(parts_left=len(ex.remaining_parts(info)), parts=len(info.volumes))
        raise
    if args.delete:
        with open(os.path.join(dest, DONE_MARKER), "w", encoding="utf-8") as f:
            json.dump({"archive": os.path.basename(info.first), "files": info.files,
                       "unpacked": info.unpacked}, f)
    return {"ok": True, "dest": dest, "files": info.files, "unpacked": info.unpacked,
            "parts_left": len(ex.remaining_parts(info))}


# ---------- iso ----------
def load_iso(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise Stop(2, f"ISO not found: {path}")
    try:
        img = udf.UDFImage(path)
    except (OSError, udf.UDFError) as e:
        raise Stop(2, f"Cannot read this ISO: {e}")
    img.close()
    return path, img.files()


def install_size(args):
    return int(args.install_size_mb * iso.MB) if args.install_size_mb else None


def cmd_iso_inspect(args, out):
    path, files = load_iso(args.iso)
    total = sum(e.size for e in files)
    has_setup = any(e.path.lower() == "/setup.exe" for e in files)
    big = [e for e in files if e.path.lower().endswith(".bin") and e.size >= 256 * iso.MB]
    out("iso", f"{os.path.basename(path)}: {len(files)} files, {iso.human(total)}; setup.exe in root: "
               f"{'yes' if has_setup else 'NO'}; {len(big)} big .bin files can be freed",
        path=path, files=len(files), size=total, has_setup=has_setup, freeable=[e.path for e in big])
    if args.files:
        for e in files:
            out("file", f"{e.size:>16,}  {e.path}", path=e.path, size=e.size)
    freed = iso.was_freed(path)
    if freed:
        out("warning", "This ISO was already partly freed in an earlier run; freed parts are gone.")
    attached = iso.iso_attached(path)
    if attached:
        out("warning", "Windows has this ISO mounted; eject it before iso install.")
    result = {"ok": True, "files": len(files), "size": total, "has_setup": has_setup,
              "was_freed": freed, "windows_mounted": attached}
    size = install_size(args)
    if size:
        need, growth = iso.space_needed(args.buffer_gb, size, files)
        free = iso.drive_free(path)
        out("space", f"Free {iso.human(free)}, needed {iso.human(need)} ({args.buffer_gb:g} GB buffer + "
                     f"{iso.EXTRA_NEEDED_GB} GB margin + {iso.human(growth)} game bigger than ISO): "
                     f"{'OK' if free >= need else 'NOT ENOUGH'}", free=free, needed=need, growth=growth,
            enough=free >= need)
        result["space_ok"] = free >= need
    return result


def wait_for_drive(drive, out, timeout=30):
    """Wait until the drive process says it mounted and the letter shows up."""
    deadline = time.time() + timeout
    mounted = False
    while time.time() < deadline:
        for msg in drive.poll(timeout=0.25):
            t = msg.get("type")
            if t == "mounted":
                mounted = True
            elif t == "fatal":
                raise Stop(1, msg["msg"])
            elif t == "ended":
                raise Stop(1, f"The virtual drive stopped before mounting (exit code {msg['code']}).")
            elif t == "event":
                out("event", msg["msg"])
        if mounted and os.path.exists(drive.letter + "\\"):
            return
    raise Stop(1, f"Drive {drive.letter} did not appear within {timeout} seconds.")


def report_drive(drive, out, msgs, status_every, last):
    """Pass drive messages on. Returns (ended, time of the last status line)."""
    ended = False
    for msg in msgs:
        t = msg.get("type")
        if t == "event":
            bad = msg["msg"].startswith(("BLOCKED", "Freeing STOPPED", "Freeing error"))
            out("warning" if bad else "event", msg["msg"])
        elif t == "fatal":
            out("error", msg["msg"])
        elif t == "ended":
            ended = True
    st = drive.status
    if st and time.time() - last >= status_every:
        last = time.time()
        freed = sum(f["freed"] for f in st["files"].values())
        out("status", f"read {iso.human(st['bytes_read'])}, freed {iso.human(freed)}, installed "
                      f"{iso.human(st['installed'])}" + (", FREEING STOPPED" if st["paused"] else ""),
            bytes_read=st["bytes_read"], freed=freed, installed=st["installed"], paused=st["paused"],
            violations=st["violations"], max_back=st["max_back"])
    return ended, last


def unmount(drive, out, timeout=15):
    drive.quit()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(m.get("type") == "ended" for m in drive.poll(timeout=0.25)):
            out("event", f"Virtual drive {drive.letter} unmounted.")
            return
    drive.kill()
    out("warning", f"Virtual drive {drive.letter} did not unmount in time and was killed.")


def iso_preflight(args, out, path, files):
    """Every check before mounting; the same checks run for --dry-run. Raises Stop for
    anything that blocks the install."""
    freeing = not args.no_free
    run_setup = not args.no_setup
    if not iso.winfsp_installed():
        raise Stop(5, "WinFsp is not installed.", fix=f"{PROG} system install-winfsp   (as administrator)")
    if not fusepy_available():
        raise Stop(5, "fusepy is not installed.", fix="python -m pip install fusepy")
    if run_setup and not any(e.path.lower() == "/setup.exe" for e in files):
        raise Stop(2, "No setup.exe in the ISO root.", fix=command_line(args.argv, "--no-setup"))
    if run_setup and not iso.is_admin():
        raise Stop(5, "Not running as administrator. Game setups restart themselves as admin and then "
                      "can't see a drive mounted by a normal process.",
                   fix=f"Run from an administrator terminal: {command_line(args.argv)}")
    if not iso.is_admin():
        out("warning", "Not administrator: admin programs (like most setups) won't see the drive.")
    if args.buffer_gb < iso.MIN_BUFFER_GB:
        raise Stop(2, f"--buffer-gb must be at least {iso.MIN_BUFFER_GB}.")
    size = install_size(args)
    if freeing:
        example = (f"{PROG} iso install \"{path}\" --install-dir \"D:\\Games\\MyGame\" "
                   "--install-size-mb 52000 --yes")
        if not args.install_dir:
            raise Stop(2, "--install-dir is required: the folder setup installs into.", fix=example)
        if not size:
            raise Stop(2, "--install-size-mb is required: the number from setup's 'At least ... MB of "
                          "free disk space is required'.", fix=example)
        need, growth = iso.space_needed(args.buffer_gb, size, files)
        free = iso.drive_free(path)
        if free < need:
            raise Stop(4, f"Not enough free space: free {iso.human(free)}, needed {iso.human(need)} "
                          f"(= {args.buffer_gb:g} GB buffer + {iso.EXTRA_NEEDED_GB} GB margin + "
                          f"{iso.human(growth)} game bigger than ISO).",
                       fix="Free some space, lower --buffer-gb, or install without freeing: "
                           + command_line(args.argv, "--no-free"), free=free, needed=need)
        if os.path.splitdrive(os.path.abspath(args.install_dir))[0].lower() != os.path.splitdrive(path)[0].lower():
            out("warning", "The install folder is on a different drive than the ISO: freeing the ISO will "
                           "not make room on the install drive.")
        if iso.was_freed(path):
            out("warning", "This ISO was already partly freed in an earlier run; freed parts are gone.")
    if iso.iso_attached(path):
        raise Stop(1, "Windows has this ISO mounted.", fix="In Explorer, right-click its drive -> Eject.")
    if args.dry_run:
        return
    if freeing and not args.yes:
        raise Stop(6, f"Install while freeing deletes parts of the ISO as setup reads them (keeping the "
                      f"last {args.buffer_gb:g} GB). If setup fails, is cancelled or the PC crashes, the "
                      "ISO is lost. Use --no-free to change nothing.", fix=with_yes(args))
    if args.delete_iso and not args.yes:
        raise Stop(6, "--delete-iso deletes the ISO after a successful install.", fix=with_yes(args))


def cmd_iso_install(args, out):
    path, files = load_iso(args.iso)
    iso_preflight(args, out, path, files)
    mode = "dry" if args.no_free else "free"
    install_dir = os.path.abspath(args.install_dir) if args.install_dir else None
    if args.dry_run:
        steps = ["mount the ISO as a virtual drive" + ("" if args.no_free else " and free it behind setup")]
        if not args.no_setup:
            steps.append("run setup.exe" + (" silently into " + install_dir if args.silent and install_dir else ""))
            steps.append("check setup's exit code and log, then unmount")
            if args.delete_iso:
                steps.append("delete the ISO if setup fully succeeded")
        else:
            steps.append("serve the drive until 'quit' on stdin or Ctrl+C")
        out("plan", "Would " + ", then ".join(steps) + ".", steps=steps, mode=mode)
        return {"ok": True, "dry_run": True, "mode": mode,
                "needs_yes": not args.no_free or args.delete_iso}
    if install_dir:
        os.makedirs(install_dir, exist_ok=True)
    letter = iso.free_drive_letter()
    if not letter:
        raise Stop(1, "No free drive letter.")
    os.makedirs(iso.LOG_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    read_log = os.path.join(iso.LOG_DIR, f"{os.path.basename(path)}-{'dry-' if args.no_free else ''}{stamp}.csv")
    out("event", f"Mounting {os.path.basename(path)} as {letter} ({mode} mode, {args.buffer_gb:g} GB buffer)...",
        letter=letter, mode=mode, read_log=read_log)
    drive = iso.VDrive(path, letter, mode, args.buffer_gb, install_dir=install_dir, log=read_log)
    try:
        wait_for_drive(drive, out)
        out("mounted", f"Mounted as {letter}", letter=letter)
        if args.no_setup:
            return serve_until_quit(drive, out, args)
        return run_setup(drive, out, args, path, install_dir, stamp)
    finally:
        if drive.running():
            unmount(drive, out)


def serve_until_quit(drive, out, args):
    out("event", "Serving the drive. Send 'quit' on stdin (or press Ctrl+C) to unmount.")
    quit_typed = threading.Event()

    def watch_stdin():
        for line in sys.stdin:
            if line.strip() == "quit":
                quit_typed.set()
                return

    threading.Thread(target=watch_stdin, daemon=True).start()
    last = 0
    try:
        while not quit_typed.is_set():
            ended, last = report_drive(drive, out, drive.poll(timeout=0.5), args.status_every, last)
            if ended:
                raise Stop(1, "The virtual drive stopped unexpectedly.")
    except KeyboardInterrupt:
        pass
    unmount(drive, out)
    return {"ok": True, "letter": drive.letter}


def run_setup(drive, out, args, path, install_dir, stamp):
    exe = os.path.join(drive.letter + "\\", "setup.exe")
    setup_log = os.path.join(iso.LOG_DIR, f"setup-{stamp}.log")
    cmd = [exe, f"/LOG={setup_log}"]
    if args.silent:
        cmd += SETUP_SILENT + ([f"/DIR={install_dir}"] if install_dir else [])
    cmd += args.setup_arg
    try:
        setup = subprocess.Popen(cmd, cwd=drive.letter + "\\")
    except OSError as e:
        raise Stop(1, f"Could not start setup: {e}")
    out("setup_started", f"Started setup.exe{' (silent)' if args.silent else ''}; setup log: {setup_log}",
        command=cmd, setup_log=setup_log)
    if not args.silent:
        out("event", f"Choose this install folder in setup: {install_dir}")
    last = 0
    interrupted = False
    while True:
        try:
            ended, last = report_drive(drive, out, drive.poll(timeout=1), args.status_every, last)
            if ended:
                raise Stop(1, "The virtual drive stopped while setup was running.")
            code = setup.poll()
            if code is not None:
                break
        except KeyboardInterrupt:
            if interrupted:
                raise Stop(130, "Stopped with Ctrl+C while setup was still running.")
            interrupted = True
            out("warning", "Setup is still running and reads from the drive. Press Ctrl+C again to "
                           "unmount anyway (setup will fail; when freeing, the ISO is lost).")
    report_drive(drive, out, drive.poll(timeout=1.5), 0, 0)    # pick up the final status
    st = drive.status or {"files": {}, "violations": 0, "paused": False}
    problems, unread = iso.setup_result(code, setup_log, st["files"])
    unmount(drive, out)
    result = {"setup_exit_code": code, "setup_log": setup_log, "problems": problems,
              "unread": unread, "violations": st["violations"], "freeing_stopped": st["paused"]}
    if problems:
        raise Stop(1, "Setup may not have finished: " + "; ".join(problems) + ". The ISO was kept.",
                   fix=f"Read the setup log: {setup_log}", **result)
    if unread:
        out("warning", "Setup finished but did not read to the end of: " + ", ".join(unread) +
                       " (normal for optional extras like languages). The ISO was kept.")
    else:
        out("event", "Setup finished successfully (exit code 0, log confirms, all .bin files read).")
        if args.delete_iso:
            result["iso_deleted_bytes"] = delete_iso(path, out)
    return dict(result, ok=True)


def delete_iso(path, out):
    try:
        on_disk = iso.delete_iso(path)
    except OSError as e:
        raise Stop(1, f"Could not delete the ISO: {e}")
    out("event", f"Deleted {path} ({iso.human(on_disk)} given back to the drive).", freed=on_disk)
    return on_disk


def cmd_iso_delete(args, out):
    path = os.path.abspath(args.iso)
    if not os.path.isfile(path):
        out("event", f"Already gone: {path}")
        return {"ok": True, "already_done": True, "path": path}
    if args.dry_run:
        out("plan", f"Would delete {path} and its freeing record.", path=path)
        return {"ok": True, "dry_run": True, "path": path, "size": os.path.getsize(path)}
    if not args.yes:
        raise Stop(6, f"This deletes {path} permanently.", fix=with_yes(args))
    return {"ok": True, "path": path, "freed": delete_iso(path, out)}


# ---------- arguments ----------
class Parser(argparse.ArgumentParser):
    """argparse that reports bad arguments in the requested format (JSON or text)."""

    def error(self, message):
        sample = next((line.strip() for line in (self.epilog or "").splitlines()
                       if line.strip().startswith(PROG)), None)
        raise Stop(2, message, fix=f"{sample}   (more: {self.prog} --help)" if sample else f"{self.prog} --help")


def examples(*lines):
    return "Examples:\n" + "\n".join(f"  {PROG} {line}" for line in lines)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="one JSON object per line on stdout (or set EE_JSON=1)")
    common.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="text mode: only data, warnings and errors")
    fmt = argparse.RawDescriptionHelpFormatter

    def add(sub, name, func, text, epilog):
        p = sub.add_parser(name, parents=[common], help=text, description=text, epilog=epilog,
                           formatter_class=fmt)
        p.set_defaults(func=func)
        return p

    def group(name, text):
        g = sub.add_parser(name, parents=[common], help=text, description=text, formatter_class=fmt)
        g.set_defaults(func=None, parser=g)
        return g.add_subparsers(dest="cmd", metavar="<command>")

    ap = Parser(prog=PROG, parents=[common], formatter_class=fmt,
                description="EnhancedExtract in the terminal: extract RAR sets and install games from "
                            "ISOs while freeing space as you go. Never prompts; everything is a flag.",
                epilog=examples("system check", "rar extract Game.part1.rar --dry-run",
                                "--json iso inspect Game.iso --install-size-mb 52000")
                + "\n\nExit codes:\n" + "\n".join(f"  {k:<4} {v}" for k, v in EXIT.items()))
    ap.add_argument("--version", action="version", version=f"EnhancedExtract CLI {VERSION}")
    ap.set_defaults(func=None, parser=ap)
    sub = ap.add_subparsers(dest="group", metavar="<group>")

    system = group("system", "what this PC has, and installing what's missing")
    add(system, "check", cmd_system_check, "report UnRAR, WinFsp, fusepy and admin rights",
        examples("system check", "--json system check"))
    p = add(system, "install-winfsp", cmd_system_install_winfsp,
            "install the bundled WinFsp driver (needs admin; no-op if installed)",
            examples("system install-winfsp", "system install-winfsp --dry-run"))
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")

    rar = group("rar", "multi-part RAR sets")
    for name, func, text, ex_lines in (
            ("inspect", cmd_rar_inspect, "list parts, sizes and the free space an extract needs",
             ["rar inspect \"D:\\Downloads\\Game.part1.rar\"",
              "rar inspect Game.part1.rar --dest \"D:\\Games\\Game\" --delete"]),
            ("verify", cmd_rar_verify, "test every part's checksums; writes nothing",
             ["rar verify Game.part1.rar", "echo secret | rar verify Game.part1.rar --password-stdin"]),
            ("extract", cmd_rar_extract, "verify, then extract; with --delete each part is removed once used",
             ["rar extract Game.part1.rar --dest \"D:\\Games\\Game\"",
              "rar extract Game.part1.rar --delete --dry-run",
              "rar extract Game.part1.rar --delete --yes",
              "--json rar extract Game.part1.rar --delete --yes --password-stdin < pw.txt"])):
        p = add(rar, name, func, text, examples(*ex_lines))
        p.add_argument("archive", help="first part of the set, e.g. Game.part1.rar")
        pw = p.add_mutually_exclusive_group()
        pw.add_argument("--password", help="archive password (visible to other programs; prefer the next two)")
        pw.add_argument("--password-stdin", action="store_true", help="read the password from the first stdin line")
        p.epilog += "\n\nThe password can also come from the EE_PASSWORD environment variable."
        if name != "verify":
            p.add_argument("--dest", help="extract into this folder (default: next to the archive, named after it)")
            p.add_argument("--delete", action="store_true", help="delete each part once it has been extracted")
        if name == "extract":
            p.add_argument("--no-verify", action="store_true", help="skip the checksum pass before extracting")
            p.add_argument("--ignore-space", action="store_true", help="start even if free space looks too low")
            p.add_argument("--dry-run", action="store_true", help="check everything and print the plan; change nothing")
            p.add_argument("--yes", action="store_true", help="confirm --delete")

    isos = group("iso", "install a game from an ISO while freeing the ISO behind setup")
    p = add(isos, "inspect", cmd_iso_inspect, "files in the ISO and the free space an install needs",
            examples("iso inspect Game.iso", "iso inspect Game.iso --install-size-mb 52000 --buffer-gb 5",
                     "--json iso inspect Game.iso --files"))
    p.add_argument("iso", help="the game ISO (UDF, with setup.exe and .bin files)")
    p.add_argument("--install-size-mb", type=float, help="from setup: 'At least ... MB of free disk space is required'")
    p.add_argument("--buffer-gb", type=float, default=iso.DEFAULT_BUFFER_GB,
                   help=f"GB of ISO kept behind setup (default {iso.DEFAULT_BUFFER_GB})")
    p.add_argument("--files", action="store_true", help="also list every file")

    p = add(isos, "install", cmd_iso_install,
            "mount the ISO, run setup.exe and free the ISO behind it (admin terminal)",
            examples("iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --dry-run",
                     "iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --silent --yes",
                     "iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --silent "
                     "--delete-iso --yes",
                     "iso install Game.iso --no-free --no-setup        (mount only; send 'quit' to unmount)"))
    p.add_argument("iso", help="the game ISO")
    p.add_argument("--install-dir", help="folder setup installs into (required unless --no-free)")
    p.add_argument("--install-size-mb", type=float, help="from setup: 'At least ... MB of free disk space is required'")
    p.add_argument("--buffer-gb", type=float, default=iso.DEFAULT_BUFFER_GB,
                   help=f"GB of ISO kept behind setup (default {iso.DEFAULT_BUFFER_GB})")
    p.add_argument("--no-free", action="store_true", help="serve the ISO and log reads, but free nothing")
    p.add_argument("--no-setup", action="store_true", help="only mount; unmount on 'quit' (stdin) or Ctrl+C")
    p.add_argument("--silent", action="store_true",
                   help="run setup unattended: " + " ".join(SETUP_SILENT) + " /DIR=<install-dir>")
    p.add_argument("--setup-arg", action="append", default=[], help="extra argument for setup.exe (repeatable)")
    p.add_argument("--delete-iso", action="store_true", help="delete the ISO if setup fully succeeded")
    p.add_argument("--status-every", type=float, default=10, help="seconds between status lines (default 10)")
    p.add_argument("--dry-run", action="store_true", help="run every check and print the plan; mount nothing")
    p.add_argument("--yes", action="store_true", help="confirm freeing the ISO and --delete-iso")

    p = add(isos, "delete", cmd_iso_delete, "delete an ISO and its freeing record (no-op if already gone)",
            examples("iso delete Game.iso --dry-run", "iso delete Game.iso --yes"))
    p.add_argument("iso", help="the ISO to delete")
    p.add_argument("--dry-run", action="store_true", help="say what would be deleted")
    p.add_argument("--yes", action="store_true", help="confirm")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv or os.environ.get("EE_JSON", "") not in ("", "0")
    out = Out(as_json, quiet="-q" in argv or "--quiet" in argv)
    started = time.time()
    try:
        args = build_parser().parse_args(argv)
        if args.func is None:               # a group or nothing at all: show what's there
            if out.as_json:
                raise Stop(2, "Missing command.", fix=f"{args.parser.prog} --help")
            args.parser.print_help()
            return 0
        args.argv = argv
        args.pw = read_password(args) if args.group == "rar" else None
        result = args.func(args, out)
        code = 0 if result.get("ok") else 1
    except Stop as e:
        out("error", e.msg, **({"fix": e.fix} if e.fix else {}))
        if e.fix and not out.as_json:
            print(f"  {e.fix}", file=sys.stderr)
        result, code = dict(e.extra, ok=False, error=e.msg, **({"fix": e.fix} if e.fix else {})), e.code
    except KeyboardInterrupt:
        out("error", "Stopped with Ctrl+C.")
        result, code = {"ok": False, "error": "interrupted"}, 130
    result["duration_s"] = round(time.time() - started, 2)
    if out.as_json or code == 0:
        out.result(code, result)
    return code


if __name__ == "__main__":
    sys.exit(main())

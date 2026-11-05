"""Core logic: list, verify and extract multi-part RAR sets with WinRAR's UnRAR.exe.

In delete mode UnRAR runs with -vp, which makes it pause before opening each
next volume. At that pause the previous volume is fully read and closed, so it
is deleted before UnRAR is told to continue.
"""
import codecs
import os
import re
import shutil
import subprocess

import paths

BUNDLED_UNRAR = os.path.join(paths.APP_DIR, "UnRAR.exe")   # ships in the exe, for PCs without WinRAR
UNRAR_CANDIDATES = [
    r"C:\Program Files\WinRAR\UnRAR.exe",
    r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    BUNDLED_UNRAR,
]

# Extra free space kept on top of the computed need.
SAFETY_MARGIN = 1 * 1024**3

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# UnRAR writes ANSI to pipes by default, which mangles non-ASCII paths; ask for UTF-8.
UTF8_OUTPUT = "-scfr"

EXIT_CODES = {
    1: "non-fatal warning",
    2: "fatal error",
    3: "checksum error - the archive is corrupt",
    4: "archive is locked",
    5: "write error (disk full?)",
    6: "cannot open a file",
    7: "bad command line",
    8: "not enough memory",
    9: "cannot create a file",
    10: "no files to extract",
    11: "wrong password",
    255: "stopped by user",
}


class ExtractError(Exception):
    pass


class PasswordError(ExtractError):
    """The archive needs a password, or the one given is wrong."""


def password_arg(password):
    return "-p" + password if password else "-p-"


def find_unrar():
    for path in UNRAR_CANDIDATES:
        if os.path.isfile(path):
            return path
    found = shutil.which("UnRAR.exe")
    if found:
        return found
    raise ExtractError("UnRAR.exe not found. Install WinRAR (or put UnRAR.exe on PATH).")


def rar_tool():
    """(where it comes from, path) of the UnRAR the app will use, or None."""
    try:
        path = find_unrar()
    except ExtractError:
        return None
    if os.path.normcase(path) == os.path.normcase(BUNDLED_UNRAR):
        return "built into the app", path
    return ("WinRAR" if "\\winrar\\" in path.lower() else "on PATH"), path


def describe_exit(code):
    return EXIT_CODES.get(code, f"unknown error (exit code {code})")


class ArchiveInfo:
    def __init__(self, first, volumes, unpacked, files):
        self.first = first
        self.volumes = volumes          # list of paths, in order
        self.unpacked = unpacked        # total bytes after extraction
        self.files = files              # number of entries

    @property
    def packed(self):
        return sum(os.path.getsize(v) for v in self.volumes if os.path.exists(v))

    @property
    def largest_volume(self):
        return max((os.path.getsize(v) for v in self.volumes if os.path.exists(v)), default=0)


def inspect(first, password=None):
    """List every volume and the total unpacked size."""
    unrar = find_unrar()
    proc = subprocess.run([unrar, "l", "-v", UTF8_OUTPUT, password_arg(password), first], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    out = proc.stdout
    # Encrypted file names: older UnRAR exits with 11, 7.x with 6 plus this message.
    if proc.returncode == 11 or (proc.returncode and "Incorrect password" in out + proc.stderr):
        raise PasswordError("This archive's file names are encrypted - a password is needed to open it."
                            if not password else "Wrong password.")
    if proc.returncode != 0:
        raise ExtractError(f"Cannot read archive: {describe_exit(proc.returncode)}\n{out[-500:]}")
    volumes = []
    for m in re.finditer(r"^Archive: (.+)$", out, re.M):
        v = m.group(1).strip()
        if v not in volumes:
            volumes.append(v)
    totals = re.findall(r"^\s+(\d+)\s+(\d+)\s*$", out, re.M)
    if not volumes or not totals:
        raise ExtractError("Could not understand the archive listing.")
    unpacked, files = int(totals[-1][0]), int(totals[-1][1])
    missing = [v for v in volumes if not os.path.exists(v)]
    if missing:
        raise ExtractError("Missing parts:\n" + "\n".join(missing))
    return ArchiveInfo(first, volumes, unpacked, files)


def space_needed(info, dest, delete):
    """Free bytes required on the destination drive before starting."""
    same_drive = os.path.splitdrive(os.path.abspath(dest))[0].lower() == \
        os.path.splitdrive(os.path.abspath(info.first))[0].lower()
    if delete and same_drive:
        # Output grows while parts are removed; the peak is roughly the growth
        # beyond the archive size plus one part not yet freed.
        need = max(0, info.unpacked - info.packed) + info.largest_volume
    else:
        need = info.unpacked
    return need + SAFETY_MARGIN


def free_space(path):
    while path and not os.path.exists(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free


VOLUME_LINE = re.compile(r"(?:Extracting from|Testing archive) (.+)$")
PERCENT = re.compile(r"(\d{1,3})%(?=[\b\r\n ]|$)")
PROMPT = re.compile(r"\[Q\]uit\s*$")


class Runner:
    """Runs one UnRAR job and reports through callbacks. Call stop() from another thread to abort."""

    def __init__(self, log, progress, password=None):
        self.log = log              # log(text)
        self.progress = progress    # progress(percent, part_index, part_count)
        self.password = password
        self.proc = None
        self.stopped = False

    def stop(self):
        self.stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def _start(self, args):
        self.proc = subprocess.Popen([find_unrar(), UTF8_OUTPUT] + args, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     creationflags=NO_WINDOW)
        return self.proc

    def _read_loop(self, info, on_prompt=None):
        """Feed UnRAR output to the log/progress; on_prompt(buf) handles volume pauses.

        Output is read in chunks (whatever is available), not byte by byte, and lines are
        only inspected once complete."""
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        volumes = {os.path.normcase(v): i for i, v in enumerate(info.volumes)}
        buf = ""
        line = ""
        part = 1
        total = len(info.volumes)
        while True:
            chunk = self.proc.stdout.read1(65536)
            if not chunk:
                break
            text = decoder.decode(chunk)
            buf = (buf + text)[-2000:]
            for ch in text:
                if ch in "\r\n":
                    vm = VOLUME_LINE.match(line.strip())
                    if vm:
                        new_part = volumes.get(os.path.normcase(vm.group(1).strip()), part - 1) + 1
                        if new_part != part:
                            part = new_part
                            self.progress(None, part, total)
                    if line.strip():
                        self._log_line(line)
                    line = ""
                elif ch == "\b":
                    line = line[:-1]
                else:
                    line += ch
            pct = PERCENT.findall(text)
            if pct:
                self.progress(min(100, int(pct[-1])), part, total)
            if PROMPT.search(buf):
                if on_prompt is None:
                    raise ExtractError("UnRAR asked for a missing volume.")
                on_prompt(buf)
                part += 1
                self.progress(None, part, total)
                buf = line = ""
        if line.strip():
            self._log_line(line)
        return self.proc.wait()

    def _log_line(self, line):
        text = re.sub(r"\s+\d{1,3}%", "", line).rstrip()
        if text and not text.startswith("UNRAR "):
            self.log(text)

    def verify(self, info):
        self.log("Verifying all parts (reads everything, writes nothing)...")
        self._start(["t", password_arg(self.password), info.first])
        rc = self._read_loop(info)
        if self.stopped:
            raise ExtractError("Stopped by user.")
        if rc == 11:
            raise PasswordError("Verification failed: " + ("wrong password." if self.password
                                else "this archive needs a password.") + " Nothing was deleted.")
        if rc != 0:
            raise ExtractError(f"Verification FAILED: {describe_exit(rc)}. Nothing was deleted.")
        self.log("Verification passed: every file's checksum is OK.")

    def extract(self, info, dest, delete):
        os.makedirs(dest, exist_ok=True)
        args = ["x", "-o+", password_arg(self.password)]
        if delete:
            args.append("-vp")
        self._start(args + [info.first, os.path.join(dest, "")])
        state = {"done": 0}     # index of the part UnRAR just finished

        def on_prompt(buf):
            # Volumes are taken in listing order rather than parsed back out of the prompt
            # text, so an unusual file name can't break the hand-over.
            i = state["done"]
            prev = info.volumes[i]
            nxt = info.volumes[i + 1] if i + 1 < len(info.volumes) else None
            if not nxt or not os.path.exists(nxt):
                self.proc.stdin.write(b"Q\n")
                self.proc.stdin.flush()
                raise ExtractError(f"Next part not found: {nxt}. Stopped; the current part was kept.")
            try:
                os.remove(prev)
                self.log(f"Deleted {os.path.basename(prev)}")
            except OSError as e:
                self.log(f"Could not delete {os.path.basename(prev)} ({e}); will retry at the end.")
            state["done"] = i + 1
            self.proc.stdin.write(b"C\n")
            self.proc.stdin.flush()

        try:
            rc = self._read_loop(info, on_prompt if delete else None)
        except ExtractError:
            self.stop()
            raise
        if self.stopped:
            raise ExtractError("Stopped by user.")
        if rc == 11:
            raise PasswordError("Extraction failed: wrong or missing password.")
        if rc != 0:
            raise ExtractError(f"Extraction FAILED: {describe_exit(rc)}.")
        if delete:
            for v in info.volumes:
                if os.path.exists(v):
                    try:
                        os.remove(v)
                        self.log(f"Deleted {os.path.basename(v)}")
                    except OSError as e:
                        self.log(f"Could not delete {os.path.basename(v)}: {e}")
        self.log("Extraction finished successfully.")


def default_dest(first):
    """Folder next to the archive, named after it: D:\\x\\Game.part1.rar -> D:\\x\\Game."""
    base = os.path.basename(first)
    if base.lower().endswith(".rar"):
        base = base[:-4]
    return os.path.join(os.path.dirname(first), base.rsplit(".part", 1)[0])


def remaining_parts(info):
    return [v for v in info.volumes if os.path.exists(v)]


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024

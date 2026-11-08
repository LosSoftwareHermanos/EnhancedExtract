"""Core logic: list, verify and extract multi-part RAR sets with WinRAR's UnRAR.exe.

In delete mode UnRAR pauses before opening each next volume (-vp). Safe mode
keeps a file's volumes until it is extracted and flushed; early mode deletes
closed volumes immediately. A journal records completed files for resuming.
"""
import codecs
import json
import os
import tempfile
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
    def __init__(self, first, volumes, unpacked, files, password=None, start=None):
        self.first = first
        self.volumes = volumes          # list of paths, in order
        self.unpacked = unpacked        # total bytes after extraction
        self.files = files              # number of entries
        self.password = password
        self.start = start or first     # where UnRAR starts reading: a later part when resuming
        self._layout = None

    @property
    def packed(self):
        return sum(os.path.getsize(v) for v in self.volumes if os.path.exists(v))

    @property
    def largest_volume(self):
        return max((os.path.getsize(v) for v in self.volumes if os.path.exists(v)), default=0)

    @property
    def start_index(self):
        return volume_index(self.volumes, self.start)

    def layout(self):
        if self._layout is None:
            self._layout = read_layout(self)
        return self._layout


def volume_index(volumes, path):
    key = os.path.normcase(os.path.abspath(path))
    for i, v in enumerate(volumes):
        if os.path.normcase(os.path.abspath(v)) == key:
            return i
    raise ExtractError(f"{os.path.basename(path)} is not a part of this set.")


# ---------- which files have data in which part ----------
# A part can only be deleted once every file with data in it is completely extracted, or
# the file split across that part's end loses its start for good. `UnRAR lt -v` lists every
# part's file pieces, with "-->" / "<--" / "<->" marking a piece continued in the next part,
# from the previous one, or both.

class Entry:
    """One file of the set, in archive order. `first`/`last` are part indexes; `pieces` maps a
    part index to the packed bytes of this file in it. `continued` is set when the listing
    started at a later part and the file began before it."""
    __slots__ = ("name", "size", "first", "last", "pieces", "continued")

    def __init__(self, name, size, part, packed, continued):
        self.name, self.size, self.first, self.last = name, size, part, part
        self.pieces = {part: packed}
        self.continued = continued

    @property
    def packed(self):
        return sum(self.pieces.values())


class Layout:
    def __init__(self, entries, parts, solid):
        self.entries = entries
        self.solid = solid
        self.in_part = [[] for _ in range(parts)]        # entries with data in each part
        for e in entries:
            for p in e.pieces:
                self.in_part[p].append(e)


def read_layout(info):
    unrar = find_unrar()
    proc = subprocess.run([unrar, "lt", "-v", UTF8_OUTPUT, password_arg(info.password), info.start],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW)
    if proc.returncode == 11 or (proc.returncode and "Incorrect password" in proc.stdout + proc.stderr):
        raise PasswordError("Wrong password." if info.password else "This archive needs a password.")
    if proc.returncode != 0:
        raise ExtractError(f"Cannot read archive: {describe_exit(proc.returncode)}")
    entries, solid, part, field = [], False, None, {}
    open_entry = None           # the file whose last piece so far ran on into the next part

    def flush():
        nonlocal open_entry
        if part is None or field.get("Type") != "File" or "Name" not in field:
            return
        ratio = field.get("Ratio", "")
        before, after = ratio in ("<--", "<->"), ratio in ("-->", "<->")
        packed = int(field.get("Packed size", "0") or 0)
        if before and open_entry is not None and open_entry.name == field["Name"]:
            open_entry.last = part
            open_entry.pieces[part] = open_entry.pieces.get(part, 0) + packed
            entry = open_entry
        else:
            entry = Entry(field["Name"], int(field.get("Size", "0") or 0), part, packed, before)
            entries.append(entry)
        open_entry = entry if after else None

    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if line.startswith("Archive: "):
            flush()
            field = {}
            part = volume_index(info.volumes, line[len("Archive: "):].strip())
        elif line.startswith("Details: "):
            solid = solid or "solid" in line[len("Details: "):].split(", ")
        elif line.startswith("Name: "):
            flush()
            field = {"Name": line[len("Name: "):]}
        elif ": " in line and field:
            key, value = line.split(": ", 1)
            field.setdefault(key.strip(), value.strip())
    flush()
    return Layout(entries, len(info.volumes), solid)


SAFE, EARLY = "safe", "early"


def deletable_parts(layout, k, mode, finished=False):
    """Indexes of parts that may be deleted once UnRAR has read every part up to index k.

    SAFE: only parts all of whose files are complete, so a stop or crash never costs a file
    and the rest can be resumed. A solid set decodes front to back only, so nothing is freed
    before the end. EARLY: every part UnRAR has left, as soon as it leaves it."""
    if finished or mode == EARLY:
        return list(range(k + 1))
    if layout.solid:
        return []
    hold = min((e.first for e in layout.in_part[k] if e.last > k), default=k + 1)
    return list(range(min(hold, k + 1)))


def space_needed(info, dest, delete, mode=SAFE, done=()):
    """Free bytes required on the destination drive before starting.

    For delete modes this replays the extraction part by part: output grows by each file's
    share of a part as it is read, and the parts the mode may delete give their space back
    at each part boundary. The highest point is what must be free."""
    same_drive = os.path.splitdrive(os.path.abspath(dest))[0].lower() == \
        os.path.splitdrive(os.path.abspath(info.first))[0].lower()
    if not delete or not same_drive:
        return info.unpacked + SAFETY_MARGIN
    layout = info.layout()
    done = set(done)
    sizes = [os.path.getsize(v) if os.path.exists(v) else 0 for v in info.volumes]
    remaining = sum(e.size for e in layout.entries if e.name not in done)
    written = freed = peak = 0
    gone = set()
    last = len(info.volumes) - 1
    for k in range(info.start_index, last + 1):
        for e in layout.in_part[k]:
            if e.name not in done:
                written += e.size * e.pieces[k] / e.packed if e.packed else (e.size if k == e.last else 0)
        peak = max(peak, written - freed)
        for p in deletable_parts(layout, k, mode, finished=k == last):
            if p not in gone:
                gone.add(p)
                freed += sizes[p]
    return int(min(peak, remaining)) + SAFETY_MARGIN


# ---------- resume journal ----------
# `<set name>.ee-resume.json` next to the parts, written before any part is deleted and
# replaced atomically after each file flush and before each delete. It names the output
# folder, every part with its original size, the files known to be complete on disk, and
# the parts deleted, so a stopped or crashed extraction continues where it left off.

JOURNAL_SUFFIX = ".ee-resume.json"


def journal_path(first):
    return os.path.join(os.path.dirname(os.path.abspath(first)),
                        os.path.basename(default_dest(first)) + JOURNAL_SUFFIX)


def read_journal(first):
    try:
        with open(journal_path(first), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    name = os.path.normcase(os.path.basename(first))
    if not any(os.path.normcase(p) == name for p in data.get("parts", [])) or not data.get("dest"):
        return None
    return data


def write_journal(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def flush_file(path, size):
    """True once the extracted file has its full size and is on the disk, not just in cache."""
    try:
        if os.path.getsize(path) != size:
            return False
        with open(path, "r+b") as f:
            os.fsync(f.fileno())
        return True
    except OSError:
        return False


class PartFreer:
    """Deletes parts behind UnRAR in the order that keeps every stop resumable:
    flush the files the part holds, record them and the part in the journal, then delete."""

    def __init__(self, info, dest, mode, log, journal=None):
        self.info, self.dest, self.mode, self.log = info, dest, mode, log
        self.layout = info.layout()
        self.path = journal_path(info.first)
        j = journal or {}
        self.done = set(j.get("done", []))
        self.at_risk = set(j.get("at_risk", []))
        self.deleted = set(j.get("deleted", []))
        self.sizes = j.get("sizes") or [os.path.getsize(v) for v in info.volumes]
        self.save()
        # A crash between the journal write and the delete leaves a part recorded as deleted.
        for v in info.volumes:
            if os.path.basename(v) in self.deleted and os.path.exists(v):
                try:
                    os.remove(v)
                except OSError:
                    self.deleted.discard(os.path.basename(v))

    def save(self):
        write_journal(self.path, {
            "version": 1, "archive": os.path.basename(self.info.first),
            "parts": [os.path.basename(v) for v in self.info.volumes], "sizes": self.sizes,
            "dest": self.dest, "files": self.info.files, "unpacked": self.info.unpacked,
            "mode": self.mode, "done": sorted(self.done), "at_risk": sorted(self.at_risk - self.done),
            "deleted": sorted(self.deleted)})

    @property
    def lost(self):
        return sorted(self.at_risk - self.done)

    def read_through(self, k, finished=False):
        """UnRAR has read every part up to index k: delete what the mode allows."""
        for p in deletable_parts(self.layout, k, self.mode, finished):
            name = os.path.basename(self.info.volumes[p])
            if name in self.deleted:
                continue
            complete = [e for e in self.layout.in_part[p] if e.last <= k or finished]
            fresh = [e for e in complete if e.name not in self.done and not e.continued]
            not_ready = [e for e in fresh if not flush_file(os.path.join(self.dest, e.name), e.size)]
            if not_ready and self.mode == SAFE:
                self.log(f"Keeping {name} for now: {not_ready[0].name} is not fully written yet.")
                return
            self.done.update(e.name for e in fresh if e not in not_ready)
            self.at_risk.update(e.name for e in self.layout.in_part[p] if e not in complete or e in not_ready)
            self.deleted.add(name)
            self.save()
            try:
                os.remove(self.info.volumes[p])
                self.log(f"Deleted {name}")
            except FileNotFoundError:
                pass
            except OSError as e:
                self.deleted.discard(name)
                self.save()
                self.log(f"Could not delete {name} ({e}); will retry.")

    def finish(self):
        self.read_through(len(self.info.volumes) - 1, finished=True)
        if any(os.path.exists(v) for v in self.info.volumes):
            return
        for path in (self.path, self.path + ".tmp"):
            try:
                os.remove(path)
            except OSError:
                pass


# ---------- files still being written ----------
# A part that is still being copied, downloaded or extracted into place is incomplete: reading it
# fails part-way (or worse, a delete mode frees the parts before it). Such a file is held open for
# writing by the program filling it, so opening it while refusing to share write access fails.

ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION = 32, 33


def in_use(path):
    """True while another program has `path` open for writing. Always False off Windows."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    # GENERIC_READ, share read only (no write), OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL
    h = k32.CreateFileW(os.path.abspath(path), 0x80000000, 0x1, None, 3, 0x80, None)
    if h is None or h == ctypes.c_void_p(-1).value:
        return ctypes.get_last_error() in (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION)
    k32.CloseHandle(h)
    return False


def rar_more_volumes(path):
    """True when this RAR 5 volume says another volume follows it, False when it is the last,
    None when that can't be told (RAR 4, damaged, unreadable). Reads only the file's last bytes:
    the end-of-archive header (size 3, type 5, flags 4, then 1 = not the last volume), which
    some volumes follow with zero padding."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            n = min(f.tell(), 64)
            f.seek(-n, os.SEEK_END)
            tail = f.read(n)
    except OSError:
        return None
    i = tail.rfind(b"\x03\x05\x04")
    if i < 0 or i + 3 >= len(tail) or tail[i + 4:].strip(b"\x00"):
        return None
    return bool(tail[i + 3] & 1)


SET_FILE = re.compile(r"^(?P<base>.+?)(?:\.part\d+\.(?:rar|dat)|\.rar|\.r\d\d)$", re.I)


def set_files(first):
    """Every file of the RAR set `first` belongs to that is in its folder (old and new naming)."""
    folder, name = os.path.split(os.path.abspath(first))
    m = SET_FILE.match(name)
    if not m:
        return [first]
    base = m["base"].lower()
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if (k := SET_FILE.match(n)) and k["base"].lower() == base)


def check_not_busy(files):
    """Stop before reading a set while any of its files is still being written."""
    busy = [os.path.basename(p) for p in files if os.path.exists(p) and in_use(p)]
    if busy:
        names = busy[0] if len(busy) == 1 else ", ".join(busy[:-1]) + " and " + busy[-1]
        raise ExtractError(f"Still being copied: {names} {'is' if len(busy) == 1 else 'are'} open for writing "
                           "by another program (a copy or download that hasn't finished). "
                           "Wait for it to finish, then try again.")


def inspect(first, password=None):
    """List every volume and the total unpacked size."""
    check_not_busy(set_files(first))
    unrar = find_unrar()
    proc = subprocess.run([unrar, "l", "-v", UTF8_OUTPUT, password_arg(password), first], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    out = proc.stdout
    # Encrypted file names: older UnRAR exits with 11, 7.x with 6 plus this message.
    if proc.returncode == 11 or (proc.returncode and "Incorrect password" in out + proc.stderr):
        raise PasswordError("This archive's file names are encrypted - a password is needed to open it."
                            if not password else "Wrong password.")
    # A later part not there yet (still downloading, or never downloaded): say which.
    gone = [g.strip() for g in re.findall(r"Cannot find volume (.+)", out + proc.stderr)]
    if gone:
        raise ExtractError("Missing parts:\n" + "\n".join(dict.fromkeys(gone)))
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
    # File contents encrypted, names not: the listing above works without a password, but UnRAR
    # marks every such file with "*". Ask for the password now, not when verify fails.
    if re.search(r"^\*", out, re.M):
        if not password:
            raise PasswordError("This archive is password protected - a password is needed to extract it.")
        if password_rejected(unrar, first, password):
            raise PasswordError("Wrong password.")
    return ArchiveInfo(first, volumes, unpacked, files, password)


def password_rejected(unrar, first, password, wait=6.0):
    """True when UnRAR says the password is wrong. RAR stores a check value for it, so a wrong one
    is refused within a moment of testing; a right one starts testing the data, which is stopped
    as soon as that shows (or after `wait` seconds). Reads only, writes nothing."""
    import threading
    import time
    proc = subprocess.Popen([unrar, "t", UTF8_OUTPUT, password_arg(password), first], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    seen = bytearray()

    def pump():
        while chunk := proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096):
            seen.extend(chunk)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    end = time.monotonic() + wait
    try:
        while time.monotonic() < end and proc.poll() is None:
            text = seen.decode("utf-8", "replace")
            if "Incorrect password" in text or "password is incorrect" in text:
                return True
            if re.search(r"\b[1-9]\d?%", text):       # data is being decrypted: the password works
                return False
            time.sleep(0.1)
        reader.join(1)
        text = seen.decode("utf-8", "replace")
        return "Incorrect password" in text or "password is incorrect" in text
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


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
        part = info.start_index + 1
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

    def _exclude(self, names):
        """UnRAR switches that skip files already extracted (a list file, UTF-8)."""
        if not names:
            return [], None
        fd, path = tempfile.mkstemp(suffix=".lst", prefix="ee-done-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(names) + "\n")
        return ["-scfl", "-x@" + path], path

    def verify(self, info, skip=()):
        self.log("Verifying all parts (reads everything, writes nothing)...")
        switches, listfile = self._exclude(skip)
        try:
            self._start(["t", password_arg(self.password)] + switches + [info.start])
            rc = self._read_loop(info)
        finally:
            if listfile:
                os.remove(listfile)
        if self.stopped:
            raise ExtractError("Stopped by user.")
        if rc == 11:
            raise PasswordError("Verification failed: " + ("wrong password." if self.password
                                else "this archive needs a password.") + " Nothing was deleted.")
        if rc != 0:
            raise ExtractError(f"Verification FAILED: {describe_exit(rc)}. Nothing was deleted.")
        self.log("Verification passed: every file's checksum is OK.")

    def extract(self, info, dest, delete, mode=SAFE, journal=None):
        """Extract into dest. With delete, parts are deleted behind UnRAR by a PartFreer in
        the given mode, and `journal` (from read_journal) continues a stopped run: files it
        records as done are skipped. Returns the freer (None without delete)."""
        os.makedirs(dest, exist_ok=True)
        freer = PartFreer(info, dest, mode, self.log, journal) if delete else None
        args = ["x", "-o+", password_arg(self.password)]
        if delete:
            args.append("-vp")
        switches, listfile = self._exclude(sorted(freer.done | set(freer.lost)) if freer else [])
        self._start(args + switches + [info.start, os.path.join(dest, "")])
        state = {"part": info.start_index}      # index of the part UnRAR is reading

        def on_prompt(buf):
            # Parts are taken in listing order rather than parsed back out of the prompt
            # text, so an unusual file name can't break the hand-over.
            k = state["part"]
            nxt = info.volumes[k + 1] if k + 1 < len(info.volumes) else None
            if not nxt or not os.path.exists(nxt):
                self.proc.stdin.write(b"Q\n")
                self.proc.stdin.flush()
                raise ExtractError(f"Next part not found: {nxt}. Stopped; the current part was kept.")
            freer.read_through(k)
            state["part"] = k + 1
            self.proc.stdin.write(b"C\n")
            self.proc.stdin.flush()

        try:
            rc = self._read_loop(info, on_prompt if delete else None)
        except ExtractError:
            self.stop()
            raise
        finally:
            if listfile:
                os.remove(listfile)
        if self.stopped:
            raise ExtractError("Stopped by user.")
        if rc == 11:
            raise PasswordError("Extraction failed: wrong or missing password.")
        if rc != 0:
            raise ExtractError(f"Extraction FAILED: {describe_exit(rc)}.")
        if freer:
            freer.finish()
            if freer.lost:
                self.log(f"{len(freer.lost)} file(s) could not be recovered: their start was in a part "
                         "already deleted.")
                for name in freer.lost:
                    try:
                        os.remove(os.path.join(dest, name))
                    except OSError:
                        pass
        self.log("Extraction finished successfully.")
        return freer


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

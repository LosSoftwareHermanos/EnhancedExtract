"""Every archive format except RAR (zip, 7z, tar, gz, bz2, xz, zst, cab, wim, ...), through 7-Zip.

RAR keeps its own engine (extractor.py: UnRAR frees parts while it reads them). Everything
else goes through `7z.exe`: the copy of an installed 7-Zip if there is one, else the copy
that ships with the app. 7-Zip is LGPL; its licence text ships next to it.

Differences from the RAR engine worth knowing:
- Split sets (`x.7z.001 ...`, `x.zip.001 ...`, `x.z01 ... x.zip`) are opened through their
  first piece; handing 7-Zip any later piece fails, so `first_volume` maps back.
- Nothing can be freed while reading, so `--delete` removes the archive (all its pieces)
  only after a verified extraction finished with no error.
- `.tar.gz` and its relatives hold one tar inside one compressor. They are extracted in one
  streamed pass (`7z x -so | 7z x -si -ttar`), so no temporary tar is written.
- Passwords go to 7-Zip on stdin, never on its command line.
"""
import codecs
import os
import re
import shutil
import subprocess
import threading

import extractor as ex
import paths

BUNDLED_DIRS = [os.path.join(paths.APP_DIR, "7zip"), os.path.join(paths.APP_DIR, "deps", "7zip")]
SYSTEM_DIRS = [r"C:\Program Files\7-Zip", r"C:\Program Files (x86)\7-Zip"]

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Extensions that name an archive 7-Zip can unpack. ISO is left out on purpose: the app's ISO
# path installs from an image; and RAR is left out because it has its own engine.
SINGLE_EXTS = (".zip", ".zipx", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2", ".xz", ".txz",
               ".zst", ".tzst", ".lzma", ".z", ".cab", ".wim", ".arj", ".lzh", ".lha", ".cpio")
TAR_SHORT = {".tgz", ".tbz", ".tbz2", ".txz", ".tzst"}          # one-piece spellings of .tar.<compressor>
EXT_FILTER = [e.lstrip(".") for e in SINGLE_EXTS] + ["001"]     # for file pickers

VOLUME = re.compile(r"^(?P<base>.+?)(?P<ext>\.[A-Za-z0-9]+)\.(?P<n>\d{3,})$")
ZIP_SPLIT = re.compile(r"^(?P<base>.+)\.z(?P<n>\d{2,})$", re.I)
RAR_NAME = re.compile(r"\.rar$|\.r\d\d$", re.I)


# ---------- the tool ----------

def _candidates():
    for folder in SYSTEM_DIRS + BUNDLED_DIRS:
        yield os.path.join(folder, "7z.exe")


def find_7z():
    for path in _candidates():
        if os.path.isfile(path):
            return path
    found = shutil.which("7z.exe") or shutil.which("7z")
    if found:
        return found
    raise ex.ExtractError("7z.exe not found. Install 7-Zip (or put 7z.exe on PATH).")


def tool():
    """(where it comes from, path) of the 7-Zip the app will use, or None."""
    try:
        path = find_7z()
    except ex.ExtractError:
        return None
    norm = os.path.normcase(os.path.dirname(path))
    if norm in {os.path.normcase(d) for d in BUNDLED_DIRS}:
        return "built into the app", path
    return ("7-Zip" if "7-zip" in norm else "on PATH"), path


# ---------- names and split sets ----------

def is_rar(path):
    return bool(RAR_NAME.search(os.path.basename(path)))


def classify(name):
    """(base, number, kind) for a file name 7-Zip can open, else None.

    kind is "single", "volume" (x.7z.001) or "zsplit" (x.z01; its last piece is x.zip). For
    "zsplit" the base is the shared stem; number is the piece number (the .zip itself is
    "single" with number 0 and joins the set through the stem)."""
    low = name.lower()
    m = VOLUME.match(name)
    if m and m["ext"].lower() in SINGLE_EXTS:
        return m["base"] + m["ext"], int(m["n"]), "volume"
    m = ZIP_SPLIT.match(name)
    if m:
        return m["base"], int(m["n"]), "zsplit"
    for ext in SINGLE_EXTS:
        if low.endswith(ext) and len(name) > len(ext):
            return name, 0, "single"
    return None


def is_archive_name(name):
    return classify(name) is not None and not RAR_NAME.search(name)


def first_volume(path):
    """The file to hand to 7-Zip for the set `path` belongs to."""
    path = os.path.abspath(path)
    name = os.path.basename(path)
    folder = os.path.dirname(path)
    c = classify(name)
    if not c:
        return path
    base, n, kind = c
    if kind == "volume":
        stem = name[:VOLUME.match(name).end("ext")]
        width = len(VOLUME.match(name)["n"])
        first = os.path.join(folder, f"{stem}.{1:0{width}d}")
        return first if os.path.exists(first) or not os.path.exists(path) else path
    if kind == "zsplit":
        last = os.path.join(folder, base + ".zip")
        for candidate in (last, os.path.join(folder, base + ".ZIP")):
            if os.path.exists(candidate):
                return candidate
    return path


def volumes(first):
    """Every piece of the set starting at `first`, in order. Raises when a piece is missing."""
    first = os.path.abspath(first)
    name = os.path.basename(first)
    folder = os.path.dirname(first)
    m = VOLUME.match(name)
    if m and m["ext"].lower() in SINGLE_EXTS:
        stem = name[:m.end("ext")]
        width = len(m["n"])
        found = {}
        for other in os.listdir(folder):
            o = VOLUME.match(other)
            if o and other[:o.end("ext")].lower() == stem.lower():
                found[int(o["n"])] = os.path.join(folder, other)
        if not found:
            return [first]
        missing = [n for n in range(1, max(found) + 1) if n not in found]
        if missing:
            raise ex.ExtractError("Missing parts:\n" + "\n".join(
                os.path.join(folder, f"{stem}.{n:0{width}d}") for n in missing))
        return [found[n] for n in sorted(found)]
    if name.lower().endswith(".zip"):
        stem = name[:-4]
        pieces = {}
        for other in os.listdir(folder):
            z = ZIP_SPLIT.match(other)
            if z and z["base"].lower() == stem.lower():
                pieces[int(z["n"])] = os.path.join(folder, other)
        if pieces:
            missing = [n for n in range(1, max(pieces) + 1) if n not in pieces]
            if missing:
                raise ex.ExtractError("Missing parts:\n" + "\n".join(
                    os.path.join(folder, f"{stem}.z{n:02d}") for n in missing))
            return [pieces[n] for n in sorted(pieces)] + [first]
    return [first]


def default_dest(first):
    """Folder next to the archive named after it: D:\\x\\Pack.tar.gz -> D:\\x\\Pack."""
    name = os.path.basename(first)
    m = VOLUME.match(name)
    if m and m["ext"].lower() in SINGLE_EXTS:
        name = name[:m.end("ext")]
    low = name.lower()
    if low.endswith(".tar.gz") or low.endswith(".tar.bz2") or low.endswith(".tar.xz") or low.endswith(".tar.zst") \
            or low.endswith(".tar.lzma") or low.endswith(".tar.z"):
        name = name[:low.rindex(".tar")]
    else:
        for ext in SINGLE_EXTS:
            if low.endswith(ext) and len(name) > len(ext):
                name = name[:-len(ext)]
                break
    return os.path.join(os.path.dirname(first), name or "Extracted")


# ---------- listing ----------

class SzInfo(ex.ArchiveInfo):
    """What `inspect` learned. Progress is one figure for the whole set (`single_progress`),
    since 7-Zip reports a percentage of everything, not of one piece."""
    single_progress = True

    def __init__(self, first, volumes, unpacked, files, password, kind, nested_tar, encrypted):
        super().__init__(first, volumes, unpacked, files, password)
        self.kind = kind                # 7-Zip's name for the format: zip, 7z, gzip, ...
        self.nested_tar = nested_tar    # a tar inside one compressor: extracted in one streamed pass
        self.encrypted = encrypted


PASSWORD_HINTS = ("Wrong password", "Enter password", "Cannot open encrypted archive", "Break signaled")
EXIT = {1: "finished with warnings", 2: "a fatal error", 7: "bad command line", 8: "not enough memory",
        255: "stopped by user"}


def describe(rc):
    return EXIT.get(rc, f"exit code {rc}")


def _run(args, password, capture=True):
    """Run 7z once with the password on stdin. Returns (returncode, text)."""
    proc = subprocess.run([find_7z(), "-sccUTF-8", "-y"] + args, input=((password or "") + "\n").encode("utf-8"),
                          capture_output=True, creationflags=NO_WINDOW)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")


def needs_password(text):
    return any(h in text for h in PASSWORD_HINTS)


def parse_listing(text):
    """(kind, entries) from `7z l -slt`. `kind` is the innermost archive's Type; entries is a list
    of dicts with Path, Folder, Size, Encrypted."""
    kind, entries, cur, body = None, [], None, False
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("----------"):
            body = True
            continue
        if not body:
            if line.startswith("Type = "):
                kind = line[7:].strip()
            continue
        if line.startswith("Path = "):
            cur = {"Path": line[7:]}
            entries.append(cur)
        elif cur is None and line.startswith("Size = "):
            # Raw compressor streams (bzip2/xz/zstd) have no Path field.
            cur = {"Path": "", "Size": line[7:].strip()}
            entries.append(cur)
        elif cur is not None and " = " in line:
            key, value = line.split(" = ", 1)
            cur.setdefault(key.strip(), value.strip())
    return kind, entries


def inspect(first, password=None):
    """List a set: its pieces, total unpacked size and file count. Raises PasswordError when a
    password is needed (or wrong) to read it."""
    first = first_volume(first)
    pieces = volumes(first)
    rc, text = _run(["l", "-slt", first], password)
    if rc != 0 and needs_password(text):       # header-encrypted: the listing itself needs the password
        raise ex.PasswordError("Wrong password." if password else "This archive's file names are "
                                                                  "encrypted - a password is needed to open it.")
    if rc not in (0, 1):
        tail = " ".join(l.strip() for l in text.splitlines() if "ERROR" in l or "Can't open" in l)[:300]
        raise ex.ExtractError(f"Cannot read archive: {describe(rc)}. {tail}".strip())
    kind, entries = parse_listing(text)
    if not entries and "Can't open as archive" in text:
        raise ex.ExtractError(f"{os.path.basename(first)} is not an archive 7-Zip can open.")
    files = [e for e in entries if e.get("Folder") != "+"]
    unpacked = sum(int(e.get("Size") or 0) for e in files)
    encrypted = any(e.get("Encrypted") == "+" for e in files)
    if encrypted and not password:
        raise ex.PasswordError("This archive is password protected - a password is needed.")
    name = os.path.basename(first).lower()
    volume = VOLUME.match(name)
    if volume:
        name = name[:volume.end("ext")]
    tar_name = any(name.endswith(ext) for ext in TAR_SHORT) or bool(
        re.search(r"\.tar\.(gz|bz2|xz|zst|lzma|z)$", name))
    nested = (len(files) == 1 and (files[0]["Path"].lower().endswith(".tar") or tar_name)
              and kind in ("gzip", "bzip2", "xz", "zstd", "lzma", "Z"))
    count = len(files)
    if nested:
        count, member_bytes = _tar_members(first, sum(os.path.getsize(p) for p in pieces) if unpacked else 0)
        unpacked = max(unpacked, member_bytes)
    elif files and any(not e.get("Size") for e in files):
        unpacked = _stream_size(first)
    missing = [p for p in pieces if not os.path.exists(p)]
    if missing:
        raise ex.ExtractError("Missing parts:\n" + "\n".join(missing))
    return SzInfo(first, pieces, unpacked, count, password, kind, nested, encrypted)


LIST_NESTED_LIMIT = 512 * 1024**2      # decompressing a bigger archive only to count its files is not worth it


def _tar_members(first, packed):
    """Count and total bytes inside a compressed tar without writing an intermediate file."""
    if packed > LIST_NESTED_LIMIT:
        return 0, 0
    seven = find_7z()
    outer = subprocess.Popen([seven, "x", first, "-so", "-bso0", "-bsp0", "-bse0", "-y"], stdout=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    inner = subprocess.run([seven, "l", "-slt", "-si", "-ttar", "-sccUTF-8"], stdin=outer.stdout,
                           capture_output=True, creationflags=NO_WINDOW)
    outer.stdout.close()
    rc = outer.wait()
    if rc != 0 or inner.returncode != 0:
        raise ex.ExtractError("Cannot read the TAR contents of this compressed archive.")
    _, entries = parse_listing(inner.stdout.decode("utf-8", "replace"))
    files = [e for e in entries if e.get("Folder") != "+"]
    return len(files), sum(int(e.get("Size") or 0) for e in files)


def _stream_size(first):
    """Some compressors store no unpacked size. Count their output with bounded memory."""
    proc = subprocess.Popen([find_7z(), "x", first, "-so", "-bso0", "-bsp0", "-bse0", "-y"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=NO_WINDOW)
    total = 0
    with proc.stdout:
        while chunk := proc.stdout.read(1024 * 1024):
            total += len(chunk)
    if proc.wait() != 0:
        raise ex.ExtractError("Cannot determine the unpacked size of this compressed archive.")
    return total


# ---------- running ----------

PERCENT = re.compile(r"^\s*(\d{1,3})%")     # "  45% 3 - sub\big.bin": progress, then files done and the current one


class Runner:
    """Runs one 7-Zip job and reports through callbacks (same shape as extractor.Runner).
    Call stop() from another thread to abort."""

    def __init__(self, log, progress, password=None):
        self.log = log                  # log(text), one call per output line
        self.progress = progress        # progress(percent, part_index, part_count)
        self.password = password
        self.procs = []
        self.stopped = False

    def stop(self):
        self.stopped = True
        for p in self.procs:
            if p.poll() is None:
                p.kill()

    def _spawn(self, args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT):
        proc = subprocess.Popen([find_7z(), "-sccUTF-8", "-y", "-bb1", "-bsp1"] + args, stdin=stdin, stdout=stdout,
                                stderr=stderr, creationflags=NO_WINDOW)
        self.procs.append(proc)
        return proc

    def _feed_password(self, proc):
        try:
            proc.stdin.write(((self.password or "") + "\n").encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass

    def _read(self, stream):
        """Feed 7-Zip's output to the log and progress callbacks. Returns everything read (tail)."""
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        tail, line = "", ""
        while True:
            chunk = stream.read1(65536)
            if not chunk:
                break
            text = decoder.decode(chunk)
            tail = (tail + text)[-4000:]
            for ch in text:
                if ch in "\r\n":
                    pct = PERCENT.match(line)
                    if pct:
                        self.progress(min(100, int(pct.group(1))), 1, 1)
                    elif line.strip():
                        self.log(line.strip())
                    line = ""
                elif ch == "\b":
                    line = line[:-1]
                else:
                    line += ch
        if line.strip():
            self.log(line.strip())
        return tail

    def _fail(self, what, rc, tail):
        if self.stopped:
            raise ex.ExtractError("Stopped by user.")
        if needs_password(tail):
            raise ex.PasswordError(f"{what} failed: " + ("wrong password." if self.password
                                                         else "this archive needs a password."))
        problems = [l.strip() for l in tail.splitlines() if re.search(r"ERROR|CRC Failed|Data Error|Unexpected end|"
                                                                      r"Can't open|Cannot open", l)]
        detail = f" {problems[0]}" if problems else ""
        raise ex.ExtractError(f"{what} failed: {describe(rc)}.{detail}")

    def verify(self, info, skip=()):
        self.log("Verifying the archive (reads everything, writes nothing)...")
        proc = self._spawn(["t", info.first])
        self._feed_password(proc)
        tail = self._read(proc.stdout)
        rc = proc.wait()
        if rc not in (0,):
            self._fail("Verification", rc, tail)
        self.log("Verification passed: every file's checksum is OK.")

    def extract(self, info, dest, delete=False, mode=None, journal=None):
        os.makedirs(dest, exist_ok=True)
        if info.nested_tar:
            self._extract_tar_pipe(info, dest, delete)
        else:
            proc = self._spawn(["x", "-aoa", "-o" + dest, info.first])
            self._feed_password(proc)
            tail = self._read(proc.stdout)
            self._finish("Extraction", proc.wait(), tail, delete)
        if self.stopped:
            raise ex.ExtractError("Stopped by user.")
        self.log("Extraction finished successfully.")
        return None

    def _finish(self, what, rc, tail, strict):
        """7-Zip's exit code 1 is "done, with warnings" (say, a file it could not set a date on).
        That passes unless the archive is about to be deleted: then anything short of clean fails."""
        if rc == 0:
            return
        if rc == 1 and not strict and not self.stopped:
            self.log("Warning: 7-Zip finished with warnings; some details may not have been restored.")
            return
        self._fail(what, rc, tail)

    def _extract_tar_pipe(self, info, dest, delete=False):
        """compressor -> tar in one streamed pass: the outer 7-Zip writes the tar stream to a pipe,
        the inner one unpacks it. Progress comes from the outer one (position in the compressed file)."""
        seven = find_7z()
        outer = subprocess.Popen([seven, "-sccUTF-8", "-y", "x", info.first, "-so", "-bso0", "-bsp2", "-bse2"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=NO_WINDOW)
        inner = subprocess.Popen([seven, "-sccUTF-8", "-y", "x", "-si", "-ttar", "-aoa", "-o" + dest, "-bb1", "-bsp0"],
                                 stdin=outer.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 creationflags=NO_WINDOW)
        outer.stdout.close()
        self.procs += [outer, inner]
        tails = {}

        def watch(name, proc, stream):
            tails[name] = self._read(stream)

        t_outer = threading.Thread(target=watch, args=("outer", outer, outer.stderr), daemon=True)
        t_outer.start()
        tails["inner"] = self._read(inner.stdout)
        rc_inner = inner.wait()
        rc_outer = outer.wait()
        t_outer.join(5)
        self._finish("Extraction", rc_outer, tails.get("outer", ""), delete)
        self._finish("Extraction", rc_inner, tails.get("inner", ""), delete)


def delete_volumes(info, log):
    """Remove every piece of the set; returns the bytes given back. Only called after a good extraction."""
    freed = 0
    for path in info.volumes:
        try:
            size = os.path.getsize(path)
            os.remove(path)
            freed += size
            log(f"Deleted {os.path.basename(path)}")
        except FileNotFoundError:
            pass
        except OSError as e:
            log(f"Could not delete {os.path.basename(path)} ({e}).")
    return freed


def space_needed(info, dest):
    """Free bytes needed to extract. Nothing is freed while reading, so --delete changes nothing here."""
    margin = min(ex.SAFETY_MARGIN, 64 * 1024**2 + info.unpacked // 50)
    return info.unpacked + margin

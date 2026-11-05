"""Virtual drive that serves an ISO's files and frees ISO space behind the reader.

Run as its own process (the GUI starts it):
    python vdrive.py --iso FILE --mount X: --mode dry|free [--install-dir DIR] [--buffer-gb 5]

Modes:
  dry   serve files and log every read; nothing is changed.
  free  also release ISO sections setup has finished with (NTFS sparse file).

Status goes to stdout as JSON lines. Send "quit" on stdin to unmount.

Freeing rules (free mode), all must hold for a byte to be freed:
  - only big .bin files are freed
  - at least BUFFER bytes behind the furthest point read in that file
  - never the first HEAD_KEEP or last TAIL_KEEP bytes of a file
  - total freed never exceeds bytes written to the install folder minus a margin,
    so a read-only verify pass frees nothing
  - setup going back by less than half the buffer is fine (that data is still
    there); going back further stops freeing for good
A read that touches freed data fails with an I/O error instead of returning zeros.
"""
import argparse
import errno
import json
import os
import stat
import sys
import threading
import time

from fuse import FUSE, FuseOSError, Operations

import sparse
import udf

GB = 1024**3
MB = 1024**2
HEAD_KEEP = 16 * MB
TAIL_KEEP = 64 * MB
MIN_FREE_FILE = 256 * MB      # files smaller than this are never freed
FREE_STEP = 64 * MB           # free in batches of at least this much
INSTALL_MARGIN = 1 * GB
BACKJUMP = 64 * MB            # reading this far behind the furthest point counts as going back


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def event(msg):
    emit({"type": "event", "msg": msg})


def folder_size(path):
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            # os.stat, not e.stat: the directory listing reports 0 for
                            # files still being written, os.stat gives the live size.
                            total += os.stat(e.path, follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


class FileState:
    def __init__(self, entry):
        self.entry = entry
        self.hwm = 0            # furthest byte read
        self.freed_upto = 0     # bytes [0, freed_upto) of the file are gone
        self.eligible = entry.path.lower().endswith(".bin") and entry.size >= MIN_FREE_FILE
        self.reported = None    # (hwm, freed_upto) last sent in a status message


class IsoFS(Operations):
    def __init__(self, iso, mode, install_dir, lag, log_path, state_path):
        self.mode = mode
        self.install_dir = install_dir
        self.lag = lag
        self.state_path = state_path
        self.lock = threading.Lock()
        img = udf.UDFImage(iso)
        img.close()
        self.f = open(iso, "r+b" if mode == "free" else "rb")
        if mode == "free":
            sparse.make_sparse(self.f)
        self.now = time.time()
        self.files = {}
        self.dirs = {"/": set()}
        for e in img.entries:
            key = e.path.lower()
            parent = os.path.dirname(key) or "/"
            self.dirs.setdefault(parent, set()).add(os.path.basename(e.path))
            if e.is_dir:
                self.dirs.setdefault(key, set())
            else:
                self.files[key] = FileState(e)
        if state_path and os.path.exists(state_path):
            with open(state_path, encoding="utf-8") as sf:
                for p, upto in json.load(sf).get("freed", {}).items():
                    if p.lower() in self.files:
                        self.files[p.lower()].freed_upto = upto
        self.reads = 0
        self.bytes_read = 0
        self.violations = 0
        self.backjumps = 0
        self.max_back = 0
        self.paused = False
        self.installed = 0
        self.log = open(log_path, "w", encoding="utf-8") if log_path else None
        if self.log:
            self.log.write("t,file,offset,size\n")
        self.t0 = time.time()

    # ---------- filesystem ----------
    def getattr(self, path, fh=None):
        key = path.lower()
        base = dict(st_ctime=self.now, st_mtime=self.now, st_atime=self.now)
        if key in self.dirs:
            return dict(base, st_mode=stat.S_IFDIR | 0o555, st_nlink=2)
        fs = self.files.get(key)
        if fs:
            # r-x: without the x bit WinFsp grants no execute right and setup.exe can't start
            return dict(base, st_mode=stat.S_IFREG | 0o555, st_nlink=1, st_size=fs.entry.size)
        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        names = self.dirs.get(path.lower())
        if names is None:
            raise FuseOSError(errno.ENOENT)
        return [".", ".."] + sorted(names)

    def open(self, path, flags):
        if path.lower() not in self.files:
            raise FuseOSError(errno.ENOENT)
        if flags & (os.O_WRONLY | os.O_RDWR):
            raise FuseOSError(errno.EROFS)
        return 0

    def read(self, path, size, offset, fh):
        fs = self.files.get(path.lower())
        if fs is None:
            raise FuseOSError(errno.ENOENT)
        e = fs.entry
        if offset >= e.size:
            return b""
        end = min(offset + size, e.size)
        with self.lock:
            if fs.freed_upto and offset < fs.freed_upto and end > HEAD_KEEP:
                self.violations += 1
                event(f"BLOCKED read of freed data: {e.path} offset {offset:,} (freed up to {fs.freed_upto:,})")
                raise FuseOSError(errno.EIO)
            data = udf.read_file_range(self.f, e, offset, end - offset)
            self.reads += 1
            self.bytes_read += len(data)
            if self.log:
                self.log.write(f"{time.time() - self.t0:.3f},{e.path},{offset},{end - offset}\n")
            # Reads inside the head/tail that are never freed (e.g. an archive's table of
            # contents at the end, read before anything else) don't move the read position.
            if fs.eligible and (offset >= e.size - TAIL_KEEP or end <= HEAD_KEEP):
                return data
            back = fs.hwm - offset
            if fs.hwm - end > BACKJUMP:
                self.backjumps += 1
                if back > self.max_back:
                    self.max_back = back
                    event(f"Setup went back {back / MB:,.0f} MB in {e.path} "
                          f"({'inside' if back <= self.lag // 2 else 'BEYOND half'} the safety buffer)")
                if self.mode == "free" and not self.paused and back > self.lag // 2:
                    self.paused = True
                    event("Freeing STOPPED for safety: setup went back further than half the buffer. "
                          "Setup keeps installing, but nothing more will be freed.")
            fs.hwm = max(fs.hwm, end)
        return data

    def statfs(self, path):
        total = sum(fs.entry.size for fs in self.files.values()) // 2048 + 1
        return dict(f_bsize=2048, f_frsize=2048, f_blocks=total, f_bfree=0, f_bavail=0,
                    f_files=len(self.files), f_ffree=0, f_namemax=255)

    # ---------- freeing ----------
    def tick(self, measure_install):
        if measure_install and self.install_dir:
            self.installed = folder_size(self.install_dir)
        with self.lock:
            if self.log:
                self.log.flush()
            if self.mode != "free" or self.paused or self.violations:
                return
            freed_total = sum(fs.freed_upto for fs in self.files.values())
            budget = self.installed - INSTALL_MARGIN - freed_total
            for fs in self.files.values():
                if not fs.eligible or budget < FREE_STEP:
                    continue
                start = max(fs.freed_upto, HEAD_KEEP)
                target = min(fs.hwm - self.lag, fs.entry.size - TAIL_KEEP, start + budget)
                if target - start < FREE_STEP:
                    continue
                if fs.freed_upto == 0:
                    event(f"Started freeing {fs.entry.path}")
                budget -= target - fs.freed_upto
                # Marked freed before freeing: if freeing fails halfway, reads of the range
                # fail loudly instead of silently returning zeros to setup.
                fs.freed_upto = target
                for a, b in udf.iso_ranges(fs.entry, start, target - start):
                    sparse.free_range(self.f, a, b)
            self.save_state()

    def save_state(self):
        if not self.state_path or not any(fs.freed_upto for fs in self.files.values()):
            return
        data = {"freed": {fs.entry.path: fs.freed_upto for fs in self.files.values() if fs.freed_upto}}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.state_path)

    def status(self):
        """Status message. "files" only holds files that changed since the last one, so an
        ISO with thousands of files doesn't send them all every second."""
        with self.lock:
            changed = {}
            for fs in self.files.values():
                now = (fs.hwm, fs.freed_upto)
                if now != fs.reported:
                    fs.reported = now
                    changed[fs.entry.path] = {"size": fs.entry.size, "hwm": fs.hwm, "freed": fs.freed_upto,
                                              "eligible": fs.eligible}
            return {
                "type": "status",
                "mode": self.mode,
                "reads": self.reads,
                "bytes_read": self.bytes_read,
                "violations": self.violations,
                "backjumps": self.backjumps,
                "max_back": self.max_back,
                "buffer": self.lag,
                "paused": self.paused,
                "installed": self.installed,
                "files": changed,
            }

    def close(self):
        """Flush the read log and save what was freed. Safe to call more than once."""
        with self.lock:
            if self.log:
                self.log.flush()
            if self.mode == "free":
                self.save_state()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--mount", required=True)
    ap.add_argument("--mode", choices=["dry", "free"], default="dry")
    ap.add_argument("--install-dir")
    ap.add_argument("--buffer-gb", type=float, default=5.0)
    ap.add_argument("--log")
    ap.add_argument("--state")
    ap.add_argument("--label", default="ISO")
    args = ap.parse_args()
    if args.mode == "free" and not args.install_dir:
        ap.error("--install-dir is required in free mode")

    try:
        fs = IsoFS(args.iso, args.mode, args.install_dir, int(args.buffer_gb * GB), args.log, args.state)
    except (OSError, udf.UDFError) as e:
        emit({"type": "fatal", "msg": f"Cannot open ISO: {e}"})
        sys.exit(2)

    def ticker():
        n = 0
        while True:
            time.sleep(1)
            n += 1
            try:
                fs.tick(measure_install=(n % 2 == 0))
                emit(fs.status())
            except Exception as e:  # keep serving even if a free step fails
                event(f"Freeing error: {e!r} - freeing paused.")
                fs.paused = True
                fs.close()      # record the range that was being freed

    def stdin_watch():
        for line in sys.stdin:
            if line.strip() == "quit":
                break
        fs.close()
        emit({"type": "exit"})
        os._exit(0)

    threading.Thread(target=ticker, daemon=True).start()
    threading.Thread(target=stdin_watch, daemon=True).start()
    emit({"type": "mounted", "mount": args.mount})
    try:
        FUSE(fs, args.mount, foreground=True, ro=True, volname=args.label)
    finally:
        fs.close()      # unmounted from outside (not via "quit"): keep the log and freeing record


if __name__ == "__main__":
    main()

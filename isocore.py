"""Install-from-ISO logic without any UI: system checks, space maths, the virtual drive
process and judging whether setup finished. Used by the GUI (install_tab.py) and the
terminal version (cli.py)."""
import json
import os
import queue
import shutil
import string
import subprocess
import threading

import paths
import sparse

GB = 1024**3
MB = 1024**2
DEFAULT_BUFFER_GB = 5
MIN_BUFFER_GB = 1
EXTRA_NEEDED_GB = 2   # free space needed on top of the buffer (install margin + freeing step)
BIN_END_SLACK = 128 * MB  # a .bin counts as read to the end if setup got this close
LOG_DIR = os.path.join(paths.DATA_DIR, "logs")
WINFSP_MSI = os.path.join(paths.APP_DIR, "deps", "winfsp-2.1.25156.msi")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Inno Setup exit codes (game repack setups are built with Inno Setup).
SETUP_EXIT_CODES = {
    0: "success",
    1: "setup failed to initialize",
    2: "cancelled before installing started",
    3: "fatal error while preparing to install",
    4: "fatal error during installation",
    5: "cancelled during installation",
    6: "setup was terminated",
    7: "preparing to install failed",
    8: "preparing to install failed, restart needed",
}


def human(n):
    return f"{n / GB:.2f} GB" if n >= 0.1 * GB else f"{n / MB:.0f} MB"


# ---------- the PC ----------
def winfsp_installed():
    """True if the WinFsp driver is installed, looked up the same way fusepy finds it."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WinFsp", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as key:
            folder = winreg.QueryValueEx(key, "InstallDir")[0]
    except OSError:
        return False
    return os.path.isfile(os.path.join(folder, "bin", "winfsp-x64.dll"))


def install_winfsp():
    """Install WinFsp silently from the bundled installer (blocks ~30 s). Returns None on
    success, else a short reason."""
    if not os.path.isfile(WINFSP_MSI):
        return "installer missing from the app"
    try:
        code = subprocess.run(["msiexec", "/i", WINFSP_MSI, "/qn", "/norestart"],
                              creationflags=NO_WINDOW).returncode
    except OSError as e:
        return str(e)
    if winfsp_installed():
        return None
    return f"code {code}" + (" - run as administrator" if code == 1625 else "")


def is_admin():
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def free_drive_letter():
    used = {d[0].upper() for d in os.listdrives()} if hasattr(os, "listdrives") else set()
    for letter in reversed(string.ascii_uppercase[12:]):  # Z..M
        if letter not in used and not os.path.exists(f"{letter}:\\"):
            return f"{letter}:"
    return None


def iso_attached(path):
    """True if Windows itself has this ISO mounted. Asks the virtual disk API (about 1 ms);
    PowerShell (about 1 s) is only the fallback if that API can't answer."""
    try:
        return _attached_virtdisk(path)
    except OSError:
        return _attached_powershell(path)


def _attached_virtdisk(path):
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    class StorageType(ctypes.Structure):
        _fields_ = [("DeviceId", ctypes.c_ulong), ("VendorId", GUID)]

    microsoft = GUID(0xEC984AEC, 0xA0F9, 0x47E9, (ctypes.c_ubyte * 8)(0x90, 0x1F, 0x71, 0x41, 0x5A, 0x66, 0x34, 0x5B))
    iso_type = StorageType(1, microsoft)            # VIRTUAL_STORAGE_TYPE_DEVICE_ISO
    vd = ctypes.WinDLL("virtdisk")
    handle = wintypes.HANDLE()
    rc = vd.OpenVirtualDisk(ctypes.byref(iso_type), ctypes.c_wchar_p(path), 0x000D0000, 0, None,
                            ctypes.byref(handle))   # VIRTUAL_DISK_ACCESS_READ
    if rc:
        raise OSError(rc, "OpenVirtualDisk failed")
    try:
        size = wintypes.ULONG(1024)
        buf = ctypes.create_unicode_buffer(512)
        rc = vd.GetVirtualDiskPhysicalPath(handle, ctypes.byref(size), buf)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    if rc == 0:
        return True                 # it has a physical drive, so it is mounted
    if rc == 55:                    # ERROR_DEV_NOT_EXIST: not attached
        return False
    raise OSError(rc, "GetVirtualDiskPhysicalPath failed")


def _attached_powershell(path):
    cmd = f"(Get-DiskImage -ImagePath '{path.replace(chr(39), chr(39) * 2)}').Attached"
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                             text=True, timeout=20, creationflags=NO_WINDOW).stdout.strip()
        return out.lower() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def drive_free(path):
    d = path
    while d and not os.path.exists(d):
        d = os.path.dirname(d)
    return shutil.disk_usage(d).free if d else 0


# ---------- the ISO ----------
def state_path(iso):
    return iso + ".enhancedextract.json"


def was_freed(iso):
    try:
        with open(state_path(iso), encoding="utf-8") as f:
            return any(json.load(f).get("freed", {}).values())
    except (OSError, ValueError):
        return False


def delete_iso(iso):
    """Delete the ISO and its freeing record. Returns the bytes it took on disk.
    Raises OSError if it can't be deleted."""
    try:
        on_disk = sparse.size_on_disk(iso)
    except OSError:
        on_disk = 0
    os.remove(iso)
    if os.path.exists(state_path(iso)):
        os.remove(state_path(iso))
    return on_disk


def space_needed(buffer_gb, install_size, iso_files):
    """(needed bytes, growth bytes) on the ISO's drive before mounting.

    The installed game can be bigger than the archive it comes from (it gets
    decompressed). That growth can't be covered by freeing the ISO, so it must be free
    up front, on top of the buffer and margin."""
    growth = max(0, install_size - sum(e.size for e in iso_files))
    return int((buffer_gb + EXTRA_NEEDED_GB) * GB) + growth, growth


def setup_result(code, setup_log, files):
    """Judge a finished setup. files: the virtual drive's per-file status.
    Returns (problems, unread): problems mean setup may have failed; unread lists the big
    .bin files setup never read to the end (normal for skipped optional parts)."""
    try:
        with open(setup_log, encoding="utf-8", errors="ignore") as f:
            log_ok = "Installation process succeeded" in f.read()
    except OSError:
        log_ok = False
    problems = []
    if code != 0:
        problems.append(f"setup exit code {code}: {SETUP_EXIT_CODES.get(code, 'unknown')}")
    if not log_ok:
        problems.append("setup's log has no 'Installation process succeeded' line")
    unread = [p for p, f in files.items() if f["eligible"] and f["hwm"] < f["size"] - BIN_END_SLACK]
    return problems, unread


# ---------- the virtual drive process ----------
class VDrive:
    """Runs vdrive.py as its own process and collects what it reports.

    poll() returns the messages that arrived (dicts with a "type"); the last one is
    {"type": "ended", "code": n} once the process is gone. Status messages only carry
    the files that changed; poll() merges them so status["files"] is always complete."""

    def __init__(self, iso, letter, mode, buffer_gb, install_dir=None, log=None, label=None):
        args = paths.vdrive_command() + ["--iso", iso, "--mount", letter, "--mode", mode,
                                         "--buffer-gb", f"{buffer_gb:g}", "--state", state_path(iso),
                                         "--label", label or os.path.splitext(os.path.basename(iso))[0][:30]]
        if install_dir:
            args += ["--install-dir", install_dir]
        if log:
            args += ["--log", log]
        self.letter = letter
        self.files = {}
        self.status = None
        self._queue = queue.Queue()
        self.proc = subprocess.Popen(args, cwd=paths.APP_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", creationflags=NO_WINDOW)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                # WinFsp's own "The service <exe name> has been started/stopped." lines
                if not line.strip() or (line.startswith("The service ") and " has been " in line):
                    continue
                msg = {"type": "event", "msg": line.strip()}
            self._queue.put(msg)
        self._queue.put({"type": "ended", "code": self.proc.wait()})

    def poll(self, timeout=0):
        """Messages received so far; waits up to `timeout` seconds for the first one."""
        out = []
        try:
            out.append(self._queue.get(timeout=timeout) if timeout else self._queue.get_nowait())
            while True:
                out.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        for msg in out:
            if msg.get("type") == "status":
                self.files.update(msg.get("files", {}))
                msg["files"] = self.files
                self.status = msg
        return out

    def running(self):
        return self.proc.poll() is None

    def quit(self):
        """Ask the drive to unmount (saves its state first). Returns at once."""
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def kill(self):
        if self.running():
            self.proc.kill()

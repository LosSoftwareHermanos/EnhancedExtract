"""NTFS sparse-file helpers: mark a file sparse and release byte ranges back to the drive."""
import ctypes
import msvcrt
from ctypes import wintypes

FSCTL_SET_SPARSE = 0x000900C4
FSCTL_SET_ZERO_DATA = 0x000980C8

# Freed ranges are aligned inward to this so whole clusters are released.
ALIGN = 64 * 1024

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                 wintypes.LPVOID]
_k32.DeviceIoControl.restype = wintypes.BOOL
_k32.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
_k32.GetCompressedFileSizeW.restype = wintypes.DWORD


class _ZeroData(ctypes.Structure):
    _fields_ = [("FileOffset", ctypes.c_longlong), ("BeyondFinalZero", ctypes.c_longlong)]


def _ioctl(f, code, inbuf=None, insize=0):
    handle = msvcrt.get_osfhandle(f.fileno())
    returned = wintypes.DWORD()
    ok = _k32.DeviceIoControl(handle, code, inbuf, insize, None, 0, ctypes.byref(returned), None)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def make_sparse(f):
    """f: file object opened 'r+b'."""
    _ioctl(f, FSCTL_SET_SPARSE)


def free_range(f, start, end):
    """Release [start, end) of a sparse file. Returns the aligned range actually freed (or None)."""
    a = (start + ALIGN - 1) // ALIGN * ALIGN
    b = end // ALIGN * ALIGN
    if b <= a:
        return None
    z = _ZeroData(a, b)
    _ioctl(f, FSCTL_SET_ZERO_DATA, ctypes.byref(z), ctypes.sizeof(z))
    return a, b


def size_on_disk(path):
    high = wintypes.DWORD()
    low = _k32.GetCompressedFileSizeW(path, ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return (high.value << 32) | low

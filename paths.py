"""Where the app's files are, run from source or as the single EnhancedExtract.exe.

From source everything sits next to the .py files. In the exe, the bundled files (fonts,
sounds, pictures, UnRAR, the WinFsp installer) unpack to a temp folder that is gone
after the app closes, so what the app writes (logs, settings) goes to
%LOCALAPPDATA%\\EnhancedExtract instead."""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
APP_DIR = sys._MEIPASS if FROZEN else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = (os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "EnhancedExtract")
            if FROZEN else APP_DIR)


def vdrive_command():
    """Command that starts the virtual drive process. The exe runs it as itself with
    --vdrive, since there is no separate Python to run vdrive.py with."""
    if FROZEN:
        return [sys.executable, "--vdrive"]
    return [sys.executable, os.path.join(APP_DIR, "vdrive.py")]

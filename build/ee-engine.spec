# PyInstaller recipe for ee-engine, the engine the Tauri UI runs (engine.py: the JSON CLI and the
# virtual drive process, no Tk app). Build with build-engine.bat; the Tauri bundle ships the folder.
#
# A folder build, not one file: the UI runs the engine about once a second, and a one-file exe
# unpacks itself to a temp folder on every start. A console exe, so stdout works; the UI and the
# engine's own child processes start it with CREATE_NO_WINDOW, so no window shows. No uac_admin:
# Windows refuses to start an elevated-manifest exe from a normal process.
import os

SRC = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(SRC, "deps", "winfsp-2.1.25156.msi"), "deps"),   # `system install-winfsp`
]
binaries = [
    (r"C:\Program Files\WinRAR\UnRAR.exe", "."),    # freeware, may be shared on its own (WinRAR license 2a)
]
excludes = ["tkinter", "_tkinter", "pygame", "PIL", "numpy", "scipy", "pandas", "matplotlib",
            "setuptools", "pkg_resources", "unittest", "pydoc", "doctest", "lib2to3", "sqlite3", "xmlrpc"]

a = Analysis([os.path.join(SRC, "engine.py")], pathex=[SRC], binaries=binaries, datas=datas,
             hiddenimports=["cli", "vdrive", "fuse"], excludes=excludes)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="ee-engine",
          icon=os.path.join(SRC, "icon.ico"),
          console=True,
          upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ee-engine", upx=False)

# PyInstaller recipe for the single-file EnhancedExtract.exe. Build with build.bat.
import os

SRC = os.path.abspath(os.path.join(SPECPATH, ".."))

# Only what the app reads at runtime. Left out on purpose: EE (design sources, the
# title art's copy is taken from it below), dev, logo, logs, deps\wheels, settings.json.
datas = [
    (os.path.join(SRC, "fonts"), "fonts"),
    (os.path.join(SRC, "sounds"), "sounds"),
    (os.path.join(SRC, "EE", "title", "title2.png"), "title"),
    (os.path.join(SRC, "icon.ico"), "."),
    (os.path.join(SRC, "deps", "winfsp-2.1.25156.msi"), "deps"),   # driver for tab 2, installed on demand
]
binaries = [
    (r"C:\Program Files\WinRAR\UnRAR.exe", "."),    # freeware, may be shared on its own (WinRAR license 2a)
]

# Installed on this PC but never used by the app; keep PyInstaller from following them in.
excludes = ["numpy", "scipy", "pandas", "matplotlib", "setuptools", "pkg_resources",
            "unittest", "pydoc", "doctest", "lib2to3", "sqlite3", "xmlrpc",
            "pygame.examples", "pygame.tests", "pygame.docs", "pygame.sndarray", "pygame.surfarray",
            # Pillow only opens one PNG; no AVIF/WebP/colour profiles/font drawing
            "PIL._avif", "PIL.AvifImagePlugin", "PIL._webp", "PIL.WebPImagePlugin",
            "PIL._imagingcms", "PIL.ImageCms", "PIL._imagingft", "PIL.ImageFont",
            # no network or encryption (hashlib falls back to Python's built-in hashes)
            "ssl", "_ssl", "_hashlib"]

# pygame is only used for its mixer. Its font, MIDI and image-format libraries are
# optional to pygame (it imports without them), so they stay out.
PYGAME_UNUSED = {"sdl2_ttf.dll", "freetype.dll", "libtiff-5.dll", "libwebp-7.dll", "libjpeg-9.dll",
                 "portmidi.dll", "libmodplug-1.dll", "libopus-0.dll", "libopusfile-0.dll"}

a = Analysis([os.path.join(SRC, "app.py")], pathex=[SRC], binaries=binaries, datas=datas,
             hiddenimports=["vdrive", "cli"], excludes=excludes)
def from_pygame(src):
    return os.sep + "pygame" + os.sep in os.path.normcase(src)

a.binaries = [(dest, src, kind) for dest, src, kind in a.binaries
              if os.path.basename(dest).lower() not in PYGAME_UNUSED
              # PyInstaller also copies pygame's DLLs to the top level; pygame loads its own.
              # Tk needs zlib1.dll at the top level, so that one stays even if taken from pygame.
              and not (os.path.dirname(dest) == "" and from_pygame(src) and dest.lower() != "zlib1.dll")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas,
          name="EnhancedExtract",
          icon=os.path.join(SRC, "icon.ico"),
          console=False,
          uac_admin=True,       # Windows asks for admin on start, showing this icon
          upx=False)            # UPX-packed exes often get flagged by antivirus

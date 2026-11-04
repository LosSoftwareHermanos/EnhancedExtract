"""UI sounds. Which sound goes with which action comes from EE\\audio\\fit.txt; the files
live in the sounds folder next to this file.

Sounds are an extra: if pygame is missing or there is no audio device, every call here
quietly does nothing and the app works as before."""
import os
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import paths
import settings

SOUND_DIR = os.path.join(paths.APP_DIR, "sounds")
FILES = {
    "button": "glass_001.ogg",
    "minimize": "toggle_001.ogg",
    "exit": "back_001.ogg",
    "key": "click_003.ogg",
    "check_on": "select_007.ogg",
    "check_off": "select_008.ogg",
    "progress": "kuzu420-sci-fi-radar-beeping-571479.mp3",
    "buffer_up": "select_007.ogg",
    "buffer_down": "select_008.ogg",
    "tab_iso": "forceField_000.ogg",
    "tab_rar": "forceField_001.ogg",
    "popup": "soundshelfstudio-cyber-ui-click-527091.mp3",
    "sound_on": "glass_005.ogg",
    "sound_off": "glass_006.ogg",
}
VOLUME = 0.6
PROGRESS_VOLUME = 0.3   # it loops for the whole job, so it sits under the other sounds

_sounds = None          # name -> pygame Sound, filled on first use; {} if sound is unavailable
_progress_channel = None
_progress_wanted = False    # a job is running, so the loop should play whenever not muted
_load_lock = threading.Lock()


_muted = bool(settings.get("muted", False))     # the mute button, remembered between runs


def is_muted():
    return _muted


def set_muted(muted):
    """Turn every sound off or back on, and remember it for the next run."""
    global _muted
    _muted = bool(muted)
    if _muted:
        _stop_loop()
    elif _progress_wanted:
        _start_loop()
    settings.put("muted", _muted)


def preload():
    """Load the sounds in the background now. Loading takes most of a second, and doing it
    on the first click made that click (and its tab switch) lag."""
    threading.Thread(target=_load, daemon=True).start()


def _load():
    global _sounds
    with _load_lock:
        if _sounds is not None:
            return _sounds
        loaded = {}
        try:
            import pygame
            pygame.mixer.pre_init(44100, -16, 2, 256)   # small buffer: clicks follow the key press closely
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)           # fast typing over the progress loop still overlaps
            cache = {}
            for name, file in FILES.items():
                if file not in cache:
                    cache[file] = pygame.mixer.Sound(os.path.join(SOUND_DIR, file))
                loaded[name] = cache[file]
            for s in cache.values():
                s.set_volume(VOLUME)
        except Exception:   # no pygame, no audio device, missing file: run silent
            loaded = {}
        _sounds = loaded
        return _sounds


def _ready():
    """The sounds, without waiting: while the background load is still going, a click
    stays silent instead of freezing the app until it finishes."""
    if _sounds is None and _load_lock.locked():
        return {}
    return _load()


def play(name):
    if _muted:
        return
    s = _ready().get(name)
    if s:
        try:
            s.play()
        except Exception:
            pass


def length_ms(name):
    s = _load().get(name)
    return int(s.get_length() * 1000) if s else 0


def start_progress():
    """Loop the progress sound until stop_progress()."""
    global _progress_wanted
    _progress_wanted = True
    if not _muted:
        _start_loop()


def stop_progress():
    global _progress_wanted
    _progress_wanted = False
    _stop_loop()


def _start_loop():
    global _progress_channel
    s = _ready().get("progress")
    if not s or (_progress_channel and _progress_channel.get_busy()):
        return
    try:
        _progress_channel = s.play(loops=-1)
        if _progress_channel:
            _progress_channel.set_volume(PROGRESS_VOLUME / VOLUME)
    except Exception:
        _progress_channel = None


def _stop_loop():
    global _progress_channel
    if _progress_channel:
        try:
            _progress_channel.fadeout(300)
        except Exception:
            pass
        _progress_channel = None


def install_typing_sound(root):
    """Click on every key that types into a text box (not on Tab, arrows, Ctrl, ...)."""
    def on_key(event):
        w = event.widget
        try:
            if w.winfo_class() not in ("TEntry", "TSpinbox", "Entry"):
                return
            if str(w.cget("state")) in ("readonly", "disabled"):
                return
        except Exception:
            return
        if event.char and event.char.isprintable() or event.keysym in ("BackSpace", "Delete"):
            play("key")
    root.bind_all("<KeyPress>", on_key, add="+")
